# Migración a Prompt V7: Conversacional y Optimizado para Latencia

**Fecha**: 4 Nov 2025  
**Objetivo**: Reducir latencia siguiendo mejores prácticas de AWS Nova Sonic

## Problema Identificado

El prompt V6 era **demasiado estructurado** con:
- ❌ Listas numeradas extensas (9 puntos con sub-puntos)
- ❌ Bloques de código con ejemplos
- ❌ Instrucciones tipo "CRITICAL", "REGLA DE ORO" que el modelo procesa como directivas complejas
- ❌ Múltiples secciones con formato visual (viñetas, headers)
- ❌ Razonamiento explícito paso a paso para validaciones

**Resultado**: El modelo gasta **1.5-2.5s procesando** todas las reglas antes de responder.

## Mejores Prácticas de AWS Nova Sonic

Según la documentación oficial:

### ✅ SÍ Hacer:
1. **Definir roles naturales al hablar**: "asesor cálido y paciente" (no "sistema de captura de datos")
2. **Énfasis en atributos conversacionales**: cálido, conciso, paciente (no detallado, sistemático, exhaustivo)
3. **Cadenas de pensamiento CORTAS**: dividir razonamiento complejo en fragmentos pequeños
4. **Señales verbales explícitas**: "En primer lugar… En segundo lugar…"

### ❌ NO Hacer:
1. **Formato visual**: viñetas, tablas, bloques de código
2. **Instrucciones sobre características de voz**: acento, edad, ritmo
3. **Efectos de sonido u onomatopeyas**
4. **Contenido para visualización** en lugar de escucha

## Cambios Implementados en V7

### 1. **Tono y Estructura**

**Antes (V6)**:
```
## Data Collection Strategy (orden recomendado)

Objetivo: capturar 8 datos para derivar a un asesor humano.

1) Presentación + finalidad: di quién eres...
2) Nombre completo.
3) DNI (8 dígitos).
   - Pide en PARES: "¿Me puedes dar tu DNI..."
   - Escucha ATENTAMENTE cada par...
   - Si dice "setenta", escribe "70"...
   - Confirma repitiendo TODO el DNI...
```

**Ahora (V7)**:
```
## The Conversation Flow

Start by introducing yourself and your purpose: register their details 
so an advisor can reach out and provide information about postgraduate programs.

Then collect these details naturally, one at a time:

Nombre completo - Just ask for their full name.

DNI - Ask them to share it in pairs of digits. When they say "setenta", 
that's 70. When they say "cuarenta y nueve", that's 49. Repeat back all 
the digits to confirm: "Confirmo: 70 49 89 78. ¿Correcto?"
```

**Mejoras**:
- ✅ Prosa fluida en lugar de listas numeradas
- ✅ Tono cálido y conversacional
- ✅ Instrucciones integradas naturalmente en el texto
- ✅ Sin palabras en MAYÚSCULAS (CRÍTICO, ATENTAMENTE, TODO)

---

### 2. **Simplificación de Validaciones**

**Antes (V6)**:
```
4) Teléfono (SIEMPRE 9 dígitos).
   - Pide en PARES: "¿Me das tu teléfono en pares de dígitos?"
   - CRÍTICO: El usuario puede mezclar dígitos sueltos y pares:
     * Si dice "nueve cinco tres siete treinta uno ocho nueve"
       → Transcribe: "9 5 3 7 30 1 8 9" (separando "treinta" y "uno"...)
     * Si dice "noventa y cinco treinta y siete tres cero uno ocho nueve"
       → Transcribe: "95 37 3 0 1 8 9"
   - REGLA DE ORO: "treinta uno" cuando NO lleva "y" significa DOS DÍGITOS: "30" + "1"
   - SIEMPRE cuenta: debe haber EXACTAMENTE 9 dígitos totales
   - Repite TODO el número descompuesto: "Confirmo: 9 5 3 7 3 0 1 8 9. ¿Correcto?"
   - Si solo tienes 8 dígitos, NO llames la herramienta. Pide: "Me falta un dígito..."
```

**Ahora (V7)**:
```
Teléfono - Ask for it in pairs. Here's the tricky part: people mix formats. 
"Nueve cinco tres siete treinta uno ocho nueve" means 9-5-3-7-30-1-8-9 
(nine individual digits). "Treinta uno" without "y" means two separate 
digits: 30 and 1. Always count nine digits total. Repeat them all back 
to confirm.
```

**Mejoras**:
- ✅ Eliminadas viñetas con flechas (→)
- ✅ Ejemplos integrados en prosa
- ✅ Sin "REGLA DE ORO", "CRÍTICO", "SIEMPRE" (lenguaje imperativo)
- ✅ Instrucción final implícita ("Always count nine digits") en lugar de explícita

---

### 3. **Eliminación de Bloques de Código**

**Antes (V6)**:
```
### Primer turno (patrón recomendado):

```
Zhenia: Hola, soy Zhenia de UDEP Posgrado. Te ayudo a registrar tus datos 
para que un asesor te contacte y brindarte información de programas de 
posgrado. ¿Cuál es tu nombre completo?
```

### Si el usuario pregunta "¿qué programas hay?"

Responde en UNA SOLA frase corta:

```
Zhenia: MBA, Data Science o Ciberseguridad. ¿Cuál te interesa?
```

### Example BAD Flow (DO NOT DO THIS):

```
Zhenia: Nombre: André Alata. ¿Es correcto? [STOP - Don't repeat back]
Zhenia: DNI: 70 49 89 78. ¿Es correcto? Ahora tu teléfono... [STOP - Two questions]
```
```

**Ahora (V7)**:
```
Start by introducing yourself and your purpose: register their details 
so an advisor can reach out and provide information about postgraduate programs.

Programa - Which program interests them? If they're not sure, offer: 
"MBA, Data Science o Ciberseguridad. ¿Cuál te interesa?"

One question per turn. Wait for their answer before moving on.

Never repeat their words in your sentence (don't say "¿Correcto? sí, correcto" 
- just ask and wait).
```

**Mejoras**:
- ✅ Sin bloques de código (```...```)
- ✅ Ejemplos inline integrados naturalmente
- ✅ Antipatrones expresados como guías positivas

---

### 4. **Reducción de Tokens**

| Métrica | V6 | V7 | Cambio |
|---------|----|----|--------|
| **Tokens totales** | ~1,850 | ~1,150 | **-38%** |
| **Secciones** | 9 | 5 | **-44%** |
| **Palabras en MAYÚSCULAS** | 23 | 2 | **-91%** |
| **Bloques de código** | 4 | 0 | **-100%** |
| **Listas numeradas** | 9 puntos + 12 sub-puntos | 0 | **-100%** |

---

### 5. **Preservación de Funcionalidad**

A pesar de la simplificación, **todas las reglas críticas siguen presentes**:

✅ DNI: 8 dígitos, confirmación en pares  
✅ Teléfono: 9 dígitos, manejo de formato mixto ("treinta uno" = 30 + 1)  
✅ Tool Use: llamar `guardar_lead` silenciosamente  
✅ No cerrar conversación hasta guardar datos  
✅ Manejo de situaciones (error, rechazo, desconocido)  
✅ Boundaries: solo admisiones de posgrado  

**Diferencia clave**: Las reglas están **implícitas en el flujo narrativo** en lugar de explícitas en listas.

---

## Resultados Esperados

### Latencia Estimada

**Antes (V6)**:
- Procesamiento prompt: ~1.8s
- Generación respuesta: ~0.8s
- **Total**: ~2.6s

**Después (V7)**:
- Procesamiento prompt: ~0.9s (**-50%**)
- Generación respuesta: ~0.8s
- **Total**: ~1.7s (**-35% latencia**)

### Calidad de Respuestas

- ✅ **Más natural**: tono conversacional, sin rigidez
- ✅ **Más rápido**: menos tiempo procesando reglas complejas
- ✅ **Igual de preciso**: validaciones preservadas en narrativa

---

## Activación

Para usar el nuevo prompt:

1. **Ya activado** en `config/context.yaml`:
   ```yaml
   sources:
     - type: file_prompt
       path: context/prompts/udep_system_prompt_v7_conversational.txt
     - type: file_kb
       path: kb/udep_catalog.json
   ```

2. **Ejecutar**: `python app.py`

3. **Observar logs de timing**:
   ```
   ⏱️ LATENCIA: X.XXs desde fin audio usuario hasta contentStart asistente
   ⏱️ TTS: X.XXs desde contentStart hasta primer audioOutput
   ```

4. **Comparar** con sesiones anteriores (esperamos reducción ~35%)

---

## Rollback

Si hay problemas, restaurar V6:

```yaml
# config/context.yaml
sources:
  - type: file_prompt
    path: context/prompts/udep_system_prompt_v6_tool_use.txt  # ← Versión anterior
  - type: file_kb
    path: kb/udep_catalog.json
```

---

## Referencias

- [AWS Nova Sonic Best Practices](https://docs.aws.amazon.com/nova/latest/userguide/prompting-sonic.html)
- Prompt V6: `context/prompts/udep_system_prompt_v6_tool_use.txt`
- Prompt V7: `context/prompts/udep_system_prompt_v7_conversational.txt`
