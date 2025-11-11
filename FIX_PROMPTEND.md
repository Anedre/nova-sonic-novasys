# Fix: Esperar promptEnd y Formato JSON Correcto

## Problema Identificado

```
Error: "Unable to parse input chunk. Please check input format contains correct format."
```

**Causa Raíz**: Dos problemas combinados:
1. **Formato JSON incorrecto**: Usábamos `json.dumps(payload, ensure_ascii=True)` que el modelo rechazaba
2. **Eventos enviados demasiado rápido**: Sin delays entre eventos de inicialización
3. **Contexto gigante en un solo chunk**: Era mejor enviarlo fragmentado por fuente
4. **Timing incorrecto**: Intentábamos enviar audio antes de recibir confirmación del modelo

## Flujo Incorrecto (Antes)

```
1. sessionStart + promptStart + context sources (SIN DELAYS)
2. contentStart (audio) ← ❌ DEMASIADO PRONTO
3. Modelo rechaza: "Unable to parse input chunk"
```

## Flujo Correcto (Ahora)

Según el patrón oficial de AWS Nova Sonic:

```
1. Cliente envía:
   ├─ sessionStart
   ├─ [delay 0.1s]
   ├─ promptStart  
   ├─ [delay 0.1s]
   ├─ context sources (contentStart → textInput → contentEnd con delays 0.05s)
   └─ [delay 0.1s]

2. ⏳ ESPERAR → Modelo responde: promptEnd

3. ✅ SOLO AHORA Cliente envía:
   └─ contentStart (audio)

4. Streaming continuo de audio chunks
```

## Cambios Implementados

### 1. `nova_sonic_es_sd.py`

**Agregado flag de sincronización:**

```python
# En __init__
self._prompt_ready = asyncio.Event()  # Flag para esperar promptEnd
```

**Modificado `send_audio_content_start_event()`:**

```python
async def send_audio_content_start_event(self) -> None:
    # Esperar confirmación del modelo
    self._debug("⏳ Esperando confirmación del modelo (promptEnd)...")
    await asyncio.wait_for(self._prompt_ready.wait(), timeout=10)
    self._debug("✅ Modelo listo, enviando contentStart para audio")
    # ... resto del código
```

**Agregado manejo de evento `promptEnd`:**

```python
async def _handle_model_payload(self, payload: Dict[str, Any]) -> None:
    # ... código existente ...
    
    if "promptEnd" in event:
        self._debug("✅ Recibido promptEnd - modelo listo para audio")
        self._prompt_ready.set()  # Desbloquea send_audio_content_start_event
```

**Removido `ensure_ascii=True` de `_send_event()`:**

```python
# Antes:
data = json.dumps(payload, ensure_ascii=True)  # ❌ Causaba errores

# Ahora:
data = json.dumps(payload)  # ✅ Formato compatible con Nova Sonic
```

**Agregados delays en `initialize_stream()`:**

```python
async def initialize_stream(self) -> "BedrockStreamManager":
    # ... código de inicialización ...
    
    await self._send_event(self._build_session_start_event())
    await asyncio.sleep(0.1)  # ✅ Delay como en ejemplo oficial
    await self._send_event(self._build_prompt_start_event())
    await asyncio.sleep(0.1)
    await self._send_context_sources()
    await asyncio.sleep(0.1)  # ✅ Esperar que el modelo procese
    
    self._reader_task = asyncio.create_task(self._read_loop())
    return self
```

**Agregados delays en `_send_text_block()` y fragmentación de contexto:**

```python
await self._send_event(start)
await asyncio.sleep(0.05)  # ✅ Delay entre eventos
await self._send_event(body)
await asyncio.sleep(0.05)
await self._send_event(end)

**`_send_context_sources()` ahora envía cada bloque por separado:**

```python
for src in self.context_sources:
    text = src.render().strip()
    self._debug(f"📚 Enviando contexto ({role}) len={len(text)}")
    await self._send_text_block(text, role=role)
    await asyncio.sleep(0.05)
```
```

### 2. `nova_sonic_web_adapter_v3.py`

**Simplificado bootstrap:**

```python
# Antes:
await self.manager.initialize_stream()
self._log("✅ Stream inicializado")
await self.manager.send_audio_content_start_event()
await asyncio.sleep(0.1)  # Delay innecesario

# Ahora:
await self.manager.initialize_stream()
self._log("✅ Stream inicializado, esperando confirmación del modelo...")
await self.manager.send_audio_content_start_event()  # Espera internamente
self._log("🎬 Sesión lista")
```

## Validación

### Logs Esperados (Correctos):

```
[HH:MM:SS] 📡 Solicitando stream Nova Sonic...
[HH:MM:SS] → Evento enviado (['sessionStart']): {...}
[HH:MM:SS] → Evento enviado (['promptStart']): {...}
[HH:MM:SS] → Evento enviado (['contentStart']): {"role": "SYSTEM"...}
[HH:MM:SS] → Evento enviado (['textInput']): {...}
[HH:MM:SS] → Evento enviado (['contentEnd']): {...}
[HH:MM:SS] ✅ Stream inicializado, esperando confirmación del modelo...
[HH:MM:SS] ⏳ Esperando confirmación del modelo (promptEnd)...
[HH:MM:SS] ✅ Recibido promptEnd - modelo listo para audio
[HH:MM:SS] ✅ Modelo listo, enviando contentStart para audio
[HH:MM:SS] → Evento enviado (['contentStart']): {"type": "AUDIO"...}
[HH:MM:SS] 🎬 Sesión lista: enviando audio continuo
[HH:MM:SS] 📤 Audio enviado: X KB
```

### ❌ Si el modelo no responde promptEnd:

```
[HH:MM:SS] ⏳ Esperando confirmación del modelo (promptEnd)...
[HH:MM:SS] ❌ RuntimeError: Timeout esperando promptEnd del modelo
```

Esto indicaría un problema con las credenciales AWS o la configuración del modelo.

## Referencias

- **AWS Official Sample**: `amazon-nova-samples/speech-to-speech/sample-codes/console-python/nova_sonic_tool_use.py`
- **Patrón documentado**: Siempre esperar `promptEnd` antes de enviar contenido interactivo

## Testing

1. Iniciar servidor: `python app.py`
2. Abrir navegador: http://localhost:5000
3. Iniciar llamada
4. Verificar en logs:
   - ✅ "Esperando confirmación del modelo"
   - ✅ "Recibido promptEnd"
   - ✅ "Modelo listo, enviando contentStart"
   - ❌ NO debe aparecer "Unable to parse input chunk"

---

**Fecha**: 31 Oct 2025  
**Versión**: V3.1 (Fix promptEnd)
