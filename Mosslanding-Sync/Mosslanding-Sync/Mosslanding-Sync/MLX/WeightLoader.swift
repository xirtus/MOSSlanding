import Foundation
import MLX
import MLXNN

// MARK: - Safetensors Weight Loader

nonisolated enum WeightLoader {

    private static let shardFiles = [
        "model-00001-of-00002.safetensors",
        "model-00002-of-00002.safetensors",
    ]

    /// Load all weight arrays from safetensors shards in a snapshot directory.
    nonisolated static func loadWeightArrays(from snapshotDir: URL) throws -> [String: MLXArray] {
        var allWeights: [String: MLXArray] = [:]

        for shard in shardFiles {
            let url = snapshotDir.appendingPathComponent(shard)
            guard FileManager.default.fileExists(atPath: url.path) else {
                print("[WeightLoader] Warning: shard not found: \(shard)")
                continue
            }
            let arrays = try MLX.loadArrays(url: url)
            for (key, value) in arrays {
                allWeights[key] = value
            }
        }

        guard !allWeights.isEmpty else {
            throw InferenceError.ioFailure("No weights loaded from \(snapshotDir.path)")
        }

        return allWeights
    }

    /// Update model parameters from a flat weight dictionary.
    nonisolated static func updateModel(_ model: MLXNN.Module, with weights: [String: MLXArray]) throws {
        var params = ModuleParameters()
        for (key, array) in weights {
            params[key] = .value(array)
        }
        try model.update(parameters: params, verify: .all)
    }
}
