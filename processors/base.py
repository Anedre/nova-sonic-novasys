from abc import ABC, abstractmethod
from typing import Dict, Optional

class DataProcessor(ABC):
    """Interfaz para procesar texto y generar artefactos (leads/JSON)."""

    @abstractmethod
    def on_user_text(self, text: str) -> None:
        """Se llama cuando llega texto ROLE=USER."""
        ...

    @abstractmethod
    def on_assistant_text(self, text: str) -> None:
        """Opcional: si quieres observar lo que genera el asistente."""
        ...

    @abstractmethod
    def maybe_capture_action(self, text: str) -> bool:
        """
        Intenta capturar un bloque JSON de acción en una sola línea.
        Retorna True si capturó JSON (para que el manager silencie el audio
        hasta contentEnd).
        """
        ...

    @abstractmethod
    def on_content_end(self) -> None:
        """Señal de fin de turno (contentEnd). Útil para limpiar estados."""
        ...

    @abstractmethod
    def on_session_end(self, session_id: str) -> Optional[str]:
        """
        Fin de sesión. Si no hubo JSON del modelo, genera fallback y exporta.
        Debe devolver la ruta del archivo exportado (si corresponde) o None.
        """
        ...

    @abstractmethod
    def snapshot_lead(self) -> Dict:
        """Devuelve el estado actual del lead (para inspección/log)."""
        ...
