"""Threaded adapter that exposes Nova Sonic to the Flask-SocketIO backend."""

from __future__ import annotations

import asyncio
import base64
import datetime
import json
import os
import queue
import re
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Optional
from collections import deque

_FFMPEG_EXE = "ffmpeg"

# Límites de buffer para prevenir OOM
DECODER_MAX_BUFFER_BYTES = 4 * 1024 * 1024  # 4MB max buffer de entrada
AUDIO_INPUT_QUEUE_MAX_SIZE = 50  # Máximo 50 chunks PCM en cola (~5 segundos)


class _StreamingAudioDecoder:
    """Decodifica audio WebM/Opus usando pipe a FFmpeg para streaming continuo."""

    def __init__(self, fmt: str, target_rate: int = 16000, logger: Optional[Callable[[str], None]] = None) -> None:
        self._fmt = fmt
        self._target_rate = target_rate
        self._logger = logger
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=AUDIO_INPUT_QUEUE_MAX_SIZE)  # Backpressure
        self._lock = threading.Lock()
        
        # Acumular chunks hasta tener suficiente data para iniciar FFmpeg
        self._buffer = bytearray()
        self._ffmpeg_process: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._writer_thread: Optional[threading.Thread] = None
        self._stop_flag = False
        self._first_pcm_logged = False
        self._started = False
        self._chunks_received = 0  # Contador de chunks recibidos
        self._first_chunk_time: Optional[float] = None  # Timestamp del primer chunk
        
        if logger:
            logger(f"🎛️ Decoder creado (streaming pipe)")

    def feed(self, data: bytes) -> None:
        """Acumula chunks y los envía a FFmpeg cuando esté listo."""
        if not data or self._stop_flag:
            return
        
        # Registrar el primer chunk
        if self._chunks_received == 0:
            self._first_chunk_time = time.time()
        
        self._chunks_received += 1
        
        with self._lock:
            # Límite de buffer para prevenir OOM
            if len(self._buffer) + len(data) > DECODER_MAX_BUFFER_BYTES:
                if self._logger:
                    self._logger(f"⚠️ Buffer lleno ({len(self._buffer)} bytes), descartando chunk de {len(data)} bytes")
                return
            
            self._buffer.extend(data)
            buffer_size = len(self._buffer)
        
        # Detectar si tenemos un header EBML válido en el buffer
        has_valid_header = False
        if buffer_size >= 4:
            with self._lock:
                first_bytes = bytes(self._buffer[:4])
            has_valid_header = (first_bytes == b'\x1a\x45\xdf\xa3')
        
        # Log solo para los primeros chunks
        if not self._started and self._chunks_received <= 3:
            if len(data) >= 4:
                chunk_header = data[:4]
                # Calcular si el chunk tiene variación (no es silencio puro)
                chunk_variance = self._calculate_variance(data[:min(1024, len(data))])
                if self._logger:
                    if chunk_header == b'\x1a\x45\xdf\xa3':
                        self._logger(f"🔍 ✅ Chunk {self._chunks_received} con header EBML válido ({len(data)} bytes, varianza={chunk_variance:.2f})")
                    else:
                        self._logger(f"🔍 ⚠️ Chunk {self._chunks_received} sin header EBML: {chunk_header.hex()[:16]} ({len(data)} bytes, varianza={chunk_variance:.2f})")
        
        # Estrategia: esperar a tener header válido + mínimo 16KB O esperar 2 segundos máximo
        time_elapsed = time.time() - self._first_chunk_time if self._first_chunk_time else 0
        min_size_met = buffer_size >= 16384
        has_header_and_size = has_valid_header and min_size_met
        timeout_fallback = time_elapsed > 2.0 and buffer_size >= 8192
        
        # Iniciar FFmpeg cuando se cumplan las condiciones
        if not self._started and (has_header_and_size or timeout_fallback):
            if timeout_fallback and not has_valid_header:
                if self._logger:
                    self._logger(f"⚠️ Timeout alcanzado sin header válido, intentando de todas formas con {buffer_size} bytes...")
            self._start_ffmpeg()
        
        # Si FFmpeg ya está corriendo, enviar datos acumulados
        elif self._started and self._ffmpeg_process and buffer_size > 0:
            self._feed_to_ffmpeg()
    
    def _calculate_variance(self, data: bytes) -> float:
        """Calcula la varianza de los bytes para detectar si hay señal real."""
        if not data:
            return 0.0
        values = list(data)
        if not values:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance

    def _start_ffmpeg(self) -> None:
        """Inicia el proceso FFmpeg con pipe de entrada."""
        if self._started:
            return
        
        # Capturar tamaño del buffer ANTES de marcarlo como started
        with self._lock:
            buffer_size = len(self._buffer)
            header = bytes(self._buffer[:20]) if len(self._buffer) >= 20 else bytes(self._buffer)
        
        # Validar que tenemos suficientes datos
        if buffer_size < 4096:
            if self._logger:
                self._logger(f"⚠️ Buffer muy pequeño ({buffer_size} bytes), esperando más datos...")
            return
        
        # Verificar header WebM (EBML magic: 0x1A 0x45 0xDF 0xA3)
        has_valid_header = (len(header) >= 4 and header[0:4] == b'\x1a\x45\xdf\xa3')
        
        if not has_valid_header:
            if self._logger:
                self._logger(f"⚠️ Header EBML no detectado en buffer ({header[:8].hex()})")
                self._logger(f"   Intentando procesar de todas formas con {buffer_size} bytes...")
        else:
            if self._logger:
                self._logger(f"✅ Header EBML válido confirmado ({buffer_size} bytes)")
        
        self._started = True
        
        # Detectar formato correcto basado en el mime type original
        # - audio/ogg → formato "ogg" de FFmpeg
        # - audio/webm → formato "matroska" (WebM es variante de Matroska)
        if self._fmt.lower() == "ogg":
            format_hint = "ogg"
        else:
            format_hint = "matroska"  # WebM es una variante de Matroska
        
        if self._logger:
            self._logger(f"🎛️ Usando formato FFmpeg: {format_hint} (mime: {self._fmt})")
        
        # Args ultra-permisivos: ignorar errores de formato
        args = [
            _FFMPEG_EXE,
            "-loglevel", "warning",
            "-f", format_hint,
            "-fflags", "+genpts+igndts+ignidx+discardcorrupt",  # ignorar corrupción
            "-err_detect", "ignore_err",    # ignorar todos los errores de stream
            "-i", "pipe:0",                 # leer desde stdin
            "-acodec", "pcm_s16le",
            "-ac", "1",
            "-ar", str(self._target_rate),
            "-f", "s16le",
            "pipe:1",                       # escribir a stdout
        ]
        
        try:
            # En Windows, evitar ventana emergente
            popen_kwargs = {
                "stdin": subprocess.PIPE,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
                "bufsize": 0,  # Sin buffer
            }
            if os.name == "nt":
                popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            
            self._ffmpeg_process = subprocess.Popen(args, **popen_kwargs)
            
            if self._logger:
                self._logger(f"🎛️ FFmpeg iniciado con {buffer_size} bytes acumulados")
            
            # Thread para leer PCM output
            self._reader_thread = threading.Thread(target=self._read_pcm_output, daemon=True)
            self._reader_thread.start()
            
            # Thread para escribir WebM input
            self._writer_thread = threading.Thread(target=self._write_webm_input, daemon=True)
            self._writer_thread.start()
            
            # Thread para monitorear stderr de FFmpeg
            self._stderr_thread = threading.Thread(target=self._monitor_stderr, daemon=True)
            self._stderr_thread.start()
                
        except Exception as e:
            if self._logger:
                self._logger(f"❌ Error iniciando FFmpeg: {e}")
            self._started = False
            self._ffmpeg_process = None

    def _feed_to_ffmpeg(self) -> None:
        """Señala al writer thread que hay datos nuevos disponibles."""
        pass  # El writer thread lee continuamente del buffer

    def _monitor_stderr(self) -> None:
        """Thread que monitorea stderr de FFmpeg para errores."""
        if not self._ffmpeg_process or not self._ffmpeg_process.stderr:
            return
        
        try:
            for line in self._ffmpeg_process.stderr:
                if self._stop_flag:
                    break
                msg = line.decode('utf-8', errors='ignore').strip()
                if msg and self._logger:
                    # Solo loguear errores importantes
                    if any(kw in msg.lower() for kw in ['error', 'invalid', 'failed', 'could not']):
                        self._logger(f"⚠️ FFmpeg stderr: {msg[:200]}")
        except Exception:
            pass

    def _write_webm_input(self) -> None:
        """Thread que escribe datos WebM al stdin de FFmpeg."""
        if not self._ffmpeg_process or not self._ffmpeg_process.stdin:
            return
            
        try:
            # Enviar datos iniciales acumulados
            with self._lock:
                initial_data = bytes(self._buffer)
                self._buffer.clear()
            
            if initial_data and self._ffmpeg_process.poll() is None:
                try:
                    self._ffmpeg_process.stdin.write(initial_data)
                    self._ffmpeg_process.stdin.flush()
                except (BrokenPipeError, OSError) as e:
                    if self._logger:
                        self._logger(f"⚠️ No se pudo escribir datos iniciales: {e}")
                    return
            
            # Continuar enviando datos nuevos
            while not self._stop_flag and self._ffmpeg_process:
                # Verificar que FFmpeg sigue corriendo
                if self._ffmpeg_process.poll() is not None:
                    if self._logger:
                        self._logger("⚠️ FFmpeg terminó inesperadamente")
                    break
                
                time.sleep(0.05)  # 50ms entre escrituras
                
                with self._lock:
                    if len(self._buffer) > 0:
                        chunk = bytes(self._buffer)
                        self._buffer.clear()
                    else:
                        continue
                
                try:
                    self._ffmpeg_process.stdin.write(chunk)
                    self._ffmpeg_process.stdin.flush()
                except (BrokenPipeError, OSError) as e:
                    if self._logger:
                        self._logger(f"⚠️ Pipe roto al escribir: {e}")
                    break
                    
        except Exception as e:
            if self._logger and not self._stop_flag:
                self._logger(f"⚠️ Error escribiendo a FFmpeg: {e}")
        finally:
            if self._ffmpeg_process and self._ffmpeg_process.stdin:
                try:
                    self._ffmpeg_process.stdin.close()
                except:
                    pass
                    pass

    def _read_pcm_output(self) -> None:
        """Thread que lee PCM desde stdout de FFmpeg."""
        if not self._ffmpeg_process or not self._ffmpeg_process.stdout:
            return
            
        chunk_size = 3200  # ~100ms @ 16kHz
        start_time = time.time()
        first_output_received = False
        total_pcm_bytes = 0
        silent_chunks = 0
        non_silent_chunks = 0
        
        try:
            while not self._stop_flag and self._ffmpeg_process:
                # Timeout de 5 segundos para el primer chunk
                if not first_output_received and (time.time() - start_time) > 5.0:
                    if self._logger:
                        self._logger("❌ FFmpeg timeout: no produjo output en 5s, posible problema con codec")
                    break
                
                pcm_chunk = self._ffmpeg_process.stdout.read(chunk_size)
                
                if not pcm_chunk:
                    break
                
                if not first_output_received:
                    first_output_received = True
                    if self._logger:
                        self._logger("🔊 FFmpeg produciendo PCM correctamente")
                
                total_pcm_bytes += len(pcm_chunk)
                
                # Verificar si el chunk es silencio puro
                is_silent = all(b == 0 for b in pcm_chunk[:min(100, len(pcm_chunk))])
                if is_silent:
                    silent_chunks += 1
                else:
                    non_silent_chunks += 1
                
                if not self._first_pcm_logged and self._logger:
                    variance = self._calculate_variance(pcm_chunk[:min(1024, len(pcm_chunk))])
                    self._logger(f"🔊 PCM generado: {len(pcm_chunk)} bytes (varianza={variance:.2f}, {'SILENCIO' if is_silent else 'CON AUDIO'})")
                    self._first_pcm_logged = True
                
                # Backpressure: bloquear si la cola está llena (timeout 1s)
                try:
                    self._queue.put(pcm_chunk, timeout=1.0)
                except queue.Full:
                    if self._logger:
                        self._logger(f"⚠️ Cola PCM llena, descartando chunk (backpressure activado)")
                    continue
                
            # Log final de estadísticas
            if self._logger and total_pcm_bytes > 0:
                self._logger(f"📊 PCM stats: {total_pcm_bytes} bytes total, {non_silent_chunks} chunks con audio, {silent_chunks} silencios")
                
        except Exception as e:
            if self._logger and not self._stop_flag:
                self._logger(f"⚠️ Error leyendo PCM de FFmpeg: {e}")

    def flush_buffer(self) -> None:
        """Forzar envío de datos restantes a FFmpeg."""
        pass

    def read(self) -> bytes:
        """Lee PCM decodificado disponible."""
        chunks: list[bytes] = []
        while True:
            try:
                chunk = self._queue.get_nowait()
            except queue.Empty:
                break
            if chunk:
                chunks.append(chunk)
        return b"".join(chunks)

    def close(self) -> None:
        """Limpia recursos."""
        self._stop_flag = True
        
        # Cerrar proceso FFmpeg
        if self._ffmpeg_process:
            try:
                if self._ffmpeg_process.stdin:
                    self._ffmpeg_process.stdin.close()
                self._ffmpeg_process.terminate()
                self._ffmpeg_process.wait(timeout=2)
            except Exception:
                if self._ffmpeg_process:
                    try:
                        self._ffmpeg_process.kill()
                    except:
                        pass
        
        # Esperar threads
        if self._writer_thread and self._writer_thread.is_alive():
            self._writer_thread.join(timeout=1)
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1)


from nova_sonic_es_sd import BedrockStreamManager, discover_context_sources
from processors.base import DataProcessor
from processors.tool_use_processor import ToolUseProcessor


class _WebAdapterProcessor(DataProcessor):
    """Adapter that forwards text to the UI while delegating lead logic."""

    def __init__(
        self,
        delegate: DataProcessor,
        on_user_text: Optional[Callable[[str], None]],
        on_assistant_text: Optional[Callable[[str], None]],
        on_lead_snapshot: Optional[Callable[[dict], None]],
        on_session_summary: Optional[Callable[[dict], None]],
        send_coach: Optional[Callable[[str], None]] = None,
        on_usage_update: Optional[Callable[[dict], None]] = None,
        adjust_silence_timeout: Optional[Callable[[float], None]] = None,
    ) -> None:
        self._delegate = delegate
        self._on_user_text = on_user_text
        self._on_assistant_text = on_assistant_text
        self._on_lead_snapshot = on_lead_snapshot
        self._on_session_summary = on_session_summary
        self._on_usage_update = on_usage_update
        self._adjust_silence_timeout = adjust_silence_timeout
        self._skip_next_maybe = False
        self._last_suppress = False
        self._last_snapshot_sig: Optional[str] = None
        self._send_coach = send_coach
        self._last_coach_key: Optional[tuple[str, tuple[str, ...]]] = None
        self._last_coach_at: Optional[datetime.datetime] = None
        self._coach_cooldown_seconds: float = 6.0
        self._last_user_text = None  # type: Optional[str]
        self._last_assistant_text = None  # type: Optional[str]
        self._last_emitted_role = None  # type: Optional[str]
        # Mantener historial reciente para deduplicación temporal
        self._recent_assistant = deque(maxlen=20)  # list of (timestamp, normalized_text)
        self._greeted_once = False
        self._user_turn_id = 0
        # Control dinámico del VAD: umbral por defecto y cache del valor aplicado
        self._default_silence_timeout = 0.8
        self._fast_silence_timeout = 0.5
        self._current_silence_timeout: Optional[float] = None

    def set_adjust_silence_timeout(self, cb: Optional[Callable[[float], None]]) -> None:
        """Permite inyectar el callback una vez que el manager exista."""
        self._adjust_silence_timeout = cb

    def _is_recent_duplicate(self, normalized: str, window_secs: float = 10.0) -> bool:
        now = datetime.datetime.utcnow().timestamp()
        for ts, msg in list(self._recent_assistant):
            if msg == normalized and (now - ts) <= window_secs:
                return True
        return False

    def _remember_assistant(self, normalized: str) -> None:
        ts = datetime.datetime.utcnow().timestamp()
        self._recent_assistant.append((ts, normalized))
    
    def _maybe_adjust_silence_timeout(self, assistant_text: str) -> None:
        """Reduce temporalmente el timeout de silencio cuando el asistente pide DNI/teléfono.

        - Baja a 0.5s al detectar solicitud de datos numéricos.
        - Restaura a 0.8s en otros mensajes.
        """
        if not self._adjust_silence_timeout:
            return
        text = (assistant_text or "").lower()
        # Heurística simple para detectar pedido de DNI o teléfono
        asks_number = bool(re.search(r"\b(dni|documento\s+de\s+identidad|n[uú]mero\s+de\s+documento)\b", text))
        asks_phone = bool(re.search(r"\b(tel[eé]fono|celular|n[uú]mero\s+de\s+contacto|n[uú]mero\s+de\s+celular)\b", text))
        wants_fast = asks_number or asks_phone
        target = self._fast_silence_timeout if wants_fast else self._default_silence_timeout
        if self._current_silence_timeout == target:
            return
        self._current_silence_timeout = target
        self._adjust_silence_timeout(target)
    
    def handle_tool_use(self, tool_name: str, tool_input: dict) -> dict:
        """Delega tool use al processor interno."""
        return self._delegate.handle_tool_use(tool_name, tool_input)

    def _emit_snapshot(self, reason: str, force: bool = False) -> None:
        if not self._on_lead_snapshot:
            return
        snapshot = self._delegate.snapshot_lead()
        signature = json.dumps(snapshot, sort_keys=True, ensure_ascii=False)
        if not force and signature == self._last_snapshot_sig:
            return
        self._last_snapshot_sig = signature
        payload = {
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "reason": reason,
            "lead": snapshot,
        }
        try:
            self._on_lead_snapshot(payload)
        except Exception:
            pass

    def on_user_text(self, text: str) -> None:  # noqa: D401
        self._delegate.on_user_text(text)
        self._last_coach_key = None
        # Avanza el contador de turno de usuario; así evitamos repetir prompts del mismo bloque
        self._user_turn_id += 1
        
        # Detectar si el usuario intenta cerrar (antes de que Nova responda)
        text_lower = text.lower()
        user_closing_trigger = re.search(
            r"\b(eso sería todo|eso seria todo|ya está|ya esta|nada más|nada mas|gracias|chau|adiós|adios)\b",
            text_lower
        )
        
        if user_closing_trigger:
            # Verificar si faltan datos críticos
            lead = self._delegate.snapshot_lead()
            confirmed = lead.get("confirmed", {})
            missing_critical = []
            
            if not confirmed.get("nombre_completo"):
                missing_critical.append("nombre_completo")
            if not confirmed.get("telefono"):
                missing_critical.append("telefono")
            if not confirmed.get("modalidad_preferida"):
                missing_critical.append("modalidad_preferida")
            
            # Enviar coach preventivo si faltan datos
            if missing_critical:
                self._issue_coach(missing_critical, "closing")
        
        self._emit_snapshot("user_text")
        if self._on_user_text:
            normalized = text.strip()
            if normalized and normalized == self._last_user_text:
                return
            if normalized:
                self._last_user_text = normalized
                self._last_emitted_role = "USER"
            try:
                self._on_user_text(text)
            except Exception:
                pass

    def on_assistant_text(self, text: str) -> None:  # noqa: D401
        suppress = self._delegate.maybe_capture_action(text)
        self._last_suppress = suppress
        self._skip_next_maybe = True
        if suppress:
            self._emit_snapshot("captured_action", force=True)
            return
        self._delegate.on_assistant_text(text)
        self._emit_snapshot("assistant_text")
        self._maybe_inject_coach(text)
        # Ajuste dinámico del timeout de silencio para capturas numéricas (DNI/teléfono)
        try:
            self._maybe_adjust_silence_timeout(text)
        except Exception:
            # No bloquear la conversación por este ajuste heurístico
            pass
        if self._on_assistant_text:
            normalized = text.strip()
            if normalized:
                lower = normalized.lower()
                # Suprimir saludos repetidos tipo "Hola, soy Zhenia ..."
                if "hola" in lower and "soy zhenia" in lower:
                    if self._greeted_once:
                        return
                    self._greeted_once = True
                
                # Suprimir repetición de bloque de opciones de programa - lógica mejorada
                is_options_block = (
                    ("universidad de piura" in lower and "programas" in lower and "posgrado" in lower) or
                    ("mba" in lower and "finanzas" in lower and "data science" in lower and "ciberseguridad" in lower) or
                    "tenemos varias opciones" in lower or
                    "ofrecemos" in lower and "mba" in lower
                )
                now = datetime.datetime.utcnow().timestamp()
                if is_options_block:
                    # Buscar en recientes un mensaje similar (bloque de programas) en los últimos 60 segundos
                    for ts, msg in list(self._recent_assistant):
                        # Si ya enviamos un bloque de programas hace menos de 60s, suprimir este
                        msg_lower = msg.lower()
                        is_prev_options = (
                            ("universidad de piura" in msg_lower and "programas" in msg_lower) or
                            ("mba" in msg_lower and "finanzas" in msg_lower and "data science" in msg_lower) or
                            ("ofrecemos" in msg_lower and "mba" in msg_lower)
                        )
                        if is_prev_options and (now - ts) <= 60.0:
                            # Bloque de programas repetido, suprimido
                            return
                    # Si pasó la verificación, registrar este bloque
                    self._remember_assistant(normalized)
                
                # Dedupe por último emitido y por ventana temporal
                if normalized == self._last_assistant_text or self._is_recent_duplicate(normalized):
                    return
                self._last_assistant_text = normalized
                self._last_emitted_role = "ASSISTANT"
                self._remember_assistant(normalized)
            try:
                self._on_assistant_text(text)
            except Exception:
                pass

    def maybe_capture_action(self, text: str) -> bool:  # noqa: D401
        if self._skip_next_maybe:
            self._skip_next_maybe = False
            if self._last_suppress:
                self._emit_snapshot("captured_action", force=True)
            return self._last_suppress
        suppress = self._delegate.maybe_capture_action(text)
        self._last_suppress = suppress
        if suppress:
            self._emit_snapshot("captured_action", force=True)
        else:
            self._emit_snapshot("assistant_text")
        return suppress

    def on_content_end(self) -> None:  # noqa: D401
        self._delegate.on_content_end()
        self._emit_snapshot("content_end", force=True)

    def on_session_end(self, session_id: str):  # noqa: D401
        export_path = self._delegate.on_session_end(session_id)
        self._emit_snapshot("session_end", force=True)
        if self._on_session_summary:
            summary = {
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "session_id": session_id,
                "export_path": export_path,
            }
            try:
                self._on_session_summary(summary)
            except Exception:
                pass
        return export_path

    def snapshot_lead(self) -> dict:  # noqa: D401
        return self._delegate.snapshot_lead()

    def on_usage_update(self, payload: dict) -> None:
        """Reenvía las métricas de uso al frontend."""
        if self._on_usage_update:
            try:
                self._on_usage_update(payload)
            except Exception:
                pass

    @staticmethod
    def _join_spanish_list(items: list[str]) -> str:
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        if len(items) == 2:
            return f"{items[0]} y {items[1]}"
        return ", ".join(items[:-1]) + f" y {items[-1]}"

    def _build_coach_message(self, missing: list[str], reason: str) -> str:
        labels = {
            "nombre_completo": "el nombre completo de la persona",
            "dni": "el DNI",
            "telefono": "el teléfono",
            "email": "el correo electrónico",
            "modalidad_preferida": "la modalidad preferida (presencial, híbrida u online)",
        }
        ordered = [labels[field] for field in missing if field in labels]
        if not ordered:
            return ""
        needs = self._join_spanish_list(ordered)
        if reason == "consent_precheck":
            message = (
                f"Antes de pedir consentimiento, asegúrate de confirmar {needs}. "
                "Retoma la conversación con calidez, solicita los datos pendientes, repítelos para validar y recién después vuelve a consentimiento."
            )
        elif reason == "field_skip":
            message = (
                f"Antes de pasar a otro dato, confirma {needs}. "
                "Agradece la información entregada, indica con tacto que aún falta ese campo y obtén su confirmación antes de seguir avanzando."
            )
        else:
            message = (
                f"DETENER CIERRE INMEDIATAMENTE. Falta {needs}. "
                "NO digas 'un asesor se comunicará' hasta tener todos los datos. "
                "Responde: 'Antes de terminar, necesito confirmar [dato faltante]...'"
            )
        if "telefono" in missing:
            message += " Pide el número claramente, repítelo para confirmar y pregunta “¿Correcto?”."
        if "nombre_completo" in missing:
            message += " Solicita el nombre completo, repítelo tal cual y confirma con “¿Correcto?”."
        if "modalidad_preferida" in missing:
            message += " Pregunta explícitamente si prefiere modalidad presencial, híbrida u online y registra la respuesta."
        return message

    def _issue_coach(self, missing: list[str], reason: str) -> None:
        if not missing or not self._send_coach:
            return
        key = (reason, tuple(sorted(missing)))
        if key == self._last_coach_key:
            return
        message = self._build_coach_message(missing, reason)
        if not message:
            return
        if not self._can_issue_coach():
            return
        self._last_coach_key = key
        try:
            self._send_coach(message)
        except Exception:
            pass

    def _issue_pair_coach(self) -> None:
        if not self._send_coach:
            return
        key = ("pairs", tuple())
        if self._last_coach_key == key:
            return
        self._last_coach_key = key
        if not self._can_issue_coach():
            return
        message = (
            "Al confirmar DNI o teléfono, pronuncia los dígitos con claridad y evita ambigüedades como ‘treinta’ o ‘setenta’ si no fueron dichas por la persona. Repite el número completo y luego pregunta “¿Correcto?”."
        )
        try:
            self._send_coach(message)
        except Exception:
            pass

    def _maybe_inject_coach(self, assistant_text: str) -> None:
        if not assistant_text or not self._send_coach:
            return
        lead_snapshot = self._delegate.snapshot_lead()
        pending = getattr(self._delegate, "pending", {}) if hasattr(self._delegate, "pending") else {}
        awaiting = getattr(self._delegate, "awaiting_confirm", None)

        def is_missing(field: str) -> bool:
            val = lead_snapshot.get(field)
            if isinstance(val, str):
                if val.strip():
                    return False
            elif val:
                return False
            if isinstance(pending, dict):
                pend_val = pending.get(field)
                if isinstance(pend_val, str):
                    if pend_val.strip():
                        return False
                elif pend_val:
                    return False
            return True

        missing_core = [field for field in ("nombre_completo", "telefono") if is_missing(field)]
        missing_modalidad = ["modalidad_preferida"] if is_missing("modalidad_preferida") else []

        text_lower = assistant_text.lower()
        consent_trigger = re.search(r"\b(consentimiento|autoriza|permiso|autorizas|autorizar)\b", text_lower)
        closing_trigger = re.search(
            r"(un asesor se comunicará|un asesor se comunicara|asesor se comunicará|asesor se comunicara|nos estaremos comunicando|hasta luego|gracias por tu tiempo|muchas gracias|estamos en contacto|que tengas un buen|perfecto, gracias|eso sería todo|eso seria todo|cu[ií]date|cuidate|listo, gracias)",
            text_lower,
        )

        if re.search(r"\bconfirmo\b", text_lower):
            tens_words = ("veinte", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa", "cien", "ciento")
            if any(re.search(rf"\b{w}\b", text_lower) for w in tens_words):
                self._issue_pair_coach()

        if is_missing("telefono") and awaiting not in ("telefono",) and not pending.get("telefono"):
            if re.search(r"\b(correo\s+electr[oó]nico|correo|email|e-?mail|gmail|outlook|hotmail)\b", text_lower):
                self._issue_coach(["telefono"], "field_skip")
                return

        if consent_trigger and not awaiting and (missing_core or missing_modalidad):
            missing = sorted(set(missing_core + missing_modalidad))
            self._issue_coach(missing, "consent_precheck")
            return

        if closing_trigger and not awaiting and (missing_core or missing_modalidad):
            missing = sorted(set(missing_core + missing_modalidad))
            self._issue_coach(missing, "closing")

    def _can_issue_coach(self) -> bool:
        now = datetime.datetime.utcnow()
        if self._last_coach_at and (now - self._last_coach_at).total_seconds() < self._coach_cooldown_seconds:
            return False
        self._last_coach_at = now
        return True


class NovaSonicWebAdapterV3:
    """Adapts the real-time sample flow so it can be used from Flask."""

    def __init__(
        self,
        *,
        context_config: Optional[str] = None,  # Path al archivo YAML de configuración
        prompt_file: Optional[str] = None,  # Deprecated: usar context_config
        kb_folder: str = "kb",
        voice: str = "lupe",
        on_transcript: Optional[Callable[[str], None]] = None,
        on_audio_response: Optional[Callable[[str], None]] = None,
        on_debug: Optional[Callable[[str], None]] = None,
        on_assistant_text: Optional[Callable[[str], None]] = None,
        on_usage: Optional[Callable[[dict], None]] = None,
        on_lead_snapshot: Optional[Callable[[dict], None]] = None,
        on_session_summary: Optional[Callable[[dict], None]] = None,
        on_event: Optional[Callable[[dict], None]] = None,  # Nuevo: eventos de reconexión y errores
    ) -> None:
        self.context_config = context_config
        self.prompt_file = prompt_file
        self.kb_folder = kb_folder
        self.voice = voice
        self.region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"

        self.on_transcript = on_transcript
        self.on_audio_response = on_audio_response
        self.on_debug = on_debug
        self.on_assistant_text = on_assistant_text
        self.on_usage = on_usage
        self.on_lead_snapshot = on_lead_snapshot
        self.on_session_summary = on_session_summary
        self.on_event = on_event  # Nuevo callback

        self.is_running = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.thread: Optional[threading.Thread] = None
        self.manager: Optional[BedrockStreamManager] = None
        self._processor: Optional[_WebAdapterProcessor] = None
        self._audio_task: Optional[asyncio.Task] = None
        self._subscription = None
        self._ready = threading.Event()
        self._decoder: Optional[_StreamingAudioDecoder] = None
        self._decoder_format: Optional[str] = None
        self._debug_pcm_dump_written = False
        self._last_ui_debug = None  # type: Optional[str]
        self._silence_threshold = int(os.getenv("NOVA_SONIC_SILENCE_PEAK", "800"))  # Umbral más alto para reducir falsos positivos
        self._max_silence_chunks = int(os.getenv("NOVA_SONIC_SILENCE_WINDOW", "20"))  # Más chunks antes de pausar
        self._silence_chunk_streak = 0
        self._silence_drop_active = False
        self._silence_last_keepalive = time.monotonic()
        self._silence_keepalive_interval = float(os.getenv("NOVA_SONIC_SILENCE_KEEPALIVE_S", "5.0"))  # 5s entre keepalives

    # ---------------------------------------------------------------- helpers
    def _log(self, message: str) -> None:
        console_message = f"[NovaSonic] {message}"
        try:
            print(console_message)
        except Exception:
            pass

        summary = self._summarize_debug_message(message)
        if not summary:
            return

        if self.on_debug:
            if summary == self._last_ui_debug:
                return
            self._last_ui_debug = summary
            try:
                self.on_debug(summary)
            except Exception:
                pass

    def _summarize_debug_message(self, message: str) -> Optional[str]:
        if not message:
            return None
        if message.startswith("→ Audio chunk"):
            return None
        if message.startswith("→ Evento enviado"):
            keys_start = message.find("(")
            keys_end = message.find(")")
            if keys_start != -1 and keys_end != -1 and keys_end > keys_start:
                keys = message[keys_start + 1 : keys_end]
                return f"Evento enviado {keys}"
            return "Evento enviado"
        if len(message) > 160 and "{" in message:
            return message[:157] + "..."
        return message

    @staticmethod
    def _peak_amplitude(chunk: bytes) -> int:
        if not chunk:
            return 0
        if len(chunk) % 2:
            chunk = chunk[:-1]
        if not chunk:
            return 0
        mv = memoryview(chunk).cast("h")
        return max(abs(sample) for sample in mv) if mv else 0

    def _build_context_sources(self):
        # Si se proporciona context_config, usarlo directamente
        if self.context_config:
            from context.bootstrap import load_context_sources
            config_path = Path(self.context_config)
            if not config_path.exists():
                raise FileNotFoundError(f"Config file no existe: {self.context_config}")
            return load_context_sources(str(config_path))
        
        # Fallback a método legacy (prompt_file + kb_folder)
        kb_arg: Optional[str] = None
        if self.kb_folder:
            kb_path = Path(self.kb_folder)
            if kb_path.is_dir():
                preferred = [
                    kb_path / "udep_catalog.json",
                    kb_path / "udep_catalog.yaml",
                    kb_path / "udep_catalog.yml",
                ]
                kb_file = next((p for p in preferred if p.exists()), None)
                if not kb_file:
                    for pattern in ("*.json", "*.yml", "*.yaml"):
                        kb_file = next(kb_path.glob(pattern), None)
                        if kb_file:
                            break
                if not kb_file:
                    raise FileNotFoundError(
                        f"La carpeta de KB '{self.kb_folder}' no contiene archivos .json/.yml"
                    )
                kb_arg = str(kb_file)
            else:
                kb_arg = str(kb_path)

        return discover_context_sources(
            explicit_prompt=self.prompt_file,
            explicit_kb=kb_arg,
        )

    # ---------------------------------------------------------------- runtime
    def start(self) -> None:
        if self.is_running:
            return
        self.is_running = True
        self._ready.clear()

        def runner() -> None:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            try:
                self.loop.run_until_complete(self._bootstrap())
            finally:
                self.loop.close()

        self.thread = threading.Thread(target=runner, daemon=True)
        self.thread.start()
        started = self._ready.wait(timeout=20)
        if not started or not self.is_ready:
            self._log("⚠️ Timeout esperando la sesión de Nova Sonic")
            self.stop()
            raise RuntimeError(
                "Nova Sonic no respondió a tiempo. Revisa tus credenciales y la región configurada."
            )

    async def _bootstrap(self) -> None:
        try:
            self._log("🔄 Inicializando Nova Sonic...")
            sources = self._build_context_sources()
            self._log(f"✅ Contexto cargado: {len(sources)} bloques")

            delegate = ToolUseProcessor()
            self._processor = _WebAdapterProcessor(
                delegate,
                self.on_transcript,
                self.on_assistant_text,
                getattr(self, "on_lead_snapshot", None),
                getattr(self, "on_session_summary", None),
                self._send_coach_instruction,
                self.on_usage,
            )

            self._log(f"🌎 Región seleccionada: {self.region}")

            self.manager = BedrockStreamManager(
                context_sources=sources,
                processor=self._processor,
                region=self.region,
                voice_id=self.voice,
                debug_callback=self._log,
            )

            # Conectar el ajuste dinámico del timeout de silencio al manager
            try:
                self._processor.set_adjust_silence_timeout(self.manager.set_silence_timeout)
            except Exception:
                pass

            self._log("📡 Solicitando stream Nova Sonic...")
            try:
                await asyncio.wait_for(self.manager.initialize_stream(), timeout=20)
            except asyncio.TimeoutError as exc:
                raise RuntimeError("Timeout inicializando stream Nova Sonic") from exc
            self._log("✅ Stream inicializado, esperando confirmación del modelo...")
            
            # send_audio_content_start_event ahora espera internamente el promptEnd
            await self.manager.send_audio_content_start_event()
            
            self._ready.set()
            self._log("🎬 Sesión lista: enviando audio continuo")

            self._subscription = self.manager.output_subject.subscribe(
                on_next=self._handle_event,
                on_error=lambda exc: self._log(f"❌ Evento de error: {exc}"),
            )

            self._audio_task = asyncio.create_task(self._drain_audio())

            while self.is_running:
                await asyncio.sleep(0.1)
        except Exception as exc:
            self._ready.set()
            self._log(f"❌ Error en adaptador: {exc}")
            raise
        finally:
            if self._subscription:
                try:
                    self._subscription.dispose()
                except Exception:
                    pass
                self._subscription = None

            if self._audio_task:
                self._audio_task.cancel()
                try:
                    await self._audio_task
                except Exception:
                    pass
                self._audio_task = None

            if self.manager:
                try:
                    await self.manager.close()
                except Exception as close_exc:
                    self._log(f"⚠️ Error cerrando sesión: {close_exc}")
                self.manager = None
            self._processor = None
            if self._decoder:
                try:
                    self._decoder.close()
                except Exception:
                    pass
                self._decoder = None
                self._decoder_format = None

    def _send_coach_instruction(self, text: str) -> None:
        if not text or not self.is_running:
            return
        manager = self.manager
        loop = self.loop
        if not manager or not loop:
            return
        preview = text if len(text) <= 160 else f"{text[:157]}..."
        self._log(f"📝 Coach interno: {preview}")

        payload = text.strip()
        if payload:
            payload = f"[NO-VOZ][COACH]{payload}[/COACH][/NO-VOZ]"
        else:
            return

        async def _inject() -> None:
            await manager.send_system_message(payload, role="ASSISTANT")

        future = asyncio.run_coroutine_threadsafe(_inject(), loop)

        def _report(result_future: asyncio.Future) -> None:
            exc = result_future.exception()
            if exc:
                self._log(f"⚠️ No se pudo inyectar coach: {exc}")

        future.add_done_callback(_report)

    async def _drain_audio(self) -> None:
        manager = self.manager
        if not manager:
            return
        try:
            while self.is_running and manager.is_active:
                pcm_bytes = await manager.audio_output_queue.get()
                if not self.on_audio_response:
                    continue
                try:
                    audio_b64 = base64.b64encode(pcm_bytes).decode("utf-8")
                    self.on_audio_response(audio_b64)
                except Exception as exc:
                    self._log(f"⚠️ Error remitindo audio: {exc}")
        except asyncio.CancelledError:
            pass

    def _handle_event(self, payload: dict) -> None:
        event = payload.get("event") if isinstance(payload, dict) else None
        if not event:
            return
        
        # Manejo de eventos de reconexión
        if "streamReconnecting" in event:
            reconnect_info = event["streamReconnecting"]
            attempt = reconnect_info.get("attempt", 0)
            max_attempts = reconnect_info.get("maxAttempts", 3)
            delay = reconnect_info.get("delaySeconds", 0)
            reason = reconnect_info.get("reason", "Error desconocido")
            
            self._log(f"🔄 Reconectando stream (intento {attempt}/{max_attempts}, delay={delay}s): {reason}")
            
            # Emitir al frontend para UI
            if self.on_event:
                try:
                    self.on_event({
                        "type": "stream_reconnecting",
                        "attempt": attempt,
                        "maxAttempts": max_attempts,
                        "delaySeconds": delay,
                        "reason": reason
                    })
                except Exception:
                    pass
            return
        
        if "streamReconnected" in event:
            reconnect_info = event["streamReconnected"]
            attempt = reconnect_info.get("attempt", 0)
            
            self._log(f"✅ Stream reconectado exitosamente (después de {attempt} intentos)")
            
            # Emitir al frontend para UI
            if self.on_event:
                try:
                    self.on_event({
                        "type": "stream_reconnected",
                        "attempt": attempt
                    })
                except Exception:
                    pass
            return
        
        if "streamError" in event:
            error_info = event["streamError"]
            is_fatal = error_info.get("fatal", False)
            reason = error_info.get("reason", "Error desconocido")
            
            if is_fatal:
                self._log(f"💀 Error fatal del stream: {reason}")
            else:
                self._log(f"⚠️ Error del stream: {reason}")
            
            # Emitir al frontend para UI
            if self.on_event:
                try:
                    self.on_event({
                        "type": "stream_error",
                        "fatal": is_fatal,
                        "reason": reason
                    })
                except Exception:
                    pass
            return
        
        # Manejo existente de eventos
        if "usage" in event and self.on_usage:
            try:
                self.on_usage(event["usage"])
            except Exception:
                pass
        elif "usageEvent" in event and self.on_usage:
            # Fallback para flujos que emiten 'usageEvent' directamente desde AWS
            try:
                ue = event["usageEvent"] or {}
                # Preferir totales si están presentes
                input_total = ue.get("totalInputTokens")
                output_total = ue.get("totalOutputTokens")
                # Si no, intentar leer del bloque 'details.total'
                if input_total is None or output_total is None:
                    details = ue.get("details") or {}
                    total = details.get("total") or {}
                    input_total = (
                        input_total if input_total is not None else
                        (total.get("input", {}).get("textTokens") or 0) + (total.get("input", {}).get("speechTokens") or 0)
                    )
                    output_total = (
                        output_total if output_total is not None else
                        (total.get("output", {}).get("textTokens") or 0) + (total.get("output", {}).get("speechTokens") or 0)
                    )
                total_tokens = int((input_total or 0) + (output_total or 0))
                # Calcular costo estimado con la misma tarifa que el manager
                input_cost = (float(input_total or 0) / 1000.0) * 0.0006
                output_cost = (float(output_total or 0) / 1000.0) * 0.0024
                cost = round(float(input_cost + output_cost), 6)
                payload_simple = {
                    "inputTokens": int(input_total or 0),
                    "outputTokens": int(output_total or 0),
                    "totalTokens": int(total_tokens),
                    "estimatedCostUsd": cost,
                }
                self.on_usage(payload_simple)
            except Exception:
                pass
        elif "error" in event:
            self._log(f"⚠️ Evento de error del modelo: {event['error']}")

    @property
    def is_ready(self) -> bool:
        return bool(self._ready.is_set() and self.manager and getattr(self.manager, "is_active", False))

    # ---------------------------------------------------------------- control
    def send_audio_chunk(self, audio_bytes: bytes, mime_type: Optional[str] = None) -> None:
        if not self.is_running or not self.loop or not self.manager:
            return
        if not self._ready.wait(timeout=5):
            self._log("⚠️ Sesión no lista para audio")
            return

        asyncio.run_coroutine_threadsafe(
            self._convert_and_send(audio_bytes, mime_type),
            self.loop,
        )

    async def _convert_and_send(self, audio_bytes: bytes, mime_type: Optional[str]) -> None:
        manager = self.manager
        if not manager or not manager.is_active:
            return
        try:
            if mime_type and not self._decoder_format:
                lowered = mime_type.lower()
                if "ogg" in lowered:
                    self._decoder_format = "ogg"
                elif "webm" in lowered:
                    self._decoder_format = "webm"
            fmt = self._decoder_format or "webm"

            if not self._decoder:
                self._decoder = _StreamingAudioDecoder(fmt, target_rate=16000, logger=self._log)
                self._log(f"🎛️ Decoder creado ({fmt}), esperando suficientes datos...")
                if not self._decoder_format:
                    self._decoder_format = fmt
            # No loggear "activo" en cada chunk - genera ruido

            self._decoder.feed(audio_bytes)
            pcm_bytes = self._decoder.read()
            if pcm_bytes:
                # Solo loggear primera vez para debug
                if not self._debug_pcm_dump_written:
                    self._log(f"🔊 PCM listo: {len(pcm_bytes)} bytes (head {pcm_bytes[:8].hex()})")
                    try:
                        Path("debug_pcm_chunk.raw").write_bytes(pcm_bytes)
                        self._debug_pcm_dump_written = True
                    except Exception as dump_exc:
                        self._log(f"⚠️ No se pudo escribir debug PCM: {dump_exc}")

                # Enviar en chunks de ~100ms (3200 bytes) para balance latencia/throughput
                # Demasiado pequeño (20ms) genera overhead de red
                # Demasiado grande (>200ms) agrega latencia perceptible
                chunk_size = 3200  # 100ms @ 16kHz mono 16-bit
                for offset in range(0, len(pcm_bytes), chunk_size):
                    portion = pcm_bytes[offset:offset + chunk_size]
                    if not portion:
                        continue
                    if len(portion) % 2:
                        portion = portion[:-1]
                        if not portion:
                            continue
                    
                    # ENVIAR TODO EL AUDIO - Nova Sonic tiene su propio VAD
                    # No intentar detectar silencio en el backend
                    manager.add_audio_chunk(portion)
        except Exception as exc:
            self._log(f"⚠️ Error temporal procesando audio ({mime_type or 'desconocido'}): {exc}")
            # NO resetear decoder - dejarlo persistente para chunks futuros
            # Solo cerrar si es un error fatal irrecuperable
            if "Decoder process is not available" in str(exc):
                self._log("❌ Decoder perdido, será reiniciado en próximo chunk")
                if self._decoder:
                    try:
                        self._decoder.close()
                    except Exception:
                        pass
                self._decoder = None
                self._decoder_format = None

    def stop(self) -> None:
        if not self.is_running:
            return

        self.is_running = False
        if self.thread:
            self.thread.join(timeout=5)
            self.thread = None
        self.loop = None
        self.manager = None
        self._processor = None
        self._audio_task = None
        self._subscription = None
        self._ready.clear()
        if self._decoder:
            try:
                self._decoder.close()
            except Exception:
                pass
            self._decoder = None
        self._decoder_format = None
        self._log("✅ Adaptador detenido")
