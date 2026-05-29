import AppKit
import WebKit
import Foundation

// MARK: - AppDelegate

class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate {

    private var statusItem: NSStatusItem?
    private var window: NSWindow?
    private var webView: WKWebView?
    private var serverProcess: Process?
    private var serverReady = false
    private var serverPort = 8765

    // Base URL for the local server
    private var serverURL: URL { URL(string: "http://127.0.0.1:\(serverPort)")! }

    // MARK: applicationDidFinishLaunching

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)   // no dock icon

        setupStatusItem()
        setupWindow()
        startServer()
    }

    func applicationWillTerminate(_ notification: Notification) {
        serverProcess?.terminate()
    }

    // MARK: Status bar

    private func setupStatusItem() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        guard let button = statusItem?.button else { return }

        if let img = NSImage(systemSymbolName: "waveform", accessibilityDescription: "MOSS TTS") {
            img.isTemplate = true
            button.image = img
        } else {
            button.title = "TTS"
        }

        button.action = #selector(toggleWindow)
        button.target = self

        // Right-click menu
        let menu = NSMenu()
        menu.addItem(NSMenuItem(title: "Show / Hide", action: #selector(toggleWindow), keyEquivalent: ""))
        menu.addItem(NSMenuItem.separator())
        let loginItem = NSMenuItem(title: "Start at Login", action: #selector(toggleLoginItem), keyEquivalent: "")
        loginItem.state = isLoginItemEnabled() ? .on : .off
        menu.addItem(loginItem)
        menu.addItem(NSMenuItem(title: "Restart Server", action: #selector(restartServer), keyEquivalent: ""))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Quit MOSS TTS", action: #selector(quit), keyEquivalent: "q"))

        // Left click: toggle; right click: menu
        button.sendAction(on: [.leftMouseUp, .rightMouseUp])
        statusItem?.menu = nil  // no auto-menu so we can intercept left/right clicks differently
        button.action = #selector(handleStatusItemClick)
        button.target = self
        // Store menu so we can show it on right click
        objc_setAssociatedObject(button, AssocKeys.menuKey, menu, .OBJC_ASSOCIATION_RETAIN)
    }

    @objc private func handleStatusItemClick() {
        let event = NSApp.currentEvent
        if event?.type == .rightMouseUp {
            if let menu = objc_getAssociatedObject(statusItem?.button as Any, AssocKeys.menuKey) as? NSMenu {
                statusItem?.menu = menu
                statusItem?.button?.performClick(nil)
                statusItem?.menu = nil
            }
        } else {
            toggleWindow()
        }
    }

    // MARK: Window

    private func setupWindow() {
        let config = WKWebViewConfiguration()
        config.preferences.setValue(true, forKey: "developerExtrasEnabled")

        let webV = WKWebView(frame: .zero, configuration: config)
        webV.navigationDelegate = self
        webV.allowsMagnification = false
        self.webView = webV

        let win = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 680, height: 640),
            styleMask: [.titled, .closable, .resizable, .miniaturizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        win.titlebarAppearsTransparent = true
        win.titleVisibility = .hidden
        win.contentView = webV
        win.title = "MOSS TTS"
        win.minSize = NSSize(width: 480, height: 400)
        win.center()
        win.isReleasedWhenClosed = false

        // Load a "loading" page while server starts
        let loadingHTML = """
        <html>
        <head>
          <meta charset="UTF-8">
          <style>
            body {
              display: flex; align-items: center; justify-content: center;
              height: 100vh; margin: 0;
              font-family: -apple-system, BlinkMacSystemFont, "SF Pro", sans-serif;
              background: #1e1e1e; color: #888; flex-direction: column; gap: 14px;
            }
            .spinner {
              width: 32px; height: 32px;
              border: 3px solid #333; border-top-color: #0a84ff;
              border-radius: 50%;
              animation: spin 0.8s linear infinite;
            }
            @keyframes spin { to { transform: rotate(360deg); } }
            p { font-size: 14px; }
          </style>
        </head>
        <body>
          <div class="spinner"></div>
          <p>Starting MOSS TTS server…</p>
        </body>
        </html>
        """
        webV.loadHTMLString(loadingHTML, baseURL: nil)
        self.window = win
    }

    @objc func toggleWindow() {
        guard let win = window else { return }
        if win.isVisible && NSApp.isActive {
            win.orderOut(nil)
        } else {
            win.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
        }
    }

    // MARK: Server management

    private func findPythonAndScript() -> (python: String, script: String)? {
        // Search order: venv next to app, app support dir, system
        let bundle = Bundle.main.bundleURL
        let projectDir = bundle.deletingLastPathComponent()  // Mosslanding/

        let candidates: [URL] = [
            // Same dir as .app
            projectDir.appendingPathComponent("venv/bin/python3"),
            // App support
            FileManager.default.homeDirectoryForCurrentUser
                .appendingPathComponent("Library/Application Support/MossTTS/venv/bin/python3"),
        ]

        let scriptCandidates: [URL] = [
            // Resources inside bundle
            bundle.appendingPathComponent("Contents/Resources/backend/server.py"),
            // Sibling to .app
            projectDir.appendingPathComponent("backend/server.py"),
            // App support
            FileManager.default.homeDirectoryForCurrentUser
                .appendingPathComponent("Library/Application Support/MossTTS/backend/server.py"),
        ]

        var pythonPath: String?
        for url in candidates {
            if FileManager.default.fileExists(atPath: url.path) {
                pythonPath = url.path
                break
            }
        }

        var scriptPath: String?
        for url in scriptCandidates {
            if FileManager.default.fileExists(atPath: url.path) {
                scriptPath = url.path
                break
            }
        }

        // Fallback: use system python3 + script relative to binary
        if pythonPath == nil {
            pythonPath = "/opt/homebrew/bin/python3"
            if !FileManager.default.fileExists(atPath: pythonPath!) {
                pythonPath = "/usr/bin/python3"
            }
        }

        guard let py = pythonPath, let sc = scriptPath else { return nil }
        return (py, sc)
    }

    private func startServer() {
        guard let (python, script) = findPythonAndScript() else {
            DispatchQueue.main.async { self.showSetupError() }
            return
        }

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: python)
        proc.arguments = [script]

        var env = ProcessInfo.processInfo.environment
        env["PYTORCH_MPS_HIGH_WATERMARK_RATIO"] = "0.0"
        env["OMP_NUM_THREADS"] = "4"
        env["MOSS_TTS_PORT"] = "\(serverPort)"
        // Point to the MOSS-TTS repo
        let mossTTSRepo = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("MOSS-TTS").path
        env["MOSS_TTS_REPO"] = mossTTSRepo
        proc.environment = env

        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        proc.standardOutput = stdoutPipe
        proc.standardError = stderrPipe

        // Log server output
        stdoutPipe.fileHandleForReading.readabilityHandler = { fh in
            let data = fh.availableData
            if !data.isEmpty, let s = String(data: data, encoding: .utf8) {
                NSLog("[server] %@", s.trimmingCharacters(in: .whitespacesAndNewlines))
            }
        }
        stderrPipe.fileHandleForReading.readabilityHandler = { fh in
            let data = fh.availableData
            if !data.isEmpty, let s = String(data: data, encoding: .utf8) {
                NSLog("[server-err] %@", s.trimmingCharacters(in: .whitespacesAndNewlines))
            }
        }

        proc.terminationHandler = { [weak self] _ in
            NSLog("Server process terminated (exit %d)", proc.terminationStatus)
            self?.serverReady = false
        }

        do {
            try proc.run()
            serverProcess = proc
            NSLog("Server started (pid %d): %@ %@", proc.processIdentifier, python, script)
        } catch {
            NSLog("Failed to start server: %@", error.localizedDescription)
            DispatchQueue.main.async { self.showSetupError() }
            return
        }

        // Poll until the server responds
        pollUntilReady()
    }

    private func pollUntilReady(attempt: Int = 0) {
        if attempt > 60 {
            NSLog("Server did not become ready after 60 attempts")
            DispatchQueue.main.async { self.showSetupError() }
            return
        }

        let url = serverURL.appendingPathComponent("/api/status")
        var req = URLRequest(url: url)
        req.timeoutInterval = 2

        URLSession.shared.dataTask(with: req) { [weak self] data, resp, err in
            guard let self = self else { return }
            if let httpResp = resp as? HTTPURLResponse, httpResp.statusCode == 200 {
                NSLog("Server ready after %d polls", attempt + 1)
                self.serverReady = true
                DispatchQueue.main.async { self.loadUI() }
            } else {
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
                    self.pollUntilReady(attempt: attempt + 1)
                }
            }
        }.resume()
    }

    private func loadUI() {
        guard let webV = webView else { return }
        let request = URLRequest(url: serverURL, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 10)
        webV.load(request)
        window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    private func showSetupError() {
        let html = """
        <html>
        <head><style>
          body { font-family: -apple-system; background:#1e1e1e; color:#f0f0f0;
                 display:flex; align-items:center; justify-content:center; height:100vh;
                 flex-direction:column; gap:16px; text-align:center; padding:40px; }
          h2 { color:#ff453a; }
          code { background:#333; padding:3px 8px; border-radius:5px; font-family:monospace; }
          p { color:#888; font-size:13px; max-width:480px; line-height:1.5; }
        </style></head>
        <body>
          <h2>⚠️ Could not start server</h2>
          <p>Run setup first:</p>
          <code>cd ~/Projects/Mosslanding && bash setup.sh</code>
          <p>Then relaunch the app. The backend needs Python + dependencies installed in <code>venv/</code>.</p>
        </body>
        </html>
        """
        webView?.loadHTMLString(html, baseURL: nil)
        window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    // MARK: Actions

    @objc private func restartServer() {
        serverProcess?.terminate()
        serverProcess = nil
        serverReady = false
        DispatchQueue.main.asyncAfter(deadline: .now() + 1) { [weak self] in
            self?.startServer()
        }
    }

    @objc private func quit() {
        serverProcess?.terminate()
        NSApp.terminate(nil)
    }

    // MARK: Login item

    private func launchAgentPlist() -> URL {
        let support = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/LaunchAgents/com.mosstts.launcher.plist")
        return support
    }

    private func isLoginItemEnabled() -> Bool {
        return FileManager.default.fileExists(atPath: launchAgentPlist().path)
    }

    @objc private func toggleLoginItem() {
        let script: String
        if isLoginItemEnabled() {
            script = Bundle.main.bundleURL.deletingLastPathComponent()
                .appendingPathComponent("scripts/install_launch_agent.sh").path
            let proc = Process()
            proc.executableURL = URL(fileURLWithPath: "/bin/bash")
            proc.arguments = [script, "uninstall"]
            try? proc.run(); proc.waitUntilExit()
        } else {
            let script2 = Bundle.main.bundleURL.deletingLastPathComponent()
                .appendingPathComponent("scripts/install_launch_agent.sh").path
            let proc = Process()
            proc.executableURL = URL(fileURLWithPath: "/bin/bash")
            proc.arguments = [script2, "install"]
            try? proc.run(); proc.waitUntilExit()
        }
        // Refresh menu item state
        if let menu = objc_getAssociatedObject(statusItem?.button as Any, AssocKeys.menuKey) as? NSMenu {
            for item in menu.items {
                if item.title == "Start at Login" {
                    item.state = isLoginItemEnabled() ? .on : .off
                }
            }
        }
    }

    // MARK: WKNavigationDelegate

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        NSLog("WebView navigation error: %@", error.localizedDescription)
    }
}

// MARK: - Associated object key

private enum AssocKeys {
    static let menuKey = UnsafeRawPointer(bitPattern: "mosstts.menu".hashValue)!
}

// MARK: - Entry point

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
