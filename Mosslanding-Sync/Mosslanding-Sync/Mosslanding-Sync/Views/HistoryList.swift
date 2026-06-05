import SwiftUI

struct HistoryList: View {
    @Bindable var viewModel: AppViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Recent")
                    .font(.headline)
                Spacer()
                if viewModel.nowPlayingId != nil {
                    Button {
                        viewModel.stopPlayback()
                    } label: {
                        Label("Stop", systemImage: "stop.circle")
                    }
                    .buttonStyle(.borderless)
                }
            }

            if viewModel.recentResults.isEmpty {
                Text("No results yet — synthesize something.")
                    .foregroundStyle(.secondary)
                    .font(.callout)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.vertical, 4)
            } else {
                ForEach(viewModel.recentResults) { result in
                    row(for: result)
                }
            }
        }
        .padding(14)
        .background(.background.secondary)
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    @ViewBuilder
    private func row(for result: SynthResult) -> some View {
        let isPlaying = viewModel.nowPlayingId == result.id
        HStack(spacing: 10) {
            Button {
                if isPlaying { viewModel.stopPlayback() } else { viewModel.play(result) }
            } label: {
                Image(systemName: isPlaying ? "stop.circle.fill" : "play.circle.fill")
                    .font(.title2)
            }
            .buttonStyle(.borderless)

            VStack(alignment: .leading, spacing: 2) {
                Text(result.filename)
                    .font(.callout.monospaced())
                Text(String(format: "%.2fs · %@", result.duration, formatted(result.createdAt)))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            Button {
                viewModel.revealInFinder(result)
            } label: {
                Image(systemName: "folder")
            }
            .help("Reveal in Finder")
            .buttonStyle(.borderless)
        }
        .padding(.vertical, 4)
    }

    private func formatted(_ date: Date) -> String {
        let f = DateFormatter()
        f.dateStyle = .none
        f.timeStyle = .medium
        return f.string(from: date)
    }
}
