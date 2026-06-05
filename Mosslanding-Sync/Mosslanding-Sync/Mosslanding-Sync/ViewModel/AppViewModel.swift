import AVFoundation
import AppKit
import Foundation
import Observation

/// Single source of UI state. Wraps `InferenceManager.shared` and bridges
/// async actor calls back onto the main actor for SwiftUI binding.
@MainActor
@Observable
final class AppViewModel {
    // MARK: Form state

    var promptText: String = "Hello from MOSSlanding."
    var language: String = "auto"
    var selectedVoiceFilename: String? = nil   // nil = direct mode

    var quality: Int = 16
    var temperature: Double = 0.7
    var topP: Double = 0.9
    var topK: Int = 20
    var durationTokens: Int = 0      // 0 = leave to model
    var maxNewTokens: Int = 1500
    var repetitionPenalty: Double = 1.1
    var doSample: Bool = true

    // MARK: Inference state

    var status: InferenceStatus = .initial
    var voices: [VoiceInfo] = []
    var models: [ModelInfo] = ModelCatalogue.snapshot()
    var recentResults: [SynthResult] = []

    var isSynthesizing: Bool = false
    var lastError: String? = nil
    var nowPlayingId: SynthResult.ID? = nil

    // MARK: Lifecycle

    private var statusPollTask: Task<Void, Never>?
    private var player: AVAudioPlayer?

    /// Called once from the app's launch path.
    func bootstrap() {
        AppPaths.ensureAll()
        reloadVoices()
        Task { @MainActor in
            await InferenceManager.shared.start()
            status = await InferenceManager.shared.currentStatus()
            startStatusPolling()
        }
    }

    func shutdown() async {
        statusPollTask?.cancel()
        statusPollTask = nil
        await InferenceManager.shared.terminate()
    }

    // MARK: Model control

    func loadModel() {
        Task { @MainActor in
            await InferenceManager.shared.triggerLoad()
            startStatusPolling()
        }
    }

    func unloadModel() {
        Task { @MainActor in
            await InferenceManager.shared.triggerUnload()
            startStatusPolling()
        }
    }

    func restartBackend() {
        Task { @MainActor in
            await InferenceManager.shared.terminate()
            await InferenceManager.shared.start()
            startStatusPolling()
        }
    }

    // MARK: Status polling

    private func startStatusPolling() {
        statusPollTask?.cancel()
        statusPollTask = Task { @MainActor [weak self] in
            while let self, !Task.isCancelled {
                let s = await InferenceManager.shared.currentStatus()
                self.status = s
                if s.isReady || s.hasError { break }
                try? await Task.sleep(for: .milliseconds(500))
            }
        }
    }

    // MARK: Synthesis

    func synthesize() async {
        guard !isSynthesizing else { return }
        guard !promptText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            lastError = "Prompt is empty."
            return
        }
        isSynthesizing = true
        lastError = nil
        defer { isSynthesizing = false }

        let req = SynthRequest(
            text: promptText,
            language: language.isEmpty ? nil : language,
            voice: selectedVoiceFilename,
            mode: selectedVoiceFilename == nil ? "direct" : "clone",
            maxNewTokens: maxNewTokens > 0 ? maxNewTokens : nil,
            durationTokens: durationTokens > 0 ? durationTokens : nil,
            quality: quality,
            temperature: temperature,
            topP: topP,
            topK: topK,
            repetitionPenalty: repetitionPenalty,
            doSample: doSample
        )

        do {
            let result = try await InferenceManager.shared.synthesize(req.toPayload())
            recentResults.insert(result, at: 0)
            if recentResults.count > 12 { recentResults.removeLast(recentResults.count - 12) }
            play(result)
        } catch InferenceError.backendError(let message) {
            lastError = message
        } catch InferenceError.notRunning {
            lastError = "Inference backend not running. Try Restart Backend."
        } catch {
            lastError = error.localizedDescription
        }
    }

    // MARK: Playback

    func play(_ result: SynthResult) {
        do {
            player = try AVAudioPlayer(contentsOf: URL(fileURLWithPath: result.savedPath))
            player?.prepareToPlay()
            player?.play()
            nowPlayingId = result.id
        } catch {
            lastError = "Playback failed: \(error.localizedDescription)"
            nowPlayingId = nil
        }
    }

    func stopPlayback() {
        player?.stop()
        player = nil
        nowPlayingId = nil
    }

    func revealInFinder(_ result: SynthResult) {
        let url = URL(fileURLWithPath: result.savedPath)
        NSWorkspace.shared.activateFileViewerSelecting([url])
    }

    // MARK: Voices

    func reloadVoices() {
        let voicesDir = AppPaths.voicesDirectory
        try? FileManager.default.createDirectory(at: voicesDir, withIntermediateDirectories: true)
        let allowed: Set<String> = ["wav", "mp3", "m4a", "flac", "ogg"]
        let urls = (try? FileManager.default.contentsOfDirectory(
            at: voicesDir,
            includingPropertiesForKeys: [.fileSizeKey]
        )) ?? []
        let found = urls
            .filter { allowed.contains($0.pathExtension.lowercased()) }
            .sorted { $0.lastPathComponent < $1.lastPathComponent }
            .compactMap { url -> VoiceInfo? in
                guard let size = try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize else { return nil }
                return VoiceInfo(
                    name: url.deletingPathExtension().lastPathComponent,
                    filename: url.lastPathComponent,
                    size: size
                )
            }
        voices = found
        if let selected = selectedVoiceFilename,
           !found.contains(where: { $0.filename == selected }) {
            selectedVoiceFilename = nil
        }
    }

    func importVoice(from sourceURL: URL) {
        let voicesDir = AppPaths.voicesDirectory
        try? FileManager.default.createDirectory(at: voicesDir, withIntermediateDirectories: true)

        let ext = sourceURL.pathExtension.lowercased()
        let allowed: Set<String> = ["wav", "mp3", "m4a", "flac", "ogg"]
        guard allowed.contains(ext) else {
            lastError = "Unsupported audio format: .\(ext)"
            return
        }
        let stem = sanitizeVoiceStem(sourceURL.deletingPathExtension().lastPathComponent)
        let dest = voicesDir.appendingPathComponent("\(stem).\(ext)")

        let accessing = sourceURL.startAccessingSecurityScopedResource()
        defer { if accessing { sourceURL.stopAccessingSecurityScopedResource() } }

        do {
            if FileManager.default.fileExists(atPath: dest.path) {
                try FileManager.default.removeItem(at: dest)
            }
            let data = try Data(contentsOf: sourceURL)
            try data.write(to: dest)
            reloadVoices()
            selectedVoiceFilename = dest.lastPathComponent
        } catch {
            lastError = "Voice import failed: \(error.localizedDescription)"
        }
    }

    func deleteVoice(_ filename: String) {
        guard !filename.contains("/"), !filename.contains(".."), !filename.isEmpty else { return }
        let target = AppPaths.voicesDirectory.appendingPathComponent(filename)
        try? FileManager.default.removeItem(at: target)
        if selectedVoiceFilename == filename { selectedVoiceFilename = nil }
        reloadVoices()
    }

    private func sanitizeVoiceStem(_ raw: String) -> String {
        let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "_- "))
        let filtered = raw.unicodeScalars.filter { allowed.contains($0) }
        let cleaned = String(String.UnicodeScalarView(filtered))
            .trimmingCharacters(in: .whitespaces)
        let truncated = String(cleaned.prefix(40))
        if truncated.isEmpty {
            return "voice_" + UUID().uuidString.prefix(6).lowercased()
        }
        return truncated
    }
}
