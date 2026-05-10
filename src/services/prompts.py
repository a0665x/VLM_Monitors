"""Risk prompt persistence utilities."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from pydantic import BaseModel, Field

DEFAULT_PROMPT = "The baby is not visible in the frame"
DEFAULT_PATH = Path("data/risk_prompt.json")


class PromptHistoryEntry(BaseModel):
    version: int
    text: str
    updated_at: str
    updated_by: str | None = None


class RiskPrompt(BaseModel):
    version: int = Field(default=1, ge=1)
    text: str = Field(default=DEFAULT_PROMPT, min_length=1, max_length=1000)
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_by: str | None = None
    default_flag: bool = True


class PromptHistory(BaseModel):
    entries: List[PromptHistoryEntry] = Field(default_factory=list)


class PromptStore:
    """Thread-safe persistence helper for the risk prompt JSON file."""

    def __init__(self, path: Path = DEFAULT_PATH) -> None:
        self.path = path
        self.history_path = path.parent / "prompt_history.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def load(self) -> RiskPrompt:
        with self._lock:
            return self._load_unlocked()

    def update(self, text: str, updated_by: str | None = None) -> RiskPrompt:
        text = text.strip()
        if not text:
            raise ValueError("Prompt text cannot be empty")

        with self._lock:
            current = self._load_unlocked()
            next_prompt = current.model_copy(
                update={
                    "version": current.version + 1,
                    "text": text,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "updated_by": updated_by,
                    "default_flag": False,
                }
            )
            self._write(next_prompt)
            self._append_to_history(text)
            return next_prompt

    def history(self, limit: int = 5) -> PromptHistory:
        # This method seems unused in the current app.py but keeping signature for compatibility
        # We will implement a simpler list retrieval for the UI
        prompt = self.load()
        entry = PromptHistoryEntry(
            version=prompt.version,
            text=prompt.text,
            updated_at=prompt.updated_at,
            updated_by=prompt.updated_by,
        )
        return PromptHistory(entries=[entry])
    
    def get_history_texts(self) -> List[str]:
        """Returns a list of unique historical prompts, most recent first."""
        if not self.history_path.exists():
            return [DEFAULT_PROMPT]
        try:
            data = json.loads(self.history_path.read_text())
            return data.get("texts", [DEFAULT_PROMPT])
        except Exception:
            return [DEFAULT_PROMPT]

    def _append_to_history(self, text: str) -> None:
        """Appends text to history file if not already present."""
        texts = self.get_history_texts()
        if text in texts:
            # Move to top
            texts.remove(text)
        texts.insert(0, text)
        # Limit to last 50
        texts = texts[:50]
        self.history_path.write_text(json.dumps({"texts": texts}, indent=2))

    def _default_prompt(self) -> RiskPrompt:
        return RiskPrompt(text=DEFAULT_PROMPT, default_flag=True)

    def _load_unlocked(self) -> RiskPrompt:
        if self.path.exists():
            data = json.loads(self.path.read_text())
            return RiskPrompt(**data)
        prompt = self._default_prompt()
        self._write(prompt)
        return prompt

    def _write(self, prompt: RiskPrompt) -> None:
        tmp_path = self.path.with_suffix(".tmp")
        tmp_path.write_text(prompt.model_dump_json(indent=2))
        tmp_path.replace(self.path)


__all__ = ["PromptStore", "RiskPrompt", "PromptHistory", "PromptHistoryEntry"]
