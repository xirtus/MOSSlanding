"""Voice Profile Registry — persistent JSON store for designed and cloned voices.

Stored at `<Mosslanding data dir>/voice_profiles.json` so it survives venv
rebuilds.  Each entry records the voice design instruction (or clone source),
the TTS model used, and optional metadata for cross-project reuse.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.backend import _get_app_data_dir

log = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────

VOICE_REGISTRY_PATH = _get_app_data_dir() / "voice_profiles.json"


# ── Schema ─────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_profile(
    name: str,
    instruction: str | None = None,
    reference_audio: str | None = None,
    mode: str = "generation",
    model: str = "OpenMOSS-Team/MOSS-TTS-v1.5",
    language: str = "English",
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict:
    return {
        "name": name,
        "instruction": instruction,
        "reference_audio": reference_audio,
        "mode": mode,
        "model": model,
        "language": language,
        "tags": tags or [],
        "metadata": metadata or {},
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }


# ── CRUD ───────────────────────────────────────────────────────────

def load_registry() -> dict[str, dict]:
    """Return {profile_name: profile_dict}.  Never fails — returns {} on error."""
    if not VOICE_REGISTRY_PATH.exists():
        return {}
    try:
        data = json.loads(VOICE_REGISTRY_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return data
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Failed to load voice registry: %s", e)
        return {}


def save_registry(registry: dict[str, dict]) -> None:
    """Atomically write registry to disk."""
    VOICE_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = VOICE_REGISTRY_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(VOICE_REGISTRY_PATH)


def list_profiles() -> list[dict]:
    """Return all profiles sorted by name."""
    reg = load_registry()
    return sorted(reg.values(), key=lambda p: p.get("name", ""))


def get_profile(name: str) -> dict | None:
    """Return a single profile by name, or None."""
    return load_registry().get(name)


def save_profile(
    name: str,
    instruction: str | None = None,
    reference_audio: str | None = None,
    mode: str = "generation",
    model: str = "OpenMOSS-Team/MOSS-TTS-v1.5",
    language: str = "English",
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict:
    """Create or update a voice profile. Returns the saved profile."""
    registry = load_registry()
    if name in registry:
        # Update existing
        existing = registry[name]
        existing["instruction"] = instruction or existing.get("instruction")
        existing["reference_audio"] = reference_audio or existing.get("reference_audio")
        if mode != "generation" or not existing.get("mode"):
            existing["mode"] = mode
        existing["model"] = model
        existing["language"] = language
        if tags is not None:
            existing["tags"] = list(set(existing.get("tags", []) + tags))
        if metadata:
            existing["metadata"].update(metadata)
        existing["updated_at"] = _now_iso()
    else:
        registry[name] = _new_profile(
            name=name,
            instruction=instruction,
            reference_audio=reference_audio,
            mode=mode,
            model=model,
            language=language,
            tags=tags,
            metadata=metadata,
        )
    save_registry(registry)
    log.info("Voice profile saved: %s", name)
    return registry[name]


def delete_profile(name: str) -> bool:
    """Remove a profile. Returns True if it existed."""
    registry = load_registry()
    if name in registry:
        del registry[name]
        save_registry(registry)
        log.info("Voice profile deleted: %s", name)
        return True
    return False


def find_by_tag(tag: str) -> list[dict]:
    """Return all profiles that have the given tag."""
    return [p for p in list_profiles() if tag in p.get("tags", [])]
