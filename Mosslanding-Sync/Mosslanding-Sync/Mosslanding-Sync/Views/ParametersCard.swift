import SwiftUI

struct ParametersCard: View {
    @Bindable var viewModel: AppViewModel
    @State private var expanded = false

    var body: some View {
        DisclosureGroup(isExpanded: $expanded) {
            VStack(spacing: 10) {
                slider("Quality (vq channels)", value: $viewModel.quality, range: 4...32, step: 1)
                slider("Temperature", value: $viewModel.temperature, range: 0...2, step: 0.05)
                slider("Top-p", value: $viewModel.topP, range: 0...1, step: 0.05)
                stepperRow("Top-k", value: $viewModel.topK, range: 1...100)
                stepperRow("Duration tokens (0 = auto)", value: $viewModel.durationTokens, range: 0...4000)
                stepperRow("Max new tokens", value: $viewModel.maxNewTokens, range: 100...8000, step: 100)
                slider("Repetition penalty", value: $viewModel.repetitionPenalty, range: 1...2, step: 0.05)
                Toggle("Sampling enabled", isOn: $viewModel.doSample)
            }
            .padding(.top, 8)
        } label: {
            Text("Parameters")
                .font(.headline)
        }
        .padding(14)
        .background(.background.secondary)
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private func slider<V: BinaryFloatingPoint>(
        _ title: String,
        value: Binding<V>,
        range: ClosedRange<V>,
        step: V.Stride
    ) -> some View where V.Stride: BinaryFloatingPoint {
        HStack {
            Text(title).frame(width: 200, alignment: .leading)
            Slider(value: value, in: range, step: step)
            Text(String(format: "%.2f", Double(value.wrappedValue)))
                .font(.caption.monospaced())
                .frame(width: 48, alignment: .trailing)
        }
    }

    private func slider(
        _ title: String,
        value: Binding<Int>,
        range: ClosedRange<Int>,
        step: Int
    ) -> some View {
        let doubleBinding = Binding<Double>(
            get: { Double(value.wrappedValue) },
            set: { value.wrappedValue = Int($0) }
        )
        return HStack {
            Text(title).frame(width: 200, alignment: .leading)
            Slider(value: doubleBinding,
                   in: Double(range.lowerBound)...Double(range.upperBound),
                   step: Double(step))
            Text("\(value.wrappedValue)")
                .font(.caption.monospaced())
                .frame(width: 48, alignment: .trailing)
        }
    }

    private func stepperRow(
        _ title: String,
        value: Binding<Int>,
        range: ClosedRange<Int>,
        step: Int = 1
    ) -> some View {
        HStack {
            Text(title).frame(width: 200, alignment: .leading)
            Stepper(value: value, in: range, step: step) {
                Text("\(value.wrappedValue)")
                    .font(.caption.monospaced())
            }
        }
    }
}
