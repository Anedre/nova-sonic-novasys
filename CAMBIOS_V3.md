# Cambios Implementados - Nova Sonic V3

## Problema Identificado

El bot no respondía porque **el patrón de comunicación estaba incorrecto**. Después de revisar los ejemplos oficiales de AWS (websocket-nodejs), descubrí el patrón correcto:

### ❌ Patrón Incorrecto (V2):
```
Para cada turno:
1. send_audio_content_start_event()
2. Enviar chunks de audio
3. send_audio_content_end_event()
4. Repetir para siguiente turno
```

### ✅ Patrón Correcto (V3):
```
Para toda la llamada:
1. initialize_stream() - session_start + prompt_start + context
2. send_audio_content_start_event() - UNA SOLA VEZ al inicio
3. Streamear audio CONTINUAMENTE durante toda la llamada
4. send_audio_content_end_event() - UNA SOLA VEZ al final
```

## Cambios Realizados

### 1. Nuevo Adaptador: `nova_sonic_web_adapter_v3.py`

**Características clave:**
- ✅ Envía `content_start` UNA VEZ en `_run_async()` después de inicializar
- ✅ Streaming continuo de audio sin cerrar/abrir content
- ✅ Procesa eventos `textOutput` para transcripciones USER y ASSISTANT
- ✅ Envía `content_end` solo al detener (end_call)

**Flujo simplificado:**
```python
async def _run_async(self):
    # 1. Cargar contexto
    context_sources = discover_context_sources(...)
    
    # 2. Crear stream manager
    self.stream_manager = BedrockStreamManager(...)
    
    # 3. Inicializar (envía session_start, prompt_start, context)
    await self.stream_manager.initialize_stream()
    
    # 4. Suscribirse a eventos
    self.stream_manager.output_subject.subscribe(...)
    
    # 5. CLAVE: Enviar content_start UNA VEZ
    await self.stream_manager.send_audio_content_start_event()
    
    # 6. Mantener loop vivo
    while self.is_running:
        await asyncio.sleep(0.1)
```

### 2. Backend Actualizado: `app.py`

**Cambios:**
- ✅ Usa `NovaSonicWebAdapterV3` en lugar de V2
- ✅ Eliminados métodos `start_turn()`, `end_turn()`, `end_audio_stream()`
- ✅ Simplificado `handle_call_started()` - solo crea adapter y llama `start()`
- ✅ Simplificado `handle_call_ended()` - solo llama `stop()`
- ✅ Callbacks correctos para transcripciones:
  - `on_transcript` → Emite `user_transcript` (texto del usuario)
  - `on_assistant_text` → Emite `nova_response` (texto de Zhenia)

### 3. Frontend Mejorado: `app.js`

**Mejoras en visualización:**
- ✅ Actualiza status a "Procesando..." cuando recibe transcripción de usuario
- ✅ Actualiza status a "Zhenia respondiendo..." cuando recibe respuesta de Nova
- ✅ Transcripciones aparecen en el panel de conversación con roles diferenciados
- ✅ Mensajes de debug más descriptivos (primeros 80 caracteres)

## Comparación de Código

### Antes (V2):
```python
# Backend
adapter.start()
time.sleep(1)
# ❌ NO enviaba content_start correctamente

# Audio streaming
adapter.send_audio_chunk(audio)  # ❌ Intentaba auto-iniciar pero fallaba
```

### Ahora (V3):
```python
# Backend
adapter.start()  # ✅ Inicia Y envía content_start automáticamente

# Audio streaming
adapter.send_audio_chunk(audio)  # ✅ Solo envía audio, content ya está abierto
```

## Eventos Nova Sonic Manejados

### textOutput
```json
{
  "event": {
    "textOutput": {
      "role": "USER",  // o "ASSISTANT"
      "content": "texto transcrito..."
    }
  }
}
```
- **USER**: Transcripción de lo que dijo el usuario
- **ASSISTANT**: Texto de respuesta de Zhenia

### audioOutput
```json
{
  "event": {
    "audioOutput": {
      "content": "base64_audio..."
    }
  }
}
```
- Audio sintetizado de la respuesta de Zhenia

## Flujo Completo de Conversación

```
1. Usuario: Click "Iniciar Llamada"
   ├─ Backend: create adapter → start()
   ├─ Adapter: initialize_stream()
   ├─ Adapter: send_audio_content_start_event()
   └─ Frontend: Muestra "En llamada - Conversación fluida"

2. Usuario: Habla
   ├─ Frontend: MediaRecorder captura audio cada 1s
   ├─ Frontend: Envía chunks WebM via socket
   ├─ Backend: Recibe chunks, llama send_audio_chunk()
   ├─ Adapter: Convierte WebM → PCM16, envía a Bedrock
   └─ Nova Sonic: Procesa audio continuamente

3. Nova Sonic: Detecta silencio (VAD interno)
   ├─ Nova: Envía textOutput [USER] con transcripción
   ├─ Frontend: Muestra transcripción en panel
   ├─ Nova: Procesa y genera respuesta
   ├─ Nova: Envía textOutput [ASSISTANT] con respuesta
   ├─ Frontend: Muestra respuesta de Zhenia
   ├─ Nova: Envía audioOutput con audio sintetizado
   └─ Frontend: Reproduce audio de Zhenia

4. Usuario: Sigue hablando (conversación fluida)
   └─ Volver al paso 2

5. Usuario: Click "Terminar Llamada"
   ├─ Backend: call_ended → adapter.stop()
   ├─ Adapter: send_audio_content_end_event()
   ├─ Adapter: close stream
   └─ Frontend: Muestra "Llamada finalizada"
```

## Testing

Para probar:
1. Inicia el servidor: `python app.py`
2. Abre http://localhost:5000
3. Click "Iniciar Llamada" (botón verde)
4. Espera ~2 segundos (inicialización)
5. Habla normalmente
6. Observa:
   - Panel Debug: Debe mostrar "🎬 Audio content_start enviado"
   - Panel Debug: Debe mostrar "📝 [USER]: ..." cuando hables
   - Panel Debug: Debe mostrar "📝 [ASSISTANT]: ..." cuando responda
   - Panel Transcripción: Debe mostrar tu texto y el de Zhenia
   - Audio: Debe escucharse la voz de Zhenia

## Archivos Modificados

- ✅ `nova_sonic_web_adapter_v3.py` - Nuevo adaptador correcto
- ✅ `app.py` - Backend simplificado con V3
- ✅ `static/js/app.js` - Frontend con mejor visualización de transcripciones
- ✅ `CAMBIOS_V3.md` - Esta documentación

## Diferencias Clave vs Ejemplos AWS

### websocket-nodejs (oficial):
```typescript
// Envía content_start UNA VEZ
await session.setupStartAudio(audioConfig);

// Stream continuo
while (recording) {
  await session.streamAudio(audioBuffer);
}

// Cierra UNA VEZ al final
await session.endAudioContent();
```

### Nuestra implementación (V3):
```python
# Envía content_start UNA VEZ
await self.stream_manager.send_audio_content_start_event()

# Stream continuo
def send_audio_chunk(audio_bytes):
    self.stream_manager.add_audio_chunk(pcm_bytes)

# Cierra UNA VEZ al final
await self.stream_manager.send_audio_content_end_event()
```

## Próximos Pasos

Si aún no responde:
1. Verificar logs en consola de backend
2. Verificar panel Debug en frontend
3. Confirmar que FFmpeg está instalado
4. Verificar credenciales AWS (environment variables)
5. Verificar región (debe ser us-east-1)
