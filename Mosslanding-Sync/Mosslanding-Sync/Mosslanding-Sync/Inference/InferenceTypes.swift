import Foundation
import OSLog

nonisolated let logger = Logger(subsystem: "com.mosslanding.app", category: "main")

nonisolated enum InferenceError: Error, Sendable {
    case notRunning
    case scriptNotFound
    case backendError(String)
    case ioFailure(String)
}

nonisolated struct InferenceStatus: Sendable, Equatable {
    var status: String
    var progress: Int
    var message: String
    var modelId: String
    var device: String
    var modelsDir: String
    var error: String

    static let initial = InferenceStatus(
        status: "starting",
        progress: 0,
        message: "",
        modelId: "moss-local-1.7b",
        device: "unknown",
        modelsDir: "",
        error: ""
    )

    var isBusy: Bool { status == "starting" || status == "loading" }
    var isReady: Bool { status == "ready" }
    var hasError: Bool { status == "error" || !error.isEmpty }
}

nonisolated struct SynthResult: Sendable, Identifiable, Hashable {
    let id: UUID
    let wavData: Data
    let filename: String
    let savedPath: String
    let sampleRate: Int
    let duration: Double
    let createdAt: Date

    init(
        id: UUID = UUID(),
        wavData: Data,
        filename: String,
        savedPath: String,
        sampleRate: Int,
        duration: Double,
        createdAt: Date = Date()
    ) {
        self.id = id
        self.wavData = wavData
        self.filename = filename
        self.savedPath = savedPath
        self.sampleRate = sampleRate
        self.duration = duration
        self.createdAt = createdAt
    }
}

nonisolated struct VoiceInfo: Sendable, Identifiable, Hashable {
    var id: String { filename }
    let name: String
    let filename: String
    let size: Int
}

nonisolated struct ModelInfo: Sendable, Identifiable, Hashable {
    var id: String { key }
    let key: String
    let modelId: String
    let description: String
    let sizeGb: Double
    let recommended: Bool
    let downloaded: Bool
    let active: Bool
}

/// Mirrors the previous `SynthRequest`; this is the param bundle the view-model
/// hands to `InferenceManager.synthesize`.
nonisolated struct SynthRequest: Sendable {
    var text: String
    var language: String?
    var voice: String?
    var mode: String?
    var maxNewTokens: Int?
    var durationTokens: Int?
    var quality: Int?
    var temperature: Double?
    var topP: Double?
    var topK: Int?
    var repetitionPenalty: Double?
    var doSample: Bool?

    func toPayload() -> [String: any Sendable] {
        var out: [String: any Sendable] = ["text": text]
        if let language          { out["language"] = language }
        if let voice             { out["voice"] = voice }
        if let mode              { out["mode"] = mode }
        if let maxNewTokens      { out["max_new_tokens"] = maxNewTokens }
        if let durationTokens    { out["duration_tokens"] = durationTokens }
        if let quality           { out["quality"] = quality }
        if let temperature       { out["temperature"] = temperature }
        if let topP              { out["top_p"] = topP }
        if let topK              { out["top_k"] = topK }
        if let repetitionPenalty { out["repetition_penalty"] = repetitionPenalty }
        if let doSample          { out["do_sample"] = doSample }
        return out
    }
}

// MARK: - Model catalogue

nonisolated enum ModelCatalogue {
    struct Entry: Sendable {
        let key: String
        let id: String
        let description: String
        let sizeGb: Double
        let recommended: Bool
    }

    static let entries: [Entry] = [
        Entry(
            key: "moss-local-1.7b",
            id: "OpenMOSS-Team/MOSS-TTS-Local-Transformer",
            description: "MOSS TTS Local Transformer 1.7B — fast, M-series optimised",
            sizeGb: 3.5,
            recommended: true
        ),
        Entry(
            key: "moss-v1.5-8b",
            id: "OpenMOSS-Team/MOSS-TTS-v1.5",
            description: "MOSS TTS v1.5 8B — highest quality, needs 16 GB+ RAM",
            sizeGb: 16.0,
            recommended: false
        ),
    ]

    static let activeModelId = "OpenMOSS-Team/MOSS-TTS-Local-Transformer"

    static func snapshot() -> [ModelInfo] {
        let hubDir = AppPaths.modelsHubDirectory
        return entries.map { entry in
            let slug = "models--" + entry.id.replacingOccurrences(of: "/", with: "--")
            let downloaded = FileManager.default.fileExists(
                atPath: hubDir.appendingPathComponent(slug).path
            )
            return ModelInfo(
                key: entry.key,
                modelId: entry.id,
                description: entry.description,
                sizeGb: entry.sizeGb,
                recommended: entry.recommended,
                downloaded: downloaded,
                active: entry.id == activeModelId
            )
        }
    }
}
