from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import json
import base64
import datetime
import asyncio
import os
import shutil
import sys
from pathlib import Path
from threading import Thread

from dotenv import load_dotenv

from nova_sonic_web_adapter_v3 import NovaSonicWebAdapterV3
from config import (
    get_voice_id,
    get_prompt_config_path,
    DEFAULT_PROMPT_CONFIG,
    DIAGNOSTICS_MODE
)

load_dotenv()

# ==================== Helpers ====================
def safe_print(msg):
    """Imprime mensajes manejando errores de encoding en consolas Windows."""
    try:
        print(msg)
    except UnicodeEncodeError:
        # Fallback: reemplazar caracteres problemáticos
        ascii_msg = msg.encode('ascii', errors='replace').decode('ascii')
        print(ascii_msg)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'nova-sonic-secret-key-2025'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Diccionario para manejar múltiples sesiones de Nova Sonic
nova_adapters = {}

# ==================== Pre-flight Checks ====================
def run_diagnostics():
    """Ejecuta verificaciones de entorno si DIAGNOSTICS_MODE está habilitado."""
    if not DIAGNOSTICS_MODE:
        return
    
    safe_print("\n🔍 Diagnóstico del sistema:")
    
    # Check AWS credentials
    if not os.getenv('AWS_ACCESS_KEY_ID'):
        safe_print("⚠️  AWS_ACCESS_KEY_ID no configurado")
    else:
        safe_print(f"✅ AWS_ACCESS_KEY_ID: {os.getenv('AWS_ACCESS_KEY_ID')[:8]}...")
    
    if not os.getenv('AWS_SECRET_ACCESS_KEY'):
        safe_print("⚠️  AWS_SECRET_ACCESS_KEY no configurado")
    else:
        safe_print("✅ AWS_SECRET_ACCESS_KEY: configurado")
    
    region = os.getenv('AWS_REGION') or os.getenv('AWS_DEFAULT_REGION')
    if not region:
        safe_print("⚠️  AWS_REGION no configurado (se usará us-east-1)")
    else:
        safe_print(f"✅ AWS_REGION: {region}")
    
    # Check FFmpeg
    ffmpeg_path = shutil.which('ffmpeg')
    if not ffmpeg_path:
        safe_print("❌ FFmpeg NO encontrado en PATH (requerido para audio)")
        safe_print("   Instalar: https://ffmpeg.org/download.html")
    else:
        safe_print(f"✅ FFmpeg encontrado: {ffmpeg_path}")
    
    # Check Python version
    safe_print(f"✅ Python: {sys.version.split()[0]}")
    
    safe_print()

# ==================== Routes ====================
@app.route('/')
def index():
    return render_template('index.html')

# ==================== Socket.IO Event Handlers ====================
@socketio.on('connect')
def handle_connect():
    session_id = request.sid
    emit('debug', {
        'message': '✅ Conexión WebSocket establecida',
        'session_id': session_id,
        'timestamp': datetime.datetime.now().isoformat()
    })

@socketio.on('disconnect')
def handle_disconnect():
    session_id = request.sid
    if session_id in nova_adapters:
        adapter = nova_adapters[session_id]
        adapter.stop()
        del nova_adapters[session_id]
        print(f"Sesión {session_id} terminada")

@socketio.on('audio_stream')
def handle_audio_stream(data):
    session_id = request.sid
    
    try:
        # Verificar que el adapter está inicializado
        if session_id not in nova_adapters:
            emit('debug', {
                'message': '⚠️ Llamada no iniciada. Por favor presiona "Iniciar Llamada" primero',
                'error': True
            })
            return
        
        adapter = nova_adapters[session_id]

        # Decodificar el audio en base64
        audio_data = base64.b64decode(data['audio'])
        mime_type = data.get('mime')

        # Enviar chunk de audio (el turno ya fue iniciado en call_started)
        adapter.send_audio_chunk(audio_data, mime_type)
        
    except Exception as e:
        emit('error', {'message': f'Error al procesar audio: {str(e)}'})
        emit('debug', {
            'message': f'❌ Error: {str(e)}',
            'error': True
        })

@socketio.on('call_started')
def handle_call_started(data):
    session_id = request.sid
    voice_code = data.get('voice', 'es-ES-Female')
    prompt_name = data.get('prompt', 'udep')
    
    try:
        # Convertir códigos del frontend usando configuración centralizada
        nova_voice = get_voice_id(voice_code)
        context_config_path = get_prompt_config_path(prompt_name)
        
        # Verificar que el archivo de configuración existe
        config_path = Path(context_config_path)
        if not config_path.exists():
            socketio.emit('debug', {
                'message': f"⚠️ Config '{context_config_path}' no existe. Usando default"
            }, room=session_id)
            context_config_path = DEFAULT_PROMPT_CONFIG
        
        # Definir callbacks para eventos de Nova Sonic
        def on_transcript(text):
            socketio.emit('user_transcript', {
                'text': text,
                'timestamp': datetime.datetime.now().isoformat()
            }, room=session_id)
            socketio.emit('debug', {
                'message': f'👤 Transcripción: {text[:50]}...'
            }, room=session_id)
        
        def on_audio_response(audio_base64):
            socketio.emit('audio_playback', {
                'audio': audio_base64
            }, room=session_id)
            socketio.emit('debug', {
                'message': '🔊 Audio de respuesta enviado'
            }, room=session_id)
        
        def on_debug(message):
            socketio.emit('debug', {
                'message': message
            }, room=session_id)
        
        def on_assistant_text(text):
            socketio.emit('nova_response', {
                'text': text,
                'timestamp': datetime.datetime.now().isoformat()
            }, room=session_id)

        def on_lead_snapshot(payload):
            socketio.emit('lead_snapshot', payload, room=session_id)

        def on_session_summary(summary):
            socketio.emit('lead_exported', summary or {}, room=session_id)

        def on_usage(payload):
            try:
                socketio.emit('usage_update', payload, room=session_id)
                compact = {
                    'input': payload.get('inputTokens'),
                    'output': payload.get('outputTokens'),
                    'total': payload.get('totalTokens'),
                    'cost': payload.get('estimatedCostUsd')
                }
                socketio.emit('debug', {
                    'message': f"📈 Uso: {compact}"
                }, room=session_id)
            except Exception as exc:
                socketio.emit('debug', {
                    'message': f"⚠️ Error emitiendo usage_update: {exc}"
                }, room=session_id)
        
        def on_event(event_data):
            """Maneja eventos del sistema (reconexión, errores)."""
            try:
                socketio.emit('stream_event', event_data, room=session_id)
            except Exception as exc:
                socketio.emit('debug', {
                    'message': f"⚠️ Error emitiendo stream_event: {exc}"
                }, room=session_id)
        
        # Crear y iniciar adaptador de Nova Sonic V3
        adapter = NovaSonicWebAdapterV3(
            context_config=context_config_path,
            kb_folder='kb',  # Mantener por compatibilidad
            voice=nova_voice,
            on_transcript=on_transcript,
            on_audio_response=on_audio_response,
            on_debug=on_debug,
            on_assistant_text=on_assistant_text,
            on_lead_snapshot=on_lead_snapshot,
            on_session_summary=on_session_summary,
            on_usage=on_usage,
            on_event=on_event  # Nuevo callback para eventos de sistema
        )
        
        nova_adapters[session_id] = adapter
        try:
            adapter.start()
        except Exception as exc:
            nova_adapters.pop(session_id, None)
            socketio.emit('error', {
                'message': (
                    'No se pudo iniciar la conversación con Nova Sonic. '
                    'Verifica credenciales/región AWS y vuelve a intentarlo.'
                )
            }, room=session_id)
            socketio.emit('debug', {
                'message': f'❌ Error inicializando Nova Sonic: {exc}'
            }, room=session_id)
            socketio.emit('connection_info', {
                'status': 'error',
                'message': str(exc)
            }, room=session_id)
            return
        
        emit('debug', {
            'message': '📞 Llamada iniciada - conversación fluida activada',
            'voice': voice_code,
            'nova_voice': nova_voice,
            'prompt': prompt_name,
            'model': 'amazon.nova-sonic-v1:0',
            'timestamp': data.get('timestamp')
        })
        
        emit('call_ready', {
            'timestamp': datetime.datetime.now().isoformat()
        }, room=session_id)

        emit('connection_info', {
            'model': 'amazon.nova-sonic-v1:0',
            'voice': nova_voice,
            'prompt': prompt_name,
            'status': 'connected',
            'region': adapter.region
        })
        
    except Exception as e:
        emit('error', {'message': f'Error al iniciar llamada: {str(e)}'})
        emit('debug', {
            'message': f'❌ Error al iniciar: {str(e)}',
            'error': True
        })

@socketio.on('call_ended')
def handle_call_ended(data):
    session_id = request.sid
    
    if session_id in nova_adapters:
        adapter = nova_adapters[session_id]
        adapter.stop()
        del nova_adapters[session_id]
    
    emit('debug', {
        'message': '📴 Llamada finalizada',
        'timestamp': data.get('timestamp')
    })

@socketio.on('voice_select')
def handle_voice_select(data):
    session_id = request.sid
    voice = data['voice']
    emit('debug', {
        'message': f'🗣️ Voz seleccionada: {voice} (se aplicará en la próxima llamada)'
    })

@socketio.on('prompt_select')
def handle_prompt_select(data):
    session_id = request.sid
    prompt_name = data['prompt']
    
    emit('debug', {
        'message': f'📝 Prompt seleccionado: {prompt_name} (se aplicará en la próxima llamada)'
    })

# ==================== Main ====================
if __name__ == '__main__':
    run_diagnostics()
    
    safe_print("=" * 50)
    safe_print("  Nova Sonic Interface iniciando...")
    safe_print("  Accede desde:")
    safe_print("   - Local: http://localhost:5000")
    safe_print("   - Red: http://<tu-ip>:5000")
    safe_print("=" * 50)
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
