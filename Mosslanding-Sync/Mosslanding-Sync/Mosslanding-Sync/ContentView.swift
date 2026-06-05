import SwiftUI

struct ContentView: View {
    @Environment(AppViewModel.self) private var viewModel

    var body: some View {
        @Bindable var vm = viewModel
        VStack(spacing: 0) {
            HeaderView(viewModel: vm)
            ScrollView {
                VStack(spacing: 14) {
                    InputCard(viewModel: vm)
                    ParametersCard(viewModel: vm)
                    synthesizeButton
                    if let err = vm.lastError {
                        errorBanner(err)
                    }
                    HistoryList(viewModel: vm)
                }
                .padding(14)
            }
        }
        .background(.background)
    }

    private var synthesizeButton: some View {
        @Bindable var vm = viewModel
        return Button {
            Task { await vm.synthesize() }
        } label: {
            HStack {
                if vm.isSynthesizing {
                    ProgressView()
                        .controlSize(.small)
                        .padding(.trailing, 4)
                }
                Text(vm.isSynthesizing ? "Synthesizing…" : "Synthesize")
                    .font(.body.weight(.semibold))
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 10)
        }
        .buttonStyle(.borderedProminent)
        .controlSize(.large)
        .keyboardShortcut(.return, modifiers: .command)
        .disabled(vm.isSynthesizing || !vm.status.isReady)
    }

    private func errorBanner(_ message: String) -> some View {
        @Bindable var vm = viewModel
        return HStack(alignment: .top, spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.orange)
            Text(message)
                .font(.callout)
                .textSelection(.enabled)
            Spacer()
            Button {
                vm.lastError = nil
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .foregroundStyle(.secondary)
            }
            .buttonStyle(.borderless)
        }
        .padding(12)
        .background(.orange.opacity(0.12))
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
    }
}

#Preview {
    ContentView()
        .environment(AppViewModel())
        .frame(width: 560, height: 720)
}
