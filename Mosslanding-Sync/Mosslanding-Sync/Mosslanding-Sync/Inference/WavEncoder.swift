import Foundation

/// Encodes raw little-endian float32 mono PCM as a 16-bit signed PCM WAV
/// in memory. No temp file, no AVAudioFile round-trip.
nonisolated func pcmFloat32ToWAV(pcm: Data, sampleRate: Int) -> Data {
    let sampleCount = pcm.count / MemoryLayout<Float>.size
    var int16 = [Int16](repeating: 0, count: sampleCount)
    pcm.withUnsafeBytes { raw in
        guard let floats = raw.baseAddress?.assumingMemoryBound(to: Float.self) else { return }
        for i in 0..<sampleCount {
            let s = max(-1.0, min(1.0, floats[i]))
            int16[i] = Int16(s * 32767.0)
        }
    }
    let dataSize = int16.count * MemoryLayout<Int16>.size
    let byteRate = sampleRate * 2

    var wav = Data(capacity: 44 + dataSize)
    wav.append(contentsOf: "RIFF".utf8)
    wav.appendLittleEndian(UInt32(36 + dataSize))
    wav.append(contentsOf: "WAVE".utf8)
    wav.append(contentsOf: "fmt ".utf8)
    wav.appendLittleEndian(UInt32(16))
    wav.appendLittleEndian(UInt16(1))
    wav.appendLittleEndian(UInt16(1))
    wav.appendLittleEndian(UInt32(sampleRate))
    wav.appendLittleEndian(UInt32(byteRate))
    wav.appendLittleEndian(UInt16(2))
    wav.appendLittleEndian(UInt16(16))
    wav.append(contentsOf: "data".utf8)
    wav.appendLittleEndian(UInt32(dataSize))
    int16.withUnsafeBytes { wav.append(contentsOf: $0) }
    return wav
}

private nonisolated extension Data {
    mutating func appendLittleEndian<T: FixedWidthInteger>(_ value: T) {
        var le = value.littleEndian
        Swift.withUnsafeBytes(of: &le) { append(contentsOf: $0) }
    }
}
