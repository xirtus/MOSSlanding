import Foundation
import MLX
import MLXNN

class MossTTSModel: MLXNN.Module {

    let config: MossTTSConfig
    let totalChannels: Int

    let embeddingList: [MLXNN.Embedding]
    let backbone: Qwen3Backbone
    let speechEmbeddingToLocalMLP: MossTTSSwiGLUMLP
    let localTransformer: LocalTransformer
    let localToSpeechEmbeddingMLPs: [MossTTSSwiGLUMLP]
    let layerNormBeforeLMHeads: [MossTTSRMSNorm]
    let lmHeads: [MLXNN.Linear]

    override nonisolated init() {
        fatalError("Use init(config:)")
    }

    init(config: MossTTSConfig) {
        self.config = config
        self.totalChannels = config.totalChannels

        var embeddings: [MLXNN.Embedding] = [
            MLXNN.Embedding(embeddingCount: config.vocabSize, dimensions: config.hiddenSize)
        ]
        let audioCount = config.audioVocabSize + 1
        for _ in 1..<totalChannels {
            embeddings.append(
                MLXNN.Embedding(embeddingCount: audioCount, dimensions: config.hiddenSize)
            )
        }
        self.embeddingList = embeddings

        self.backbone = Qwen3Backbone(config: config.languageConfig)

        self.speechEmbeddingToLocalMLP = MossTTSSwiGLUMLP(
            inputSize: config.hiddenSize,
            ffnHiddenSize: config.additionalMlpFfnHiddenSize,
            outputSize: config.localHiddenSize,
            prenorm: false
        )

        self.localTransformer = LocalTransformer(
            localHiddenSize: config.localHiddenSize,
            localFfnHiddenSize: config.localFfnHiddenSize,
            localNumLayers: config.localNumLayers,
            rmsNormEps: config.languageConfig.rmsNormEps
        )

        var localMLPs: [MossTTSSwiGLUMLP] = []
        for _ in 0..<totalChannels {
            localMLPs.append(MossTTSSwiGLUMLP(
                inputSize: config.localHiddenSize,
                ffnHiddenSize: config.additionalMlpFfnHiddenSize,
                outputSize: config.hiddenSize,
                prenorm: false
            ))
        }
        self.localToSpeechEmbeddingMLPs = localMLPs

        var norms: [MossTTSRMSNorm] = []
        for _ in 0..<totalChannels {
            norms.append(MossTTSRMSNorm(
                dimensions: config.hiddenSize,
                eps: config.languageConfig.rmsNormEps
            ))
        }
        self.layerNormBeforeLMHeads = norms

        var heads: [MLXNN.Linear] = [
            MLXNN.Linear(config.hiddenSize, config.vocabSize, bias: false)
        ]
        for _ in 1..<totalChannels {
            heads.append(
                MLXNN.Linear(config.hiddenSize, config.audioVocabSize + 1, bias: false)
            )
        }
        self.lmHeads = heads

        super.init()
    }

    func embedInputIDs(_ inputIDs: MLXArray, nVQForInference: Int) -> MLXArray {
        let nChannels = min(totalChannels, 1 + nVQForInference)
        let B = inputIDs.dim(0)
        let T = inputIDs.dim(1)
        let H = config.hiddenSize

        var result = MLXArray.zeros([B, T, H])

        for i in 0..<nChannels {
            let channelInput = inputIDs[0..., 0..., i]
            let emb = embeddingList[i](channelInput)
            result = result + emb
        }

        return result
    }

    func forwardBackbone(inputIDs: MLXArray,
                         attentionMask: MLXArray? = nil,
                         nVQForInference: Int) -> MLXArray {
        let embeds = embedInputIDs(inputIDs, nVQForInference: nVQForInference)
        return backbone(inputsEmbeds: embeds, attentionMask: attentionMask)
    }
}
