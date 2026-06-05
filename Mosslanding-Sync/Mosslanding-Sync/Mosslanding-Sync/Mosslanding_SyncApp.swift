import SwiftUI

@main
struct Mosslanding_SyncApp: App {

    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @State private var viewModel = AppViewModel()

    var body: some Scene {
        Window("MOSSlanding", id: "main") {
            ContentView()
                .environment(viewModel)
                .frame(minWidth: 540, minHeight: 640)
                .onAppear {
                    appDelegate.viewModel = viewModel
                    viewModel.bootstrap()
                }
        }
        .windowResizability(.contentMinSize)
        .commands {
            CommandGroup(replacing: .newItem) {}
        }
    }
}
