# Third-party notices

MOSSlanding is a desktop launcher. It does not include the MOSS-TTS model
weights in this repository; the app downloads them at runtime.

- **MOSS-TTS** — Apache License 2.0. Copyright the OpenMOSS / MOSI.AI authors.
  Upstream: https://github.com/OpenMOSS/MOSS-TTS
- **MOSS-VoiceGenerator**, **MOSS-Audio-Tokenizer** — see the upstream model
  cards for the license that applies to each download.
- **PyTorch** — BSD-style license.
- **Transformers, Accelerate, Safetensors, Tokenizers** — Apache License 2.0.
- **PySide6 / Qt** — LGPL-3.0 / commercial dual license, depending on the
  distribution.
- **Three.js** is not used by this app; the web UI is plain HTML/CSS/JS.

Model weights are downloaded separately and remain subject to their own
licenses. If you redistribute a bundled build, include the upstream license
texts and attribution.

MOSSlanding’s own source is MIT-licensed; see `LICENSE`.
