# Migración a Tool Use - Nova Sonic UDEP

## Cambios Implementados (31 Oct 2025)

### ✅ Problema Resuelto

**Anterior**: Captura de datos mediante JSON silencioso embebido en texto del asistente
- ❌ DNI y modalidad se perdían frecuentemente
- ❌ Teléfono mal parseado (9537301899 en lugar de 953730189)
- ❌ Nombre contaminado con muletillas ("Eh Llamo André Alata")
- ❌ Email con texto del asistente ("perfectotomtucorreocomoanedre12345@gmail.com")
- ❌ Modelo combinaba confirmación + nueva pregunta

**Nuevo**: Captura mediante Tool Use nativo de AWS Nova Sonic
- ✅ Nova Sonic llama automáticamente herramienta `guardar_lead` cuando tiene datos completos
- ✅ Validación de esquema en el lado del modelo (8 dígitos DNI, 9 dígitos teléfono, email válido)
- ✅ Processor limpio que solo maneja tool execution, sin parsing complejo
- ✅ Prompt simplificado y conversacional (sin instrucciones de formato JSON)

### Archivos Nuevos

1. **`processors/tool_use_processor.py`**
   - Reemplaza PERulesV1
   - Maneja `handle_tool_use()` para ejecutar herramienta guardar_lead
   - Valida y normaliza datos capturados
   - Exporta JSON al final de sesión

2. **`context/prompts/udep_system_prompt_v6_tool_use.txt`**
   - Prompt conversacional y natural
   - Sin instrucciones de JSON manual
   - Enfoque en UX: "conversación natural, no formulario robótico"
   - Reglas claras: una pregunta por turno, escuchar activamente

### Archivos Modificados

1. **`nova_sonic_es_sd.py`**
   - Añadido `GUARDAR_LEAD_TOOL` con schema JSON completo
   - Cambiado `START_PROMPT_EVENT` → `START_PROMPT_EVENT_TEMPLATE` para inyectar tools
   - Añadidos templates: `TOOL_RESULT_CONTENT_START`, `TOOL_RESULT_EVENT`
   - Método `_execute_and_send_tool_result()` para manejar tool use/result
   - Eventos `toolUse` y `contentEnd(type=TOOL)` en `_process_responses()`
   - Cambio de processor por defecto: `PERulesV1()` → `ToolUseProcessor()`

2. **`nova_sonic_web_adapter_v3.py`**
   - Import cambiado: `PERulesV1` → `ToolUseProcessor`
   - Añadido `handle_tool_use()` en `_WebAdapterProcessor`
   - Delegate usa `ToolUseProcessor` en `_bootstrap()`

3. **`config/context.yaml`**
   - Prompt actualizado: `udep_system_prompt_v5_speech.txt` → `udep_system_prompt_v6_tool_use.txt`

### Archivos Deprecados (movidos a `_archive/`)

- `processors/per_rules_v1.py` → `per_rules_v1.py.OLD`
- `context/prompts/udep_system_prompt.txt`
- `context/prompts/udep_system_prompt_v5_speech.txt`
- `udep_prompt.txt`
- `backup.txt`
- `nova_sonic_gui.py`
- Sesiones JSON antiguas (excepto última)

## Cómo Funciona Ahora

### Flujo de Tool Use

```
1. Usuario habla → Nova Sonic transcribe
2. Nova Sonic hace preguntas naturales (sin leer lista de campos)
3. Cuando tiene los 8 datos requeridos, Nova Sonic LLAMA guardar_lead tool
4. ToolUseProcessor valida datos y retorna success/error
5. Nova Sonic recibe confirmación y continúa conversación
6. Al final de sesión, lead se exporta a JSON
```

### Definición de Herramienta

```json
{
  "toolSpec": {
    "name": "guardar_lead",
    "description": "Guarda los datos del prospecto cuando tienes toda la información...",
    "inputSchema": {
      "json": {
        "type": "object",
        "properties": {
          "nombre_completo": {"type": "string"},
          "dni": {"type": "string", "pattern": "^[0-9]{8}$"},
          "telefono": {"type": "string", "pattern": "^[0-9]{9}$"},
          "email": {"type": "string", "format": "email"},
          "programa_interes": {"type": "string", "enum": ["MBA", ...]},
          "modalidad_preferida": {"type": "string", "enum": ["presencial", "hibrida", "online"]},
          "horario_preferido": {"type": "string", "enum": ["entre_semana", "fin_de_semana", ...]},
          "consentimiento": {"type": "string", "enum": ["si", "no"]}
        },
        "required": ["nombre_completo", "dni", "telefono", "email", ...]
      }
    }
  }
}
```

### Ejemplo de Conversación Mejorada

**Anterior (v5)**:
```
Zhenia: Nombre: André Alata. ¿Es correcto?
Usuario: Sí
Zhenia: DNI: 70 49 89 78. ¿Es correcto? Ahora tu teléfono...  [❌ Dos preguntas]
```

**Nuevo (v6)**:
```
Zhenia: ¿Cuál es tu nombre completo?
Usuario: André Alata
Zhenia: ¿Y tu número de contacto?
Usuario: nueve cinco tres, siete tres cero, uno ocho nueve
Zhenia: ¿Tu correo electrónico?
...
[Cuando tiene todo, tool use automático]
Zhenia: Perfecto, André. Un asesor se comunicará contigo pronto.
```

## Testing

### Probar Localmente

```bash
cd e:\TRABAJO\NOVASONIC\UDEP
python app.py
```

Abrir http://localhost:5000 y:
1. Iniciar llamada
2. Proporcionar los 8 datos naturalmente
3. Verificar que JSON exportado tiene todos los campos correctos
4. Confirmar que NO hay campos null (excepto casos válidos)

### Validar Tool Use

En logs deberías ver:
```
🔧 Tool use: guardar_lead (ID: abc123...)
✅ Tool result: {"status": "success", ...}
✅ Lead exportado: leads_session_YYYYMMDD-HHMMSS_xxxxx.json
```

## Próximos Pasos

- [ ] Probar sesión completa end-to-end
- [ ] Validar que DNI y modalidad ya no se pierdan
- [ ] Confirmar que teléfono tiene exactamente 9 dígitos
- [ ] Verificar que nombre está limpio (sin "Eh", "Llamo", etc.)
- [ ] Asegurar que email no tiene prefijos del asistente

## Rollback (si es necesario)

Si tool use no funciona, revertir a v5:

```bash
# Restaurar processor antiguo
Move-Item processors\per_rules_v1.py.OLD processors\per_rules_v1.py

# Restaurar prompt antiguo en config
# Editar config/context.yaml:
#   path: context/prompts/udep_system_prompt_v5_speech.txt

# Restaurar imports en nova_sonic_web_adapter_v3.py
# Cambiar: ToolUseProcessor → PERulesV1
```

## Referencias

- AWS Nova Sonic Tool Use: https://docs.aws.amazon.com/bedrock/latest/userguide/tool-use.html
- Amazon Nova Samples: https://github.com/aws-samples/amazon-nova-samples
- Conversation best practices: Prompt v6 comments
