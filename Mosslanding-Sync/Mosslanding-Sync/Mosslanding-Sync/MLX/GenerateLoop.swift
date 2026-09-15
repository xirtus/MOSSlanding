import Foundation
import MLX
import MLXNN
import MLXRandom

// MARK: - MOSS-TTS Generation Loop

/// Run the full autoregressive generation loop:
///   while !done and steps < maxNewTokens:
///     1. Run Qwen3 backbone on accumulated inputIDs → (B, T, hidden)
///     2. Extract last-step hidden → project to local dim
///     3. Run local transformer autoregressively over 1+nVQ channels:
///        for ch in 0..nChannels:
///          a. Local transformer → last position output
///          b. Project → norm → LM head → logits
///          c. Process logits (temp, top-k, top-p, penalty)
///          d. Sample token
///          e. Embed token → project → append to local inputs
///     4. Pad remaining channels, append to sequences
///     5. Check EOS on text channel
///
/// - Parameters:
///   - model: Loaded MOSS-TTS model.
///   - inputIDs: (1, promptLen, totalChannels) pre-tokenized prompt.
///   - attentionMask: Optional (1, seqLen) bool mask for the backbone
///     forward. Pass nil to use causal masking (NoRoPEAttention default).
///   - genConfig: Generation parameters.
/// - Returns: (1, promptLen + genLen, totalChannels) full token sequence.
func generate(
    model: MossTTSModel,
    inputIDs: MLXArray,
    attentionMask: MLXArray? = nil,
    genConfig: MossGenerationConfig
) -> MLXArray {
    let totalChannels = model.totalChannels
    let nChannels = 1 + genConfig.nVQForInference
    let eosTokenId = genConfig.eosTokenId
    let audioPadCode = model.config.audioPadCode
    let localDim = model.config.localHiddenSize

    var sequences = inputIDs
    var done = false
    var stepCount = 0

    // Per-channel logit processors
    let processors: [ChannelLogitProcessor] = (0..<nChannels).map { i in
        let padId = (i == 0) ? -1 : audioPadCode
        return ChannelLogitProcessor(config: genConfig.layerConfigs[i], padTokenId: padId)
    }

    // Build causal mask for attention (full sequence length grows each step)
    // Rebuilt each iteration since T changes. Nil = NoRoPEAttention builds its own.

    while !done && stepCount < genConfig.maxNewTokens {
        // Step 1: Run backbone on full sequence
        let backboneOut = model.forwardBackbone(
            inputIDs: sequences,
            attentionMask: attentionMask,
            nVQForInference: genConfig.nVQForInference
        )  // (1, curLen, hiddenSize)

        let lastHidden = backboneOut[0..., -1, 0...]  // (1, hiddenSize)

        // Step 2: Project backbone hidden to local transformer dim
        let globalLocal = model.speechEmbeddingToLocalMLP(lastHidden)  // (1, localDim)

        // Step 3: Autoregressive local transformer loop over channels
        var localInputs = globalLocal.reshaped([1, 1, localDim])  // (1, 1, localDim)
        var currentEmbed = globalLocal                              // (1, localDim)
        var nextTokens: [MLXArray] = []                             // nChannels × (1,)

        for ch in 0..<nChannels {
            // Run local transformer on accumulated inputs
            let localOut = model.localTransformer(inputsEmbeds: localInputs)  // (1, ch+1, localDim)
            let lastLocal = localOut[0..., -1, 0...]                          // (1, localDim)

            // Project back to backbone dim → norm → LM head
            let proj = model.localToSpeechEmbeddingMLPs[ch](lastLocal)        // (1, hiddenSize)
            let normed = model.layerNormBeforeLMHeads[ch](proj)               // (1, hiddenSize)
            var logits = model.lmHeads[ch](normed)                            // (1, vocabSize)

            // Process logits
            logits = processors[ch].process(logits)

            // Sample
            let probs = MLX.softmax(logits, axis: -1)
            let token: MLXArray
            if genConfig.layerConfigs[ch].temperature > 0 {
                token = MLXRandom.categorical(probs, axis: -1)
                    .reshaped([1])  // (1,)
            } else {
                token = MLX.argMax(probs, axis: -1, keepDims: false)
            }

            nextTokens.append(token)

            // Embed sampled token for the next channel's local transformer input
            if ch + 1 < nChannels {
                let emb = model.embeddingList[ch](token).reshaped([1, model.config.hiddenSize])
                let localEmb = model.speechEmbeddingToLocalMLP(emb).reshaped([1, 1, localDim])
                localInputs = MLX.concatenated([localInputs, localEmb], axis: 1)
            }
        }

        // Step 4: Pad remaining channels (nChannels .. totalChannels-1) with pad code
        var allTokens: [MLXArray] = []
        for token in nextTokens {
            allTokens.append(token)
        }
        for _ in nChannels..<totalChannels {
            allTokens.append(MLXArray(Int32(audioPadCode)).reshaped([1]))
        }

        // Stack into (1, 1, totalChannels) and append
        let newRow = MLX.stacked(allTokens, axis: -1).reshaped([1, 1, totalChannels])
        sequences = MLX.concatenated([sequences, newRow], axis: 1)

        // Step 5: Check EOS on text channel (channel 0)
        let textToken = nextTokens[0]  // (1,)
        let isEos = (textToken .== Int32(eosTokenId))
        let eosCount = MLX.sum(isEos).item(Int.self)
        if eosCount > 0 {
            done = true
        }

        stepCount += 1
    }

    return sequences
}

// MARK: - Logit Processor

nonisolated struct ChannelLogitProcessor {
    let config: GenerationLayerConfig
    let padTokenId: Int

    func process(_ logits: MLXArray) -> MLXArray {
        var l = logits

        // Temperature
        if config.temperature > 0 && config.temperature != 1.0 {
            l = l / config.temperature
        }

        // Block pad token on audio channels
        if padTokenId >= 0 {
            l = MLX.where(
                MLXArray(Int32(0)..<Int32(l.dim(-1))).reshaped([1, l.dim(-1)]) .== Int32(padTokenId),
                MLXArray(Float(-1e9)),
                l
            )
        }

        // Top-k filtering
        if config.topK > 0 && config.topK < l.dim(-1) {
            let topValues = MLX.top(l, k: config.topK, axis: -1)
            let threshold = topValues[0..., -1, 0...]  // k-th largest value
            l = MLX.where(l .< threshold, MLXArray(Float(-1e9)), l)
        }

        return l
    }
}

// MARK: - Input Builder

/// Build initial input_ids from tokenized text + audio_start marker.
/// Shape: (1, textLen + 1, totalChannels)
///   - Channel 0: [text_token_0, ..., text_token_N, audio_start_token_id]
///   - Channels 1..N: [audio_pad_code, ..., audio_pad_code]
nonisolated func buildInputIDs(textTokens: [Int], config: MossTTSConfig) -> MLXArray {
    let totalChannels = config.totalChannels
    let seqLen = textTokens.count + 1
    let audioPad = config.audioPadCode

    var flat: [Int32] = []
    for t in textTokens {
        flat.append(Int32(t))
        for _ in 1..<totalChannels {
            flat.append(Int32(audioPad))
        }
    }
    // Audio start token
    flat.append(Int32(config.audioStartTokenId))
    for _ in 1..<totalChannels {
        flat.append(Int32(audioPad))
    }

    return MLXArray(flat, [1, seqLen, totalChannels])
}

/// Extract audio codes from generated sequences.
/// Returns (genLen, nVQ) where genLen excludes the prompt prefix.
nonisolated func extractAudioCodes(sequences: MLXArray, promptLen: Int, nVQ: Int) -> MLXArray {
    let genLen = sequences.dim(1) - promptLen
    // Slice: batch=0, time=promptLen..., channels=1...1+nVQ
    return sequences[0..., promptLen..., 1...(1+nVQ)]
        .reshaped([genLen, nVQ])
}
