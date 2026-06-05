# Sweep 7 handoff — drop the webview, build a native SwiftUI UI

You are picking this up cold. Read this whole file once, then start.

## Where the project is

This is a macOS TTS app. The original was a FastAPI Python server hidden
behind a WKWebView shell. Six sweeps in we are:

- **Swift app shell + Hummingbird HTTP server** — `swift/MossTTSApp.swift`
  (~1100 LOC). `@MainActor AppDelegate` + `actor InferenceManager`.
  Swift 6.3 strict concurrency, default-MainActor isolation. Tokenizers/Hub
  from `swift-transformers` SwiftPM dep wired into the Xcode target.
- **Python ML subprocess** — `backend/inference.py` (~450 LOC). Reads
  newline-delimited JSON on stdin; emits status frames and synthesis
  results on stdout. No HTTP, no FastAPI, no tiktoken.
- **WKWebView UI** that loads `webui/index.html` over a localhost HTTP
  server bound by the same app. This is the leftover that sweep 7 kills.

Sweep history (most recent first):
- **Sweep 6** — Text tokenization moved Python → Swift via swift-transformers.
  Direct mode ships pre-built `(seq_len, 1+n_vq)` row-major `input_ids` over
  IPC. Clone mode (voice reference) still flows through the Python processor
  — that's sweep 8.
- Sweep 5 — WAV encoding Python → Swift. `soundfile` + `librosa` dropped.
- Sweep 4 — Pillow → CoreGraphics for icon/DMG.
- Sweep 3 — `SMAppService` for login items. Multipart parser → raw bytes.
- Sweep 2 — Deleted FastAPI. Added stdin/stdout JSON IPC.
- Sweep 1 — Swift 6.3 strict concurrency, actor IPC, native WAV encoder.

## Why sweep 7 exists

The webview is legacy from the FastAPI era. Sweeps 2-6 ate the Python
server; the UI never got rewritten. We are now in a state where:

- A Swift app spins up a Hummingbird HTTP server on `127.0.0.1:8765`
- …purely so a WKWebView in the **same process** can hit that server
- …to render UI that's basically a form: text field, voice picker,
  parameter sliders, synthesize button, status row.

This is architectural debt that's actively biting:
- Sandbox port-binding fights (the Xcode target needs
  `com.apple.security.network.server` just to talk to itself).
- WKWebView eats memory and spawns three child processes whose noisy
  RBS assertion errors pollute every log session.
- The HTTP layer between Swift and JS marshals `SynthRequest` and
  `InferenceStatus` Codables that exist only to serialize across a
  127.0.0.1 boundary the app never actually wants to cross.

Going native lets you delete the entire Hummingbird stack, the FileMiddleware,
the CORS middleware, `webui/index.html`, the `WKWebView` setup, the
`ScriptMessageProxy`, and the localhost-only HTTP routing.

What's left is `SwiftUI View` → `Button { Task { await
InferenceManager.shared.synthesize(...) } }`.

## What sweep 6 left wired up that you keep

These already work; do not re-architect them:
- **`actor InferenceManager`** — owns the Python subprocess, the
  swift-transformers tokenizer, the `MossModelConfig` cached from
  `config.json`, and the synthesis FIFO. After sweep 7 it stays the
  single source of truth for inference state; call its methods directly
  from a SwiftUI view-model instead of going through HTTP.
- **The stdin/stdout JSON IPC contract** with `inference.py`. Read the
  docstring at the top of `backend/inference.py` — `pcm_path` /
  `sample_rate` / `samples` / `duration` flow, status frames, the
  direct-mode `input_ids` shape.
- **`pcmFloat32ToWAV(pcm:sampleRate:)`** — native PCM → WAV.
- **The `MossTokenizer` integration** — eager-load in
  `InferenceManager.start()`, `tokenizeDirect(text:language:tokens:)`
  builds the row-major flat array.
- **`AppPaths`** — `supportDirectory`, `voicesDirectory`,
  `modelsDirectory`, `modelsHubDirectory`, `outputDirectory`.
- **`SMAppService`-backed login item** + sleep/wake `restartIfNeeded()`.

## What sweep 7 deletes

- `import Hummingbird`, `import NIOCore`, `import HTTPTypes` from
  `MossTTSApp.swift`.
- `func buildServer(webuiDir:)` and every route handler inside
  (`/api/status`, `/api/models`, `/api/load`, `/api/unload`,
  `/api/synthesize`, `/api/voices`, `/api/voices/upload`,
  `/api/voices/:filename`, plus the `**` catch-all).
- `CORSMiddleware`, `FileMiddleware`, `Self_jsonOK`, `Self_jsonResponse`,
  `sanitizeVoiceStem` (move into the view-model if still needed for
  voice rename safety).
- `WKWebView`, `WKWebViewConfiguration`, `ScriptMessageProxy`,
  `loadingHTML`, `setupWindow()` as currently structured,
  `loadUIWhenReady()`, the `WKNavigationDelegate`/`WKUIDelegate`
  extension, `runOpenPanelWith` plumbing, `openVoiceFilePicker()` /
  `copyVoiceFile(_:)` (move the file copy into the view-model).
- The `hummingbird` SwiftPM dep — remove from
  `Mosslanding-Sync.xcodeproj`. Possibly `async-http-client` and the
  whole swift-nio surface area drops with it; check
  `packageProductDependencies` and let xcodebuild prune.
- `webui/index.html` and its Xcode reference.
- `serverTask` and `startSwiftServer()`. `InferenceManager.shared.start()`
  moves into the app's launch path directly.

## What sweep 7 adds

- A real SwiftUI `ContentView` in
  `Mosslanding-Sync/Mosslanding-Sync/ContentView.swift` (currently a
  Hello-World placeholder).
- A view-model (`@MainActor @Observable final class AppViewModel`) that
  holds the bindable UI state and dispatches to `InferenceManager`.
- `Mosslanding_SyncApp.swift` swaps `Settings { EmptyView() }` for a
  real `WindowGroup` (or `Window` if you want exactly one), keeping the
  `@NSApplicationDelegateAdaptor` for the status-bar item.
- Status-bar menu stays — but `AppDelegate` becomes a much thinner
  controller: just the menubar item, login-item toggle, wake observer.
- An `audio/wav` preview Player using `AVAudioPlayer` (or `AVPlayer`
  with the WAV `URL` on disk) for in-app playback.

## Recommended UI structure

```
ContentView
├── HeaderView
│   ├── status pill (loading %, ready, error)
│   └── model picker (NSPopUpButton-equivalent — Picker, .menu style)
├── InputCard
│   ├── TextEditor for prompt
│   ├── Language picker
│   └── Voice picker (None / list of uploaded voices / Upload…)
├── ParametersCard (collapsible)
│   ├── Quality slider (4..32)
│   ├── Temperature slider (0..2)
│   ├── Top-p slider (0..1)
│   ├── Top-k stepper (1..50)
│   ├── Duration tokens stepper
│   └── Max new tokens stepper
├── SynthesizeButton
└── HistoryList
    └── ForEach over recent SynthResult entries — play / reveal in Finder
```

`AppViewModel` exposes:
- `var status: InferenceStatus` (refreshed via a `Task` polling
  `InferenceManager.shared.currentStatus()` every 0.5s while
  `status.status == "loading"`)
- `var voices: [VoiceInfo]` (refreshed via `loadVoices()` after upload/
  delete)
- `var recentResults: [SynthResult]`
- `func synthesize(...) async throws -> SynthResult`
- `func loadModel() async` / `func unloadModel() async`
- `func uploadVoice(at url: URL) async throws`
- `func deleteVoice(_ filename: String) async throws`

## Recommended sequence

### Step A — Read the existing wiring

```
swift/MossTTSApp.swift
Mosslanding-Sync/Mosslanding-Sync/Mosslanding_SyncApp.swift
Mosslanding-Sync/Mosslanding-Sync/ContentView.swift
Mosslanding-Sync/Mosslanding-Sync/Item.swift            ← unused, delete
```

You only need to read `MossTTSApp.swift` for the actor surface and the
types it vends (`InferenceStatus`, `SynthResult`, `VoiceInfo`,
`ModelInfo`, `ModelsResponse`, `SynthRequest`). The HTTP route bodies
are reference implementations of the actions the view-model needs to
expose.

### Step B — Split `MossTTSApp.swift`

This file is ~1100 lines and has been a single-file project since sweep
1. Sweep 7 is a good excuse to split. Suggested layout:

```
Mosslanding-Sync/Mosslanding-Sync/
├── Mosslanding_SyncApp.swift          (existing — wire up Scene)
├── AppDelegate.swift                  (status bar + login item only)
├── ContentView.swift                  (root SwiftUI view)
├── Views/
│   ├── HeaderView.swift
│   ├── InputCard.swift
│   ├── ParametersCard.swift
│   ├── HistoryList.swift
│   └── VoiceUploadSheet.swift
├── ViewModel/
│   └── AppViewModel.swift
└── Inference/
    ├── InferenceManager.swift
    ├── InferenceTypes.swift           (InferenceStatus, SynthResult, VoiceInfo, ModelInfo)
    ├── MossTokenizer.swift            (MossModelConfig, mossSnapshotDirectory, etc.)
    └── WavEncoder.swift               (pcmFloat32ToWAV)
```

You can do this in two commits: first split with no behaviour changes
(should be a green build), then layer the SwiftUI work on top.

### Step C — View model + minimal SwiftUI

Hook up just the synthesize path first. Get text → button → WAV on
Desktop → in-window playback working before you build the parameters
card or voice picker.

### Step D — Voice management

Replace the HTTP upload/delete handlers with direct file operations
inside `AppViewModel.uploadVoice(at:)` and `deleteVoice(_:)`. Use
`.fileImporter(isPresented:allowedContentTypes:)` for picker; copy the
bytes into `AppPaths.voicesDirectory` like the current
`copyVoiceFile(_:)` does.

### Step E — Window / Scene

`Mosslanding_SyncApp.swift` currently vends `Settings { EmptyView() }`
to keep SwiftUI happy in accessory-mode. Change to:

```swift
@main
struct Mosslanding_SyncApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    var body: some Scene {
        Window("MOSSlanding", id: "main") {
            ContentView()
                .frame(minWidth: 520, minHeight: 600)
        }
        .windowResizability(.contentMinSize)
    }
}
```

`AppDelegate` keeps `NSApp.setActivationPolicy(.accessory)` and the
status-bar item, and forwards "Show / Hide" through
`NSApp.activate(ignoringOtherApps: true)` + opening the named window
via `NSApp.windows.first(where: ...)` or
`OpenWindowAction` from `@Environment(\.openWindow)`.

### Step F — Sandbox + venv python

While you're in the project file:
- Decide whether to **drop App Sandbox** or **scope it down**. With the
  webview + Hummingbird gone, the only sandbox-relevant access is
  `Process.run` against the Python venv and read/write of
  `~/Library/Application Support/MOSSlanding/`. Sandboxed-with-
  exceptions is feasible but a lot of entitlements; for a local-only
  dev app, just drop it.
- **Switch `findPythonAndScript()` to prefer the venv python**:
  `~/Library/Application Support/MOSSlanding/venv/bin/python3` first,
  fall back to `/opt/homebrew/bin/python3`. The system brew Python
  doesn't have torch/transformers installed; the venv from `setup.sh`
  does.

### Step G — Verification

```bash
# Build
xcodebuild -project Mosslanding-Sync.xcodeproj -scheme Mosslanding-Sync \
  -configuration Debug build

# Run from Xcode or open the .app directly. No HTTP server should bind.
lsof -nP -iTCP:8765 -sTCP:LISTEN  # should be empty

# Sanity:
# 1. Window opens with the native UI.
# 2. Status pill transitions starting → loading X% → ready.
# 3. "Hello from native UI." → Synthesize → WAV plays in-window and
#    lands at ~/Desktop/MOSSlanding/mosslanding_<8hex>.wav.
# 4. Upload a reference voice; clone-mode synth works (still uses the
#    Python processor for audio tokens — sweep 8 territory).
```

## Files in/out of scope

| File | Sweep 7 disposition |
|------|--------------------|
| `swift/MossTTSApp.swift` | Split + strip Hummingbird/WebKit. The actor + types/tokenizer survive. |
| `Mosslanding-Sync/Mosslanding-Sync/ContentView.swift` | Real UI now. |
| `Mosslanding-Sync/Mosslanding-Sync/Mosslanding_SyncApp.swift` | Window scene instead of Settings. |
| `Mosslanding-Sync/Mosslanding-Sync/Item.swift` | Delete; orphan placeholder. |
| `webui/index.html` | Delete + remove Xcode reference. |
| `Mosslanding-Sync.xcodeproj/project.pbxproj` | Remove `hummingbird` SwiftPM dep; possibly `async-http-client` + nio products. Drop or scope down App Sandbox. |
| `backend/inference.py` | Untouched. |
| `backend/requirements.txt`, `setup.sh` | Untouched. |
| `build.sh` | Still broken from sweep 6 (swiftc can't link SwiftPM). Sweep 7 can leave it; sweep 8 migrates to `xcodebuild`. |
| `dist.sh` | Untouched. |
| `scripts/make_icon.swift`, `scripts/make_dmg_bg.swift` | Untouched. |
| `MOSSlanding.app/` legacy bundle | Untouched build artifact. |

## Constraints to respect

- **Swift 6.3 strict concurrency, default-MainActor mode.** Top-level
  declarations are inferred MainActor-isolated unless marked
  `nonisolated`. Cross-actor types stay `nonisolated`. The view-model
  is `@MainActor`; `InferenceManager` is the existing actor; the bridge
  is `await` calls from `Task { ... }` in view event handlers.
- **No new SwiftPM deps.** swift-transformers / swift-huggingface /
  Jinja / yyjson / EventSource cover everything tokenization-side.
  AVFoundation covers WAV playback.
- **Don't bypass `InferenceManager`.** It owns the Python subprocess
  and the synthesis FIFO; all UI actions go through it.
- **Don't break the IPC contract** with `backend/inference.py`. Sweep 7
  is a UI-only refactor.
- **Don't reintroduce HTTP.** No `URLSession`, no NIO. The webview is
  the reason the HTTP layer exists; deleting one and keeping the other
  is the worst of both worlds.

## Pitfalls to expect

1. **Status polling cadence.** While the model is loading you want a
   live progress bar; once ready, polling is wasteful. Use a `Task`
   that polls every 500ms while `status.status` is in
   `{starting, loading}` and stops once it's `ready` or `error`. Restart
   the poll task on `loadModel()` / restart events.
2. **Quitting the app.** `AppDelegate.applicationWillTerminate` needs
   to send `{"op":"shutdown"}` and wait briefly for the Python
   subprocess to exit, otherwise you'll leak processes. Existing
   `terminate()` on the actor handles this; just call it.
3. **`@NSApplicationDelegateAdaptor` + accessory activation policy.**
   Setting `.accessory` in `applicationDidFinishLaunching` works for
   the menu-bar shape but means `Window`/`WindowGroup` won't auto-show.
   Either drop `.accessory` (regular app with menu-bar bonus) or wire
   the status item to `OpenWindowAction`. Pick one consciously.
4. **Voice file picker permissions.** Without sandbox, `.fileImporter`
   reads any user-readable file directly. With sandbox, you need
   `com.apple.security.files.user-selected.read-only` (already on) and
   you may need security-scoped URL bookmarks if you ever read the file
   later (you don't — `uploadVoice` copies bytes immediately).
5. **AVAudioPlayer + sandboxed Desktop write.** With sandbox enabled,
   writing to `~/Desktop/MOSSlanding/` needs
   `com.apple.security.files.user-selected.read-write` plus a
   user-driven write, which you don't have for an auto-save flow. If
   you keep sandbox: write to `AppPaths.outputDirectory` under App
   Support instead, and expose a "Reveal in Finder" button.
6. **Splitting the file might shuffle the Xcode synchronized group.**
   The Xcode target uses `PBXFileSystemSynchronizedRootGroup` for
   `Mosslanding-Sync/Mosslanding-Sync/` — adding files there is
   automatic, but the `swift/` folder is a regular Group with explicit
   file references. Moving `MossTTSApp.swift` into the sync group dir
   is the cleanest path; or just delete it after extracting its
   contents into separate files under the sync group.
7. **Don't bring SwiftData in.** `Item.swift` references SwiftData; the
   project doesn't actually use a persistent store. Delete the file
   and SwiftData usage with it. Recent results history can live in
   `@AppStorage` JSON or just in-memory for now.

## Queued for sweep 8 (was sweep 7)

- **Audio tokenizer → CoreML.** Move
  `MossTTSDelayProcessor.encode_audios_from_path` and the
  `audio_tokenizer.batch_encode` forward pass into Swift via CoreML
  conversion. Read `processing_moss_tts.py` and
  `modeling_moss_audio_tokenizer.py` in the HF cache for the spec.
  After this, clone mode also ships pre-built `input_ids` and the
  Python `_synthesize()` loses its remaining tokenization branch.
- **`build.sh` resurrection.** Migrate to
  `xcodebuild -project Mosslanding-Sync.xcodeproj`. The swiftc-only
  path has been dead since sweep 6 added the SwiftPM dep.
- **`dist.sh` DMG verification** end-to-end on the new artifact.
- **`AVPlayer` waveform scrub UI** for the history list (nice-to-have).

## Don't forget

- The bundled `MOSSlanding.app/Contents/Resources/backend/server.py` in
  the project tree is a stale pre-sweep-2 artifact. Untouched.
- Sweep 6 left two graceful fallbacks in `findPythonAndScript()` and
  `startSwiftServer()` to deal with Xcode flattening `webui/` and
  `backend/` folder groups. The `startSwiftServer` one disappears with
  the HTTP server; the `findPythonAndScript` one stays, but switch its
  preferred path to the venv python (see Step F).
- After you commit, append a "sweep 7" section to git history with a
  one-line summary: *"Native SwiftUI UI; deleted webview, Hummingbird,
  and the localhost HTTP server."*

Good luck. Keep it tight.
