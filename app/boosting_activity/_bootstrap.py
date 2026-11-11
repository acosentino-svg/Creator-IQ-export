"""Enable boosting-program-only scope for the activation dashboard codebase."""
from __future__ import annotations

import os
import sys
from pathlib import Path

_SCOPE_FLAG = "CREATORIQ_BOOSTING_PROGRAM_ONLY"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_APP_DIR = _REPO_ROOT / "app"
_SRC_DIR = _REPO_ROOT / "src"

for path in (str(_APP_DIR), str(_SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)


def ensure_boosting_scope() -> None:
    os.environ[_SCOPE_FLAG] = "1"


ensure_boosting_scope()
