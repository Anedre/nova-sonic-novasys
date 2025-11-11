# processors/tool_use_processor.py
"""
Processor que maneja Tool Use de Nova Sonic para captura estructurada.
Reemplaza PERulesV1 con un enfoque nativo de AWS: el modelo llama
una herramienta 'guardar_lead' cuando tiene datos completos.
"""
import json
import re
import datetime
import uuid
from pathlib import Path
from typing import Dict, Optional
from .base import DataProcessor
from config import DNI_LENGTH, PHONE_LENGTH, LEADS_EXPORT_FOLDER, mask_pii


class ToolUseProcessor(DataProcessor):
    """Maneja tool_use events de Nova Sonic para guardar leads."""

    def __init__(self):
        self.captured_lead: Optional[Dict] = None
        self.session_id: Optional[str] = None

    def on_user_text(self, text: str) -> None:
        """Observa texto del usuario (sin procesar aquí, el modelo maneja captura)."""
        pass

    def on_assistant_text(self, text: str) -> None:
        """Observa texto del asistente (sin procesar aquí)."""
        pass

    def maybe_capture_action(self, text: str) -> bool:
        """
        Ya NO parseamos JSON del texto.
        Retorna False siempre porque usamos tool_use events.
        """
        return False

    def handle_tool_use(self, tool_name: str, tool_input: Dict) -> Dict:
        """
        Llamado cuando Nova Sonic invoca una herramienta.
        
        Args:
            tool_name: Nombre de la herramienta ("guardar_lead")
            tool_input: Parámetros que el modelo extrajo
            
        Returns:
            Resultado para enviar de vuelta al modelo
        """
        print(f"🔧 [ToolUseProcessor] Tool invocado: {tool_name}")
        
        # Defensa adicional: parsear si llega como string
        if isinstance(tool_input, str):
            try:
                tool_input = json.loads(tool_input)
                print(f"✅ [ToolUseProcessor] Input parseado de string JSON")
            except json.JSONDecodeError as e:
                print(f"❌ [ToolUseProcessor] Error parseando input JSON: {e}")
                return {
                    "status": "error",
                    "message": f"Input inválido (no es JSON válido): {str(e)}"
                }
        
        if tool_name == "guardar_lead":
            try:
                # Validar y limpiar datos (con logging de PII enmascarado)
                lead = self._validate_lead(tool_input)
                self.captured_lead = lead
                
                # Log seguro
                safe_log = {
                    'nombre': lead.get('nombre_completo', 'N/A')[:20] + '...' if lead.get('nombre_completo') else 'N/A',
                    'dni': mask_pii(lead.get('dni') or '', show_last=2),
                    'telefono': mask_pii(lead.get('telefono') or '', show_last=2),
                    'email': lead.get('email', 'N/A'),
                    'programa': lead.get('programa_interes', 'N/A')
                }
                print(f"✅ [ToolUseProcessor] Lead validado: {safe_log}")
                
                # Retornar confirmación al modelo
                return {
                    "status": "success",
                    "message": "Lead guardado correctamente",
                    "lead_id": str(uuid.uuid4())[:8]
                }
            except Exception as e:
                print(f"❌ [ToolUseProcessor] Error validando lead: {e}")
                return {
                    "status": "error",
                    "message": f"Error al procesar datos: {str(e)}"
                }
        
        print(f"⚠️ [ToolUseProcessor] Herramienta desconocida: {tool_name}")
        return {"status": "error", "message": f"Herramienta desconocida: {tool_name}"}

    def _validate_lead(self, raw_lead: Dict) -> Dict:
        """Valida y normaliza el lead capturado por el modelo."""
        
        # Extraer y limpiar DNI
        dni_raw = raw_lead.get("dni", "")
        dni_clean = self._validate_dni(dni_raw)
        if dni_raw and not dni_clean:
            print(f"⚠️ [ToolUseProcessor] DNI inválido (esperado {DNI_LENGTH} dígitos): '{mask_pii(dni_raw)}'")
        
        # Extraer y limpiar teléfono
        phone_raw = raw_lead.get("telefono", "")
        phone_clean = self._validate_phone(phone_raw)
        if phone_raw and not phone_clean:
            print(f"⚠️ [ToolUseProcessor] Teléfono inválido (esperado {PHONE_LENGTH} dígitos): '{mask_pii(phone_raw)}'")
        
        # Validar email básico
        email_raw = raw_lead.get("email", "")
        email_clean = self._validate_email(email_raw)
        if email_raw and not email_clean:
            print(f"⚠️ [ToolUseProcessor] Email inválido: '{email_raw}'")
        
        validated = {
            "nombre_completo": self._clean_text(raw_lead.get("nombre_completo", "")),
            "dni": dni_clean,
            "telefono": phone_clean,
            "email": email_clean,
            "programa_interes": self._clean_text(raw_lead.get("programa_interes", "")),
            "modalidad_preferida": raw_lead.get("modalidad_preferida", "").lower() if raw_lead.get("modalidad_preferida") else None,
            "horario_preferido": self._clean_text(raw_lead.get("horario_preferido", "")),
            "consentimiento": raw_lead.get("consentimiento", "").lower(),
            "idioma": "es-PE",
            "origen": "demo-postgrado"
        }
        
        # Retornar datos, incluso si algunos son None
        return {k: v if v else None for k, v in validated.items()}

    def _clean_text(self, text: str) -> str:
        """Limpia texto de muletillas y espacios extra."""
        if not text:
            return ""
        # Remover muletillas comunes
        text = re.sub(r'\b(eh|um|mmm|este|bueno|ya|oye|mira)\b', '', text, flags=re.IGNORECASE)
        # Normalizar espacios
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _validate_dni(self, dni: str) -> Optional[str]:
        """Valida y extrae DNI de longitud configurada."""
        if not dni:
            return None
        # Extraer solo dígitos
        digits = re.sub(r'\D', '', dni)
        if len(digits) == DNI_LENGTH:
            return digits
        print(f"⚠️ DNI con longitud incorrecta: {len(digits)} dígitos, esperado {DNI_LENGTH}")
        return None

    def _validate_phone(self, phone: str) -> Optional[str]:
        """Valida y extrae teléfono de longitud configurada."""
        if not phone:
            return None
        # Extraer solo dígitos
        digits = re.sub(r'\D', '', phone)
        if len(digits) == PHONE_LENGTH:
            return digits
        print(f"⚠️ Teléfono con longitud incorrecta: {len(digits)} dígitos, esperado {PHONE_LENGTH}")
        return None

    def _validate_email(self, email: str) -> Optional[str]:
        """Validación básica de email."""
        if not email:
            return None
        email = email.strip().lower()
        # Patrón simple: algo@algo.algo
        if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            return email
        return None

    def on_content_end(self) -> None:
        """Fin de turno."""
        pass

    def on_session_end(self, session_id: str) -> Optional[str]:
        """Exporta lead al final de la sesión."""
        self.session_id = session_id
        if self.captured_lead:
            return self._export_lead()
        return None

    def _export_lead(self) -> str:
        """Exporta el lead capturado a JSON en carpeta dedicada."""
        # Crear carpeta de leads si no existe
        leads_folder = Path(LEADS_EXPORT_FOLDER)
        leads_folder.mkdir(exist_ok=True)
        
        timestamp = datetime.datetime.utcnow()
        # Usar timestamp más preciso para evitar colisiones
        filename = f"leads_session_{timestamp.strftime('%Y%m%d-%H%M%S')}_{uuid.uuid4().hex[:8]}.json"
        
        output = {
            "action": "store_and_handoff",
            "channel": "tool_use",
            "lead": self.captured_lead,
            "handoff": {
                "motivo": "alto_interes",
                "prioridad": "alta",
                "ventana_contacto": self.captured_lead.get("horario_preferido", "semana")
            },
            "_received_at": timestamp.isoformat() + "Z",
            "_session_id": self.session_id
        }
        
        filepath = leads_folder / filename
        filepath.write_text(json.dumps([output], indent=2, ensure_ascii=False), encoding="utf-8")
        
        # Log seguro sin PII completo
        safe_log = {
            'nombre': self.captured_lead.get('nombre_completo', 'N/A')[:20],
            'dni': mask_pii(self.captured_lead.get('dni') or ''),
            'telefono': mask_pii(self.captured_lead.get('telefono') or '')
        }
        print(f"\n✅ Lead exportado: {filepath.name} - {safe_log}")
        
        return str(filepath)

    def snapshot_lead(self) -> Dict:
        """Devuelve el estado actual del lead."""
        return self.captured_lead or {}
