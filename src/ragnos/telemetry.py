from __future__ import annotations

import json
from typing import Any


def log_event(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False))
