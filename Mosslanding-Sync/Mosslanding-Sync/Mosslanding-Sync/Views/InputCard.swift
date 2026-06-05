import SwiftUI
import UniformTypeIdentifiers

struct InputCard: View {
    @Bindable var viewModel: AppViewModel
    @State private var showVoiceImporter = false

    private let languages: [(String, String)] = [
        ("auto", "Auto"),
        ("en", "English"),
        ("zh", "Chinese"),
        ("ja", "Japanese"),
        ("ko", "Korean"),
        ("es", "Spanish"),
        ("fr", "French"),
        ("de", "German"),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Prompt")
                .font(.headline)
            TextEditor(text: $viewModel.promptText)
                .font(.body)
                .frame(minHeight: 110)
                .padding(4)
                .background(.background.tertiary)
                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))

            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Language").font(.caption).foregroundStyle(.secondary)
                    Picker("Language", selection: $viewModel.language) {
                        ForEach(languages, id: \.0) { code, label in
                            Text(label).tag(code)
                        }
                    }
                    .labelsHidden()
                    .pickerStyle(.menu)
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text("Voice").font(.caption).foregroundStyle(.secondary)
                    HStack(spacing: 6) {
                        Picker("Voice", selection: $viewModel.selectedVoiceFilename) {
                            Text("None (direct)").tag(String?.none)
                            ForEach(viewModel.voices) { v in
                                Text(v.name).tag(Optional(v.filename))
                            }
                        }
                        .labelsHidden()
                        .pickerStyle(.menu)

                        Button {
                            showVoiceImporter = true
                        } label: {
                            Image(systemName: "square.and.arrow.down")
                        }
                        .help("Import voice sample")

                        if let selected = viewModel.selectedVoiceFilename {
                            Button(role: .destructive) {
                                viewModel.deleteVoice(selected)
                            } label: {
                                Image(systemName: "trash")
                            }
                            .help("Delete selected voice")
                        }
                    }
                }
            }
        }
        .padding(14)
        .background(.background.secondary)
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        .fileImporter(
            isPresented: $showVoiceImporter,
            allowedContentTypes: [.audio, .wav, .mp3],
            allowsMultipleSelection: false
        ) { result in
            switch result {
            case .success(let urls):
                if let url = urls.first { viewModel.importVoice(from: url) }
            case .failure(let error):
                viewModel.lastError = error.localizedDescription
            }
        }
    }
}
