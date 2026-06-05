import Foundation

/// Filesystem layout. Everything user-mutable lives under Application Support;
/// finished WAVs land on Desktop where the user can find them.
nonisolated enum AppPaths {
    static var supportDirectory: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appending(path: "Library/Application Support/MOSSlanding", directoryHint: .isDirectory)
    }
    static var voicesDirectory: URL {
        supportDirectory.appending(path: "voices", directoryHint: .isDirectory)
    }
    static var modelsDirectory: URL {
        supportDirectory.appending(path: "models", directoryHint: .isDirectory)
    }
    static var modelsHubDirectory: URL {
        modelsDirectory.appending(path: "hub", directoryHint: .isDirectory)
    }
    static var outputDirectory: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appending(path: "Desktop/MOSSlanding", directoryHint: .isDirectory)
    }

    static func ensureAll() {
        for dir in [supportDirectory, voicesDirectory, modelsDirectory, modelsHubDirectory, outputDirectory] {
            try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        }
    }
}
