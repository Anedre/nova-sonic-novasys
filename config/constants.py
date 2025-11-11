# config/constants.py
"""
Configuración centralizada para Nova Sonic UDEP.
Contiene mapeos de voz/prompt, umbrales y constantes del sistema.
"""
import os

# ==================== Mapeos de Voz ====================
# Frontend voice codes → Nova Sonic voice IDs
VOICE_MAPPING = {
    'es-ES-Female': 'lupe',   # Español Perú (recomendado)
    'es-ES-Male': 'sergio',   # Español España
    'es-MX-Female': 'mia',    # Español México
    'es-US-Female': 'lupe'    # Español US (fallback a Perú)
}

DEFAULT_VOICE = 'lupe'

# ==================== Mapeos de Prompts ====================
# Frontend prompt names → context config YAML paths
PROMPT_CONFIG_MAPPING = {
    'udep_original': 'config/context_udep_original.yaml',
    'simple_test': 'config/context_simple_test.yaml',
    'v8_minimal': 'config/context_v8_minimal.yaml',
    'v7_conversational': 'config/context_v7_conversational.yaml',
    'v6_structured': 'config/context_v6_structured.yaml',
    'udep': 'config/context_udep_original.yaml',  # Legacy alias
    'euromotors': 'config/context_euromotors.yaml'  # Euromotors - Mayra asistente automotriz
}

DEFAULT_PROMPT_CONFIG = 'config/context_v8_minimal.yaml'

# ==================== Audio Configuration ====================
# PCM settings para Nova Sonic
INPUT_SAMPLE_RATE = 16000   # Hz (mic input to Nova)
OUTPUT_SAMPLE_RATE = 24000  # Hz (Nova TTS output)
CHANNELS = 1                # Mono
PCM_SAMPLE_WIDTH = 2        # 16-bit

# Captura de audio
CAPTURE_SLICE_MS = 250      # MediaRecorder timeslice (ms)
PCM_CHUNK_SIZE = 3200       # ~100ms @ 16kHz mono 16-bit

# Decoder FFmpeg
WEBM_INIT_BUFFER_BYTES = int(os.getenv('NOVA_SONIC_WEBM_INIT_BYTES', '16384'))  # 16KB
WEBM_INIT_TIMEOUT_SECONDS = float(os.getenv('NOVA_SONIC_WEBM_TIMEOUT_S', '2.0'))
DECODER_MAX_BUFFER_BYTES = 4 * 1024 * 1024  # 4MB límite seguridad

# Queue backpressure
AUDIO_INPUT_QUEUE_MAX_SIZE = 50  # ~5 segundos @ 100ms chunks

# ==================== VAD y Silencios ====================
# Timeout de silencio para detectar fin de turno automático
SILENCE_TIMEOUT_DEFAULT = float(os.getenv('NOVA_SONIC_SILENCE_TIMEOUT_DEFAULT', '0.8'))  # 800ms
SILENCE_TIMEOUT_FAST = float(os.getenv('NOVA_SONIC_SILENCE_TIMEOUT_FAST', '0.5'))      # 500ms para DNI/teléfono

# Umbral de amplitud para detección de silencio (legacy, Nova hace su propio VAD)
SILENCE_PEAK_THRESHOLD = int(os.getenv('NOVA_SONIC_SILENCE_PEAK', '800'))
SILENCE_MAX_CHUNKS = int(os.getenv('NOVA_SONIC_SILENCE_WINDOW', '20'))

# ==================== Tarifas y Métricas ====================
# Nova Sonic v1:0 pricing (USD por 1K tokens)
TOKEN_COST_INPUT = 0.0006   # $0.0006 per 1K input tokens
TOKEN_COST_OUTPUT = 0.0024  # $0.0024 per 1K output tokens

# ==================== Tool Use y Validación ====================
# Longitudes esperadas para campos
DNI_LENGTH = 8              # Perú
PHONE_LENGTH = 9            # Perú (celular)

# Carpeta de exportación de leads
LEADS_EXPORT_FOLDER = 'leads'

# ==================== AWS Configuration ====================
DEFAULT_AWS_REGION = 'us-east-1'
NOVA_SONIC_MODEL_ID = 'amazon.nova-sonic-v1:0'

# ==================== Debug y Logging ====================
DEBUG_MODE = os.getenv('NOVA_SONIC_DEBUG', 'false').lower() in {'1', 'true', 'yes', 'y'}
DIAGNOSTICS_MODE = os.getenv('NOVA_SONIC_DIAGNOSTICS', 'false').lower() in {'1', 'true', 'yes', 'y'}

# Límite de mensajes en panel de debug del frontend
MAX_DEBUG_MESSAGES = 350

# ==================== Utilidades ====================
def get_voice_id(frontend_code: str) -> str:
    """Convierte código de voz del frontend a voice ID de Nova."""
    return VOICE_MAPPING.get(frontend_code, DEFAULT_VOICE)

def get_prompt_config_path(prompt_name: str) -> str:
    """Obtiene ruta de configuración de prompt o default."""
    return PROMPT_CONFIG_MAPPING.get(prompt_name.lower(), DEFAULT_PROMPT_CONFIG)

def calculate_token_cost(input_tokens: int, output_tokens: int) -> float:
    """Calcula costo estimado en USD dado contadores de tokens."""
    input_cost = (float(input_tokens) / 1000.0) * TOKEN_COST_INPUT
    output_cost = (float(output_tokens) / 1000.0) * TOKEN_COST_OUTPUT
    return round(float(input_cost + output_cost), 6)

def mask_pii(value: str, mask_char: str = '*', show_last: int = 2) -> str:
    """Enmascara datos sensibles mostrando solo últimos N caracteres."""
    if not value or len(value) <= show_last:
        return mask_char * len(value) if value else ''
    visible = value[-show_last:]
    masked_len = len(value) - show_last
    return (mask_char * masked_len) + visible
