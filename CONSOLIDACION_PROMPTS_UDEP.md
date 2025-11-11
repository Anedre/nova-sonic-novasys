# Consolidación de Prompts UDEP

## Fecha: 5 de noviembre de 2025

## Problema
Existían múltiples versiones del prompt de UDEP (v6, v6.1, v6.2, v6.3, v7, v8) con mejoras fragmentadas en cada una, dificultando:
- Mantenimiento
- Identificar cuál usar
- Evolución coherente
- Testing consistente

## Solución: Prompt Consolidado

**Archivo:** `context/prompts/udep_system_prompt_consolidated.txt`

### Estructura del Nuevo Prompt

```
1. IDENTIDAD Y ROL
   - Definición clara: Zhenia, asistente UDEP Posgrado
   - Objetivo: Captura de leads para contacto posterior

2. PRINCIPIOS DE COMUNICACIÓN
   - Naturalidad y fluidez (de v6.3)
   - Ritmo de conversación (de v8)

3. PROCESO DE CAPTURA DE DATOS
   ├─ 1. Saludo e Introducción (de v7)
   ├─ 2. Nombre Completo (v6.3 + v7)
   ├─ 3. DNI (v6.2 validación)
   ├─ 4. Teléfono (v6.2 validación reforzada)
   ├─ 5. Email (v6.2 deletreo)
   ├─ 6. Programa (v6.3 agilizado)
   ├─ 7. Modalidad (v6.3 flujo)
   ├─ 8. Horario (v6.3 flexibilidad)
   └─ 9. Consentimiento (v6.3 claridad)

4. MANEJO DE CONFIRMACIONES
   - Datos con validación: DNI, teléfono, email (ESPERA respuesta)
   - Datos sin validación: programa, modalidad, horario (puede encadenar)

5. CIERRE DE CONVERSACIÓN
   - Detección inteligente (de v6.3 - FIX crítico)
   - Anti-repetición
   - Señales de cierre

6. USO DE HERRAMIENTA guardar_lead
   - Tool use silencioso (de v6/v7)
   - Formato JSON

7. SITUACIONES ESPECIALES
   - Usuario sin tiempo
   - Correcciones
   - Preguntas sobre programas

8. LÍMITES Y RESTRICCIONES
   - Alcance definido
   - Manejo de costos
   - Redirección

9. PRINCIPIOS FINALES
   - 10 principios clave
```

## Lo Mejor de Cada Versión

### De V6.3 (udep_system_prompt_v6_3_improved.txt)
✅ **Detección inteligente de cierre** - FIX crítico de repetición  
✅ **Anti-repetición de datos** - No vuelve a preguntar lo ya confirmado  
✅ **Señales de cierre explícitas** - "nada más", "eso es todo"  
✅ **Flujo agilizado** - Encadena programa+modalidad, modalidad+horario  
✅ **Validación de teléfonos reforzada** - Conteo mental antes de confirmar  

### De V8 (udep_system_prompt_v8_minimal.txt)
✅ **Brevedad extrema** - Respuestas de 1-2 oraciones  
✅ **Ritmo ágil** - Una pregunta a la vez  
✅ **Confirmaciones cortas** - "¿Correcto?" simple  

### De V7 (udep_system_prompt_v7_conversational.txt)
✅ **Tono cálido y profesional** - "Warm and patient advisor"  
✅ **Saludo estructurado** - Presentación clara al inicio  
✅ **Explicación de límites** - Qué puede/no puede hacer  
✅ **Manejo de knowledge base** - Referencias entre ##REFERENCE_DOCS##  

### De V6.2 (udep_system_prompt_v6_2_phone_validation.txt)
✅ **Validación telefónica robusta** - Reglas de transcripción detalladas  
✅ **Ejemplos de dictado** - Casos reales documentados  
✅ **Manejo de deletreo de emails** - "anedre uno dos tres" = anedre123  

### De V6.1 y Original
✅ **Instrucciones de tool use** - Llamada silenciosa a guardar_lead  
✅ **Base de conocimientos** - Integración con KB  
✅ **Formato de datos** - Estructura JSON clara  

## Mejoras Adicionales en Consolidado

### 1. Organización Jerárquica
```
# Sección Principal
## Subsección
### Detalle

Facilita navegación y mantenimiento
```

### 2. Ejemplos Visuales
```
**Ejemplo CORRECTO:**
Tú: "Confirmo DNI..."
Usuario: "Sí"
Tú: "Perfecto. ¿Teléfono?"

**Ejemplo INCORRECTO:**
Tú: "Confirmo DNI... ¿Teléfono?" ← MAL
```

### 3. Secciones Separadas
- Comunicación separada de captura de datos
- Confirmaciones en sección propia
- Cierre como proceso independiente

### 4. Checkmarks Visuales
```
✅ SÉ HUMANA
✅ SÉ EFICIENTE
✅ SÉ EMPÁTICA
```

### 5. Formato Consistente
- **Negrita** para énfasis
- `Código` para datos técnicos
- Bullets para listas
- Números para secuencias

## Comparación de Tamaño

| Versión | Líneas | Tokens (~) | Observación |
|---------|--------|------------|-------------|
| V8 Minimal | 81 | ~600 | Muy conciso, falta detalle |
| V7 Conversational | 81 | ~650 | Buen tono, falta validación |
| V6.3 Improved | 273 | ~2,400 | Completo pero sin estructura |
| V6.2 Phone Valid | 223 | ~2,000 | Validación robusta |
| **Consolidado** | **~350** | **~3,000** | **Balance perfecto** |

## Ventajas del Consolidado

✅ **Completo:** Incluye todas las mejoras de versiones anteriores  
✅ **Estructurado:** Secciones claras con jerarquía  
✅ **Mantenible:** Fácil de actualizar secciones específicas  
✅ **Documentado:** Ejemplos y casos de uso explícitos  
✅ **Balanceado:** No es ni muy corto (v8) ni muy largo (v6.3)  
✅ **Production-ready:** Maneja todos los casos edge conocidos  

## Migración

### Antes
```yaml
# config/context_udep_original.yaml
sources:
  - type: file_prompt
    path: context/prompts/udep_system_prompt_original_v6.txt
```

### Ahora
```yaml
# config/context_udep_original.yaml
sources:
  - type: file_prompt
    path: context/prompts/udep_system_prompt_consolidated.txt
```

## Testing del Consolidado

### Test 1: Flujo Completo
```
Usuario: "Hola"
Zhenia: "Hola, soy Zhenia de UDEP Posgrado. Te ayudo a registrar tus datos..."
Usuario: "André Alata"
Zhenia: "Perfecto, André Alata"
[Continúa hasta los 8 datos]
Usuario: "Eso sería todo"
Zhenia: "Gracias a ti, André. ¡Hasta pronto!"
[NO repite "¿Hay algo más?"]
```

### Test 2: Validación de Teléfono
```
Usuario: "nueve cinco tres siete treinta uno ocho nueve"
Zhenia: [Cuenta: 9,5,3,7,3,0,1,8,9 = 9 dígitos ✓]
Zhenia: "Confirmo: 9 5 3 7 3 0 1 8 9. ¿Correcto?"
```

### Test 3: Deletreo de Email
```
Usuario: "anedre uno dos tres cuatro cinco arroba gmail com"
Zhenia: [Captura: anedre12345@gmail.com]
Zhenia: "Confirmo: anedre12345 arroba gmail punto com. ¿Correcto?"
```

### Test 4: Cierre con Datos Incompletos
```
Usuario: [solo ha dado nombre y teléfono] "Gracias, eso es todo"
Zhenia: "Antes de terminar, necesito confirmar tu DNI, email y programa..."
```

## Archivos Anteriores (Mantener para Referencia)

Los prompts anteriores se mantienen en `context/prompts/` para:
- Referencia histórica
- Comparación de evolución
- Rollback si es necesario

```
context/prompts/
├── udep_system_prompt_consolidated.txt  ← NUEVO (USAR)
├── udep_system_prompt_v6_3_improved.txt ← Referencia
├── udep_system_prompt_v6_2_phone_validation.txt ← Referencia
├── udep_system_prompt_v7_conversational.txt ← Referencia
├── udep_system_prompt_v8_minimal.txt ← Referencia
└── udep_system_prompt_original_v6.txt ← Original
```

## Próximos Pasos

1. **Testing en producción:**
   - 10-20 conversaciones con el prompt consolidado
   - Verificar métricas: turnos promedio, datos capturados, repeticiones

2. **Monitoreo:**
   - Repeticiones de preguntas
   - Fallos de validación de teléfonos
   - Cierres forzados

3. **Iteración:**
   - Si surge un fix, aplicar SOLO en consolidated
   - Documentar cambios en commits
   - No crear nuevas versiones (v9, v10...)

## Actualización del Selector

El selector de prompts en `templates/index.html` ahora usa:
```html
<option value="udep_original">UDEP Consolidado</option>
```

Que carga `config/context_udep_original.yaml` → `udep_system_prompt_consolidated.txt`

## Conclusión

**El prompt consolidado es ahora la versión canónica de UDEP.** Combina:
- ✅ La brevedad de v8
- ✅ El tono de v7
- ✅ Las validaciones de v6.2
- ✅ Los fixes de v6.3
- ✅ La estructura que faltaba

**No es necesario crear más versiones (v9, v10...).** Todos los cambios futuros se hacen **directamente** en `udep_system_prompt_consolidated.txt`.

---

**Estado:** ✅ Listo para producción  
**Archivo activo:** `context/prompts/udep_system_prompt_consolidated.txt`  
**Config activa:** `config/context_udep_original.yaml`
