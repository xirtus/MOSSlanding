import AppKit
import ServiceManagement
import SwiftUI

/// Thin controller: menu-bar item, login-item toggle, sleep/wake observer.
/// The Window scene in `Mosslanding_SyncApp` owns the actual UI.
@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {

    private var statusItem: NSStatusItem?
    private var statusMenu: NSMenu?

    /// Set from `Mosslanding_SyncApp` so we can drive synthesize from menu/etc.
    /// Optional because the delegate finishes launching before the App body
    /// constructs the model; wiring is best-effort.
    var viewModel: AppViewModel?

    func applicationDidFinishLaunching(_ notification: Notification) {
        AppPaths.ensureAll()
        setupStatusItem()
        observeSleepWake()
    }

    func applicationWillTerminate(_ notification: Notification) {
        // Best-effort: tell the Python subprocess to shut down cleanly.
        let semaphore = DispatchSemaphore(value: 0)
        Task.detached {
            await InferenceManager.shared.terminate()
            semaphore.signal()
        }
        _ = semaphore.wait(timeout: .now() + 1.5)
    }

    // MARK: Status bar

    private func setupStatusItem() {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        statusItem = item
        guard let button = item.button else { return }

        if let image = NSImage(systemSymbolName: "waveform", accessibilityDescription: "MOSSlanding") {
            image.isTemplate = true
            button.image = image
        } else {
            button.title = "ML"
        }

        let menu = NSMenu()
        menu.addItem(NSMenuItem(title: "Show Window", action: #selector(showMainWindow), keyEquivalent: ""))
        menu.addItem(.separator())
        let loginItem = NSMenuItem(title: "Start at Login", action: #selector(toggleLoginItem), keyEquivalent: "")
        loginItem.state = isLoginItemEnabled() ? .on : .off
        menu.addItem(loginItem)
        menu.addItem(NSMenuItem(title: "Restart Backend", action: #selector(restartBackend), keyEquivalent: ""))
        menu.addItem(.separator())
        menu.addItem(NSMenuItem(title: "Quit MOSSlanding", action: #selector(quit), keyEquivalent: "q"))
        for m in menu.items { m.target = self }
        statusMenu = menu

        button.sendAction(on: [.leftMouseUp, .rightMouseUp])
        button.action = #selector(handleStatusItemClick)
        button.target = self
    }

    @objc private func handleStatusItemClick() {
        guard let item = statusItem, let button = item.button else { return }
        let event = NSApp.currentEvent
        if event?.type == .rightMouseUp, let menu = statusMenu {
            item.menu = menu
            button.performClick(nil)
            item.menu = nil
        } else {
            showMainWindow()
        }
    }

    @objc private func showMainWindow() {
        if #available(macOS 14.0, *) {
            NSApp.activate()
        } else {
            NSApp.activate(ignoringOtherApps: true)
        }
        if let win = NSApp.windows.first(where: { $0.identifier?.rawValue == "main" || $0.title == "MOSSlanding" }) {
            win.makeKeyAndOrderFront(nil)
        } else {
            // Window scene hasn't materialized yet; bounce the dock icon so a
            // user click on the status item still surfaces the app.
            NSApp.unhide(nil)
        }
    }

    // MARK: Login item

    private func isLoginItemEnabled() -> Bool {
        SMAppService.mainApp.status == .enabled
    }

    @objc private func toggleLoginItem() {
        let service = SMAppService.mainApp
        do {
            switch service.status {
            case .enabled:
                try service.unregister()
            case .notRegistered, .notFound:
                try service.register()
            case .requiresApproval:
                SMAppService.openSystemSettingsLoginItems()
            @unknown default:
                try service.register()
            }
        } catch {
            logger.error("Login item toggle failed: \(error.localizedDescription, privacy: .public)")
        }
        if let menu = statusMenu {
            for item in menu.items where item.title == "Start at Login" {
                item.state = isLoginItemEnabled() ? .on : .off
            }
        }
    }

    @objc private func restartBackend() {
        viewModel?.restartBackend()
    }

    @objc private func quit() {
        NSApp.terminate(nil)
    }

    // MARK: Sleep / wake

    private func observeSleepWake() {
        let center = NSWorkspace.shared.notificationCenter
        center.addObserver(
            self,
            selector: #selector(handleWake),
            name: NSWorkspace.didWakeNotification,
            object: nil
        )
    }

    @objc private func handleWake() {
        Task { await InferenceManager.shared.restartIfNeeded() }
    }
}
