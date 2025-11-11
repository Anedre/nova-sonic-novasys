# Testing del Panel de Métricas en Tiempo Real

## ✅ Implementación Completa

Se ha implementado el sistema de métricas en tiempo real para mostrar tokens y costos durante las conversaciones.

## 🎯 Cambios Realizados

### 1. Backend - Captura de Métricas

**nova_sonic_es_sd.py** (líneas ~760-790):
```python
elif "performanceMetrics" in event:
    metrics = event["performanceMetrics"]
    input_tokens = metrics.get("inputTokenCount", 0)
    output_tokens = metrics.get("outputTokenCount", 0)
    total_tokens = input_tokens + output_tokens
    
    # Precios Nova Sonic v1:0
    input_cost = (input_tokens / 1000) * 0.0006
    output_cost = (output_tokens / 1000) * 0.0024
    total_cost = input_cost + output_cost
    
    usage_payload = {
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "totalTokens": total_tokens,
        "estimatedCostUsd": round(total_cost, 6)
    }
    
    processor.on_usage_update(usage_payload)
```

### 2. Adapter - Propagación al Frontend

**nova_sonic_web_adapter_v3.py**:
- Agregado callback `on_usage_update` a `_WebAdapterProcessor.__init__()`
- Método `on_usage_update()` reenvía métricas al callback padre
- `NovaSonicWebAdapterV3` conecta `on_usage` con el processor

### 3. Frontend - Ya Existía

**templates/index.html** + **static/js/app.js**:
- ✅ UI lista: `#tokenInfo` y `#costInfo`
- ✅ Handler `socket.on('usage_update')` ya implementado
- ✅ Función `updateUsageMetrics()` ya existe

## 🧪 Cómo Probar

### Paso 1: Iniciar el Servidor
```powershell
python app.py
```

### Paso 2: Abrir el Navegador
```
http://localhost:5000
```

### Paso 3: Verificar el Panel de Métricas

1. **Antes de la llamada:**
   ```
   0 tokens • $0.00 • 00:00
   ```

2. **Iniciar llamada** (clic en el botón)

3. **Durante la conversación:**
   - Después de cada turno, las métricas se actualizan automáticamente
   - Ejemplo después de 3 turnos:
   ```
   2847 tokens • $0.0051 • 01:23
   ```

4. **Logs en la Consola del Servidor:**
   ```
   📊 Métricas recibidas: {'inputTokenCount': 1234, 'outputTokenCount': 567, ...}
   ```

5. **Logs en la Consola del Navegador (F12):**
   ```javascript
   usage_update {inputTokens: 1234, outputTokens: 567, totalTokens: 1801, estimatedCostUsd: 0.002112}
   ```

## 📊 Ejemplo de Sesión Real

**Conversación típica de captación de lead:**

| Turno | Input | Output | Total | Costo Acum. |
|-------|-------|--------|-------|-------------|
| 1 (saludo) | 150 | 80 | 230 | $0.0003 |
| 2 (nombre) | 180 | 120 | 530 | $0.0006 |
| 3 (programa) | 220 | 350 | 1100 | $0.0015 |
| 4 (teléfono) | 190 | 140 | 1430 | $0.0021 |
| 5 (email) | 160 | 110 | 1700 | $0.0026 |
| 6 (consentimiento) | 200 | 180 | 2080 | $0.0033 |
| 7 (despedida) | 140 | 90 | 2310 | $0.0038 |

**Total conversación completa:** ~2300 tokens ≈ **$0.0038 USD**

## 🔍 Debugging

### Si las métricas no se actualizan:

1. **Verificar que Nova Sonic emite eventos `performanceMetrics`:**
   ```python
   # En nova_sonic_es_sd.py, busca el log:
   📊 Métricas recibidas: {...}
   ```

2. **Verificar que el evento llega al frontend:**
   - Abrir DevTools (F12)
   - Pestaña Console
   - Buscar eventos `usage_update`

3. **Verificar el callback en app.py:**
   ```python
   def on_usage(payload):
       socketio.emit('usage_update', payload, room=session_id)
   ```

4. **Verificar la conexión WebSocket:**
   - En el panel de debug (⚙), buscar eventos `session_start`, `promptEnd`

## 🎨 Ubicación del Panel

El panel de métricas está visible en la parte inferior de la interfaz principal:

```
┌─────────────────────────────┐
│    🎙️ [Botón de llamada]   │
│                             │
│   📝 Transcripción aquí    │
│                             │
├─────────────────────────────┤
│  2847 tokens • $0.0051      │  ← Panel de métricas
│       00:01:23              │
└─────────────────────────────┘
```

## ⚠️ Notas Importantes

1. **Los eventos llegan después de cada turno completo**, no en tiempo real por palabra
2. **Nova Sonic puede tardar** 1-2 segundos después de la respuesta en emitir las métricas
3. **Los precios son estimados** según la tarifa oficial de Nova Sonic v1:0
4. **Si cambias de región AWS**, verifica que los precios sean los mismos

## 🎉 Testing Exitoso

Si ves esto, la implementación está funcionando:

```
Console del navegador:
✓ Conectado al servidor
✓ session_start recibido
✓ promptEnd recibido
✓ usage_update {inputTokens: 1234, outputTokens: 567, ...}

Panel de métricas:
2847 tokens • $0.0051 • 01:23
```

## 📚 Documentación Adicional

Ver `METRICAS_TIEMPO_REAL.md` para detalles técnicos completos.
