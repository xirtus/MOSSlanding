#!/usr/bin/env bash
# Prevent CUDA memory fragmentation (reinforces what backend.py sets)
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export PYTORCH_ALLOC_CONF=expandable_segments:True

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"
source venv/bin/activate
exec python -m src.main
