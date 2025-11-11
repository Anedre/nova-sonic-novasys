"""Nova Sonic realtime manager rebuilt using official AWS bidirectional flows."""

from __future__ import annotations

import asyncio
import base64
import inspect
import json
import time
import uuid
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    # Prefer the modern namespace exposed by reactivex>=4
    from reactivex.subject import Subject
except ImportError:
    try:
        # Fallback kept for older environments that still expose the legacy alias
        from rx.subject import Subject
    except ImportError as e:
        raise ImportError(f"reactivex not installed: {e}. Run: pip install reactivex>=4.0.0")

try:
    from aws_sdk_bedrock_runtime.client import (
        BedrockRuntimeClient,
        InvokeModelWithBidirectionalStreamOperationInput
    )
    from aws_sdk_bedrock_runtime.models import (
        BidirectionalInputPayloadPart,
        InvokeModelWithBidirectionalStreamInputChunk
    )
    from aws_sdk_bedrock_runtime.config import Config
    from smithy_aws_core.identity.environment import EnvironmentCredentialsResolver
except ImportError as e:
    raise ImportError(
        f"AWS SDK not installed: {e}. "
        f"Run: pip install aws_sdk_bedrock_runtime==0.1.0"
    )

from processors.base import DataProcessor
from processors.tool_use_processor import ToolUseProcessor

from context.bootstrap import load_context_sources
from context.base import ContextSource
from context.file_prompt import FilePromptSource
from context.file_kb import FileKBSource

from config.constants import TOKEN_COST_INPUT, TOKEN_COST_OUTPUT, calculate_token_cost

INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000
CHANNELS = 1
PCM_SAMPLE_WIDTH = 2  # 16-bit PCM
DEBUG = os.getenv("NOVA_SONIC_DEBUG", "false").lower() in {"1", "true", "yes", "y"}

# Configuración de reintentos
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAYS = [1.0, 2.0, 4.0]  # Backoff exponencial en segundos


def debug_print(message: str) -> None:
    if DEBUG:
        print(f"[nova-sonic] {message}")


def is_transient_error(error: Exception) -> bool:
    """
    Determina si un error es transitorio y puede ser reintentado.
    
    Args:
        error: La excepción capturada
        
    Returns:
        True si el error es retryable, False si es permanente
    """
    error_str = str(error).lower()
    
    # Errores transitorios comunes de AWS Bedrock
    transient_patterns = [
        "unexpected error",
        "try your request again",
        "throttl",
        "timeout",
        "temporarily unavailable",
        "service unavailable",
        "internal error",
        "rate exceeded",
        "too many requests"
    ]
    
    return any(pattern in error_str for pattern in transient_patterns)


def discover_context_sources(
    context_config: Optional[str] = None,
    explicit_prompt: Optional[str] = None,
    explicit_kb: Optional[str] = None
) -> List[ContextSource]:
    if context_config:
        return load_context_sources(context_config)

    sources: List[ContextSource] = []
    if explicit_prompt:
        sources.append(FilePromptSource(explicit_prompt, vars={}))
    if explicit_kb:
        sources.append(FileKBSource(explicit_kb))

    if sources:
        return sources

    for candidate in (
        "./config/context.yaml",
        "./config/context.yml",
        "./config/context.json"
    ):
        if Path(candidate).exists():
            return load_context_sources(candidate)

    if Path("./udep_prompt.txt").exists():
        sources.append(FilePromptSource("./udep_prompt.txt", vars={}))
    for kb_candidate in (
        "./kb/udep_catalog.json",
        "./kb/udep_catalog.yaml",
        "./kb/udep_catalog.yml"
    ):
        if Path(kb_candidate).exists():
            sources.append(FileKBSource(kb_candidate))
            break

    if not sources:
        raise FileNotFoundError(
            "No hay contexto disponible. Crea ./udep_prompt.txt o configura ./config/context.yaml."
        )

    return sources


class NovaAgent:
    """Preserved for legacy callers."""

    def __init__(self, prompt_file: Optional[str] = None, kb_folder: Optional[str] = None) -> None:
        self.prompt_file = prompt_file
        self.kb_folder = kb_folder
        self.context_sources = discover_context_sources(
            explicit_prompt=prompt_file,
            explicit_kb=kb_folder
        )
        self.processor: DataProcessor = ToolUseProcessor()

    async def process_message(self, _message: str, callback=None):  # pragma: no cover
        raise NotImplementedError("NovaAgent no expone procesamiento directo en esta versión.")


def _parse_usage_metrics(metrics: Dict[str, Any], session_totals: Dict[str, int]) -> Optional[Dict[str, Any]]:
    """
    Función centralizada para parsear métricas de uso (performanceMetrics o usageEvent).
    
    Args:
        metrics: Diccionario con métricas del evento
        session_totals: Dict mutable con 'input' y 'output' para acumular tokens
    
    Returns:
        Dict con payload de uso formateado, o None si no se puede parsear
    """
    # Intentar extraer contadores de manera flexible
    input_tokens = (
        metrics.get("inputTokenCount")
        or metrics.get("inputTextTokenCount")
        or metrics.get("inputTokens")
        or 0
    )
    output_tokens = (
        metrics.get("outputTokenCount")
        or metrics.get("outputTextTokenCount")
        or metrics.get("outputTokens")
        or 0
    )
    
    # Convertir a int y acumular en totales de sesión
    input_tokens = int(input_tokens)
    output_tokens = int(output_tokens)
    
    if input_tokens == 0 and output_tokens == 0:
        return None  # Evento sin datos útiles
    
    session_totals["input"] += input_tokens
    session_totals["output"] += output_tokens
    
    total_tokens = session_totals["input"] + session_totals["output"]
    total_cost = calculate_token_cost(session_totals["input"], session_totals["output"])
    
    return {
        "inputTokens": session_totals["input"],
        "outputTokens": session_totals["output"],
        "totalTokens": total_tokens,
        "estimatedCostUsd": round(total_cost, 6)
    }


class BedrockStreamManager:
    """Coordinates the bidirectional Nova Sonic stream."""

    _DEFAULT_TOOL_SCHEMA = json.dumps(
        {
            "type": "object",
            "properties": {
                "nombre_completo": {"type": "string"},
                "dni": {"type": "string"},  # Validación relajada - limpiaremos en processor
                "telefono": {"type": "string"},  # Validación relajada - limpiaremos en processor
                "email": {"type": "string"},  # Validación relajada - limpiaremos en processor
                "programa_interes": {"type": "string"},
                "modalidad_preferida": {"type": "string"},
                "horario_preferido": {"type": "string"},
                "consentimiento": {"type": "string"}
            },
            "required": [
                "nombre_completo",
                "telefono",
                "email",
                "programa_interes",
                "modalidad_preferida",
                "consentimiento"
            ]
        }
    )

    DEFAULT_TOOL_SPEC: Dict[str, Any] = {
        "toolSpec": {
            "name": "guardar_lead",
            "description": (
                "Guarda los datos del prospecto cuando tienes TODOS los campos requeridos: "
                "nombre completo, DNI (8 dígitos exactos), teléfono (9 dígitos exactos), email, programa, "
                "modalidad, horario y consentimiento. VERIFICA que el teléfono tenga EXACTAMENTE 9 dígitos "
                "antes de llamar esta herramienta. Si tiene 8, pide el dígito faltante al usuario."
            ),
            "inputSchema": {"json": _DEFAULT_TOOL_SCHEMA},
        }
    }

    def __init__(
        self,
        *,
        context_sources: List[ContextSource],
        processor: Optional[DataProcessor] = None,
        model_id: str = "amazon.nova-sonic-v1:0",
        region: str = "us-east-1",
        voice_id: str = "lupe",
        prompt_name: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        debug_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        if not context_sources:
            raise ValueError("Debes proporcionar al menos un ContextSource")

        self.model_id = model_id
        self.region = region
        self.voice_id = voice_id
        self.prompt_name = prompt_name or f"prompt-{uuid.uuid4().hex}"
        self.session_id = str(uuid.uuid4())
        self.context_sources = context_sources
        self.processor: DataProcessor = processor or ToolUseProcessor()
        self.tool_specs = tools or [self.DEFAULT_TOOL_SPEC]

        self.bedrock_client: Optional[BedrockRuntimeClient] = None
        self.stream_response = None
        self.is_active = False

        self.output_subject: Subject = Subject()
        self.audio_output_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.audio_input_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()

        self._reader_task: Optional[asyncio.Task] = None
        self._audio_task: Optional[asyncio.Task] = None
        self._send_lock = asyncio.Lock()
        self._audio_send_clock: Optional[float] = None
        self._last_payload_sent: Optional[str] = None
        self._debug_callback = debug_callback
        self.audio_content_name: Optional[str] = None

        self._current_role = "ASSISTANT"
        self._current_content_type: Optional[str] = None
        self.display_assistant_text = True

        self._pending_tool_use: Optional[Dict[str, Any]] = None
        self.suppress_audio_until_content_end = False
        self.barge_in = False
        
        # Flag para esperar promptEnd antes de enviar audio
        self._prompt_ready = asyncio.Event()
        self._last_text_by_role = {"USER": None, "ASSISTANT": None}  # type: Dict[str, Optional[str]]
        self._last_emitted_role = None  # type: Optional[str]
        
        # Timing tracking para debug de latencia
        self._last_user_audio_end = None  # type: Optional[float]
        self._last_assistant_response_start = None  # type: Optional[float]
        
        # OPTIMIZACIÓN: Sistema de detección de pausas para enviar contentEnd automático
        self._last_audio_chunk_received = None  # type: Optional[float]
        self._silence_timeout = 0.8  # 800ms sin audio = usuario terminó de hablar
        self._turn_active = False  # Si hay un turno de usuario en progreso
        self._silence_monitor_task: Optional[asyncio.Task] = None
        
        # Acumuladores de uso (tokens) por sesión para costo total
        self._usage_totals = {"input": 0, "output": 0}  # type: Dict[str, int]
        
        # Sistema de reintentos para errores transitorios
        self._retry_count = 0
        self._is_reconnecting = False

    def _debug(self, message: str) -> None:
        if self._debug_callback:
            try:
                self._debug_callback(message)
            except Exception:
                pass
        debug_print(message)

    async def initialize_stream(self) -> "BedrockStreamManager":
        client = self._ensure_client()
        request = InvokeModelWithBidirectionalStreamOperationInput(model_id=self.model_id)
        self.stream_response = await client.invoke_model_with_bidirectional_stream(request)

        self.is_active = True
        await self._send_event(self._build_session_start_event())
        # OPTIMIZACIÓN: Sleeps eliminados - AWS SDK maneja backpressure automáticamente
        await self._send_event(self._build_prompt_start_event())
        await self._send_context_sources()
        # Algunos modelos no emiten promptEnd automáticamente; habilitamos audio después de enviar el contexto
        if not self._prompt_ready.is_set():
            self._debug("ℹ️ Contexto entregado, habilitando audio")
            self._prompt_ready.set()

        self._reader_task = asyncio.create_task(self._read_loop())
        
        # OPTIMIZACIÓN: Iniciar monitor de silencios para auto-enviar contentEnd
        self._silence_monitor_task = asyncio.create_task(self._monitor_silence())
        
        return self

    async def send_audio_content_start_event(self) -> None:
        """Envía contentStart para audio. Debe llamarse después de recibir promptEnd."""
        if not self.is_active:
            raise RuntimeError("La sesión todavía no está activa")
        
        # Esperar a que el modelo confirme que está listo (promptEnd recibido)
        self._debug("⏳ Esperando confirmación del modelo (promptEnd)...")
        try:
            await asyncio.wait_for(self._prompt_ready.wait(), timeout=10)
        except asyncio.TimeoutError:
            raise RuntimeError("Timeout esperando promptEnd del modelo")
        
        self._debug("✅ Modelo listo, enviando contentStart para audio")
        content_name = f"audio-{uuid.uuid4().hex}"
        self._audio_send_clock = None
        self.audio_content_name = content_name
        event = {
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name,
                    "contentName": content_name,
                    "type": "AUDIO",
                    "interactive": True,
                    "role": "USER",
                    "audioInputConfiguration": {
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": INPUT_SAMPLE_RATE,
                        "sampleSizeBits": PCM_SAMPLE_WIDTH * 8,
                        "channelCount": CHANNELS,
                        "audioType": "SPEECH",
                        "encoding": "base64"
                    }
                }
            }
        }
        await self._send_event(event)
        self._ensure_audio_task_started()

    def add_audio_chunk(self, audio_bytes: bytes) -> None:
        if not self.is_active or not audio_bytes:
            return
        
        # OPTIMIZACIÓN: Registrar timestamp de último audio recibido
        self._last_audio_chunk_received = time.time()
        if not self._turn_active:
            self._turn_active = True
            self._debug("🎤 Turno de usuario iniciado")
        
        try:
            self.audio_input_queue.put_nowait(audio_bytes)
        except asyncio.QueueFull:
            self._debug("Audio queue full, dropping chunk")

    async def send_system_message(self, text: str, role: str = "SYSTEM") -> None:
        if not text:
            return
        await self._send_text_block(text, role=role)

    async def _attempt_reconnection(self, delay: float) -> None:
        """
        Intenta reconectar el stream de Bedrock después de un error transitorio.
        
        Args:
            delay: Segundos a esperar antes de reconectar (backoff exponencial)
        """
        self._is_reconnecting = True
        self._debug(f"🔄 Iniciando reconexión en {delay}s...")
        
        # Esperar el delay de backoff
        await asyncio.sleep(delay)
        
        try:
            # Cancelar tareas existentes
            if self._reader_task and not self._reader_task.done():
                self._reader_task.cancel()
                try:
                    await self._reader_task
                except asyncio.CancelledError:
                    pass
            
            # Cerrar stream anterior si existe
            if self.stream_response:
                try:
                    await self.stream_response.input_stream.close()
                except Exception:
                    pass
                self.stream_response = None
            
            # Crear nuevo stream
            self._debug("🔌 Creando nuevo stream bidireccional...")
            client = self._ensure_client()
            request = InvokeModelWithBidirectionalStreamOperationInput(model_id=self.model_id)
            self.stream_response = await client.invoke_model_with_bidirectional_stream(request)
            
            # Re-enviar eventos de inicialización
            self._debug("📤 Re-enviando sesión y prompt...")
            await self._send_event(self._build_session_start_event())
            await self._send_event(self._build_prompt_start_event())
            
            # Re-enviar contexto
            self._debug("📚 Re-enviando fuentes de contexto...")
            await self._send_context_sources()
            
            # Reactivar el stream
            self.is_active = True
            
            # Resetear flag de prompt ready (esperaremos nuevo promptEnd)
            self._prompt_ready.clear()
            
            # Reiniciar reader task
            self._reader_task = asyncio.create_task(self._read_loop())
            
            self._debug("✅ Stream reconectado exitosamente")
            self._is_reconnecting = False
            
        except Exception as exc:
            self._is_reconnecting = False
            self._debug(f"❌ Error durante reconexión: {exc}")
            raise

    async def close(self) -> None:
        if not self.is_active:
            return

        self.is_active = False
        try:
            await self.audio_input_queue.put(None)
        except Exception:
            pass

        if self._audio_task:
            self._audio_task.cancel()
        if self._reader_task:
            self._reader_task.cancel()
        if self._silence_monitor_task:
            self._silence_monitor_task.cancel()

        try:
            await self.send_audio_content_end_event()
        except Exception:
            pass
        try:
            await self._send_prompt_end_event()
        except Exception:
            pass
        try:
            await self._send_session_end_event()
        except Exception:
            pass

        await self._await_task(self._audio_task)
        await self._await_task(self._reader_task)
        await self._await_task(self._silence_monitor_task)

        if self.stream_response:
            try:
                await self.stream_response.input_stream.close()
            except Exception:
                pass

        result = self.processor.on_session_end(self.session_id)
        if inspect.isawaitable(result):
            await result

        self.output_subject.on_completed()
        self.audio_content_name = None

    def _ensure_client(self) -> BedrockRuntimeClient:
        if not self.bedrock_client:
            config = Config(
                endpoint_uri=f"https://bedrock-runtime.{self.region}.amazonaws.com",
                region=self.region,
                aws_credentials_identity_resolver=EnvironmentCredentialsResolver()
            )
            self.bedrock_client = BedrockRuntimeClient(config=config)
        return self.bedrock_client

    def _build_session_start_event(self) -> Dict[str, Any]:
        return {
            "event": {
                "sessionStart": {
                    "sessionId": self.session_id,
                    "inferenceConfiguration": {
                        "maxTokens": 1024,
                        "topP": 0.9,
                        "temperature": 0.7
                    }
                }
            }
        }

    def _build_prompt_start_event(self) -> Dict[str, Any]:
        prompt: Dict[str, Any] = {
            "event": {
                "promptStart": {
                    "promptName": self.prompt_name,
                    "textOutputConfiguration": {"mediaType": "text/plain"},
                    "audioOutputConfiguration": {
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": OUTPUT_SAMPLE_RATE,
                        "sampleSizeBits": PCM_SAMPLE_WIDTH * 8,
                        "channelCount": CHANNELS,
                        "voiceId": self.voice_id,
                        "encoding": "base64",
                        "audioType": "SPEECH"
                    },
                    "toolUseOutputConfiguration": {"mediaType": "application/json"},
                    # Solicitar métricas de desempeño (tokens/costo) en tiempo real
                    "responseOutputConfiguration": {"performanceMetrics": "ENABLED"}
                }
            }
        }
        if self.tool_specs:
            prompt["event"]["promptStart"]["toolConfiguration"] = {"tools": self.tool_specs}
        return prompt

    async def _send_context_sources(self) -> None:
        grouped: Dict[str, List[str]] = {}
        for src in self.context_sources:
            role = getattr(src, "role", "SYSTEM") or "SYSTEM"
            try:
                rendered = src.render()
            except Exception as exc:
                self._debug(f"Context source error: {exc}")
                continue
            if not rendered:
                continue
            text = rendered.strip()
            if not text:
                continue
            grouped.setdefault(role.upper(), []).append(text)

        for role, fragments in grouped.items():
            if not fragments:
                continue
            if role == "SYSTEM" and len(fragments) > 1:
                await self._send_combined_text_block(role, fragments)
            else:
                for fragment in fragments:
                    self._debug(f"📚 Enviando contexto ({role}) len={len(fragment)}")
                    await self._send_text_block(fragment, role=role)
                    await asyncio.sleep(0.05)

    async def _send_combined_text_block(self, role: str, fragments: List[str]) -> None:
        content_name = f"text-{uuid.uuid4().hex}"
        start = {
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name,
                    "contentName": content_name,
                    "role": role,
                    "type": "TEXT",
                    "interactive": False,
                    "textInputConfiguration": {"mediaType": "text/plain"},
                }
            }
        }
        end = {
            "event": {
                "contentEnd": {
                    "promptName": self.prompt_name,
                    "contentName": content_name,
                }
            }
        }

        await self._send_event(start)
        # OPTIMIZACIÓN: Sleep eliminado - no necesario entre eventos
        for fragment in fragments:
            self._debug(f"📚 Enviando contexto combinado ({role}) len={len(fragment)}")
            body = {
                "event": {
                    "textInput": {
                        "promptName": self.prompt_name,
                        "contentName": content_name,
                        "content": fragment,
                    }
                }
            }
            await self._send_event(body)
            # OPTIMIZACIÓN: Sleep eliminado - no necesario entre eventos
        await self._send_event(end)
        # OPTIMIZACIÓN: Sleep eliminado - no necesario entre eventos

    async def _send_text_block(self, text: str, role: str) -> None:
        content_name = f"text-{uuid.uuid4().hex}"
        start = {
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name,
                    "contentName": content_name,
                    "role": role,
                    "type": "TEXT",
                    "interactive": False,
                    "textInputConfiguration": {"mediaType": "text/plain"}
                }
            }
        }
        body = {
            "event": {
                "textInput": {
                    "promptName": self.prompt_name,
                    "contentName": content_name,
                    "content": text
                }
            }
        }
        end = {
            "event": {
                "contentEnd": {
                    "promptName": self.prompt_name,
                    "contentName": content_name
                }
            }
        }
        await self._send_event(start)
        # OPTIMIZACIÓN: Sleep eliminado - no necesario entre eventos
        await self._send_event(body)
        # OPTIMIZACIÓN: Sleep eliminado - no necesario entre eventos
        await self._send_event(end)

    async def _send_event(self, payload: Dict[str, Any]) -> None:
        if not self.stream_response:
            raise RuntimeError("El stream bidireccional no está inicializado")
        data = json.dumps(payload)  # Removed ensure_ascii=True para mejor compatibilidad
        self._last_payload_sent = data
        chunk = InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(bytes_=data.encode("utf-8"))
        )
        event_keys = list(payload.get("event", {}).keys()) if isinstance(payload, dict) else []
        
        # Solo loggear eventos importantes, no audio chunks para reducir ruido
        if event_keys and "audioInput" not in event_keys:
            preview = data[:160]
            self._debug(f"→ Evento enviado ({event_keys}): {preview}")
        
        async with self._send_lock:
            await self.stream_response.input_stream.send(chunk)

    async def _drain_audio_queue(self) -> None:
        try:
            while True:
                chunk = await self.audio_input_queue.get()
                if chunk is None:
                    break
                await self._send_audio_chunk(chunk)
                await self._pace_audio_stream(len(chunk))
        except asyncio.CancelledError:
            pass
        finally:
            self._audio_send_clock = None

    async def _send_audio_chunk(self, audio_bytes: bytes) -> None:
        if not audio_bytes or not getattr(self, "audio_content_name", None):
            return
        blob = base64.b64encode(audio_bytes).decode("ascii")
        event = {
            "event": {
                "audioInput": {
                    "promptName": self.prompt_name,
                    "contentName": self.audio_content_name,
                    "content": blob
                }
            }
        }
        # No loggear cada audio chunk - genera ruido excesivo
        # self._debug(f"→ Audio chunk {len(audio_bytes)} bytes (b64 len {len(blob)})")
        await self._send_event(event)

    async def _pace_audio_stream(self, byte_count: int) -> None:
        # OPTIMIZACIÓN: Pacing desactivado - audio ya llega en tiempo real desde MediaRecorder
        # Nova Sonic puede procesar más rápido que tiempo real para reducir latencia
        # El navegador controla el timing con timeslice de MediaRecorder
        return
        
        # Código original comentado (causaba +100ms por chunk):
        # bytes_per_second = INPUT_SAMPLE_RATE * CHANNELS * PCM_SAMPLE_WIDTH
        # if bytes_per_second <= 0 or byte_count <= 0:
        #     return
        # duration = byte_count / bytes_per_second
        # now = time.monotonic()
        # target = self._audio_send_clock or now
        # if target < now:
        #     target = now
        # target += duration
        # self._audio_send_clock = target
        # delay = target - time.monotonic()
        # if delay > 0:
        #     await asyncio.sleep(min(delay, 0.1))

    async def _monitor_silence(self) -> None:
        """Monitor de silencios: envía contentEnd automático después de 800ms sin audio."""
        try:
            while self.is_active:
                await asyncio.sleep(0.1)  # Check cada 100ms
                
                if not self._turn_active or not self._last_audio_chunk_received:
                    continue
                
                silence_duration = time.time() - self._last_audio_chunk_received
                
                # Si llevamos más de 800ms sin audio, asumir que usuario terminó
                if silence_duration > self._silence_timeout:
                    self._turn_active = False
                    self._debug(f"🔇 Silencio detectado ({silence_duration:.2f}s), enviando señal de fin de turno")
                    
                    # Enviar señal interna de fin de turno (simular contentEnd del usuario)
                    # Esto permite que el modelo empiece a procesar sin esperar indefinidamente
                    try:
                        # Marcar timestamp para medir latencia
                        self._last_user_audio_end = time.time()
                        self._debug("📍 Fin de turno detectado automáticamente")
                        
                        # Llamar a on_content_end del processor
                        self.processor.on_content_end()
                        
                        # Resetear last_audio_chunk para evitar múltiples triggers
                        self._last_audio_chunk_received = None
                        
                    except Exception as exc:
                        self._debug(f"⚠️ Error enviando señal de fin de turno: {exc}")
                        
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self._debug(f"⚠️ Error en monitor de silencios: {exc}")

    # ------------------------------- tuning
    def set_silence_timeout(self, seconds: float) -> None:
        """Ajusta dinámicamente el tiempo de silencio para cierre automático de turno.

        Útil para acelerar la captura cuando se piden números (DNI/teléfono).
        """
        try:
            seconds = float(seconds)
        except Exception:
            return
        # Limitar a un rango razonable
        seconds = max(0.3, min(seconds, 2.0))
        if abs(self._silence_timeout - seconds) >= 0.05:
            self._silence_timeout = seconds
            self._debug(f"🛠️ Silence timeout ajustado a {self._silence_timeout:.2f}s")

    async def _read_loop(self) -> None:
        try:
            while self.is_active and self.stream_response:
                try:
                    output = await self.stream_response.await_output()
                    message = await output[1].receive()
                except StopAsyncIteration:
                    break
                if not message or not message.value or not message.value.bytes_:
                    continue
                raw = message.value.bytes_.decode("utf-8")
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    self.output_subject.on_next({"raw": raw})
                    continue
                await self._handle_model_payload(payload)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            error_msg = str(exc)
            self._debug(
                f"Falla leyendo stream: {error_msg} | último evento enviado: {self._last_payload_sent[:120] if self._last_payload_sent else 'N/A'}"
            )
            
            # Verificar si es un error transitorio y si podemos reintentar
            if is_transient_error(exc) and self._retry_count < MAX_RETRY_ATTEMPTS:
                self._retry_count += 1
                delay = RETRY_DELAYS[min(self._retry_count - 1, len(RETRY_DELAYS) - 1)]
                
                self._debug(f"🔄 Error transitorio detectado. Reintento {self._retry_count}/{MAX_RETRY_ATTEMPTS} en {delay}s")
                
                # Emitir evento de reconexión al frontend
                self.output_subject.on_next({
                    "event": {
                        "streamReconnecting": {
                            "attempt": self._retry_count,
                            "maxAttempts": MAX_RETRY_ATTEMPTS,
                            "delaySeconds": delay,
                            "reason": error_msg
                        }
                    }
                })
                
                # Intentar reconexión
                try:
                    await self._attempt_reconnection(delay)
                    self._debug(f"✅ Reconexión exitosa (intento {self._retry_count})")
                    
                    # Emitir evento de reconexión exitosa
                    self.output_subject.on_next({
                        "event": {
                            "streamReconnected": {
                                "attempt": self._retry_count
                            }
                        }
                    })
                    
                    # Resetear contador de reintentos tras éxito
                    self._retry_count = 0
                    return  # Salir del loop actual, se reiniciará automáticamente
                    
                except Exception as retry_exc:
                    self._debug(f"❌ Fallo reintento {self._retry_count}: {retry_exc}")
                    
                    # Si aún quedan intentos, el loop continuará
                    if self._retry_count < MAX_RETRY_ATTEMPTS:
                        return  # Reintentar de nuevo
                    else:
                        # Sin más reintentos, propagar error
                        self._debug(f"💀 Agotados {MAX_RETRY_ATTEMPTS} reintentos. Error permanente.")
                        self.output_subject.on_next({
                            "event": {
                                "streamError": {
                                    "fatal": True,
                                    "reason": f"Fallo después de {MAX_RETRY_ATTEMPTS} reintentos: {error_msg}"
                                }
                            }
                        })
                        self.output_subject.on_error(exc)
            else:
                # Error no retryable o se agotaron reintentos
                if self._retry_count >= MAX_RETRY_ATTEMPTS:
                    self._debug(f"💀 Sin más reintentos disponibles")
                else:
                    self._debug(f"❌ Error no retryable: {error_msg}")
                
                self.output_subject.on_next({
                    "event": {
                        "streamError": {
                            "fatal": True,
                            "reason": error_msg
                        }
                    }
                })
                self.output_subject.on_error(exc)
        finally:
            self.is_active = False

    async def _handle_model_payload(self, payload: Dict[str, Any]) -> None:
        if "error" in payload:
            details = payload.get("error")
            if isinstance(details, dict):
                try:
                    rendered = json.dumps(details, ensure_ascii=False)
                except (TypeError, ValueError):
                    rendered = str(details)
            else:
                rendered = str(details)
            last_event_preview = self._last_payload_sent[:120] if self._last_payload_sent else "N/A"
            self._debug(
                f"Bedrock error recibido: {rendered} | último evento enviado: {last_event_preview}"
            )
            self.output_subject.on_next(payload)
            return
        event = payload.get("event")
        if not event:
            self.output_subject.on_next(payload)
            return

        # Logear claves de eventos para depuración de métricas/uso
        try:
            self._debug(f"🧩 Evento recibido: keys={list(event.keys())}")
        except Exception:
            pass

        if "promptEnd" in event:
            # El modelo confirma que el prompt está listo
            self._debug("✅ Recibido promptEnd - modelo listo para audio")
            self._prompt_ready.set()

        elif "contentStart" in event:
            content = event["contentStart"]
            self._current_role = content.get("role", self._current_role)
            self._current_content_type = content.get("type")
            
            # Log de inicio de respuesta del asistente
            if self._current_role == "ASSISTANT" and self._last_user_audio_end:
                latency = time.time() - self._last_user_audio_end
                self._debug(f"⏱️ LATENCIA: {latency:.2f}s desde fin audio usuario hasta contentStart asistente")
                self._last_assistant_response_start = time.time()
                
                # OPTIMIZACIÓN: Resetear estado de turno cuando asistente responde
                self._turn_active = False
            
            additional = content.get("additionalModelFields")
            if isinstance(additional, str):
                try:
                    fields = json.loads(additional)
                    stage = fields.get("generationStage")
                    self.display_assistant_text = stage not in {"SPECULATIVE", "DRAFT"}
                except json.JSONDecodeError:
                    pass

        elif "contentEnd" in event:
            content = event["contentEnd"]
            content_type = content.get("type")
            
            # Log de fin de audio del usuario
            if content_type == "AUDIO" and self._current_role == "USER":
                self._last_user_audio_end = time.time()
                self._debug("📍 Usuario terminó de hablar (contentEnd AUDIO)")
            
            if content_type == "AUDIO":
                self.processor.on_content_end()
            if content_type == "TOOL":
                await self._execute_pending_tool()
            self.suppress_audio_until_content_end = False

        elif "textOutput" in event:
            text = event["textOutput"].get("content", "")
            if not text:
                self.output_subject.on_next(payload)
                return
            normalized = self._normalize_text(text)
            # Filtrar mensajes de control que vienen como JSON embebido (p.ej. {"interrupted": true})
            ctrl = normalized.strip()
            if (ctrl.startswith("{") and ctrl.endswith("}")):
                try:
                    ctrl_obj = json.loads(ctrl)
                    if any(k in ctrl_obj for k in ("interrupted", "bargeIn", "stopped", "segment")):
                        self._debug("⏭️ Mensaje de control (JSON) omitido en transcript")
                        return
                except Exception:
                    pass
            # También filtrar strings de control simples
            if "\"interrupted\"" in ctrl or ctrl.lower() == "interrupted":
                self._debug("⏭️ Señal 'interrupted' omitida en transcript")
                return
            if self._current_role == "ASSISTANT":
                # Filtro más robusto: comparar con último texto ASSISTANT sin importar rol intermedio
                last_assistant = self._last_text_by_role.get("ASSISTANT")
                if normalized and last_assistant and normalized == last_assistant:
                    self._debug("🔁 Texto del asistente repetido, se omite")
                    return
                if self.processor.maybe_capture_action(text):
                    self.suppress_audio_until_content_end = True
                    self.barge_in = True
                else:
                    self.processor.on_assistant_text(text)
                    if normalized:
                        self._last_text_by_role["ASSISTANT"] = normalized
                        self._last_emitted_role = "ASSISTANT"
            elif self._current_role == "USER":
                # Filtro más robusto: comparar con último texto USER sin importar rol intermedio
                last_user = self._last_text_by_role.get("USER")
                if normalized and last_user and normalized == last_user:
                    self._debug("🔁 Texto del usuario repetido, se omite")
                    return
                self.processor.on_user_text(text)
                if normalized:
                    self._last_text_by_role["USER"] = normalized
                    self._last_emitted_role = "USER"

        elif "audioOutput" in event:
            if not self.suppress_audio_until_content_end:
                audio_b64 = event["audioOutput"].get("content")
                if audio_b64:
                    # Log del primer chunk de audio de respuesta
                    if self._last_assistant_response_start:
                        tts_latency = time.time() - self._last_assistant_response_start
                        self._debug(f"⏱️ TTS: {tts_latency:.2f}s desde contentStart hasta primer audioOutput")
                        self._last_assistant_response_start = None  # Solo log una vez
                    
                    audio_bytes = base64.b64decode(audio_b64)
                    await self.audio_output_queue.put(audio_bytes)

        elif "toolUse" in event:
            self._pending_tool_use = event["toolUse"]

        elif "performanceMetrics" in event:
            # Capturar métricas de uso (tokens y costos) usando función centralizada
            metrics = event["performanceMetrics"]
            self._debug(f"📊 Métricas recibidas: {metrics}")
            
            usage_payload = _parse_usage_metrics(metrics, self._usage_totals)
            if usage_payload and hasattr(self.processor, 'on_usage_update'):
                self.processor.on_usage_update(usage_payload)

        elif "usageEvent" in event:
            # Variante nueva de métricas de uso - usar la misma función centralizada
            metrics = event["usageEvent"]
            self._debug(f"📊 usageEvent: {metrics}")
            
            usage_payload = _parse_usage_metrics(metrics, self._usage_totals)
            if usage_payload and hasattr(self.processor, 'on_usage_update'):
                self.processor.on_usage_update(usage_payload)

        self.output_subject.on_next(payload)

    @staticmethod
    def _normalize_text(text: str) -> str:
        stripped = text.strip()
        if not stripped:
            return ""
        return " ".join(stripped.split())

    async def _execute_pending_tool(self) -> None:
        if not self._pending_tool_use:
            return
        tool_use = self._pending_tool_use
        self._pending_tool_use = None

        tool_name = tool_use.get("toolName")
        tool_input_raw = tool_use.get("content", {})
        tool_use_id = tool_use.get("toolUseId")

        # Parsear tool_input si viene como string JSON
        if isinstance(tool_input_raw, str):
            try:
                tool_input = json.loads(tool_input_raw)
                self._debug(f"🔧 Tool input parseado de string JSON: {tool_input}")
            except json.JSONDecodeError as e:
                self._debug(f"❌ Error parseando tool_input JSON: {e}")
                tool_input = {}
        else:
            tool_input = tool_input_raw

        self._debug(f"🔧 Ejecutando tool: {tool_name} con input: {tool_input}")

        try:
            result = self.processor.handle_tool_use(tool_name, tool_input)
            if inspect.isawaitable(result):
                result = await result
            self._debug(f"✅ Tool ejecutado exitosamente: {result}")
        except Exception as exc:
            self._debug(f"❌ Error ejecutando tool: {exc}")
            result = {"status": "error", "message": str(exc)}

        await self._send_tool_result(tool_use_id, result)

    async def _send_tool_result(self, tool_use_id: Optional[str], result: Any) -> None:
        if not tool_use_id:
            return
        content_name = f"tool-{uuid.uuid4().hex}"
        start = {
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name,
                    "contentName": content_name,
                    "type": "TOOL",
                    "role": "TOOL",
                    "toolResultInputConfiguration": {
                        "toolUseId": tool_use_id,
                        "type": "TEXT",
                        "textInputConfiguration": {"mediaType": "text/plain"}
                    }
                }
            }
        }
        if isinstance(result, str):
            payload = result
        else:
            payload = json.dumps(result, ensure_ascii=False)
        body = {
            "event": {
                "toolResult": {
                    "promptName": self.prompt_name,
                    "contentName": content_name,
                    "content": payload
                }
            }
        }
        end = {
            "event": {
                "contentEnd": {
                    "promptName": self.prompt_name,
                    "contentName": content_name
                }
            }
        }
        await self._send_event(start)
        await self._send_event(body)
        await self._send_event(end)

    async def send_audio_content_end_event(self) -> None:
        if not getattr(self, "audio_content_name", None):
            return
        event = {
            "event": {
                "contentEnd": {
                    "promptName": self.prompt_name,
                    "contentName": self.audio_content_name
                }
            }
        }
        await self._send_event(event)
        self.audio_content_name = None

    async def _send_prompt_end_event(self) -> None:
        event = {"event": {"promptEnd": {"promptName": self.prompt_name}}}
        await self._send_event(event)

    async def _send_session_end_event(self) -> None:
        await self._send_event({"event": {"sessionEnd": {}}})

    def _ensure_audio_task_started(self) -> None:
        if self._audio_task and not self._audio_task.done():
            return
        if not self.is_active:
            return
        self._audio_task = asyncio.create_task(self._drain_audio_queue())

    @staticmethod
    async def _await_task(task: Optional[asyncio.Task]) -> None:
        if task is None:
            return
        try:
            await asyncio.gather(task, return_exceptions=True)
        except Exception:
            pass


__all__ = ["BedrockStreamManager", "discover_context_sources", "NovaAgent"]
