# context/base.py
from abc import ABC, abstractmethod
from typing import Literal

Role = Literal["SYSTEM", "USER"]

class ContextSource(ABC):
    """Produce un bloque de contexto para inyectar antes de la conversación."""
    role: Role = "SYSTEM"

    @abstractmethod
    def render(self) -> str:
        """Devuelve el texto final a inyectar (ya procesado)."""
        ...
