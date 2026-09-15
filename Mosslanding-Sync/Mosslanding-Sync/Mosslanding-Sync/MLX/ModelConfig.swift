import Foundation

// MARK: - MOSS-TTS Model Configuration

/// Configuration for the Qwen3 language backbone.
nonisolated struct Qwen3BackboneConfig: Codable, Sendable {
    let hiddenSize: Int
    let numHiddenLayers: Int
    let numAttentionHeads: Int
    let numKeyValueHeads: Int
    let headDim: Int
    let intermediateSize: Int
    let vocabSize: Int
    let rmsNormEps: Float
    let ropeTheta: Float
    let maxPositionEmbeddings: Int
    let padTokenId: Int

    enum CodingKeys: String, CodingKey {
        case hiddenSize = "hidden_size"
        case numHiddenLayers = "num_hidden_layers"
        case numAttentionHeads = "num_attention_heads"
        case numKeyValueHeads = "num_key_value_heads"
        case headDim = "head_dim"
        case intermediateSize = "intermediate_size"
        case vocabSize = "vocab_size"
        case rmsNormEps = "rms_norm_eps"
        case ropeTheta = "rope_theta"
        case maxPositionEmbeddings = "max_position_embeddings"
        case padTokenId = "pad_token_id"
    }
}

/// Top-level MOSS-TTS Delay model configuration.
nonisolated struct MossTTSConfig: Codable, Sendable {
    let modelType: String
    let dtype: String
    let nVQ: Int
    let audioVocabSize: Int
    let audioPadCode: Int
    let audioStartTokenId: Int
    let audioEndTokenId: Int
    let audioUserSlotTokenId: Int
    let audioAssistantGenSlotTokenId: Int
    let audioAssistantDelaySlotTokenId: Int
    let samplingRate: Int
    let additionalMlpFfnHiddenSize: Int
    let localFfnHiddenSize: Int
    let localHiddenSize: Int
    let localNumLayers: Int
    let padTokenId: Int
    let languageConfig: Qwen3BackboneConfig

    enum CodingKeys: String, CodingKey {
        case modelType = "model_type"
        case dtype
        case nVQ = "n_vq"
        case audioVocabSize = "audio_vocab_size"
        case audioPadCode = "audio_pad_code"
        case audioStartTokenId = "audio_start_token_id"
        case audioEndTokenId = "audio_end_token_id"
        case audioUserSlotTokenId = "audio_user_slot_token_id"
        case audioAssistantGenSlotTokenId = "audio_assistant_gen_slot_token_id"
        case audioAssistantDelaySlotTokenId = "audio_assistant_delay_slot_token_id"
        case samplingRate = "sampling_rate"
        case additionalMlpFfnHiddenSize = "additional_mlp_ffn_hidden_size"
        case localFfnHiddenSize = "local_ffn_hidden_size"
        case localHiddenSize = "local_hidden_size"
        case localNumLayers = "local_num_layers"
        case padTokenId = "pad_token_id"
        case languageConfig = "language_config"
    }

    var totalChannels: Int { 1 + nVQ }
    var hiddenSize: Int { languageConfig.hiddenSize }
    var vocabSize: Int { languageConfig.vocabSize }

    nonisolated static func load(from snapshotDir: URL) throws -> MossTTSConfig {
        let configURL = snapshotDir.appendingPathComponent("config.json")
        let data = try Data(contentsOf: configURL)
        return try JSONDecoder().decode(MossTTSConfig.self, from: data)
    }
}

// MARK: - Generation Parameters

nonisolated struct GenerationLayerConfig: Sendable {
    let temperature: Float
    let topP: Float
    let topK: Int
    let repetitionPenalty: Float
}

nonisolated struct MossGenerationConfig: Sendable {
    let maxNewTokens: Int
    let eosTokenId: Int
    let nVQForInference: Int
    let layerConfigs: [GenerationLayerConfig]

    nonisolated static func `default`(config: MossTTSConfig,
                          maxNewTokens: Int = 4096,
                          quality: Int = 32) -> MossGenerationConfig {
        let nVQ = max(1, min(config.nVQ, quality))
        let textCfg = GenerationLayerConfig(
            temperature: 1.5, topP: 1.0, topK: 50, repetitionPenalty: 1.0
        )
        let audioCfg = GenerationLayerConfig(
            temperature: 1.0, topP: 0.95, topK: 50, repetitionPenalty: 1.1
        )
        var layers = [textCfg]
        for _ in 1..<(1 + nVQ) { layers.append(audioCfg) }
        return MossGenerationConfig(
            maxNewTokens: maxNewTokens,
            eosTokenId: config.audioEndTokenId,
            nVQForInference: nVQ,
            layerConfigs: layers
        )
    }
}
