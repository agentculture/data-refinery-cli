"""Entry point for ``python -m data_refinery``."""

from __future__ import annotations

import sys

from data_refinery.cli import main

if __name__ == "__main__":
    sys.exit(main())
