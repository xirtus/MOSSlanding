import Foundation
import MLX
import MLXNN

/// Qwen3 transformer backbone stripped of embedding and RoPE.
class Qwen3Backbone: MLXNN.Module {

    let config: Qwen3BackboneConfig
    let layers: [Qwen3DecoderLayer]
    let finalNorm: MossTTSRMSNorm

    override nonisolated init() {
        fatalError("Use init(config:)")
    }

    init(config: Qwen3BackboneConfig) {
        self.config = config
        self.layers = (0..<config.numHiddenLayers).map { _ in
            Qwen3DecoderLayer(config: config)
        }
        self.finalNorm = MossTTSRMSNorm(dimensions: config.hiddenSize, eps: config.rmsNormEps)
        super.init()
    }

    func callAsFunction(inputsEmbeds: MLXArray, attentionMask: MLXArray? = nil) -> MLXArray {
        var h = inputsEmbeds
        for layer in layers {
            h = layer(h, mask: attentionMask)
        }
        return finalNorm(h)
    }
}
