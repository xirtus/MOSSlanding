#!/usr/bin/env bash
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"
if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Run ./install.sh first."
    exit 1
fi
source venv/bin/activate
exec python -m src.main "$@"
