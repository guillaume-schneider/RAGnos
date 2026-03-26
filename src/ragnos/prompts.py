from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.prompts import ChatPromptTemplate


class PromptError(ValueError):
    pass


def load_prompt_text(prompt_path: Path) -> str:
    try:
        prompt_text = prompt_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise PromptError(f"Prompt file not found: {prompt_path}") from exc
    except UnicodeDecodeError as exc:
        raise PromptError(f"Prompt file must be valid UTF-8 text: {prompt_path}") from exc

    normalized = prompt_text.strip()
    if not normalized:
        raise PromptError(f"Prompt file is empty: {prompt_path}")
    if "{context}" not in normalized:
        raise PromptError(f"Prompt file must contain the {{context}} placeholder: {prompt_path}")
    return normalized


def build_prompt(config_or_prompt_text: Any) -> ChatPromptTemplate:
    prompt_text = getattr(config_or_prompt_text, "prompt_text", config_or_prompt_text)
    if not isinstance(prompt_text, str):
        raise TypeError("build_prompt expects a prompt string or an object exposing prompt_text.")

    return ChatPromptTemplate.from_messages(
        [
            ("system", prompt_text),
            ("human", "{input}"),
        ]
    )
