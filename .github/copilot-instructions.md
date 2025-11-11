# Nova Sonic UDEP - AI Coding Guide

## Project Overview

This is a **real-time voice AI conversational system** built with AWS Nova Sonic for lead capture in Spanish (Peruvian accent). The system enables bidirectional voice conversations between users and an AI assistant that captures structured lead data through natural dialogue.

### Architecture

**3-Layer Design:**
1. **Frontend** (`templates/index.html` + `static/`) - WebSocket-based voice interface with real-time transcription
2. **Flask Backend** (`app.py`) - WebSocket server managing multiple concurrent voice sessions
3. **AWS Integration** (`nova_sonic_es_sd.py`, `nova_sonic_web_adapter_v3.py`) - Bidirectional streaming with Nova Sonic v1

**Critical Data Flow:**
```
Browser Audio (WebM/Opus) 
→ WebSocket (base64) 
→ FFmpeg decoder (→ 16kHz PCM) 
→ Nova Sonic bidirectional stream 
→ Tool Use capture 
→ Lead JSON export
```

## Key Patterns

### 1. Bidirectional Streaming (Critical!)

**The streaming model changed in V3** - see `CAMBIOS_V3.md`:
- ✅ **Correct**: Send `content_start` ONCE at session initialization, stream audio continuously, send `content_end` ONCE at session end
- ❌ **Incorrect V2 pattern**: Sending content_start/end per turn breaks conversation flow

**Code location**: `nova_sonic_web_adapter_v3.py` lines 400-500, `nova_sonic_es_sd.py::BedrockStreamManager.initialize_stream()`

### 2. Tool Use for Data Capture

**Modern approach** (replaced JSON parsing) - see `MIGRACION_TOOL_USE.md`:
- Nova Sonic natively calls `guardar_lead` tool when it has complete lead data
- Schema validation happens model-side (8-digit DNI, 9-digit phone, valid email)
- `processors/tool_use_processor.py::ToolUseProcessor` handles execution and validation
- Prompt is conversational (`context/prompts/udep_system_prompt_v6_tool_use.txt`), not instruction-heavy

**Tool definition**: `nova_sonic_es_sd.py::BedrockStreamManager.DEFAULT_TOOL_SPEC`

### 3. Context Loading System

Configuration uses **pluggable context sources** (`context/bootstrap.py`):
- `config/context.yaml` defines source chain: prompt file + knowledge base
- `FilePromptSource` - system instructions
- `FileKBSource` - JSON/YAML knowledge base for RAG
- Auto-discovery: checks `context.yaml` → legacy paths → raises error

**Extend**: Register new source types in `context/bootstrap.py::_REGISTRY`

### 4. Real-Time Usage Metrics

**Performance monitoring** (see `METRICAS_TIEMPO_REAL.md`):
- Nova Sonic emits `performanceMetrics` events after each turn
- `nova_sonic_es_sd.py` captures `inputTokenCount` and `outputTokenCount`
- Calculates costs: Input $0.0006/1K tokens, Output $0.0024/1K tokens
- Payload flows: BedrockStreamManager → _WebAdapterProcessor → Flask emit → Frontend UI
- Frontend displays: `2847 tokens • $0.0051 • 01:23`

**Code location**: `nova_sonic_es_sd.py` lines 756-784, `nova_sonic_web_adapter_v3.py::_WebAdapterProcessor.on_usage_update()`

### 5. Audio Streaming & Decoding

**WebM/Opus → PCM conversion** (`nova_sonic_web_adapter_v3.py::_StreamingAudioDecoder`):
- **Streaming pipe architecture**: Sends WebM directly to FFmpeg stdin (no temp files)
- Accumulates initial 32KB buffer before starting FFmpeg (WebM headers requirement)
- **Two-thread model**:
  - Writer thread: Continuously feeds WebM chunks to FFmpeg stdin
  - Reader thread: Reads PCM output from FFmpeg stdout and queues it
- Nova requires: 16kHz, mono, 16-bit PCM
- **Critical**: WebM is a container format that can't be built incrementally in files

**Silence handling** (lines 750-850): Drops silent chunks after threshold, sends keepalives every 5s to maintain stream

### 6. Session Management

**Multi-session support** (`app.py`):
- Each WebSocket connection gets unique `request.sid`
- `nova_adapters[session_id]` dict stores per-session `NovaSonicWebAdapterV3` instances
- Adapter lifecycle: created on `call_started`, destroyed on `call_ended`/`disconnect`

### 7. Coach Injection System

**Proactive quality control** (`nova_sonic_web_adapter_v3.py::_WebAdapterProcessor`):
- Detects missing critical fields (nombre, teléfono, modalidad) when user tries to close
- Injects `[NO-VOZ][COACH]...[/COACH][/NO-VOZ]` system messages to guide Nova
- Cooldown: 6s between coaches to avoid spam
- Triggers: closing phrases detection, consent pre-check, field skipping

## Development Workflows

### Running Locally
```powershell
python app.py  # Starts Flask-SocketIO on 0.0.0.0:5000
```

**Prerequisites**:
- FFmpeg on PATH (for audio decoding)
- AWS credentials (Nova Sonic uses `EnvironmentCredentialsResolver`)
- Python 3.10+, dependencies from `requirements.txt`

### Testing Voice Flow
1. Open browser → `http://localhost:5000`
2. Select voice/prompt, click call button
3. Monitor debug panel (⚙ button) for events: `session_start`, `promptEnd`, `content_start`, transcriptions
4. Check `lead_snapshot` events in browser console for real-time capture status

### Debugging Audio Issues
- **No response**: Check if `content_start` sent after `promptEnd` (see V3 pattern)
- **Choppy audio**: Verify PCM chunk sizes (~100ms/3200 bytes optimal)
- **Decoder errors**: 
  - Check FFmpeg availability on PATH
  - Ensure 32KB initial buffer before FFmpeg starts
  - Look for "FFmpeg iniciado" message in logs
  - If `EBML header parsing failed`: WebM stream corruption (should not happen with pipe architecture)
- **Tool not called**: Validate prompt has complete tool spec, check model has all required fields

### Lead Export Format
JSON files saved to workspace root: `leads_session_YYYYMMDD-HHMMSS_<uuid>.json`
```json
{
  "session_id": "...",
  "confirmed": {
    "nombre_completo": "...",
    "dni": "12345678",
    "telefono": "987654321",
    ...
  }
}
```

## Important Files

- `nova_sonic_web_adapter_v3.py` - Main threading adapter exposing Nova to Flask
- `nova_sonic_es_sd.py` - Core bidirectional stream manager with tool execution
- `processors/tool_use_processor.py` - Lead capture via tool use (current approach)
- `config/context.yaml` - Source configuration (prompt + knowledge base)
- `app.py` - Flask-SocketIO entry point

## Migration Notes

- **V2→V3**: Continuous audio streaming (see `CAMBIOS_V3.md`)
- **JSON→Tool Use**: Replaced PERulesV1 parser with native tool calling (see `MIGRACION_TOOL_USE.md`)
- `bedrock_client.py` is **deprecated** - imports moved to official AWS SDK

## Common Pitfalls

1. **Don't** call `send_audio_content_start` per turn - ONLY once per session
2. **Don't** parse JSON from assistant text manually - use tool_use events
3. **Don't** skip waiting for `promptEnd` before sending audio
4. **Don't** write WebM chunks to file incrementally - use streaming pipe to FFmpeg
5. **Do** handle FFmpeg missing gracefully (check PATH before decoder creation)
6. **Do** respect 16kHz sample rate for Nova Sonic input
7. **Do** validate tool_input can be string or dict (defensive parsing in `handle_tool_use`)
8. **Do** accumulate 32KB buffer before starting FFmpeg (WebM headers requirement)

## Voice Mapping
Frontend voice codes → Nova voices:
- `es-ES-Female` → `lupe` (Peruvian Spanish)
- `es-ES-Male` → `sergio` (Spain Spanish)
- `es-MX-Female` → `mia` (Mexican Spanish)

See `app.py::handle_call_started` for complete mapping.
