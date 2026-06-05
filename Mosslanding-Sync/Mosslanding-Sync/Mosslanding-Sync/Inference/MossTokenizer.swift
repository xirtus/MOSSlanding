import Foundation

/// Subset of MOSS-TTS `model_config` read from `config.json`. Needed to build
/// the (T+1, 1+n_vq) row-major `input_ids` array the LM consumes in direct
/// mode — mirrors the tail of `MossTTSDelayProcessor.__call__` in
/// `processing_moss_tts.py`.
nonisolated struct MossModelConfig: Sendable {
    let nVQ: Int
    let audioPadCode: Int
    let audioStartTokenId: Int

    init(snapshotDir: URL) throws {
        let url = snapshotDir.appendingPathComponent("config.json")
        let data = try Data(contentsOf: url)
        guard
            let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
            let nVQ = json["n_vq"] as? Int,
            let pad = json["audio_pad_code"] as? Int,
            let start = json["audio_start_token_id"] as? Int
        else {
            throw InferenceError.ioFailure("malformed config.json at \(url.path)")
        }
        self.nVQ = nVQ
        self.audioPadCode = pad
        self.audioStartTokenId = start
    }
}

/// Resolves the MOSS-TTS-Local-Transformer snapshot directory under the
/// HuggingFace hub cache. `refs/main` holds the resolved commit hash; the
/// snapshot lives at `snapshots/<hash>/`.
nonisolated func mossSnapshotDirectory() throws -> URL {
    let hub = AppPaths.modelsHubDirectory
    let slug = "models--OpenMOSS-Team--MOSS-TTS-Local-Transformer"
    let refs = hub.appendingPathComponent("\(slug)/refs/main")
    let rev = (try? String(contentsOf: refs, encoding: .utf8))?
        .trimmingCharacters(in: .whitespacesAndNewlines)
    guard let rev, !rev.isEmpty else {
        throw InferenceError.ioFailure("missing or empty refs/main at \(refs.path)")
    }
    return hub.appendingPathComponent("\(slug)/snapshots/\(rev)")
}

/// Replicates `UserMessage.__post_init__` from `processing_moss_tts.py` for
/// the direct-mode case (no audio reference).
nonisolated func buildUserInstContent(
    text: String,
    language: String?,
    tokens: Int?
) -> String {
    let langStr: String
    if let language, !language.isEmpty, language.lowercased() != "auto" {
        langStr = language
    } else {
        langStr = "None"
    }
    let tokStr = tokens.map(String.init) ?? "None"
    return """
    <user_inst>
    - Reference(s):
    None
    - Instruction:
    None
    - Tokens:
    \(tokStr)
    - Quality:
    None
    - Sound Event:
    None
    - Ambient Sound:
    None
    - Language:
    \(langStr)
    - Text:
    \(text)
    </user_inst>
    """
}

/// Flattens text token IDs into the row-major (T+1, 1+n_vq) layout MOSS-TTS
/// expects.
nonisolated func buildMossInputIds(textTokens: [Int], config: MossModelConfig) -> [Int] {
    let nChannels = 1 + config.nVQ
    let rows = textTokens.count + 1
    var flat = [Int](repeating: config.audioPadCode, count: rows * nChannels)
    for (i, tok) in textTokens.enumerated() {
        flat[i * nChannels] = tok
    }
    flat[textTokens.count * nChannels] = config.audioStartTokenId
    return flat
}
