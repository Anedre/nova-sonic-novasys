# 🐌 Latencia Artificial Detectada en el Código

## Problema Identificado

Aunque el prompt es simple, el código tiene **delays artificiales acumulativos** que añaden entre **1.0s y 1.5s de latencia** antes de que el modelo pueda responder.

---

## 🔴 Causa #1: Sleeps Excesivos en Inicialización

**Archivo**: `nova_sonic_es_sd.py` líneas 220-224

```python
async def initialize_stream(self) -> "BedrockStreamManager":
    # ... código ...
    await asyncio.sleep(0.1)  # Delay como en ejemplo oficial de AWS  ← +100ms
    await self._send_event(self._build_prompt_start_event())
    await asyncio.sleep(0.1)  # ← +100ms
    await self._send_context_sources()
    await asyncio.sleep(0.1)  # Esperar que el modelo procese  ← +100ms
```

**Impacto**: **+300ms en cada inicio de sesión**

### ¿Por qué está mal?

Los ejemplos de AWS usan sleeps porque son **demos síncronas con audio local**. En tu caso:
- Ya tienes `await self._send_event()` que espera confirmación del stream
- El modelo NO necesita tiempo de "procesamiento" - responde cuando recibe eventos
- Los sleeps entre eventos solo retrasan artificialmente

**Solución**: Eliminar todos los sleeps de inicialización

---

## 🔴 Causa #2: Sleeps en Envío de Contexto

**Archivo**: `nova_sonic_es_sd.py` líneas 400, 426, 439, 441, 475, 477

```python
async def _send_combined_text_block(self, role: str, fragments: List[str]) -> None:
    await self._send_event(start)
    await asyncio.sleep(0.05)  # ← +50ms POR FRAGMENTO
    for fragment in fragments:
        # ... enviar fragmento ...
        await asyncio.sleep(0.05)  # ← +50ms POR FRAGMENTO
    await self._send_event(end)
    await asyncio.sleep(0.05)  # ← +50ms

async def _send_text_block(self, text: str, role: str) -> None:
    await self._send_event(start)
    await asyncio.sleep(0.05)  # ← +50ms
    await self._send_event(body)
    await asyncio.sleep(0.05)  # ← +50ms
    await self._send_event(end)
```

**Impacto con prompt UDEP**:
- Prompt system: 1 bloque → +150ms (3 sleeps)
- Knowledge base: 1 bloque → +150ms
- **Total**: **+300ms adicionales**

**Impacto con prompt simple math**:
- Prompt system: 1 bloque → +150ms
- Sin KB → 0ms
- **Total**: **+150ms**

### ¿Por qué está mal?

`await self._send_event()` **ya es asíncrono y espera confirmación**. No necesitas sleeps adicionales entre eventos. El stream bidireccional de AWS maneja el backpressure automáticamente.

**Solución**: Eliminar todos los sleeps entre eventos de contexto

---

## 🔴 Causa #3: Pacing de Audio Innecesario

**Archivo**: `nova_sonic_es_sd.py` líneas 533-541

```python
async def _pace_audio_stream(self, byte_count: int) -> None:
    bytes_per_second = INPUT_SAMPLE_RATE * CHANNELS * PCM_SAMPLE_WIDTH
    duration = byte_count / bytes_per_second
    # ... cálculos ...
    if delay > 0:
        await asyncio.sleep(min(delay, 0.1))  # ← +hasta 100ms por chunk
```

**Impacto**: 
- Audio llega en chunks de ~3200 bytes (100ms @ 16kHz)
- Código añade sleep de hasta **100ms por chunk**
- Durante conversación activa: **+100ms cada 100ms de audio** = **50% más lento**

### ¿Por qué está mal?

Este pacing es para **reproducir audio a velocidad real**. Pero tú NO estás reproduciendo - estás **enviando audio capturado en tiempo real** desde el navegador.

El navegador ya controla el timing con `MediaRecorder` (timeslice: 1000ms). Nova Sonic puede procesar audio **más rápido que tiempo real** para reducir latencia.

**Solución**: Eliminar pacing completamente o reducir a 0ms

---

## 🔴 Causa #4: Cooldown de Coach Injection

**Archivo**: `nova_sonic_web_adapter_v3.py` líneas ~410-420

```python
def _issue_coach(self, missing_fields, trigger):
    now = datetime.datetime.utcnow().timestamp()
    if (now - self._last_coach_at) < 6.0:  # ← Cooldown de 6 segundos
        return
    # ... inyectar coach ...
    self._last_coach_at = now
```

**Impacto**: 
- Si usuario intenta terminar llamada sin datos: coach se inyecta
- Cooldown de **6 segundos** entre coaches
- Si usuario persiste: múltiples coaches con delays acumulativos

### ¿Por qué está mal?

Cooldown de 6s es demasiado largo. Usuario podría cerrar 2-3 veces antes de que coach se reactive.

**Solución**: Reducir cooldown a 2-3 segundos

---

## 📊 Latencia Total Acumulada

### Escenario: Prompt UDEP V6/V7/V8 con KB

```
Inicialización:                  +300ms  (3 sleeps de 100ms)
Envío contexto (2 bloques):      +300ms  (6 sleeps de 50ms)
Primer turno audio (3 chunks):   +300ms  (pacing 100ms × 3)
───────────────────────────────────────
TOTAL LATENCIA ARTIFICIAL:       +900ms  (casi 1 segundo)
```

### Escenario: Prompt Simple Math (sin KB)

```
Inicialización:                  +300ms
Envío contexto (1 bloque):       +150ms
Primer turno audio (3 chunks):   +300ms
───────────────────────────────────────
TOTAL LATENCIA ARTIFICIAL:       +750ms  (0.75 segundos)
```

---

## ✅ Soluciones Implementables

### 1. Eliminar Sleeps de Inicialización (CRÍTICO)

```python
async def initialize_stream(self) -> "BedrockStreamManager":
    client = self._ensure_client()
    request = InvokeModelWithBidirectionalStreamOperationInput(model_id=self.model_id)
    self.stream_response = await client.invoke_model_with_bidirectional_stream(request)

    self.is_active = True
    await self._send_event(self._build_session_start_event())
    # await asyncio.sleep(0.1)  ← ELIMINAR
    await self._send_event(self._build_prompt_start_event())
    # await asyncio.sleep(0.1)  ← ELIMINAR
    await self._send_context_sources()
    # await asyncio.sleep(0.1)  ← ELIMINAR
    
    if not self._prompt_ready.is_set():
        self._debug("ℹ️ Contexto entregado, habilitando audio")
        self._prompt_ready.set()

    self._reader_task = asyncio.create_task(self._read_loop())
    return self
```

**Ganancia**: -300ms

---

### 2. Eliminar Sleeps de Contexto (CRÍTICO)

```python
async def _send_combined_text_block(self, role: str, fragments: List[str]) -> None:
    # ... código ...
    await self._send_event(start)
    # await asyncio.sleep(0.05)  ← ELIMINAR
    for fragment in fragments:
        self._debug(f"📚 Enviando contexto combinado ({role}) len={len(fragment)}")
        await self._send_event(body)
        # await asyncio.sleep(0.05)  ← ELIMINAR
    await self._send_event(end)
    # await asyncio.sleep(0.05)  ← ELIMINAR

async def _send_text_block(self, text: str, role: str) -> None:
    # ... código ...
    await self._send_event(start)
    # await asyncio.sleep(0.05)  ← ELIMINAR
    await self._send_event(body)
    # await asyncio.sleep(0.05)  ← ELIMINAR
    await self._send_event(end)
```

**Ganancia**: -300ms

---

### 3. Desactivar Pacing de Audio (CRÍTICO)

```python
async def _pace_audio_stream(self, byte_count: int) -> None:
    # Desactivado - audio ya llega en tiempo real desde MediaRecorder
    return
    
    # O alternativamente, reducir al mínimo:
    # await asyncio.sleep(0.001)  # 1ms simbólico para yield
```

**Ganancia**: -300ms (dependiendo de cuántos chunks se envíen antes de respuesta)

---

### 4. Reducir Cooldown de Coach (OPCIONAL)

```python
def _issue_coach(self, missing_fields, trigger):
    now = datetime.datetime.utcnow().timestamp()
    if (now - self._last_coach_at) < 2.0:  # ← Cambiar de 6.0 a 2.0
        return
```

**Ganancia**: Mejora UX en casos edge, no afecta latencia normal

---

## 🎯 Resultado Esperado

**Antes**: 2.0-2.5s latencia (prompt V6) + 900ms artificial = **2.9-3.4s total**

**Después**: 
- Prompt Simple Math: 0.5-0.8s (modelo) + 0ms artificial = **0.5-0.8s total** ✅
- Prompt V8 Mínimo: 1.0-1.3s (modelo) + 0ms artificial = **1.0-1.3s total** ✅
- Prompt V6 Estructurado: 2.0-2.5s (modelo) + 0ms artificial = **2.0-2.5s total** ✅

---

## 🔧 Orden de Implementación

1. **PRIMERO**: Eliminar sleeps de inicialización (-300ms)
2. **SEGUNDO**: Eliminar sleeps de contexto (-300ms)
3. **TERCERO**: Desactivar pacing de audio (-300ms)
4. **CUARTO**: (Opcional) Reducir cooldown de coach

Implementar en ese orden te permite **medir el impacto de cada cambio** viendo logs de timing.

---

## ⚠️ Advertencia

Los sleeps originales vienen de ejemplos de AWS que:
- Usan audio local desde archivos (no streaming real-time)
- Son demos educativas (no optimizadas para producción)
- Asumen hardware lento (Raspberry Pi, etc.)

Tu caso es diferente:
- ✅ Streaming real-time desde navegador
- ✅ Hardware moderno
- ✅ Red estable
- ✅ Backpressure manejado por AWS SDK

**No necesitas delays artificiales.**
