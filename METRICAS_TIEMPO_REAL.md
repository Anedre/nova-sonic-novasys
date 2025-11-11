# Sistema de Métricas de Uso en Tiempo Real

## Descripción General

El sistema captura y muestra en tiempo real el consumo de tokens y costos estimados de cada conversación con Nova Sonic.

## Arquitectura del Flujo de Datos

```
Nova Sonic Stream
    ↓
performanceMetrics event
    ↓
BedrockStreamManager._handle_model_payload()
    ↓ (extrae inputTokenCount, outputTokenCount)
    ↓ (calcula costos según precios de Nova Sonic v1:0)
    ↓
_WebAdapterProcessor.on_usage_update()
    ↓
NovaSonicWebAdapterV3.on_usage callback
    ↓
Flask-SocketIO emit('usage_update')
    ↓
Frontend WebSocket handler
    ↓
UI actualizado (tokens + USD)
```

## Componentes Modificados

### 1. nova_sonic_es_sd.py

**Ubicación:** `_handle_model_payload()` - después del evento `toolUse`

**Función:**
- Detecta eventos `performanceMetrics` del stream de Nova Sonic
- Extrae `inputTokenCount` y `outputTokenCount`
- Calcula costos usando precios oficiales:
  - Input: $0.0006 por 1K tokens
  - Output: $0.0024 por 1K tokens
- Construye payload con métricas agregadas
- Llama a `processor.on_usage_update(payload)`

**Payload generado:**
```python
{
    "inputTokens": int,
    "outputTokens": int,
    "totalTokens": int,
    "estimatedCostUsd": float  # 6 decimales
}
```

### 2. nova_sonic_web_adapter_v3.py

**Clase `_WebAdapterProcessor`:**
- Constructor acepta callback `on_usage_update`
- Método `on_usage_update(payload)` reenvía al callback de la clase padre

**Clase `NovaSonicWebAdapterV3`:**
- Constructor acepta callback `on_usage` (ya existía)
- En `_bootstrap()`, pasa `self.on_usage` al `_WebAdapterProcessor`

### 3. app.py

**Ya implementado:**
- Callback `on_usage()` definido en `handle_call_started`
- Emite evento `usage_update` vía SocketIO al frontend

### 4. templates/index.html + static/js/app.js

**Ya implementado:**
- UI con elementos `#tokenInfo` y `#costInfo`
- Handler `socket.on('usage_update')` que actualiza visualización
- Función `updateUsageMetrics()` con soporte para múltiples formatos

## Precios de Nova Sonic v1:0 (us-east-1)

| Tipo | Precio por 1K tokens |
|------|---------------------|
| Input | $0.0006 |
| Output | $0.0024 |

**Ejemplo:**
- 1000 tokens input + 1000 tokens output = $0.0006 + $0.0024 = **$0.0030**

## Eventos del Stream

Nova Sonic emite eventos `performanceMetrics` periódicamente durante la conversación (típicamente después de cada turno completo). El evento contiene:

```json
{
  "event": {
    "performanceMetrics": {
      "inputTokenCount": 1234,
      "outputTokenCount": 567,
      "latencyMs": 850
    }
  }
}
```

## Actualización en Tiempo Real

- **Frecuencia:** Cada vez que Nova Sonic emite `performanceMetrics` (típicamente cada turno)
- **Acumulación:** El frontend acumula valores incrementalmente
- **Precisión:** Costos con 4 decimales en UI ($0.0012), 6 en cálculos internos

## Testing

1. Inicia el servidor: `python app.py`
2. Abre el navegador en `http://localhost:5000`
3. Inicia una llamada
4. Observa el panel de métricas actualizarse después de cada turno
5. Verifica en la consola del navegador los eventos `usage_update`

## Notas Técnicas

- Los eventos `performanceMetrics` llegan **después** de la respuesta completa del modelo
- Si Nova Sonic no emite estos eventos, las métricas permanecen en 0
- Los precios están hardcoded según la documentación oficial de AWS (enero 2025)
- El sistema es backward-compatible: si falta el callback, no hay errores

## Logs de Debug

Para verificar la captura de métricas, busca en la consola del servidor:

```
📊 Métricas recibidas: {'inputTokenCount': 1234, 'outputTokenCount': 567, ...}
```

## Limitaciones Conocidas

1. Nova Sonic puede no emitir `performanceMetrics` en todas las regiones/versiones
2. Los costos son **estimados** - AWS factura por los valores reales que pueden variar
3. Los precios pueden cambiar - verificar pricing AWS actualizado
