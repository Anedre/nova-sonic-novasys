# Sistema de Contexto Dinámico - Funcionamiento Actual

## ✅ Respuesta: SÍ, el contexto cambia según el prompt seleccionado

## Cómo Funciona

### 1. **Frontend - Selector de Prompt** (`templates/index.html`)

```html
<select id="prompt-select">
    <option value="udep_original">UDEP Original</option>
    <option value="euromotors">🚗 Euromotors (Mayra)</option>
    <option value="v8_minimal">V8 Mínimo</option>
    ...
</select>
```

Usuario selecciona → Envía `prompt: 'euromotors'` en evento `call_started`

### 2. **Backend - Mapeo de Configuración** (`config/constants.py`)

```python
PROMPT_CONFIG_MAPPING = {
    'udep_original': 'config/context_udep_original.yaml',
    'euromotors': 'config/context_euromotors.yaml',  # ← NUEVO
    'v8_minimal': 'config/context_v8_minimal.yaml',
    ...
}

def get_prompt_config_path(prompt_name: str) -> str:
    """Convierte nombre de prompt → ruta del YAML"""
    return PROMPT_CONFIG_MAPPING.get(prompt_name, DEFAULT_PROMPT_CONFIG)
```

### 3. **Servidor Flask - Carga Dinámica** (`app.py`)

```python
@socketio.on('call_started')
def handle_call_started(data):
    prompt_name = data.get('prompt', 'udep')  # Recibe 'euromotors'
    
    # Obtiene la ruta: 'config/context_euromotors.yaml'
    context_config_path = get_prompt_config_path(prompt_name)
    
    # Crea adapter con el contexto específico
    adapter = NovaSonicWebAdapterV3(
        context_config=context_config_path,  # ← Pasa el YAML
        ...
    )
```

### 4. **Adapter - Carga del Contexto** (`nova_sonic_web_adapter_v3.py`)

```python
class NovaSonicWebAdapterV3:
    def __init__(self, context_config: str, ...):
        # Lee el YAML especificado
        context = load_context(context_config)
        
        # Extrae prompt y knowledge base
        system_prompt = context.get('prompt', '')
        knowledge_base = context.get('kb', {})
        
        # Crea stream manager con contexto cargado
        self._stream_manager = BedrockStreamManager(
            system_prompt=system_prompt,
            knowledge_base=knowledge_base
        )
```

### 5. **Bootstrap - Carga del YAML** (`context/bootstrap.py`)

```python
def load_context(yaml_path: str) -> dict:
    with open(yaml_path) as f:
        config = yaml.safe_load(f)
    
    sources = config.get('sources', [])
    result = {'prompt': '', 'kb': {}}
    
    for source in sources:
        if source['type'] == 'file_prompt':
            # Lee context/prompts/prompt_euromotors.txt
            result['prompt'] = read_file(source['path'])
        
        elif source['type'] == 'file_kb':
            # Lee kb/euromotors_catalog.json
            result['kb'] = read_json(source['path'])
    
    return result
```

## Flujo Completo - Ejemplo Euromotors

```
1. Usuario selecciona "Euromotors" en UI
   ↓
2. Frontend envía: socket.emit('call_started', {prompt: 'euromotors'})
   ↓
3. app.py recibe 'euromotors'
   ↓
4. get_prompt_config_path('euromotors') → 'config/context_euromotors.yaml'
   ↓
5. load_context() lee context_euromotors.yaml:
   sources:
     - type: file_prompt
       path: context/prompts/prompt_euromotors.txt
     - type: file_kb
       path: kb/euromotors_catalog.json
   ↓
6. Resultado:
   {
     'prompt': "Eres Mayra, asistente virtual de Euromotors...",
     'kb': {
       "marcas": {
         "audi": {"sedes": [...], "modelos": {...}},
         ...
       }
     }
   }
   ↓
7. BedrockStreamManager usa:
   - system_prompt de Euromotors
   - knowledge_base con catálogo de autos
   ↓
8. Nova Sonic responde como Mayra con contexto automotriz
```

## Archivos de Configuración por Prompt

| Prompt Frontend | YAML Config | Prompt TXT | Knowledge Base |
|----------------|-------------|------------|----------------|
| `udep_original` | `context_udep_original.yaml` | `udep_system_prompt_v6_2_phone_validation.txt` | `udep_catalog.json` |
| **`euromotors`** | **`context_euromotors.yaml`** | **`prompt_euromotors.txt`** | **`euromotors_catalog.json`** |
| `v8_minimal` | `context_v8_minimal.yaml` | `udep_system_prompt_v8_minimal.txt` | `udep_catalog.json` |
| `v7_conversational` | `context_v7_conversational.yaml` | `udep_system_prompt_v7_conversational.txt` | `udep_catalog.json` |

## Verificación del Sistema

### Test 1: UDEP
```bash
# 1. Seleccionar "UDEP Original" en UI
# 2. Iniciar llamada
# 3. Decir: "Hola"
# Resultado esperado: "Hola, soy Zhenia de UDEP Posgrado..."
```

### Test 2: Euromotors
```bash
# 1. Seleccionar "🚗 Euromotors (Mayra)" en UI
# 2. Iniciar llamada
# 3. Decir: "Hola"
# Resultado esperado: "Hola, soy Mayra tu Asesor Virtual Automotriz..."
```

### Test 3: Cambio de Contexto
```bash
# 1. Llamada 1: UDEP → Menciona "maestría en finanzas"
#    - Zhenia responde con info académica
# 2. Llamada 2: Euromotors → Menciona "Audi Q3"
#    - Mayra responde: "El Q3 es un SUV compacto... Tenemos sedes en Derby y Surquillo"
```

## Debug del Contexto Cargado

Agregar en `nova_sonic_web_adapter_v3.py` (temporalmente):

```python
def __init__(self, context_config: str, ...):
    context = load_context(context_config)
    
    # 🔍 DEBUG: Verificar qué contexto se cargó
    print(f"\n🔍 CONTEXTO CARGADO:")
    print(f"   Config: {context_config}")
    print(f"   Prompt primeras 100 chars: {context.get('prompt', '')[:100]}")
    print(f"   KB keys: {list(context.get('kb', {}).keys())}")
    
    if 'marcas' in context.get('kb', {}):
        print(f"   KB Marcas: {list(context['kb']['marcas'].keys())}")
    
    if 'programas' in context.get('kb', {}):
        print(f"   KB Programas: {list(context['kb']['programas'].keys())}")
    print()
```

**Salida esperada para Euromotors:**
```
🔍 CONTEXTO CARGADO:
   Config: config/context_euromotors.yaml
   Prompt primeras 100 chars: Eres Mayra, asistente virtual de la Universidad de Piura (UDEP) en Perú...
   KB keys: ['metadata', 'marcas', 'servicios', 'validaciones', ...]
   KB Marcas: ['audi', 'volkswagen', 'seat', 'porsche', 'bentley', 'lamborghini', 'revoshop', 'kyc']
```

**Salida esperada para UDEP:**
```
🔍 CONTEXTO CARGADO:
   Config: config/context_udep_original.yaml
   Prompt primeras 100 chars: Eres Zhenia, asistente virtual de la Universidad de Piura (UDEP)...
   KB keys: ['metadata', 'programas', 'modalidades', ...]
   KB Programas: ['mba_finanzas', 'maestria_data_science', 'diplomado_ciberseguridad', ...]
```

## Respuesta Final

**SÍ, el contexto CAMBIA dinámicamente según el prompt seleccionado:**

✅ Cada opción del selector carga un YAML diferente  
✅ Cada YAML apunta a prompt + KB específicos  
✅ El sistema ya estaba diseñado para multi-contexto  
✅ Solo faltaba agregar 'euromotors' al mapeo (ya agregado)  

**Ahora puedes:**
1. Seleccionar "UDEP Original" → Zhenia con KB de programas académicos
2. Seleccionar "Euromotors" → Mayra con KB de catálogo automotriz
3. Todo en el mismo servidor, sin reiniciar

**Próximo paso:** Reinicia el servidor Flask y prueba ambos contextos.
