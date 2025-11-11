# Cambios en la Implementación Nova Sonic V2

## Problema Identificado

La implementación anterior no seguía el patrón correcto de AWS Nova Sonic documentado en los ejemplos oficiales:
- https://github.com/aws-samples/amazon-nova-samples/blob/main/speech-to-speech/sample-codes/console-python/nova_sonic_tool_use.py

### Error Principal
**No se enviaba `send_audio_content_start_event()` antes del primer chunk de audio**, lo que causaba que Nova Sonic nunca respondiera.

## Patrón Correcto (Según AWS Samples)

### Flujo de Conversación:

```
1. Inicialización del Stream (una vez):
   ├─ START_SESSION_EVENT
   ├─ START_PROMPT_EVENT (con configuración de voz y tools)
   └─ Context Sources (mensajes SYSTEM)

2. Inicio de Turno de Usuario:
   └─ send_audio_content_start_event() ← CRÍTICO!

3. Durante el Turno:
   └─ Enviar chunks de audio continuamente (audioInput events)

4. Fin de Turno:
   └─ send_audio_content_end_event() ← Señal para que Nova responda

5. Nova Sonic Responde:
   ├─ textOutput events (transcripción)
   └─ audioOutput events (voz sintetizada)

6. Siguiente Turno:
   └─ Volver al paso 2 (nuevo content_start)
```

## Cambios Implementados

### 1. Nuevo Adaptador: `nova_sonic_web_adapter_v2.py`

**Métodos Principales:**

- **`start_turn()`**: Envía `content_start` - DEBE llamarse antes de enviar audio
- **`send_audio_chunk()`**: Envía chunks de audio durante un turno activo
- **`end_turn()`**: Envía `content_end` - Señala a Nova que responda

**Control de Estado:**

```python
self.is_in_turn = False  # Controla si hay un turno activo
```

### 2. Backend Actualizado: `app.py`

**Cambios en `call_started`:**

```python
# Después de crear el adapter
adapter.start()
time.sleep(1)  # Esperar inicialización

# IMPORTANTE: Iniciar el primer turno inmediatamente
adapter.start_turn()
```

**Cambios en `audio_stream`:**

```python
# Simplificado - solo envía chunks
adapter.send_audio_chunk(audio_data)
```

**Cambios en `turn_complete` (botón "Terminé de hablar"):**

```python
# 1. Finalizar turno actual
adapter.end_turn()  # Nova procesa y responde

# 2. Iniciar nuevo turno
time.sleep(0.5)  # Esperar respuesta
adapter.start_turn()  # Listo para seguir hablando
```

**Cambios en `call_ended`:**

```python
# Finalizar turno si existe
adapter.end_turn()
adapter.stop()
```

### 3. Frontend: Sin Cambios

El frontend sigue enviando chunks de WebM cada 1 segundo, pero ahora el backend los maneja correctamente con el patrón de turnos.

## Diferencias Clave vs Implementación Anterior

| Aspecto | Anterior (Incorrecto) | Nuevo (Correcto) |
|---------|----------------------|------------------|
| Inicio de turno | ❌ No se enviaba | ✅ `start_turn()` al iniciar llamada |
| Envío de audio | ❌ `send_audio()` directo | ✅ `send_audio_chunk()` durante turno |
| Fin de turno | ❌ Solo al finalizar llamada | ✅ `end_turn()` al clickear botón |
| Siguiente turno | ❌ No manejado | ✅ Auto-inicia nuevo turno después |
| Control de estado | ❌ Flag confuso | ✅ `is_in_turn` claro |

## Flujo de Uso

### Usuario Inicia Llamada:
1. Click en botón verde
2. Backend: `adapter.start()` + `adapter.start_turn()`
3. Usuario empieza a hablar
4. Frontend envía chunks cada 1 segundo
5. Backend: `send_audio_chunk()` para cada chunk

### Usuario Termina de Hablar:
1. Click en "✋ Terminé de hablar"
2. Backend: `adapter.end_turn()`
3. Nova Sonic procesa y responde
4. Backend: `adapter.start_turn()` (nuevo turno)
5. Usuario puede seguir hablando

### Usuario Finaliza Llamada:
1. Click en botón rojo
2. Backend: `adapter.end_turn()` + `adapter.stop()`

## Debugging Mejorado

El nuevo adaptador incluye mensajes de debug claros:

```
🎬 Iniciando turno de usuario (audio content_start)
✅ Turno iniciado, listo para recibir audio
🏁 Finalizando turno (audio content_end)
✅ Turno finalizado, esperando respuesta de Nova...
🗣️ Usuario: [transcripción]
💬 Nova: [respuesta]
🔊 Audio de respuesta enviado
```

## Para Probar

1. **Detener servidor** actual (Ctrl+C)
2. **Reiniciar:**
   ```powershell
   python app.py
   ```
3. **Recargar página** (F5)
4. **Iniciar llamada** (botón verde)
5. **Hablar 3-5 segundos**
6. **Click "✋ Terminé de hablar"**
7. **Observar debug panel** - deberías ver:
   - "🎬 Primer turno iniciado"
   - "🏁 Turno finalizado"
   - "🗣️ Usuario: ..." (transcripción)
   - "💬 Nova: ..." (respuesta)
   - Audio reproduciéndose

## Referencias

- [AWS Nova Samples - Python](https://github.com/aws-samples/amazon-nova-samples/blob/main/speech-to-speech/sample-codes/console-python/nova_sonic_tool_use.py)
- [AWS Nova Samples - WebSocket Node.js](https://github.com/aws-samples/amazon-nova-samples/tree/main/speech-to-speech/sample-codes/websocket-nodejs)
- [AWS Nova Samples - WebSocket Java](https://github.com/aws-samples/amazon-nova-samples/tree/main/speech-to-speech/sample-codes/websocket-java)
