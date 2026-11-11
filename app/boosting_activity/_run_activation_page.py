"""Run a shared activation page script under boosting program scope."""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parents[1].parent
_SRC_DIR = _APP_DIR.parent / "src"
for path in (str(_APP_DIR), str(_SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from boosting_activity import _bootstrap  # noqa: F401

_APP_PAGES = Path(__file__).resolve().parents[1] / "pages"


def run_activation_page(filename: str) -> None:
    target = _APP_PAGES / filename
    if not target.is_file():
        raise FileNotFoundError(target)
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    run_activation_page(sys.argv[1])
