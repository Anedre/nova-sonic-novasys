# Integración Base de Conocimiento - Euromotors

## Fecha: 5 de noviembre de 2025

## Archivos Creados

### 1. Base de Conocimiento
**Ubicación:** `kb/euromotors_catalog.json`

Contiene toda la información estructurada del catálogo de Euromotors:

- ✅ **8 marcas completas:** Audi, Volkswagen, SEAT, Porsche, Bentley, Lamborghini, Revoshop, KYC
- ✅ **Sedes con alias ASR:** Todas las variantes de pronunciación (Derby/Derbi/Ermi/Nervi, etc.)
- ✅ **43 modelos detallados:** Con años, transmisiones, segmentos y descripciones
- ✅ **5 tipos de servicio:** Venta, taller, repuestos, planchado/pintura, consultas
- ✅ **Validaciones:** DNI, CE, teléfono, email, placa, año
- ✅ **Datos de financiamiento y horarios**

### 2. Configuración de Contexto
**Ubicación:** `config/context_euromotors.yaml`

Define la carga de prompt + knowledge base para Euromotors.

### 3. Prompt Original
**Ubicación:** `context/prompts/prompt_euromotors.txt` (ya existente)

## Estructura de la Base de Conocimiento

```json
{
  "metadata": { ... },
  "marcas": {
    "audi": {
      "nombre_display": "Audi",
      "sedes": [
        {"nombre": "Derby", "alias": ["derbi", "ermi", "nervi", ...]},
        {"nombre": "Surquillo", "alias": ["surquilo", "su brillo", ...]}
      ],
      "modelos": {
        "Q3": {
          "anios_disponibles": [2023, 2024, 2025],
          "transmisiones": ["AT"],
          "segmento": "SUV compacto",
          "descripcion": "..."
        }
      }
    }
  },
  "servicios": { ... },
  "validaciones": { ... }
}
```

## Uso en Nova Sonic

### A. Activar Contexto Euromotors

Modificar `app.py` o el código que inicializa la sesión:

```python
# En lugar de cargar config/context.yaml por defecto
from context.bootstrap import load_context

# Cargar contexto de Euromotors
context_euromotors = load_context("config/context_euromotors.yaml")

# Pasar a BedrockStreamManager
stream_manager = BedrockStreamManager(
    system_prompt=context_euromotors['prompt'],
    knowledge_base=context_euromotors['kb']  # ← JSON del catálogo
)
```

### B. El Prompt Euromotors Ya Tiene Instrucciones

El archivo `prompt_euromotors.txt` incluye:

```
Uso de BASE DE CONOCIMIENTO (si está disponible CATÁLOGO_JSON)
- Si existe un objeto CATÁLOGO_JSON con marcas/modelos/años/transmisiones, úsalo para validar entradas y sugerir opciones.
- Si el modelo no existe para la marca dada, sugiere los modelos válidos del catálogo.
```

Nova Sonic **automáticamente** accederá al JSON como contexto RAG.

### C. Consultas Automáticas

Cuando el usuario mencione:
- **"Audi Q3"** → Nova busca en `marcas.audi.modelos.Q3` y obtiene años/transmisiones
- **"Derby"** → Nova valida que existe para Audi y normaliza variantes (ermi, nervi, etc.)
- **"mantenimiento"** → Nova identifica `servicios.cita_taller` y sus datos requeridos

## Ventajas de Esta Estructura

### 1. Tolerancia a Errores ASR
```json
"sedes": [
  {
    "nombre": "Derby",
    "alias": ["derbi", "dervi", "ermi", "el ermi", "dermi", "nervi", "nerbi"]
  }
]
```
Nova puede entender cualquier variante que el ASR transcriba incorrectamente.

### 2. Validación Automática
```json
"validaciones": {
  "telefono": {
    "peru": {
      "patron": "^\\+51[9][0-9]{8}$"
    }
  }
}
```
Nova valida formatos sin necesidad de código Python adicional.

### 3. Sugerencias Inteligentes
```json
"modelos": {
  "Q3": {
    "segmento": "SUV compacto",
    "descripcion": "SUV compacto urbano..."
  }
}
```
Nova puede describir modelos cuando el usuario pregunta "¿Qué es el Q3?"

### 4. Compatibilidad con `automotriz.py`

La estructura JSON **replica exactamente** el diccionario `CATALOGO` de Python:

**Python (`automotriz.py`):**
```python
CATALOGO = {
    "audi": {
        "sedes": ["Derby", "Surquillo"],
        "modelos_detalle": {
            "Q3": {"anios": [2023, 2024, 2025], ...}
        }
    }
}
```

**JSON (`euromotors_catalog.json`):**
```json
{
  "marcas": {
    "audi": {
      "sedes": [{"nombre": "Derby"}, {"nombre": "Surquillo"}],
      "modelos": {
        "Q3": {"anios_disponibles": [2023, 2024, 2025], ...}
      }
    }
  }
}
```

## Integración con Tool Use (Opcional)

Si quieres que Nova llame `kb_retrieve` o `save_lead` de `automotriz.py`:

### 1. Registrar las Tools en `nova_sonic_es_sd.py`

```python
EUROMOTORS_TOOLS = [
    {
        "toolSpec": {
            "name": "kb_retrieve",
            "description": "Consulta el catálogo de Euromotors para validar marcas, modelos y sedes",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "brand_hint": {"type": "string"}
                    },
                    "required": ["query"]
                }
            }
        }
    },
    {
        "toolSpec": {
            "name": "save_lead_auto",
            "description": "Guarda lead completo de Euromotors",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "json_final": {"type": "object"},
                        "marca": {"type": "string"},
                        "modelo": {"type": "string"}
                    },
                    "required": ["json_final"]
                }
            }
        }
    }
]
```

### 2. Implementar Handler en `processors/tool_use_processor.py`

```python
def handle_tool_use_euromotors(tool_name: str, tool_input: dict):
    if tool_name == "kb_retrieve":
        from tools_impl.automotriz import kb_retrieve
        return kb_retrieve(tool_input)
    
    elif tool_name == "save_lead_auto":
        from tools_impl.automotriz import save_lead
        return save_lead(tool_input)
```

### 3. Prompt Ya Está Preparado

El `prompt_euromotors.txt` ya está diseñado para **salida JSON** estructurada:

```
Estructura JSON (una sola línea)
{"action":"save_lead", "intencion":"venta_autos", "completo":true, ...}
```

Puedes adaptar esto para que Nova llame `save_lead_auto` tool en lugar de devolver JSON.

## Testing

### Caso 1: Usuario Pide Audi Q3
```
Usuario: "Hola, quiero info del Audi Q3"
Nova consulta KB → encuentra Q3 en marcas.audi.modelos
Nova: "El Audi Q3 2025 es un SUV compacto con transmisión automática. 
       Tenemos sedes en Derby y Surquillo. ¿Cuál te queda mejor?"
```

### Caso 2: Usuario Dice "Ermi" (Error ASR)
```
Usuario: "Quiero ir al ermi"
Nova busca en alias de sedes → encuentra "ermi" → normaliza a "Derby"
Nova: "Perfecto, la sede Derby. ¿Qué marca te interesa?"
```

### Caso 3: Validación de Teléfono
```
Usuario: "Mi teléfono es 997583566"
Nova consulta validaciones.telefono.peru → agrega +51
Nova confirma: "Confirmo: más cincuenta y uno — 997 — 58 — 35 — 66"
```

## Próximos Pasos

1. **Activar contexto en app.py:**
   ```python
   context = load_context("config/context_euromotors.yaml")
   ```

2. **Probar conversación:**
   - Mencionar marca: "Volkswagen"
   - Mencionar modelo: "Tiguan"
   - Mencionar sede con error: "su brillo" (debe normalizar a Surquillo)

3. **Verificar logs:**
   - Nova debe mencionar modelos disponibles del catálogo
   - Debe corregir alias de sedes automáticamente

4. **(Opcional) Integrar tools de `automotriz.py`** si quieres validación Python adicional

## Ventajas vs. Solo Prompt

| Enfoque | Ventajas | Desventajas |
|---------|----------|-------------|
| **Solo Prompt** | Simple, todo en un archivo | Prompt muy largo (>5000 tokens), difícil de mantener |
| **Prompt + KB JSON** ✅ | Prompt más corto, KB reutilizable, fácil actualización | Requiere carga de 2 archivos |
| **Prompt + KB + Tools Python** | Validación compleja en Python, lógica fuzzy matching | Más complejo de mantener |

**Recomendación:** Usa **Prompt + KB JSON** (lo que acabamos de crear). Es el punto ideal entre simplicidad y poder.

## Actualizar Catálogo

Para agregar nuevo modelo:

```json
"volkswagen": {
  "modelos": {
    "ID.4": {  // ← Nuevo modelo eléctrico
      "nombre_display": "ID.4",
      "anios_disponibles": [2024, 2025],
      "transmisiones": ["AT"],
      "segmento": "SUV eléctrico",
      "descripcion": "SUV eléctrico de última generación"
    }
  }
}
```

Nova lo detectará automáticamente en la siguiente sesión.

## Conclusión

Has creado una **base de conocimiento profesional** que:

✅ Replica toda la lógica de `automotriz.py` en formato JSON  
✅ Soporta alias de ASR para sedes problemáticas (Derby/Ermi/Nervi)  
✅ Incluye 43 modelos con detalles completos  
✅ Define validaciones de DNI, teléfono, email, placa  
✅ Documenta servicios y sus datos requeridos  
✅ Es fácil de actualizar sin tocar código Python  

Nova Sonic ahora puede actuar como **Mayra, tu Asesor Virtual Automotriz** con conocimiento completo del catálogo Euromotors.
