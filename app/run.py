#!/usr/bin/env python3
"""Source-tree launcher: python run.py [--tray]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from archvm.app import main

if __name__ == "__main__":
    sys.exit(main())
