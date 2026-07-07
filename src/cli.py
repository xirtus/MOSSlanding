#!/usr/bin/env python3
"""Mosslanding CLI — generate TTS audio from command line.
Usage: python -m src.cli --text "Hello world" --output out.wav [--language English] [--quality 16]
"""

import argparse
import json
import sys
import os
import time
import tempfile
import logging
from pathlib import Path

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backend import MossTTSBackend, gpu_info, setup_file_logging

log = logging.getLogger("mosslanding.cli")

def main():
    parser = argparse.ArgumentParser(description="Mosslanding TTS CLI")
    # ── Status / preload (fast paths, no generation) ──
    parser.add_argument("--status", action="store_true",
                        help="Print health status JSON and exit (no GPU load)")
    parser.add_argument("--preload", action="store_true",
                        help="Preload model into GPU and exit")
    parser.add_argument("--unload", action="store_true",
                        help="Unload model from GPU and free VRAM")
    # ── Generation ──
    parser.add_argument("--text", default=None, help="Text to synthesize")
    parser.add_argument("--output", default=None, help="Output WAV file path")
    parser.add_argument("--language", default="English", help="Language tag (default: English)")
    parser.add_argument("--quality", type=int, default=16, choices=[4, 8, 16, 32],
                        help="RVQ quality layers (4=fastest, 32=best)")
    parser.add_argument("--temperature", type=float, default=1.7, help="Generation temperature")
    parser.add_argument("--top-p", type=float, default=0.8, help="Top-p sampling")
    parser.add_argument("--top-k", type=int, default=25, help="Top-k sampling")
    parser.add_argument("--max-tokens", type=int, default=2048, help="Max new tokens")
    parser.add_argument("--reference-audio", default=None, help="Reference audio for voice cloning")
    parser.add_argument("--mode", default="clone", choices=["clone", "continue", "continue_clone", "generation"])
    parser.add_argument("--model", default="OpenMOSS-Team/MOSS-TTS-v1.5", help="Model name")
    parser.add_argument("--voice-instruction", default=None,
                        help="Natural-language voice design instruction (enables voice generation mode)")
    # ── Voice profile management ──
    parser.add_argument("--list-voices", action="store_true",
                        help="List all saved voice profiles (JSON)")
    parser.add_argument("--save-voice", default=None, metavar="NAME",
                        help="Save current generation params as a named voice profile")
    parser.add_argument("--delete-voice", default=None, metavar="NAME",
                        help="Delete a saved voice profile")
    parser.add_argument("--find-voice-by-tag", default=None, metavar="TAG",
                        help="Find voice profiles by tag (JSON array)")
    parser.add_argument("--voice-tags", default=None,
                        help="Comma-separated tags for --save-voice")
    args = parser.parse_args()

    # Setup logging
    setup_file_logging()
    log.info("Mosslanding CLI started")

    # ═══════════════════════════════════════════════════════════════
    # Fast path: --status (no model load, <500ms)
    # ═══════════════════════════════════════════════════════════════
    if args.status:
        try:
            gpu = gpu_info()
            venv_ok = True  # We're running in the venv
            # Check model config existence
            hf_cache = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
            model_configured = (hf_cache.exists() or MODELS_DIR.exists())
            print(json.dumps({
                "ok": True,
                "vram_free": sum(g.get("free_gb", 0) for g in gpu.get("gpus", [])),
                "model_loaded": False,  # status never loads the model
                "version": "1.5",
                "venv": True,
                "model_configured": model_configured,
                "gpu": gpu,
            }))
            return 0
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)}))
            return 1

    # ═══════════════════════════════════════════════════════════════
    # Fast path: --preload (load model into GPU, idempotent)
    # ═══════════════════════════════════════════════════════════════
    if args.preload:
        backend = MossTTSBackend()
        backend.set_progress_callback(lambda msg: print(f"[moss] {msg}", file=sys.stderr, flush=True))
        try:
            t0 = time.monotonic()
            if backend.is_loaded:
                print(json.dumps({
                    "ok": True,
                    "vram_used": 0.0,
                    "load_time_ms": 0.0,
                    "already_loaded": True,
                }))
                return 0
            backend.load_model(args.model)
            elapsed_ms = (time.monotonic() - t0) * 1000.0
            gpu = gpu_info()
            vram_used = sum(g.get("allocated_gb", 0) for g in gpu.get("gpus", []))
            print(json.dumps({
                "ok": True,
                "vram_used": round(vram_used, 2),
                "load_time_ms": round(elapsed_ms, 0),
                "already_loaded": False,
                "gpu": gpu,
            }))
            return 0
        except Exception as e:
            log.exception("Preload failed")
            print(json.dumps({"ok": False, "error": str(e)}))
            return 1

    # ═══════════════════════════════════════════════════════════════
    # Fast path: --unload (free GPU VRAM, always succeeds)
    # ═══════════════════════════════════════════════════════════════
    if args.unload:
        backend = MossTTSBackend()
        try:
            t0 = time.monotonic()
            backend.unload()
            elapsed_ms = (time.monotonic() - t0) * 1000.0
            gpu = gpu_info()
            free_gb = sum(g.get("free_gb", 0) for g in gpu.get("gpus", []))
            print(json.dumps({
                "ok": True,
                "vram_freed": round(free_gb, 2),
                "unload_time_ms": round(elapsed_ms, 0),
                "gpu": gpu,
            }))
            return 0
        except Exception as e:
            # Unload should never fail — but if it does, report honestly
            print(json.dumps({"ok": False, "error": str(e)}))
            return 1

    # ═══════════════════════════════════════════════════════════════
    # Voice profile management (no GPU needed)
    # ═══════════════════════════════════════════════════════════════
    if args.list_voices:
        from src.voice_registry import list_profiles
        profiles = list_profiles()
        print(json.dumps({"ok": True, "profiles": profiles}))
        return 0

    if args.save_voice:
        from src.voice_registry import save_profile
        tags = [t.strip() for t in (args.voice_tags or "").split(",") if t.strip()]
        profile = save_profile(
            name=args.save_voice,
            instruction=args.voice_instruction if args.voice_instruction else None,
            reference_audio=args.reference_audio,
            mode=args.mode if args.mode != "clone" or args.reference_audio else "generation",
            model=args.model,
            language=args.language,
            tags=tags,
        )
        print(json.dumps({"ok": True, "profile": profile}))
        return 0

    if args.delete_voice:
        from src.voice_registry import delete_profile
        deleted = delete_profile(args.delete_voice)
        print(json.dumps({"ok": True, "deleted": deleted, "name": args.delete_voice}))
        return 0

    if args.find_voice_by_tag:
        from src.voice_registry import find_by_tag
        matches = find_by_tag(args.find_voice_by_tag)
        print(json.dumps({"ok": True, "tag": args.find_voice_by_tag, "profiles": matches}))
        return 0

    # ═══════════════════════════════════════════════════════════════
    # Voice design path: --voice-instruction
    # ═══════════════════════════════════════════════════════════════
    if args.voice_instruction:
        if not args.text:
            print(json.dumps({"status": "error", "error": "--text is required with --voice-instruction"}))
            return 1
        backend = MossTTSBackend()
        backend.set_progress_callback(lambda msg: print(f"[moss] {msg}", file=sys.stderr, flush=True))
        try:
            backend.load_model(args.model)
            if not backend.is_loaded:
                print(json.dumps({"status": "error", "error": "Model failed to load"}))
                return 1
            print(f"[moss] Designing voice...", file=sys.stderr, flush=True)
            sr, audio = backend.generate_voice(
                text=args.text,
                instruction=args.voice_instruction,
                temperature=args.temperature,
                top_p=args.top_p,
                top_k=args.top_k,
                max_new_tokens=args.max_tokens,
                quality=args.quality,
            )
            import soundfile as sf
            output_path = Path(args.output) if args.output else Path(tempfile.mkstemp(suffix=".wav")[1])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            sf.write(str(output_path), audio, sr)
            duration_s = len(audio) / sr
            print(json.dumps({
                "status": "ok",
                "output": str(output_path),
                "sample_rate": sr,
                "duration_seconds": round(duration_s, 2),
                "samples": len(audio),
                "voice_instruction": args.voice_instruction,
            }))
            backend.unload()
            return 0
        except Exception as e:
            log.exception("Voice design failed")
            print(json.dumps({"status": "error", "error": str(e)}))
            try:
                backend.unload()
            except:
                pass
            return 1

    # ═══════════════════════════════════════════════════════════════
    # Standard TTS narration path (requires --text + --output)
    # ═══════════════════════════════════════════════════════════════
    if not args.text:
        parser.print_help()
        print("\nError: --text is required for generation mode", file=sys.stderr)
        return 1
    if not args.output:
        print("Error: --output is required for generation mode", file=sys.stderr)
        return 1

    log.info(f"Text: {args.text[:100]}...")
    log.info(f"Output: {args.output}")

    backend = MossTTSBackend()

    # Progress callback
    def progress(msg):
        print(f"[moss] {msg}", file=sys.stderr, flush=True)

    backend.set_progress_callback(progress)

    try:
        # Load model
        backend.load_model(args.model)
        if not backend.is_loaded:
            print("FATAL: Model failed to load", file=sys.stderr)
            return 1

        # Generate
        print(f"[moss] Synthesizing...", file=sys.stderr, flush=True)
        sr, audio = backend.generate_tts(
            text=args.text,
            reference_audio=args.reference_audio,
            mode="generation" if not args.reference_audio else args.mode,
            language_tag=args.language,
            temperature=args.temperature,
            top_p=args.top_p,
            top_k=args.top_k,
            max_new_tokens=args.max_tokens,
            quality=args.quality,
        )

        # Save as WAV
        import soundfile as sf
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output_path), audio, sr)
        duration_s = len(audio) / sr
        print(f"[moss] Saved: {output_path} ({duration_s:.1f}s, {sr}Hz)", file=sys.stderr, flush=True)

        # Print result to stdout for JSON parsing
        print(json.dumps({
            "status": "ok",
            "output": str(output_path),
            "sample_rate": sr,
            "duration_seconds": round(duration_s, 2),
            "samples": len(audio),
        }))

        backend.unload()
        return 0

    except Exception as e:
        log.exception("CLI generation failed")
        print(f"FATAL: {e}", file=sys.stderr)
        print(json.dumps({"status": "error", "error": str(e)}))
        try:
            backend.unload()
        except:
            pass
        return 1

if __name__ == "__main__":
    sys.exit(main())
