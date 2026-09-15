"""
MOSS Audio Codec Bridge — lightweight Python subprocess that decodes
audio codes to PCM via the MOSS-TTS processor's built-in codec.

Protocol (newline-delimited JSON on stdin/stdout):
  {"op":"decode","codes":[[int,...],...],"n_vq":int}
  → {"pcm_path":"/path/to/tmp.f32","sample_rate":24000,"samples":N}
or
  → {"error":"message"}

  {"op":"shutdown"} → process exits
"""
import sys
import json
import os
import uuid
from pathlib import Path

import numpy as np
import torch

_MODEL_ID = "OpenMOSS-Team/MOSS-TTS-Local-Transformer"
os.environ.setdefault("HF_HOME", str(Path.home() / "Library/Application Support/MOSSlanding/models"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")

# Lazy import (expensive — loads codec model on first decode)
_processor = None


def _get_processor():
    global _processor
    if _processor is None:
        from transformers import AutoProcessor
        _processor = AutoProcessor.from_pretrained(_MODEL_ID, trust_remote_code=True)
    return _processor


def decode(codes_tensor, n_vq):
    """codes_tensor: list of lists, shape (nVQ, genLen)."""
    processor = _get_processor()
    codes = torch.from_numpy(np.array(codes_tensor)).long()
    wav_list = processor.decode_audio_codes([codes.transpose(0, 1)])
    wav = wav_list[0].numpy().astype(np.float32)
    pcm_path = (
        Path.home()
        / "Library/Application Support/MOSSlanding/pcm-tmp"
        / f"mlx_{uuid.uuid4().hex[:8]}.f32"
    )
    pcm_path.parent.mkdir(parents=True, exist_ok=True)
    wav.tofile(str(pcm_path))
    return {"pcm_path": str(pcm_path), "sample_rate": 24000, "samples": int(wav.size)}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"json parse: {e}"}), flush=True)
            continue

        op = req.get("op")
        if op == "shutdown":
            break
        if op == "decode":
            codes = req["codes"]
            n_vq = req.get("n_vq", 32)
            try:
                result = decode(codes, n_vq)
                print(json.dumps(result), flush=True)
            except Exception as e:
                print(json.dumps({"error": str(e)}), flush=True)
        else:
            print(json.dumps({"error": f"unknown op: {op}"}), flush=True)


if __name__ == "__main__":
    main()
