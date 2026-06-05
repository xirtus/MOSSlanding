import Foundation
import Hub
import Tokenizers

/// One line from the Python subprocess's stdout. Decoded loosely because each
/// line may be either a status update, a synthesis result, or a synthesis
/// error — distinguished by which fields are present.
private nonisolated struct InferenceLine: Decodable {
    let status: String?
    let progress: Int?
    let message: String?
    let modelId: String?
    let device: String?
    let modelsDir: String?
    let error: String?
    let pcmPath: String?
    let sampleRate: Int?
    let samples: Int?
    let duration: Double?

    enum CodingKeys: String, CodingKey {
        case status, progress, message, device, error, samples, duration
        case modelId    = "model_id"
        case modelsDir  = "models_dir"
        case pcmPath    = "pcm_path"
        case sampleRate = "sample_rate"
    }
}

/// Owns the Python inference subprocess and serializes requests through a
/// newline-delimited JSON protocol. All mutable state is actor-isolated;
/// arbitrary-queue `FileHandle` callbacks bridge back in via `Task { await ... }`.
actor InferenceManager {
    static let shared = InferenceManager()

    private var process: Process?
    private var stdin: FileHandle?
    private var readBuffer = ""
    private var pending: [CheckedContinuation<SynthResult, Error>] = []
    private(set) var status: InferenceStatus = .initial

    private var tokenizer: (any Tokenizer)?
    private var mossConfig: MossModelConfig?
    private var tokenizerLoadTask: Task<Void, Never>?

    private init() {}

    func currentStatus() -> InferenceStatus { status }

    func start() {
        guard process == nil else { return }
        guard let (python, script) = findPythonAndScript() else {
            logger.error("Cannot find python or inference.py")
            status.status = "error"
            status.error = "Python or inference.py not found"
            return
        }

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: python)
        proc.arguments = [script]
        var env = ProcessInfo.processInfo.environment
        env["MOSS_TTS_MODEL_ID"] = "OpenMOSS-Team/MOSS-TTS-Local-Transformer"
        env["PYTORCH_MPS_HIGH_WATERMARK_RATIO"] = "0.0"
        env["OMP_NUM_THREADS"] = "4"
        proc.environment = env

        let stdinPipe = Pipe()
        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        proc.standardInput = stdinPipe
        proc.standardOutput = stdoutPipe
        proc.standardError = stderrPipe

        stderrPipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            guard !data.isEmpty, let s = String(data: data, encoding: .utf8) else { return }
            let trimmed = s.trimmingCharacters(in: .whitespacesAndNewlines)
            logger.debug("inference: \(trimmed, privacy: .public)")
        }
        stdoutPipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            guard !data.isEmpty else { return }
            Task { await InferenceManager.shared.ingest(data) }
        }

        do {
            try proc.run()
            process = proc
            stdin = stdinPipe.fileHandleForWriting
            status.status = "starting"
            status.progress = 0
            status.message = "Starting Python..."
            status.error = ""
            logger.info("Inference started (pid \(proc.processIdentifier, privacy: .public))")
        } catch {
            logger.error("Inference start failed: \(error.localizedDescription, privacy: .public)")
            status.status = "error"
            status.error = error.localizedDescription
        }

        if tokenizerLoadTask == nil {
            tokenizerLoadTask = Task { [weak self] in
                do {
                    try await self?.loadTokenizer()
                } catch {
                    logger.warning("Eager tokenizer load failed: \(error.localizedDescription, privacy: .public)")
                }
            }
        }
    }

    private func loadTokenizer() async throws {
        if tokenizer != nil, mossConfig != nil { return }
        let snapshot = try mossSnapshotDirectory()
        let cfg = try MossModelConfig(snapshotDir: snapshot)
        let tok = try await AutoTokenizer.from(modelFolder: snapshot)
        self.tokenizer = tok
        self.mossConfig = cfg
        logger.info("MOSS tokenizer loaded (n_vq=\(cfg.nVQ, privacy: .public))")
    }

    func terminate() {
        let outstanding = pending
        pending.removeAll()
        for cont in outstanding {
            cont.resume(throwing: InferenceError.notRunning)
        }
        if let stdin {
            try? sendCommand(["op": "shutdown"], using: stdin)
        }
        process?.terminate()
        process = nil
        stdin = nil
        readBuffer = ""
        status = .initial
        tokenizerLoadTask?.cancel()
        tokenizerLoadTask = nil
    }

    /// Restarts the subprocess if it died (e.g. broken stdin pipe after wake).
    func restartIfNeeded() {
        if let process, process.isRunning { return }
        terminate()
        start()
    }

    func triggerLoad() {
        guard let stdin else { return }
        try? sendCommand(["op": "load"], using: stdin)
    }

    func triggerUnload() {
        guard let stdin else { return }
        try? sendCommand(["op": "unload"], using: stdin)
    }

    func synthesize(_ params: [String: any Sendable]) async throws -> SynthResult {
        guard let stdin, process?.isRunning == true else {
            throw InferenceError.notRunning
        }
        var payload = params
        payload["op"] = "synthesize"

        if shouldTokenizeInSwift(payload: payload),
           let text = payload["text"] as? String, !text.isEmpty {
            do {
                let language = payload["language"] as? String
                let durationTokens = payload["duration_tokens"] as? Int
                let (flatIds, mask) = try await tokenizeDirect(
                    text: text,
                    language: language,
                    tokens: durationTokens
                )
                payload["input_ids"] = flatIds
                payload["attention_mask"] = mask
                payload.removeValue(forKey: "text")
            } catch {
                logger.warning("Swift tokenization failed, falling back to Python: \(error.localizedDescription, privacy: .public)")
            }
        }

        return try await withCheckedThrowingContinuation { (cont: CheckedContinuation<SynthResult, Error>) in
            pending.append(cont)
            do {
                try sendCommand(payload, using: stdin)
            } catch {
                _ = pending.popLast()
                cont.resume(throwing: error)
            }
        }
    }

    /// Direct mode is explicit `mode == "direct"`, or no voice reference at
    /// all. Anything that supplies a non-empty `voice` is clone mode and
    /// stays on the Python tokenizer path this sweep.
    private func shouldTokenizeInSwift(payload: [String: any Sendable]) -> Bool {
        if let mode = payload["mode"] as? String, mode == "direct" { return true }
        let voice = (payload["voice"] as? String) ?? ""
        return voice.isEmpty
    }

    private func tokenizeDirect(
        text: String,
        language: String?,
        tokens: Int?
    ) async throws -> (flatIds: [Int], mask: [Int]) {
        try await loadTokenizer()
        guard let tok = tokenizer, let cfg = mossConfig else {
            throw InferenceError.ioFailure("tokenizer not loaded")
        }
        let content = buildUserInstContent(text: text, language: language, tokens: tokens)
        let messages: [[String: any Sendable]] = [["role": "user", "content": content]]
        let textTokens = try tok.applyChatTemplate(messages: messages)
        let flat = buildMossInputIds(textTokens: textTokens, config: cfg)
        let mask = [Int](repeating: 1, count: textTokens.count + 1)
        return (flat, mask)
    }

    private func sendCommand(_ payload: [String: any Sendable], using handle: FileHandle) throws {
        var data = try JSONSerialization.data(withJSONObject: payload, options: [])
        data.append(0x0A)
        try handle.write(contentsOf: data)
    }

    fileprivate func ingest(_ data: Data) {
        guard let chunk = String(data: data, encoding: .utf8) else { return }
        readBuffer.append(chunk)
        while let newline = readBuffer.firstIndex(of: "\n") {
            let line = String(readBuffer[..<newline])
            readBuffer.removeSubrange(...newline)
            guard let lineData = line.data(using: .utf8), !lineData.isEmpty else { continue }
            handleLine(lineData)
        }
    }

    private func handleLine(_ data: Data) {
        let line: InferenceLine
        do {
            line = try JSONDecoder().decode(InferenceLine.self, from: data)
        } catch {
            logger.warning("Bad inference line: \(error.localizedDescription, privacy: .public)")
            return
        }

        if let s = line.status {
            status.status = s
            if let p = line.progress { status.progress = p }
            if let m = line.message  { status.message = m }
            if let id = line.modelId { status.modelId = id }
            if let dev = line.device { status.device = dev }
            if let md = line.modelsDir { status.modelsDir = md }
            status.error = line.error ?? ""
            return
        }

        if let path = line.pcmPath, let sr = line.sampleRate {
            guard !pending.isEmpty else { return }
            let cont = pending.removeFirst()
            do {
                let pcm = try Data(contentsOf: URL(fileURLWithPath: path))
                try? FileManager.default.removeItem(atPath: path)
                let wav = pcmFloat32ToWAV(pcm: pcm, sampleRate: sr)

                let outDir = AppPaths.outputDirectory
                try? FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)
                let filename = "mosslanding_\(UUID().uuidString.prefix(8).lowercased()).wav"
                let savedURL = outDir.appendingPathComponent(filename)
                try? wav.write(to: savedURL)

                let result = SynthResult(
                    wavData: wav,
                    filename: filename,
                    savedPath: savedURL.path,
                    sampleRate: sr,
                    duration: line.duration
                        ?? (line.samples.map { Double($0) / Double(sr) } ?? 0)
                )
                cont.resume(returning: result)
            } catch {
                cont.resume(throwing: InferenceError.ioFailure("read pcm: \(error.localizedDescription)"))
            }
            return
        }

        if let message = line.error {
            guard !pending.isEmpty else { return }
            let cont = pending.removeFirst()
            cont.resume(throwing: InferenceError.backendError(message))
        }
    }

    /// Prefers the venv python created by `setup.sh`. Falls back to the system
    /// Homebrew python (which usually won't have torch/transformers installed —
    /// keep it only as a last-resort diagnostic path).
    nonisolated private func findPythonAndScript() -> (String, String)? {
        let candidates = [
            AppPaths.supportDirectory.appendingPathComponent("venv/bin/python3").path,
            "/opt/homebrew/bin/python3",
        ]
        let python = candidates.first { FileManager.default.fileExists(atPath: $0) }
        guard let python else { return nil }

        let script = Bundle.main.url(forResource: "inference", withExtension: "py", subdirectory: "backend")
            ?? Bundle.main.url(forResource: "inference", withExtension: "py")
        guard let script else { return nil }
        return (python, script.path)
    }
}
