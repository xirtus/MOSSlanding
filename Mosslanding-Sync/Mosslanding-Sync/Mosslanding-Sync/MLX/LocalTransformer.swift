import Foundation
import MLX
import MLXNN

class LocalTransformer: MLXNN.Module {

    let layers: [LocalDecoderLayer]
    let finalNorm: MossTTSRMSNorm

    override nonisolated init() {
        fatalError("Use designated init")
    }

    init(localHiddenSize: Int,
         localFfnHiddenSize: Int,
         localNumLayers: Int,
         numHeads: Int = 16,
         numKVHeads: Int = 8,
         rmsNormEps: Float = 1e-6) {
        self.layers = (0..<localNumLayers).map { _ in
            LocalDecoderLayer(
                hiddenSize: localHiddenSize,
                ffnHiddenSize: localFfnHiddenSize,
                numHeads: numHeads,
                numKVHeads: numKVHeads,
                headDim: localHiddenSize / numHeads,
                rmsNormEps: rmsNormEps
            )
        }
        self.finalNorm = MossTTSRMSNorm(dimensions: localHiddenSize, eps: rmsNormEps)
        super.init()
    }

    func callAsFunction(inputsEmbeds: MLXArray) -> MLXArray {
        var h = inputsEmbeds
        for layer in layers {
            h = layer(h)
        }
        return finalNorm(h)
    }
}
