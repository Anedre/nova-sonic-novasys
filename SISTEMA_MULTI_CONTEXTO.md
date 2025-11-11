# Sistema Multi-Contexto - UDEP y Euromotors

## Problema
Actualmente el sistema carga un solo contexto (`config/context.yaml`). Necesitamos soportar múltiples contextos para diferentes clientes:
- **UDEP:** Captura de leads educativos
- **Euromotors:** Captura de leads automotrices

## Solución: Selector de Contexto en Frontend

### Opción 1: Selector en UI (Recomendado)

Agregar dropdown en `templates/index.html`:

```html
<!-- Después del selector de voz -->
<div class="control-group">
    <label for="context-selector">Cliente:</label>
    <select id="context-selector" class="form-control">
        <option value="udep">UDEP Posgrado</option>
        <option value="euromotors">Euromotors</option>
    </select>
</div>
```

**JavaScript en `static/app.js`:**

```javascript
// Al iniciar llamada, enviar contexto seleccionado
socket.emit('call_started', {
    voice: selectedVoice,
    prompt: selectedPrompt,
    context: document.getElementById('context-selector').value  // ← Nuevo
});
```

### Opción 2: URL Parameter

```
http://localhost:5000/?context=euromotors
http://localhost:5000/?context=udep
```

```javascript
// app.js
const urlParams = new URLSearchParams(window.location.search);
const context = urlParams.get('context') || 'udep';
```

## Modificaciones en Backend

### 1. Actualizar `app.py`

```python
# Agregar al inicio
AVAILABLE_CONTEXTS = {
    'udep': 'config/context.yaml',
    'euromotors': 'config/context_euromotors.yaml'
}

@socketio.on('call_started')
def handle_call_started(data):
    session_id = request.sid
    voice = data.get('voice', 'lupe')
    prompt_name = data.get('prompt', 'v6_tool_use')
    context_name = data.get('context', 'udep')  # ← Nuevo parámetro
    
    # Cargar contexto dinámicamente
    context_file = AVAILABLE_CONTEXTS.get(context_name, AVAILABLE_CONTEXTS['udep'])
    context = load_context(context_file)
    
    print(f"[{session_id}] Iniciando sesión con contexto: {context_name}")
    
    # Crear adapter con contexto específico
    adapter = NovaSonicWebAdapterV3(
        voice=voice_mapping[voice],
        system_context=context,  # ← Pasar contexto completo
        session_metadata={'context': context_name, 'client': context_name}
    )
    
    nova_adapters[session_id] = adapter
    # ... resto del código
```

### 2. Actualizar `nova_sonic_web_adapter_v3.py`

```python
class NovaSonicWebAdapterV3:
    def __init__(
        self,
        voice: str = "lupe",
        system_context: dict = None,  # ← Nuevo parámetro
        session_metadata: dict = None
    ):
        self._voice = voice
        self._session_metadata = session_metadata or {}
        
        # Cargar contexto (prompt + knowledge base)
        if system_context:
            system_prompt = system_context.get('prompt', '')
            knowledge_base = system_context.get('kb', {})
        else:
            # Fallback a UDEP por defecto
            from context.bootstrap import load_context
            ctx = load_context('config/context.yaml')
            system_prompt = ctx['prompt']
            knowledge_base = ctx['kb']
        
        # Crear stream manager con contexto
        self._stream_manager = BedrockStreamManager(
            system_prompt=system_prompt,
            knowledge_base=knowledge_base,
            session_metadata=self._session_metadata
        )
```

### 3. Actualizar `nova_sonic_es_sd.py`

```python
class BedrockStreamManager:
    def __init__(
        self,
        system_prompt: str = "",
        knowledge_base: dict = None,  # ← Nuevo parámetro
        session_metadata: dict = None
    ):
        self.system_prompt = system_prompt
        self.knowledge_base = knowledge_base or {}
        self.session_metadata = session_metadata or {}
        
        # Detectar cliente y cargar tools específicas
        client_type = self.session_metadata.get('client', 'udep')
        
        if client_type == 'euromotors':
            self.tool_config = self._load_euromotors_tools()
        else:
            self.tool_config = self.DEFAULT_TOOL_SPEC  # UDEP
    
    def _load_euromotors_tools(self):
        """Tools específicas para Euromotors"""
        return {
            "tools": [
                {
                    "toolSpec": {
                        "name": "guardar_lead_auto",
                        "description": "Guarda lead automotriz con marca, modelo y sede",
                        "inputSchema": {
                            "json": {
                                "type": "object",
                                "properties": {
                                    "nombre_completo": {"type": "string"},
                                    "telefono": {"type": "string"},
                                    "marca": {"type": "string"},
                                    "modelo": {"type": "string"},
                                    "local_preferido": {"type": "string"},
                                    "intencion": {"type": "string"}
                                },
                                "required": ["nombre_completo", "telefono", "marca"]
                            }
                        }
                    }
                }
            ]
        }
```

### 4. Actualizar `processors/tool_use_processor.py`

```python
class ToolUseProcessor:
    def __init__(self, session_metadata: dict = None):
        self.session_metadata = session_metadata or {}
        self.client_type = self.session_metadata.get('client', 'udep')
    
    def handle_tool_use(self, tool_name: str, tool_input: dict):
        # Routing según cliente
        if self.client_type == 'euromotors':
            return self._handle_euromotors_tool(tool_name, tool_input)
        else:
            return self._handle_udep_tool(tool_name, tool_input)
    
    def _handle_euromotors_tool(self, tool_name: str, tool_input: dict):
        if tool_name == "guardar_lead_auto":
            from tools_impl.automotriz import save_lead
            return save_lead(tool_input)
        return {"error": "Unknown tool"}
    
    def _handle_udep_tool(self, tool_name: str, tool_input: dict):
        if tool_name == "guardar_lead":
            # Lógica actual de UDEP
            return self._save_udep_lead(tool_input)
        return {"error": "Unknown tool"}
```

## Frontend Mejorado

### HTML (`templates/index.html`)

```html
<div class="context-selector-container">
    <h3>Selecciona Cliente</h3>
    <div class="context-cards">
        <div class="context-card" data-context="udep">
            <img src="/static/images/udep-logo.png" alt="UDEP">
            <h4>UDEP Posgrado</h4>
            <p>Zhenia - Captura de leads educativos</p>
        </div>
        <div class="context-card active" data-context="euromotors">
            <img src="/static/images/euromotors-logo.png" alt="Euromotors">
            <h4>Euromotors</h4>
            <p>Mayra - Asistente automotriz</p>
        </div>
    </div>
</div>
```

### CSS (`static/style.css`)

```css
.context-cards {
    display: flex;
    gap: 20px;
    margin-bottom: 30px;
}

.context-card {
    flex: 1;
    padding: 20px;
    border: 2px solid #ddd;
    border-radius: 10px;
    cursor: pointer;
    transition: all 0.3s;
    text-align: center;
}

.context-card:hover {
    border-color: #007bff;
    transform: translateY(-5px);
    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
}

.context-card.active {
    border-color: #007bff;
    background-color: #f0f8ff;
}

.context-card img {
    max-width: 100px;
    margin-bottom: 10px;
}
```

### JavaScript (`static/app.js`)

```javascript
let selectedContext = 'udep';

// Selector de contexto
document.querySelectorAll('.context-card').forEach(card => {
    card.addEventListener('click', () => {
        document.querySelectorAll('.context-card').forEach(c => c.classList.remove('active'));
        card.classList.add('active');
        selectedContext = card.dataset.context;
        
        // Actualizar voces/prompts disponibles según contexto
        updateAvailableOptions(selectedContext);
    });
});

function updateAvailableOptions(context) {
    if (context === 'euromotors') {
        // Cambiar a voz femenina profesional
        document.getElementById('voice-selector').value = 'es-ES-Female';
        // Ocultar selector de prompts (solo hay uno)
        document.getElementById('prompt-selector-container').style.display = 'none';
    } else {
        // Restaurar opciones UDEP
        document.getElementById('prompt-selector-container').style.display = 'block';
    }
}

// Al iniciar llamada
function startCall() {
    socket.emit('call_started', {
        voice: selectedVoice,
        prompt: selectedPrompt,
        context: selectedContext  // ← Enviar contexto
    });
}
```

## Exportación de Leads Diferenciada

```python
# En app.py - al guardar leads
@socketio.on('save_lead')
def handle_save_lead(data):
    session_id = request.sid
    adapter = nova_adapters.get(session_id)
    
    if adapter:
        context = adapter._session_metadata.get('context', 'udep')
        
        # Guardar en carpeta específica
        lead_dir = f"leads/{context}"
        os.makedirs(lead_dir, exist_ok=True)
        
        filename = f"{lead_dir}/lead_{session_id}_{int(time.time())}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"Lead guardado: {filename}")
```

## Estructura de Carpetas Final

```
UDEP/
├── config/
│   ├── context.yaml              # UDEP (por defecto)
│   └── context_euromotors.yaml   # Euromotors
├── kb/
│   ├── udep_catalog.json         # Programas académicos
│   └── euromotors_catalog.json   # Catálogo automotriz
├── context/
│   └── prompts/
│       ├── udep_system_prompt_v6_3_improved.txt
│       └── prompt_euromotors.txt
├── leads/
│   ├── udep/
│   │   ├── lead_xxx.json
│   │   └── lead_yyy.json
│   └── euromotors/
│       ├── lead_zzz.json
│       └── lead_www.json
├── tools_impl/
│   ├── udep.py                   # Tools de UDEP
│   └── automotriz.py             # Tools de Euromotors
└── app.py
```

## Testing

### Test 1: UDEP
```
1. Seleccionar "UDEP Posgrado"
2. Iniciar llamada
3. Usuario: "Hola"
4. Zhenia: "Hola, soy Zhenia de UDEP Posgrado..."
5. Verificar: Lead guardado en leads/udep/
```

### Test 2: Euromotors
```
1. Seleccionar "Euromotors"
2. Iniciar llamada
3. Usuario: "Hola"
4. Mayra: "Hola, soy Mayra tu Asesor Virtual Automotriz..."
5. Mencionar: "Audi Q3"
6. Verificar: Mayra menciona sedes Derby/Surquillo
7. Verificar: Lead guardado en leads/euromotors/
```

## Ventajas de Esta Arquitectura

✅ **Escalable:** Agregar nuevos clientes solo requiere nuevo YAML + KB  
✅ **Aislado:** Cada cliente tiene su contexto, prompts y tools separados  
✅ **Fácil testing:** Cambiar entre contextos sin reiniciar servidor  
✅ **Organizado:** Leads separados por cliente  
✅ **Mantenible:** Modificar un cliente no afecta a otros  

## Próximos Pasos

1. Implementar selector de contexto en frontend
2. Modificar `app.py` para aceptar parámetro `context`
3. Probar ambos flujos (UDEP y Euromotors)
4. Agregar logos de clientes en UI
5. Configurar analytics por cliente

## Conclusión

Con esta arquitectura puedes **gestionar múltiples clientes** en el mismo sistema Nova Sonic, cada uno con:
- Su propio prompt personalizado
- Su propia base de conocimiento
- Sus propias tools de captura
- Sus propios leads separados

**Es production-ready y fácil de escalar a más clientes en el futuro.**
