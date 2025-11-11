# Nova Sonic UDEP - Sistema de Captura de Leads por Voz

Sistema de conversación de voz en tiempo real construido con AWS Nova Sonic para captura estructurada de leads en español (acento peruano). Permite conversaciones bidireccionales fluidas entre usuarios y un asistente de IA que captura datos estructurados a través de diálogo natural.

## 🏗️ Arquitectura

**Diseño de 3 Capas:**

1. **Frontend** (`templates/index.html` + `static/`) - Interfaz WebSocket con transcripción en tiempo real
2. **Backend Flask** (`app.py`) - Servidor WebSocket gestionando múltiples sesiones de voz concurrentes  
3. **Integración AWS** (`nova_sonic_es_sd.py`, `nova_sonic_web_adapter_v3.py`) - Streaming bidireccional con Nova Sonic v1

**Flujo Crítico de Datos:**
```
Audio del Navegador (WebM/Opus)
→ WebSocket (base64)
→ Decoder FFmpeg (→ PCM 16kHz)
→ Stream bidireccional Nova Sonic
→ Captura vía Tool Use
→ Export JSON de leads
```

## 📋 Requisitos

### Obligatorios

- **Python 3.10+**
- **FFmpeg** instalado y en PATH (para decodificación de audio)
- **Credenciales AWS** con acceso a Amazon Bedrock (Nova Sonic)
- Navegador moderno con soporte para MediaRecorder API

### Verificación rápida

```powershell
# Python
python --version

# FFmpeg
ffmpeg -version

# Variables de entorno AWS
echo $env:AWS_ACCESS_KEY_ID
echo $env:AWS_REGION
```

## 🚀 Setup Rápido

### 1. Clonar e instalar dependencias

```powershell
cd e:\TRABAJO\NOVASONIC\UDEP
pip install -r requirements.txt
```

### 2. Configurar credenciales AWS

Copia `.env.example` a `.env` y configura tus credenciales:

```bash
AWS_ACCESS_KEY_ID=tu_access_key_aqui
AWS_SECRET_ACCESS_KEY=tu_secret_key_aqui
AWS_REGION=us-east-1
```

⚠️ **Importante**: Nunca subas el archivo `.env` con credenciales reales al repositorio.

### 3. Instalar FFmpeg (si no está instalado)

**Windows:**
```powershell
# Via Chocolatey
choco install ffmpeg

# O descargar desde https://ffmpeg.org/download.html
# Asegúrate de añadir ffmpeg.exe al PATH
```

**Linux:**
```bash
sudo apt update && sudo apt install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

### 4. Ejecutar diagnóstico (opcional)

```powershell
$env:NOVA_SONIC_DIAGNOSTICS='true'
python app.py
```

Esto verificará:
- ✅ Credenciales AWS configuradas
- ✅ FFmpeg disponible en PATH
- ✅ Versión de Python

### 5. Iniciar servidor

```powershell
python app.py
```

Accede desde:
- **Local**: http://localhost:5000
- **Red local**: http://<tu-ip>:5000

## 🎯 Uso

1. Abre el navegador en `http://localhost:5000`
2. Selecciona **voz** (Lupe/Sergio/Mia) y **prompt** (UDEP original recomendado)
3. Presiona el botón **"Iniciar Llamada"**
4. Habla naturalmente; el sistema captura:
   - Nombre completo
   - DNI (8 dígitos)
   - Teléfono (9 dígitos)
   - Email
   - Programa de interés
   - Modalidad preferida
   - Horario preferido
   - Consentimiento
5. El lead se exporta automáticamente al finalizar la llamada en `leads/`

## ⚙️ Configuración Avanzada

### Variables de entorno opcionales

```bash
# Debug mode (muestra logs detallados)
NOVA_SONIC_DEBUG=true

# Diagnostics mode (verifica entorno al iniciar)
NOVA_SONIC_DIAGNOSTICS=true

# Timeouts de silencio (segundos)
NOVA_SONIC_SILENCE_TIMEOUT_DEFAULT=0.8
NOVA_SONIC_SILENCE_TIMEOUT_FAST=0.5

# Decoder FFmpeg
NOVA_SONIC_WEBM_INIT_BYTES=16384
NOVA_SONIC_WEBM_TIMEOUT_S=2.0
```

### Selección de prompts

Disponibles en el selector del frontend:

- **`udep_original`** (recomendado): Prompt estructurado v6 con tool use
- **`v8_minimal`**: Versión minimalista para pruebas rápidas
- **`v7_conversational`**: Enfoque conversacional más natural
- **`v6_structured`**: Estructurado original con formato JSON
- **`simple_test`**: Tutor de matemáticas (testing)

Configúralos en `config/context_*.yaml`

## 🔧 Arquitectura Técnica

### Captura y Streaming de Audio (Frontend)

```javascript
// MediaRecorder con slices de 250ms para baja latencia
const CAPTURE_SLICE_MS = 250; // 4 chunks/segundo

// Preferencia: OGG/Opus (más robusto) > WebM/Opus
const recorderMimeType = 'audio/ogg;codecs=opus';

// Envío continuo vía WebSocket
socket.emit('audio_stream', {
    audio: base64Audio,
    mime: recorderMimeType
});
```

### Decodificación (Backend)

```python
# _StreamingAudioDecoder en nova_sonic_web_adapter_v3.py

# 1. Acumula chunks hasta detectar header EBML válido (0x1A45DFA3)
# 2. Inicia FFmpeg con pipe: WebM/OGG stdin → PCM 16kHz stdout
# 3. Lee chunks PCM de ~100ms (3200 bytes) en thread separado
# 4. Envía directamente a Nova Sonic (sin VAD backend)
```

### Patrón V3 Nova Sonic (Crítico)

```python
# ✅ CORRECTO (V3):
# - Un solo contentStart de audio por sesión
# - Audio continuo (múltiples audioInput)
# - contentEnd solo al cerrar sesión

await manager.send_audio_content_start_event()  # UNA VEZ
# ... stream continuo de audioInput ...
await manager.send_audio_content_end_event()    # AL CERRAR

# ❌ INCORRECTO (V2):
# - contentStart/End por cada turno → rompe conversación
```

### Tool Use para Captura de Leads

El sistema usa **Tool Use nativo de AWS** en lugar de parsing JSON manual:

```python
# Nova Sonic llama automáticamente cuando tiene datos completos
DEFAULT_TOOL_SPEC = {
    "toolSpec": {
        "name": "guardar_lead",
        "description": "Guarda datos del prospecto cuando...",
        "inputSchema": {
            "type": "object",
            "properties": {
                "nombre_completo": {"type": "string"},
                "dni": {"type": "string"},  # 8 dígitos
                "telefono": {"type": "string"},  # 9 dígitos
                # ...
            }
        }
    }
}
```

Validación automática en `processors/tool_use_processor.py`:
- Limpieza de muletillas
- Validación de longitud DNI/teléfono
- Email regex básico
- Masking de PII en logs

## 📊 Métricas y Costos

El sistema muestra en tiempo real:

```
Tokens: 2847 tokens
Costo: $0.0051
Duración: 01:23
```

**Tarifas Nova Sonic v1:0:**
- Input: $0.0006 por 1K tokens
- Output: $0.0024 por 1K tokens

Configurables en `config/constants.py`

## 🐛 Troubleshooting

### Error: "FFmpeg NO encontrado en PATH"

```powershell
# Verifica instalación
ffmpeg -version

# Si no está instalado
choco install ffmpeg  # Windows
# o descarga desde https://ffmpeg.org/
```

### Error: "AWS credentials not configured"

```powershell
# Verifica .env
cat .env

# Debe contener:
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
```

### Error: "EBML header parsing failed"

Esto indica problemas con el formato WebM del navegador:

1. El sistema detecta y tolera esto automáticamente
2. Revisa logs: "FFmpeg iniciado" y "PCM generado"
3. Si persiste, prueba con navegador diferente (Chrome/Edge recomendados)

### Latencia alta o respuestas lentas

```bash
# Activar debug para análisis
NOVA_SONIC_DEBUG=true python app.py

# Busca en logs:
# "⏱️ LATENCIA: X.XXs desde fin audio usuario..."
# "⏱️ TTS: X.XXs desde contentStart..."
```

Optimizaciones aplicadas:
- ✅ Sleeps eliminados de inicialización
- ✅ Pacing de audio desactivado
- ✅ Chunks de 250ms (frontend) + 100ms (backend)
- ✅ Monitor de silencio automático (800ms)

### Prompt no se carga

```python
# Verifica que el archivo existe
ls config/context_udep_original.yaml
ls context/prompts/udep_system_prompt_original_v6.txt
ls kb/udep_catalog.json

# Si falta, el sistema usa fallback (v8_minimal)
```

### Audio cortado o robótico

- **Problema**: Pérdida de paquetes o decoder sobrecargado
- **Solución**: 
  - Reduce load del sistema
  - Verifica conexión de red
  - Revisa "⚠️ Pipe roto" en logs

### Lead no se exporta

- Verifica que el asistente llamó la herramienta: busca "🔧 Tool invocado: guardar_lead" en logs
- Los leads válidos se guardan en `leads/leads_session_*.json`
- Si faltan datos, el modelo esperará confirmación antes de llamar la herramienta

## 📁 Estructura del Proyecto

```
UDEP/
├── app.py                          # Servidor Flask-SocketIO
├── nova_sonic_web_adapter_v3.py    # Adapter threading + FFmpeg decoder
├── nova_sonic_es_sd.py             # Manager bidireccional Nova Sonic
├── config/
│   ├── __init__.py
│   ├── constants.py                # ⭐ Configuración centralizada
│   ├── context_udep_original.yaml  # Config prompt UDEP original
│   └── context_v8_minimal.yaml     # Config prompt minimalista
├── context/
│   ├── bootstrap.py                # Sistema de carga de contexto
│   ├── prompts/
│   │   ├── udep_system_prompt_original_v6.txt
│   │   └── udep_system_prompt_v8_minimal.txt
│   └── ...
├── kb/
│   └── udep_catalog.json           # Knowledge base (RAG)
├── processors/
│   ├── base.py
│   └── tool_use_processor.py       # ⭐ Validación y export de leads
├── leads/                          # ⭐ Carpeta de exports (auto-creada)
│   └── leads_session_*.json
├── static/
│   ├── css/styles.css
│   └── js/app.js                   # Frontend WebSocket + audio
├── templates/
│   └── index.html
├── requirements.txt
├── .env                            # ⚠️ Credenciales (NO subir a git)
└── .env.example                    # Template de configuración
```

## 🔐 Seguridad

- ✅ Credenciales en `.env` (incluido en `.gitignore`)
- ✅ PII enmascarado en logs (`mask_pii()`)
- ✅ Leads exportados a carpeta dedicada con `.gitignore`
- ✅ Validación de input en tool use
- ⚠️ **IMPORTANTE**: Rotar credenciales si fueron expuestas

## 📚 Referencias

- [Documentación de cambios V3](./CAMBIOS_V3.md)
- [Migración a Tool Use](./MIGRACION_TOOL_USE.md)
- [Optimización VAD](./OPTIMIZACION_VAD_CHUNKS.md)
- [Métricas en tiempo real](./METRICAS_TIEMPO_REAL.md)

## 🧪 Testing

```powershell
# Prueba básica de conexión
python -c "from config import *; print('✅ Config OK')"

# Verifica FFmpeg
python -c "import shutil; print('✅ FFmpeg:', shutil.which('ffmpeg'))"

# Simula carga de contexto
python -c "from context.bootstrap import load_context_sources; print(load_context_sources('config/context_udep_original.yaml'))"
```

## 🤝 Contribuciones

Para contribuir:

1. Mantén el patrón V3 de streaming (un contentStart por sesión)
2. No agregues sleeps innecesarios (optimización crítica)
3. Usa `config/constants.py` para nuevas constantes
4. Enmascara PII en logs con `mask_pii()`
5. Añade tests unitarios en `tests/` para nueva funcionalidad

## 📝 Licencia

[Especifica tu licencia aquí]

## 🆘 Soporte

Para issues o preguntas:
- Revisa troubleshooting arriba
- Activa `NOVA_SONIC_DEBUG=true` para logs detallados
- Verifica documentación en `*.md` del proyecto

---

**Versión**: 3.0 (Optimizada Nov 2025)
**Última actualización**: 5 de noviembre de 2025
