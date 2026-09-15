import Foundation
import MLX
import MLXNN
import OSLog

// MARK: - Codec bridge response

nonisolated private struct CodecResponse: Decodable {
    let pcmPath: String?
    let sampleRate: Int?
    let samples: Int?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case pcmPath = "pcm_path"
        case sampleRate = "sample_rate"
        case samples, error
    }
}

// MARK: - MLX Inference Engine

/// High-level inference engine that replaces the Python inference subprocess.
/// Runs the MOSS-TTS language model natively on MLX, then bridges audio codec
/// decoding through a lightweight Python subprocess.
///
/// Future: port the MOSS-Audio-Tokenizer codec to MLX to eliminate Python entirely.
actor MLXInferenceEngine {

    static let shared = MLXInferenceEngine()

    private let engineLogger = Logger(
        subsystem: "com.mosslanding.app",
        category: "mlx-engine"
    )

    // MARK: State

    enum State: Sendable {
        case unloaded
        case loading(progress: Int, message: String)
        case ready
        case generating
        case error(String)

        var status: String {
            switch self {
            case .unloaded:    return "idle"
            case .loading:     return "loading"
            case .ready:       return "ready"
            case .generating:  return "generating"
            case .error:       return "error"
            }
        }
    }

    private(set) var state = State.unloaded
    private var model: MossTTSModel?
    private var config: MossTTSConfig?
    private var codecProcess: Process?
    private var codecStdin: FileHandle?
    private var codecStdout: FileHandle?
    private var codecReadBuffer = ""
    private var codecPending: [CheckedContinuation<Data, Error>] = []

    // Track progress as (0-100) for UI
    private(set) var loadingProgress: Int = 0
    private(set) var loadingMessage: String = ""

    // MARK: Accessors (for sibling actors)
    func getConfig() -> MossTTSConfig? { config }
    func getState() -> State { state }

    // MARK: - Model Loading

    /// Load the model from a local snapshot directory.
    func loadModel(snapshotDir: URL) async throws {
        state = .loading(progress: 0, message: "Loading model...")

        let snapshot = snapshotDir
        guard FileManager.default.fileExists(atPath: snapshot.path) else {
            state = .error("Snapshot not found: \(snapshot.path)")
            throw InferenceError.backendError("Snapshot not found: \(snapshot.path)")
        }

        // Parse config
        updateProgress(5, "Loading configuration...")
        let cfg = try await MainActor.run { try MossTTSConfig.load(from: snapshot) }
        self.config = cfg

        // Create model
        updateProgress(10, "Building model graph...")
        let mdl = await MainActor.run { MossTTSModel(config: cfg) }

        // Load weights
        updateProgress(15, "Loading safetensors weights...")
        let weights = try WeightLoader.loadWeightArrays(from: snapshot)
        updateProgress(50, "Mapping \(weights.count) parameter tensors...")

        // Map weights to model parameters
        try WeightLoader.updateModel(mdl, with: weights)
        updateProgress(90, "Model ready on Apple Silicon GPU")

        self.model = mdl
        self.state = .ready
        engineLogger.info("MLX model loaded from: \(snapshot.path, privacy: .public)")

        // Start codec subprocess
        startCodecSubprocess()
    }

    /// Unload the model to free memory.
    func unloadModel() {
        stopCodecSubprocess()
        model = nil
        config = nil
        state = .unloaded
        loadingProgress = 0
        loadingMessage = ""

        // Force GC
        MLX.Memory.clearCache()
        engineLogger.info("MLX model unloaded")
    }

    // MARK: - Synthesis

    /// Synthesize audio from pre-tokenized input_ids.
    func synthesize(inputIDs: MLXArray,
                    attentionMask: MLXArray?,
                    generationConfig: MossGenerationConfig) async throws -> AudioResult {
        guard let model, state.isReady else {
            throw InferenceError.notRunning
        }

        state = .generating
        defer { state = .ready }

        // Run generation
        engineLogger.info("Starting generation: max_tokens=\(generationConfig.maxNewTokens)")

        let sequences = await MainActor.run {
            generate(
                model: model,
                inputIDs: inputIDs,
                attentionMask: attentionMask,
                genConfig: generationConfig
            )
        }

        // Extract audio codes from sequences
        // sequences shape: (1, totalSeqLen, totalChannels)
        // Strip text prefix, extract audio codes on channels 1..nVQForInference
        let promptLen = inputIDs.dim(1)
        let genLen = sequences.dim(1) - promptLen

        // audioCodes shape: (genLen, nVQForInference)
        let nVQ = generationConfig.nVQForInference
        let audioCodesSlice = sequences[0..., promptLen..., 1...(1+nVQ)]
        // audioCodes is (1, genLen, nVQ) — squeeze batch dim
        let audioCodes = audioCodesSlice.reshaped([genLen, nVQ])
        // Transpose to (nVQ, genLen) for codec decode
        let codesTransposed = audioCodes.transposed(0, 1)

        // Decode audio codes to PCM via codec subprocess
        let pcmData = try await decodeAudioCodes(codes: codesTransposed, nVQ: nVQ)

        return AudioResult(
            pcmData: pcmData,
            sampleRate: model.config.samplingRate,
            sampleCount: pcmData.count / MemoryLayout<Float>.size,
            duration: Double(pcmData.count / MemoryLayout<Float>.size) / Double(model.config.samplingRate)
        )
    }

    // MARK: - Codec Subprocess (temporary Python bridge)

    private func startCodecSubprocess() {
        guard config != nil else { return }

        let pythonPath = findPython()
        guard let python = pythonPath else {
            engineLogger.warning("No Python found for codec bridge; audio decode unavailable")
            return
        }

        // Prefer the bundled script; fall back to inline template (dev builds).
        let bridgeURL: URL
        if let bundled = Bundle.main.url(forResource: "codec_bridge", withExtension: "py") {
            bridgeURL = bundled
        } else if let legacy = Bundle.main.url(forResource: "codec_bridge", withExtension: "py", subdirectory: "backend") {
            bridgeURL = legacy
        } else {
            // Inline fallback — write a temp script (same as bundled version).
            let codecScript = """
import sys, json, os, uuid
from pathlib import Path
import numpy as np
import torch

_MODEL_ID = "OpenMOSS-Team/MOSS-TTS-Local-Transformer"
os.environ.setdefault("HF_HOME", str(Path.home() / "Library/Application Support/MOSSlanding/models"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")

_processor = None
def _get_processor():
    global _processor
    if _processor is None:
        from transformers import AutoProcessor
        _processor = AutoProcessor.from_pretrained(_MODEL_ID, trust_remote_code=True)
    return _processor

def decode(codes_tensor, n_vq):
    processor = _get_processor()
    codes = torch.from_numpy(np.array(codes_tensor)).long()
    wav_list = processor.decode_audio_codes([codes.transpose(0, 1)])
    wav = wav_list[0].numpy().astype(np.float32)
    pcm_path = Path.home() / "Library/Application Support/MOSSlanding/pcm-tmp" / f"mlx_{uuid.uuid4().hex[:8]}.f32"
    pcm_path.parent.mkdir(parents=True, exist_ok=True)
    wav.tofile(str(pcm_path))
    return {"pcm_path": str(pcm_path), "sample_rate": 24000, "samples": int(wav.size)}

for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try:
        req = json.loads(line)
        if req.get("op") == "shutdown": break
        if req.get("op") == "decode":
            result = decode(req["codes"], req.get("n_vq", 32))
            print(json.dumps(result), flush=True)
        else:
            print(json.dumps({"error": f"unknown op: {req.get('op')}"}), flush=True)
    except Exception as e:
        print(json.dumps({"error": str(e)}), flush=True)
"""
            let tmp = FileManager.default.temporaryDirectory
                .appendingPathComponent("moss_codec_bridge_\(UUID().uuidString.prefix(8)).py")
            try? codecScript.write(to: tmp, atomically: true, encoding: .utf8)
            bridgeURL = tmp
        }

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: python)
        proc.arguments = [bridgeURL.path]

        let stdinPipe = Pipe()
        let stdoutPipe = Pipe()
        proc.standardInput = stdinPipe
        proc.standardOutput = stdoutPipe
        proc.standardError = FileHandle.nullDevice

        stdoutPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty else { return }
            Task { await self?.ingestCodecResponse(data) }
        }

        do {
            try proc.run()
            codecProcess = proc
            codecStdin = stdinPipe.fileHandleForWriting
            codecStdout = stdoutPipe.fileHandleForReading
            engineLogger.info("Codec bridge started (pid \(proc.processIdentifier))")
        } catch {
            engineLogger.error("Codec bridge failed: \(error.localizedDescription)")
        }
    }

    private func stopCodecSubprocess() {
        let outstanding = codecPending
        codecPending.removeAll()
        for cont in outstanding {
            cont.resume(throwing: InferenceError.notRunning)
        }
        if codecStdin != nil {
            try? sendCodecCommand(["op": "shutdown"])
        }
        codecProcess?.terminate()
        codecProcess = nil
        codecStdin = nil
        codecStdout = nil
        codecReadBuffer = ""
    }

    /// Decode audio codes using the Python codec bridge.
    private func decodeAudioCodes(codes: MLXArray, nVQ: Int) async throws -> Data {
        guard codecStdin != nil, codecProcess?.isRunning == true else {
            throw InferenceError.backendError("Codec bridge not running")
        }

        // Convert MLXArray to nested [[Int]] for JSON
        let codesArray = codes.asArray(Int32.self)
        let nVQActual = codes.dim(0)
        let genLen = codes.dim(1)
        var codesList: [[Int]] = []
        for q in 0..<nVQActual {
            var row: [Int] = []
            for t in 0..<genLen {
                row.append(Int(codesArray[q * genLen + t]))
            }
            codesList.append(row)
        }

        let payload: [String: any Sendable] = [
            "op": "decode",
            "codes": codesList,
            "n_vq": nVQ
        ]

        return try await withCheckedThrowingContinuation { cont in
            codecPending.append(cont)
            do {
                try sendCodecCommand(payload)
            } catch {
                _ = codecPending.popLast()
                cont.resume(throwing: error)
            }
        }
    }

    private func sendCodecCommand(_ payload: [String: any Sendable]) throws {
        guard let stdin = codecStdin else {
            throw InferenceError.notRunning
        }
        var data = try JSONSerialization.data(withJSONObject: payload, options: [])
        data.append(0x0A)
        try stdin.write(contentsOf: data)
    }

    private func ingestCodecResponse(_ data: Data) {
        guard let chunk = String(data: data, encoding: .utf8) else { return }
        codecReadBuffer.append(chunk)
        while let newline = codecReadBuffer.firstIndex(of: "\n") {
            let line = String(codecReadBuffer[..<newline])
            codecReadBuffer.removeSubrange(...newline)
            guard let lineData = line.data(using: .utf8), !lineData.isEmpty else { continue }

            let response: CodecResponse
            do {
                response = try JSONDecoder().decode(CodecResponse.self, from: lineData)
            } catch {
                engineLogger.warning("Bad codec response line: \(error.localizedDescription, privacy: .public)")
                continue
            }

            if let err = response.error {
                if !codecPending.isEmpty {
                    let cont = codecPending.removeFirst()
                    cont.resume(throwing: InferenceError.backendError(err))
                }
                continue
            }

            if let path = response.pcmPath {
                guard !codecPending.isEmpty else { continue }
                let cont = codecPending.removeFirst()
                do {
                    let pcm = try Data(contentsOf: URL(fileURLWithPath: path))
                    try? FileManager.default.removeItem(atPath: path)
                    cont.resume(returning: pcm)
                } catch {
                    cont.resume(throwing: InferenceError.ioFailure("read codec pcm: \(error.localizedDescription)"))
                }
            }
        }
    }

    // MARK: - Helpers

    private func updateProgress(_ progress: Int, _ message: String) {
        loadingProgress = progress
        loadingMessage = message
        state = .loading(progress: progress, message: message)
    }

    private func findPython() -> String? {
        let candidates = [
            AppPaths.supportDirectory.appendingPathComponent("venv/bin/python3").path,
            "/opt/homebrew/bin/python3",
            "/usr/local/bin/python3",
        ]
        return candidates.first { FileManager.default.fileExists(atPath: $0) }
    }
}

// MARK: - Audio result

struct AudioResult: Sendable {
    let pcmData: Data
    let sampleRate: Int
    let sampleCount: Int
    let duration: Double
}

// MARK: - State helpers

nonisolated extension MLXInferenceEngine.State {
    var isReady: Bool {
        if case .ready = self { return true }
        return false
    }
}
