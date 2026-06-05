import SwiftUI

struct HeaderView: View {
    @Bindable var viewModel: AppViewModel

    var body: some View {
        HStack(spacing: 12) {
            statusPill
            Spacer()
            Picker("Model", selection: activeModelBinding) {
                ForEach(viewModel.models) { model in
                    Text(model.modelId).tag(model.modelId)
                }
            }
            .pickerStyle(.menu)
            .labelsHidden()
            .frame(maxWidth: 280)

            Menu {
                Button("Load model")   { viewModel.loadModel() }
                Button("Unload model") { viewModel.unloadModel() }
                Divider()
                Button("Restart backend") { viewModel.restartBackend() }
            } label: {
                Image(systemName: "ellipsis.circle")
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
        }
        .padding(.horizontal)
        .padding(.vertical, 10)
        .background(.background.secondary)
    }

    private var statusPill: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(statusColor)
                .frame(width: 9, height: 9)
            VStack(alignment: .leading, spacing: 0) {
                Text(statusLabel)
                    .font(.callout.weight(.medium))
                if !statusSubtitle.isEmpty {
                    Text(statusSubtitle)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            if viewModel.status.isBusy && viewModel.status.progress > 0 {
                ProgressView(value: Double(viewModel.status.progress), total: 100)
                    .progressViewStyle(.linear)
                    .frame(width: 80)
            }
        }
    }

    private var statusColor: Color {
        if viewModel.status.hasError { return .red }
        if viewModel.status.isReady { return .green }
        return .yellow
    }

    private var statusLabel: String {
        switch viewModel.status.status {
        case "ready":    return "Ready"
        case "loading":  return "Loading model… \(viewModel.status.progress)%"
        case "starting": return "Starting backend…"
        case "error":    return "Error"
        case "":         return "Idle"
        default:         return viewModel.status.status.capitalized
        }
    }

    private var statusSubtitle: String {
        if viewModel.status.hasError {
            return viewModel.status.error
        }
        if !viewModel.status.message.isEmpty {
            return viewModel.status.message
        }
        if viewModel.status.isReady, !viewModel.status.device.isEmpty {
            return "Device: \(viewModel.status.device)"
        }
        return ""
    }

    private var activeModelBinding: Binding<String> {
        Binding(
            get: { viewModel.models.first(where: { $0.active })?.modelId ?? "" },
            set: { _ in }
        )
    }
}
