# context/bootstrap.py
from pathlib import Path
import json
from typing import List, Dict, Any
try:
    import yaml
except Exception:
    yaml = None

from .base import ContextSource
from .file_prompt import FilePromptSource
from .file_kb import FileKBSource

# Puedes registrar más tipos aquí
_REGISTRY = {
    "file_prompt": FilePromptSource,
    "file_kb": FileKBSource,
}

def _load_config(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Context config no existe: {path}")
    raw = p.read_text(encoding="utf-8")
    if p.suffix.lower() in (".yml", ".yaml"):
        if not yaml:
            raise ImportError("Falta PyYAML para YAML: pip install pyyaml")
        return yaml.safe_load(raw) or {}
    return json.loads(raw or "{}")

def load_context_sources(config_path: str) -> List[ContextSource]:
    cfg = _load_config(config_path)
    items = cfg.get("sources", [])
    if not isinstance(items, list) or not items:
        raise ValueError("Config vacío: se espera 'sources: [...]'")

    sources: List[ContextSource] = []
    for item in items:
        t = item.get("type")
        cls = _REGISTRY.get(t)
        if not cls:
            raise ValueError(f"ContextSource desconocido: {t}")
        kwargs = {k: v for k, v in item.items() if k not in ("type", "role")}
        src = cls(**kwargs)
        # Permite override de role si algún día necesitas USER
        if "role" in item: src.role = item["role"]
        sources.append(src)
    return sources
