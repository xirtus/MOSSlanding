import Foundation
import MLX
import MLXFast
import MLXNN

// MARK: - RMS Normalization

class MossTTSRMSNorm: MLXNN.Module {
    let weight: MLXArray
    let eps: Float

    override nonisolated init() {
        fatalError("Use init(dimensions:eps:)")
    }

    init(dimensions: Int, eps: Float = 1e-6) {
        self.weight = MLXArray.ones([dimensions])
        self.eps = eps
        super.init()
    }

    func callAsFunction(_ x: MLXArray) -> MLXArray {
        let norm = MLX.rsqrt(x.square().mean(axis: -1, keepDims: true) + eps)
        return (x * norm) * weight
    }
}

// MARK: - SwiGLU MLP

class MossTTSSwiGLUMLP: MLXNN.Module {
    let norm: MossTTSRMSNorm?
    let gateProj: MLXNN.Linear
    let upProj: MLXNN.Linear
    let downProj: MLXNN.Linear

    override nonisolated init() {
        fatalError("Use designated init")
    }

    init(inputSize: Int, ffnHiddenSize: Int, outputSize: Int,
         bias: Bool = false, prenorm: Bool = false, normEps: Float = 1e-6) {
        if prenorm {
            self.norm = MossTTSRMSNorm(dimensions: inputSize, eps: normEps)
        } else {
            self.norm = nil
        }
        self.gateProj = MLXNN.Linear(inputSize, ffnHiddenSize, bias: bias)
        self.upProj   = MLXNN.Linear(inputSize, ffnHiddenSize, bias: bias)
        self.downProj = MLXNN.Linear(ffnHiddenSize, outputSize, bias: bias)
        super.init()
    }

    func callAsFunction(_ x: MLXArray) -> MLXArray {
        let h = norm?(x) ?? x
        let gate = gateProj(h)
        let up = upProj(h)
        return downProj(silu(gate) * up)
    }
}

// MARK: - Causal Mask Helper

private func causalMask(length T: Int) -> MLXArray {
    let i = MLXArray(Int32(0)..<Int32(T)).reshaped([T, 1])
    let j = MLXArray(Int32(0)..<Int32(T)).reshaped([1, T])
    let cmp = MLX.greaterEqual(i, j)
    let mask = MLX.where(cmp, MLXArray(0.0), MLXArray(Float(-1e9)))
    return mask.reshaped([1, 1, T, T])
}

// MARK: - Qwen3 Attention (no RoPE)

class NoRoPEAttention: MLXNN.Module {

    let numHeads: Int
    let numKVHeads: Int
    let headDim: Int
    let scale: Float

    let qProj: MLXNN.Linear
    let kProj: MLXNN.Linear
    let vProj: MLXNN.Linear
    let oProj: MLXNN.Linear

    let qNorm: MossTTSRMSNorm
    let kNorm: MossTTSRMSNorm

    override nonisolated init() {
        fatalError("Use init(config:)")
    }

    init(config: Qwen3BackboneConfig) {
        self.numHeads = config.numAttentionHeads
        self.numKVHeads = config.numKeyValueHeads
        self.headDim = config.headDim
        self.scale = 1.0 / sqrt(Float(config.headDim))

        let hidden = config.hiddenSize
        let kvHidden = config.headDim * config.numKeyValueHeads

        self.qProj = MLXNN.Linear(hidden, config.numAttentionHeads * config.headDim, bias: true)
        self.kProj = MLXNN.Linear(hidden, kvHidden, bias: true)
        self.vProj = MLXNN.Linear(hidden, kvHidden, bias: true)
        self.oProj = MLXNN.Linear(config.numAttentionHeads * config.headDim, hidden, bias: false)

        self.qNorm = MossTTSRMSNorm(dimensions: config.headDim, eps: config.rmsNormEps)
        self.kNorm = MossTTSRMSNorm(dimensions: config.headDim, eps: config.rmsNormEps)
        super.init()
    }

    func callAsFunction(_ x: MLXArray, mask: MLXArray? = nil) -> MLXArray {
        let B = x.dim(0)
        let T = x.dim(1)

        let q = qProj(x).reshaped(B, T, numHeads, headDim).transposed(0, 2, 1, 3)
        let k = kProj(x).reshaped(B, T, numKVHeads, headDim).transposed(0, 2, 1, 3)
        let v = vProj(x).reshaped(B, T, numKVHeads, headDim).transposed(0, 2, 1, 3)

        let qn = qNorm(q)
        let kn = kNorm(k)

        let nRep = numHeads / numKVHeads
        let kExp = nRep > 1
            ? MLX.repeated(k, count: nRep, axis: 1)
            : k
        let vExp = nRep > 1
            ? MLX.repeated(v, count: nRep, axis: 1)
            : v

        var scores = MLX.matmul(qn, kn.transposed(0, 1, 3, 2)) * scale

        let attnMask = mask ?? causalMask(length: T)
        scores = scores + attnMask

        let attn = MLX.softmax(scores, axis: -1)
        let out = MLX.matmul(attn, vExp)
            .transposed(0, 2, 1, 3)
            .reshaped(B, T, numHeads * headDim)

        return oProj(out)
    }
}

// MARK: - Bidirectional Attention (local transformer)

class BidirectionalAttention: MLXNN.Module {

    let numHeads: Int
    let numKVHeads: Int
    let headDim: Int
    let scale: Float

    let qProj: MLXNN.Linear
    let kProj: MLXNN.Linear
    let vProj: MLXNN.Linear
    let oProj: MLXNN.Linear

    let qNorm: MossTTSRMSNorm
    let kNorm: MossTTSRMSNorm

    override nonisolated init() {
        fatalError("Use designated init")
    }

    init(hiddenSize: Int, numHeads: Int, numKVHeads: Int, headDim: Int, rmsNormEps: Float) {
        self.numHeads = numHeads
        self.numKVHeads = numKVHeads
        self.headDim = headDim
        self.scale = 1.0 / sqrt(Float(headDim))

        let kvHidden = headDim * numKVHeads

        self.qProj = MLXNN.Linear(hiddenSize, numHeads * headDim, bias: true)
        self.kProj = MLXNN.Linear(hiddenSize, kvHidden, bias: true)
        self.vProj = MLXNN.Linear(hiddenSize, kvHidden, bias: true)
        self.oProj = MLXNN.Linear(numHeads * headDim, hiddenSize, bias: false)

        self.qNorm = MossTTSRMSNorm(dimensions: headDim, eps: rmsNormEps)
        self.kNorm = MossTTSRMSNorm(dimensions: headDim, eps: rmsNormEps)
        super.init()
    }

    func callAsFunction(_ x: MLXArray) -> MLXArray {
        let B = x.dim(0)
        let T = x.dim(1)

        let q = qProj(x).reshaped(B, T, numHeads, headDim).transposed(0, 2, 1, 3)
        let k = kProj(x).reshaped(B, T, numKVHeads, headDim).transposed(0, 2, 1, 3)
        let v = vProj(x).reshaped(B, T, numKVHeads, headDim).transposed(0, 2, 1, 3)

        let qn = qNorm(q)
        let kn = kNorm(k)

        let nRep = numHeads / numKVHeads
        let kExp = nRep > 1
            ? MLX.repeated(k, count: nRep, axis: 1)
            : k
        let vExp = nRep > 1
            ? MLX.repeated(v, count: nRep, axis: 1)
            : v

        var scores = MLX.matmul(qn, kn.transposed(0, 1, 3, 2)) * scale
        // No mask — fully bidirectional
        let attn = MLX.softmax(scores, axis: -1)
        let out = MLX.matmul(attn, vExp)
            .transposed(0, 2, 1, 3)
            .reshaped(B, T, numHeads * headDim)

        return oProj(out)
    }
}

// MARK: - Qwen3 Decoder Layer

class Qwen3DecoderLayer: MLXNN.Module {
    let inputNorm: MossTTSRMSNorm
    let postAttnNorm: MossTTSRMSNorm
    let attention: NoRoPEAttention
    let mlp: MossTTSSwiGLUMLP

    override nonisolated init() {
        fatalError("Use init(config:)")
    }

    init(config: Qwen3BackboneConfig) {
        let hidden = config.hiddenSize
        self.inputNorm = MossTTSRMSNorm(dimensions: hidden, eps: config.rmsNormEps)
        self.postAttnNorm = MossTTSRMSNorm(dimensions: hidden, eps: config.rmsNormEps)
        self.attention = NoRoPEAttention(config: config)
        self.mlp = MossTTSSwiGLUMLP(
            inputSize: hidden,
            ffnHiddenSize: config.intermediateSize,
            outputSize: hidden,
            prenorm: false
        )
        super.init()
    }

    func callAsFunction(_ x: MLXArray, mask: MLXArray? = nil) -> MLXArray {
        var h = x + attention(inputNorm(x), mask: mask)
        h = h + mlp(postAttnNorm(h))
        return h
    }
}

// MARK: - Local Decoder Layer

class LocalDecoderLayer: MLXNN.Module {
    let inputNorm: MossTTSRMSNorm
    let postAttnNorm: MossTTSRMSNorm
    let attention: BidirectionalAttention
    let mlp: MossTTSSwiGLUMLP

    override nonisolated init() {
        fatalError("Use designated init")
    }

    init(hiddenSize: Int, ffnHiddenSize: Int, numHeads: Int, numKVHeads: Int,
         headDim: Int, rmsNormEps: Float) {
        self.inputNorm = MossTTSRMSNorm(dimensions: hiddenSize, eps: rmsNormEps)
        self.postAttnNorm = MossTTSRMSNorm(dimensions: hiddenSize, eps: rmsNormEps)
        self.attention = BidirectionalAttention(
            hiddenSize: hiddenSize,
            numHeads: numHeads,
            numKVHeads: numKVHeads,
            headDim: headDim,
            rmsNormEps: rmsNormEps
        )
        self.mlp = MossTTSSwiGLUMLP(
            inputSize: hiddenSize,
            ffnHiddenSize: ffnHiddenSize,
            outputSize: hiddenSize,
            prenorm: false
        )
        super.init()
    }

    func callAsFunction(_ x: MLXArray) -> MLXArray {
        var h = x + attention(inputNorm(x))
        h = h + mlp(postAttnNorm(h))
        return h
    }
}
