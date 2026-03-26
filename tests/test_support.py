from __future__ import annotations

import shutil
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

TEST_TMP_ROOT = Path(".files") / "test-temp"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)

PROMPT_TEXT = (
    "Tu es un assistant strict.\n"
    "Contexte :\n"
    "{context}"
)


@contextmanager
def workspace_tempdir():
    path = TEST_TMP_ROOT / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def write_prompt(root: Path, content: str = PROMPT_TEXT) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    prompt_path = root / ".prompt"
    prompt_path.write_text(content, encoding="utf-8")
    return prompt_path
