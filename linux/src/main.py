#!/usr/bin/env python3
"""Mosslanding — MOSS-TTS Desktop Application entry point."""

import sys
import os

# Ensure src is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.app import MosslandingApp


def main():
    app = MosslandingApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
