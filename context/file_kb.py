# context/file_kb.py
from pathlib import Path
import json
from typing import Any, Dict
from .base import ContextSource

try:
    import yaml
except Exception:
    yaml = None

def _load_kb(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"KB no existe: {path}")
    raw = p.read_text(encoding="utf-8")
    if p.suffix.lower() in (".yml", ".yaml"):
        if not yaml:
            raise ImportError("Falta PyYAML: pip install pyyaml")
        return yaml.safe_load(raw) or {}
    return json.loads(raw or "{}")

def _render_kb_text(kb: Dict[str, Any]) -> str:
    passages = []
    counter = 1

    def add_passage(text: str) -> None:
        nonlocal counter
        passages.append(f"Passage %{counter}% {text}")
        counter += 1

    if kb.get("universidad"):
        add_passage(f"Universidad: {kb['universidad']}")
    if kb.get("unidad"):
        add_passage(f"Unidad académica: {kb['unidad']}")

    programs = kb.get("programas", [])
    for program in programs:
        nombre = program.get("nombre", "N/D")
        modalidades = ", ".join(program.get("modalidades", [])) or "N/D"
        fechas = program.get("fechas_inicio", "N/D")
        duracion = program.get("duracion", "N/D")
        costo = program.get("costo_referencial", "N/D")
        sede = program.get("sede", "N/D")
        add_passage(
            f"Programa: {nombre} | Modalidades: {modalidades} | Inicios: {fechas} | Duración: {duracion} | Costo referencial: {costo} | Sede: {sede}"
        )

    politicas = kb.get("politicas")
    if isinstance(politicas, dict):
        for clave, valor in politicas.items():
            add_passage(f"Política ({clave}): {valor}")

    contacto = kb.get("contacto")
    if isinstance(contacto, dict):
        detalles = []
        if contacto.get("correo"):
            detalles.append(f"correo: {contacto['correo']}")
        if contacto.get("telefono"):
            detalles.append(f"teléfono: {contacto['telefono']}")
        if contacto.get("whatsapp"):
            detalles.append(f"whatsapp: {contacto['whatsapp']}")
        if detalles:
            add_passage("Contacto: " + " | ".join(detalles))

    return "\n".join(passages).strip()

class FileKBSource(ContextSource):
    role = "SYSTEM"

    def __init__(self, path: str) -> None:
        self.path = path

    def render(self) -> str:
        kb = _load_kb(self.path)
        body = _render_kb_text(kb)
        if not body:
            return ""
        return f"##REFERENCE_DOCS##\n{body}\n##END_REFERENCE_DOCS##".strip()
