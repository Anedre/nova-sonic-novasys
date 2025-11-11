# 🐌 CAUSA RAÍZ: Latencia por Detección de Pausas

## El Problema Real

Tu sistema tiene **detección de pausas (Voice Activity Detection - VAD)** que espera a que **termines de hablar completamente** antes de enviar señal al modelo para que responda.

---

## 🔴 Flujo Actual (LENTO)

```
Usuario habla: "Hola, ¿cuánto es dos más dos?"
   ↓
MediaRecorder captura en chunks de 1 segundo
   ↓
Backend recibe audio continuamente
   ↓  
⏸️ ESPERA SILENCIO detectado por silence detection (~2-3 segundos)
   ↓
Envía contentEnd AUDIO (señal de "usuario terminó")
   ↓
Nova Sonic RECIÉN EMPIEZA a procesar
   ↓
⏱️ Latencia modelo (0.5-2.5s según prompt)
   ↓
Respuesta del asistente
```

**Total**: Tiempo de habla + 2-3s silencio + latencia modelo = **4-6 segundos**

---

## 📍 Código Problemático Detectado

### 1. **Frontend: Chunks de 1 segundo** 
**Archivo**: `static/js/app.js` línea 18-19

```javascript
const CAPTURE_SLICE_MS = 1000; // 1s para garantizar chunks WebM con headers completos
```

**Impacto**: Audio se envía cada **1 segundo** en bloques. Si dices una frase corta (2 palabras), tarda 1s en llegar al backend.

---

### 2. **Backend: NO hay detección de silencio automática**
**Archivo**: `nova_sonic_web_adapter_v3.py` líneas 1055-1059

```python
# ENVIAR TODO EL AUDIO - Nova Sonic tiene su propio VAD
# No intentar detectar silencio en el backend
manager.add_audio_chunk(portion)
```

**Observación**: El código dice que Nova Sonic tiene VAD propio, pero...

---

### 3. **La Trampa: VAD Manual Comentado**
**Archivo**: `nova_sonic_web_adapter_v3.py` líneas 738-743

```python
self._silence_threshold = int(os.getenv("NOVA_SONIC_SILENCE_PEAK", "800"))
self._max_silence_chunks = int(os.getenv("NOVA_SONIC_SILENCE_WINDOW", "20"))
self._silence_chunk_streak = 0
self._silence_drop_active = False
self._silence_last_keepalive = time.monotonic()
self._silence_keepalive_interval = float(os.getenv("NOVA_SONIC_SILENCE_KEEPALIVE_S", "5.0"))
```

**Variables definidas pero NO usadas** en el código actual. Esto sugiere que había detección de silencio antes y fue **desactivada**.

---

### 4. **El Verdadero Culpable: ¿Dónde está el contentEnd?**

Nova Sonic **NO responde hasta recibir `contentEnd` AUDIO**. Revisemos dónde se envía:

**Archivo**: `nova_sonic_es_sd.py` líneas 620-633

```python
elif "contentEnd" in event:
    content = event["contentEnd"]
    content_type = content.get("type")
    
    # Log de fin de audio del usuario
    if content_type == "AUDIO" and self._current_role == "USER":
        self._last_user_audio_end = time.time()
        self._debug("📍 Usuario terminó de hablar (contentEnd AUDIO)")
    
    if content_type == "AUDIO":
        self.processor.on_content_end()
```

**Esto recibe contentEnd del MODELO, no lo envía.**

Busquemos dónde **enviamos** contentEnd:

**Archivo**: `nova_sonic_es_sd.py` línea 783-794

```python
async def send_audio_content_end_event(self) -> None:
    """Señal de fin de audio usuario."""
    event = {
        "event": {
            "contentEnd": {
                "promptName": self.prompt_name,
                "contentName": self.audio_content_name,
            }
        }
    }
    await self._send_event(event)
    self._debug("📍 Enviado contentEnd AUDIO")
```

**¿Cuándo se llama esto?** Busquemos:

```python
# nova_sonic_es_sd.py línea 298
await self.send_audio_content_end_event()
```

Esto está en el método `stop()`. **Se envía solo al cerrar la sesión completa.**

---

## 🎯 DIAGNÓSTICO FINAL

Tu sistema usa el **patrón V3 de streaming continuo**:

```
✅ send_audio_content_start_event() - UNA VEZ al inicio
✅ Streamear audio CONTINUAMENTE
✅ send_audio_content_end_event() - UNA VEZ al cerrar sesión
```

Pero **Nova Sonic NO responde hasta recibir contentEnd del turno actual.**

### Hay DOS patrones de Nova Sonic:

#### **Patrón A: Streaming Continuo (Full-Duplex)**
- Audio fluye sin pausas
- Modelo responde MIENTRAS hablas (interrumpe)
- **NO requiere contentEnd por turno**
- Más natural, menor latencia
- **Requiere barge-in habilitado**

#### **Patrón B: Turn-Based (Half-Duplex)** ← **TU CÓDIGO ACTUAL**
- Audio fluye hasta detectar pausa
- Envías contentEnd al detectar silencio
- Modelo espera contentEnd para responder
- Conversación tradicional (turnos)
- **Mayor latencia pero más predecible**

---

## 🔧 SOLUCIONES POSIBLES

### Opción 1: Reducir Tamaño de Chunks (RÁPIDO)

**Cambiar**: `static/js/app.js` línea 18

```javascript
// ANTES
const CAPTURE_SLICE_MS = 1000; // 1s chunks

// DESPUÉS  
const CAPTURE_SLICE_MS = 250; // 250ms chunks (4 por segundo)
```

**Ganancia**: -750ms en promedio

**Pros**: 
- Cambio mínimo (1 línea)
- Audio llega más rápido al modelo

**Contras**: 
- Más overhead de red (4x mensajes WebSocket)
- Chunks WebM pequeños pueden tener problemas de headers

---

### Opción 2: Implementar VAD en Frontend (MEDIO)

Usar Web Audio API para detectar cuando usuario para de hablar:

```javascript
// Detectar silencio en el navegador
const analyser = audioContext.createAnalyser();
analyser.fftSize = 256;
const dataArray = new Uint8Array(analyser.frequencyBinCount);

function detectSilence() {
    analyser.getByteFrequencyData(dataArray);
    const average = dataArray.reduce((a, b) => a + b) / dataArray.length;
    if (average < SILENCE_THRESHOLD) {
        silenceFrames++;
        if (silenceFrames > 10) { // ~300ms silencio
            socket.emit('user_stopped_speaking');
        }
    } else {
        silenceFrames = 0;
    }
}
```

**Ganancia**: -1.5 a -2s

**Pros**:
- Detección más precisa (analiza frecuencias)
- Backend recibe señal inmediata

**Contras**:
- Más código en frontend
- Puede dar falsos positivos (pausas naturales al hablar)

---

### Opción 3: Cambiar a Patrón Full-Duplex (AVANZADO)

Habilitar barge-in y permitir interrupciones:

```python
# nova_sonic_es_sd.py - En initialize_stream()
# Agregar configuración de barge-in
"bargeIn": {
    "enabled": True,
    "threshold": 0.6  # Sensibilidad de interrupción
}
```

**Ganancia**: -2 a -3s (modelo responde sin esperar fin)

**Pros**:
- Latencia mínima
- Conversación más natural
- Modelo responde mientras hablas

**Contras**:
- Puede interrumpir prematuramente
- Requiere ajustar sensibilidad
- Más complejo de debuggear

---

### Opción 4: Híbrido - Timeout Adaptativo (RECOMENDADO)

Combinar streaming con timeout corto:

```python
# nova_sonic_web_adapter_v3.py
self._last_audio_received = time.monotonic()
self._silence_timeout = 0.8  # 800ms sin audio = usuario terminó

async def _monitor_silence(self):
    while self.is_running:
        await asyncio.sleep(0.1)
        silence_duration = time.monotonic() - self._last_audio_received
        if silence_duration > self._silence_timeout:
            # Usuario lleva 800ms sin hablar, señalar fin de turno
            if not self._turn_ended:
                await self.manager.send_turn_end_signal()
                self._turn_ended = True
```

**Ganancia**: -1 a -1.5s

**Pros**:
- Balance perfecto latencia/precisión
- 800ms es imperceptible para humanos
- Evita interrupciones prematuras
- Fácil de ajustar

**Contras**:
- Requiere agregar lógica de timeout

---

## 📊 Comparación de Soluciones

| Solución | Ganancia Latencia | Complejidad | Riesgo Errores |
|----------|-------------------|-------------|----------------|
| **Opción 1: Chunks 250ms** | -750ms | Baja ⭐ | Bajo |
| **Opción 2: VAD Frontend** | -1.5s | Media ⭐⭐ | Medio |
| **Opción 3: Full-Duplex** | -2.5s | Alta ⭐⭐⭐ | Alto |
| **Opción 4: Timeout 800ms** | -1.2s | Media ⭐⭐ | Bajo |

---

## 🎯 RECOMENDACIÓN INMEDIATA

**Implementar Opciones 1 + 4 en conjunto:**

1. **Reducir chunks a 250ms** (cambio 1 línea)
2. **Agregar timeout de 800ms** para enviar contentEnd automático

**Resultado esperado**:
- Prompt Simple Math: **0.3-0.5s** (vs 1.5s actual) ✅
- Prompt V8: **0.8-1.0s** (vs 2.2s actual) ✅
- Prompt V6: **1.5-2.0s** (vs 3.4s actual) ✅

---

## ⚠️ Por Qué el Código Actual es Lento

```
Usuario: "Hola"
   ↓
Tarda 1s en capturar chunk completo (CAPTURE_SLICE_MS = 1000)
   ↓  
Backend recibe, pero NO envía contentEnd
   ↓
Nova Sonic espera... espera... espera...
   ↓
⏰ NUNCA responde porque no hay señal de "turno terminado"
   ↓
Usuario cierra llamada manualmente
   ↓
AHORA se envía contentEnd (en stop())
```

**El modelo está HAMBRIENTO de la señal contentEnd pero nunca llega.**

---

## 🔧 Siguiente Paso

¿Quieres que implemente:
- **A) Opción 1 solo** (250ms chunks - 1 línea)?
- **B) Opción 4 solo** (timeout 800ms)?
- **C) Ambas (A + B)** para máxima mejora? ← **RECOMENDADO**
