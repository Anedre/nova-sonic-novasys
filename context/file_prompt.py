# context/file_prompt.py
from pathlib import Path
import re
from typing import Dict
from .base import ContextSource

_PLACEHOLDER_RE = re.compile(r"\{\{([A-Z0-9_]+)\}\}")

def _apply_vars(text: str, vars_dict: Dict[str, str]) -> str:
    def repl(m):
        k = m.group(1)
        return str(vars_dict.get(k, m.group(0)))
    return _PLACEHOLDER_RE.sub(repl, text)

class FilePromptSource(ContextSource):
    role = "SYSTEM"

    def __init__(self, path: str, vars: Dict[str, str] | None = None):
        self.path = path
        self.vars = vars or {}

    def render(self) -> str:
        p = Path(self.path)
        if not p.exists() or not p.is_file():
            raise FileNotFoundError(f"Prompt file no existe: {self.path}")
        raw = p.read_text(encoding="utf-8")
        return _apply_vars(raw, self.vars)
