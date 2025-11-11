# FIX VALIDACIÓN TELÉFONOS - v6.2

**Fecha**: 2025-01-05
**Versión**: v6.2
**Archivo**: `context/prompts/udep_system_prompt_v6_2_phone_validation.txt`

## Problema Detectado

En la conversación del lead André Alata (session 20251105-150700):

- **Usuario dijo**: "nueve cinco tres siete treinta uno ocho nueve"
- **Sistema interpretó**: "9 5 3 7 3 1 8 9" (8 dígitos)
- **Debió interpretar**: "9 5 3 7 3 0 1 8 9" (9 dígitos)
- **Resultado**: Teléfono guardado como `null` porque el validador rechaza números con != 9 dígitos

### Causa Raíz

El prompt v6.1 tenía instrucciones correctas pero **NO LAS APLICABA**:

```
"treinta uno" SIN "y" después = 30 + 1 (tres dígitos separados: 3, 0, 1)
"treinta y uno" CON "y" = 31 (dos dígitos juntos: 3, 1)
```

Nova Sonic interpretó **"treinta uno"** como **31** (2 dígitos) cuando debió ser **3, 0, 1** (3 dígitos).

**El problema**: La instrucción estaba en medio de un bloque largo de ejemplos. El modelo no le dio suficiente peso.

## Solución Implementada en v6.2

### 1. Sección de Reglas de Transcripción Explícitas (NUEVO)

Agregué un bloque **"REGLAS DE TRANSCRIPCIÓN (MEMORÍZALAS):"** en la parte superior de la sección de teléfono:

```
**REGLAS DE TRANSCRIPCIÓN (MEMORÍZALAS):**
- "noventa y cinco" = 9 y 5 (DOS dígitos: 9, 5)
- "novecientos cincuenta y tres" = 9, 5 y 3 (TRES dígitos: 9, 5, 3)
- "treinta" solo = 3 y 0 (DOS dígitos: 3, 0)
- "treinta uno" (sin "y" entre medias) = 3, 0, 1 (TRES dígitos: 3, 0, 1) ← CRÍTICO
- "treinta y uno" (con "y") = 3 y 1 (DOS dígitos: 3, 1)
- "treinta y un" (apócope) = 3 y 1 (DOS dígitos: 3, 1)
- "cuarenta y cinco" = 4 y 5 (DOS dígitos: 4, 5)
- "setenta y ocho" = 7 y 8 (DOS dígitos: 7, 8)
- "nueve", "tres", "siete" = UN dígito cada uno
```

**Ventaja**: Formato de lista con **marcadores visuales explícitos** (DOS dígitos, TRES dígitos) para que el modelo lo memorice mejor.

### 2. Ejemplos Completos con Anotaciones de Conteo

Agregué ejemplos con **conteo explícito de dígitos y validación visual**:

```
**Ejemplos completos:**
* Usuario: "nueve cinco tres cuatro cinco seis siete ocho nueve"
  → Transcripción: 9, 5, 3, 4, 5, 6, 7, 8, 9 (9 dígitos) ✓

* Usuario: "noventa y cinco treinta cuatro cincuenta y seis setenta y ocho nueve"
  → Transcripción: 9, 5, 3, 0, 4, 5, 6, 7, 8, 9 (10 dígitos) ✗ → PEDIR REPETIR

* Usuario: "nueve cinco tres siete treinta uno ocho nueve"
  → Transcripción: 9, 5, 3, 7, 3, 0, 1, 8, 9 (9 dígitos) ✓
  → Confirma: "Confirmo: 9 5 3 7 3 0 1 8 9. ¿Correcto?"

* Usuario: "nueve cinco tres siete treinta y uno ocho nueve"
  → Transcripción: 9, 5, 3, 7, 3, 1, 8, 9 (8 dígitos) ✗ → PEDIR REPETIR
```

**Ventaja**: Ejemplo **EXACTO** del caso fallido (treinta uno vs treinta y uno) con **anotación de conteo** para reforzar.

### 3. Validación en Dos Pasos (CRÍTICO - NUEVO)

Agregué proceso de validación **ANTES** de confirmar:

```
**VALIDACIÓN EN DOS PASOS (CRÍTICO):**

**PASO 1 - CONTEO MENTAL ANTES DE CONFIRMAR:**
- Después de escuchar el número, cuenta MENTALMENTE cuántos dígitos transcribiste
- Si NO son exactamente 9 dígitos:
  * NO confirmes el número
  * Di: "Me parece que son [N] dígitos. Para teléfonos peruanos necesito 9. ¿Puedes repetir el número completo, por favor?"
- Si son exactamente 9 dígitos, continúa al PASO 2

**PASO 2 - CONFIRMACIÓN DÍGITO POR DÍGITO:**
- Confirma diciendo los 9 dígitos UNO POR UNO, separados con pausas: "Confirmo: 9 5 3 7 3 0 1 8 9. ¿Correcto?"
- **ESPERA la respuesta del usuario. NO hagas otra pregunta en el mismo turno.**
- Si el usuario dice "sí", "correcto", "eso es", continúa
- Si el usuario dice "no" o corrige, escucha el número completo nuevamente y repite PASO 1
```

**Ventaja**: 
- **Pre-validación**: Si el modelo cuenta mal (como en el caso de André), NO confirma y pide repetir
- **Confirmación explícita**: Dice los dígitos UNO POR UNO para que el usuario detecte errores
- **Protección doble**: Si el modelo se equivoca en el conteo, el usuario puede corregir en la confirmación

### 4. Recordatorio Final Reforzado

Agregué al final de la sección:

```
**IMPORTANTE:**
- Los teléfonos peruanos SIEMPRE tienen 9 dígitos
- Si el conteo no da 9, NO confirmes y pide repetir
- NO asumas dígitos faltantes
- NO inventes dígitos para completar 9
```

**Ventaja**: Cierre enfático con reglas absolutas (SIEMPRE, NO asumas, NO inventes).

## Cambios en Principios Finales

Agregué al final del prompt:

```
- **VALIDA TELÉFONOS**: SIEMPRE cuenta los dígitos ANTES de confirmar (deben ser exactamente 9)
```

Para reforzar la validación como **principio fundamental** del sistema.

## Impacto Esperado

### Antes (v6.1)
- Usuario: "nueve cinco tres siete treinta uno ocho nueve"
- Sistema: "Confirmo: 9 5 3 7 3 1 8 9. ¿Correcto?" (8 dígitos)
- Usuario: "Sí correcto"
- Sistema: Guarda `null` porque validador rechaza 8 dígitos

### Después (v6.2)
- Usuario: "nueve cinco tres siete treinta uno ocho nueve"
- Sistema: *[conteo mental: 9, 5, 3, 7, 3, 0, 1, 8, 9 = 9 dígitos ✓]*
- Sistema: "Confirmo: 9 5 3 7 3 0 1 8 9. ¿Correcto?"
- Usuario: "Sí correcto"
- Sistema: Guarda `"telefono": "953730189"` ✓

**Ventaja adicional**: Si el modelo sigue contando mal:
- Sistema: *[conteo mental: 9, 5, 3, 7, 3, 1, 8, 9 = 8 dígitos ✗]*
- Sistema: "Me parece que son 8 dígitos. Para teléfonos peruanos necesito 9. ¿Puedes repetir el número completo, por favor?"
- Usuario repite claramente
- **Protección**: NO se guarda un número incorrecto

## Testing Recomendado

Probar con estos casos:

1. **"treinta uno" sin "y"**: "nueve cinco tres siete treinta uno ocho nueve" → debe dar 9 dígitos
2. **"treinta y uno" con "y"**: "nueve cinco tres siete treinta y uno nueve" → debe dar 8 dígitos y pedir repetir
3. **Todos individuales**: "nueve ocho siete seis cinco cuatro tres dos uno" → 9 dígitos ✓
4. **Mezclados**: "noventa y cinco tres siete cuarenta y cinco ochenta y nueve" → verificar conteo correcto

## Archivos Modificados

1. **NUEVO**: `context/prompts/udep_system_prompt_v6_2_phone_validation.txt`
2. **MODIFICADO**: `config/context.yaml` → actualizado path a v6.2
3. **NUEVO**: `PROMPT_V6_2_VALIDACION_TELEFONOS.md` (este archivo)

## Rollback

Si v6.2 causa problemas, revertir `config/context.yaml`:

```yaml
sources:
  - type: file_prompt
    path: context/prompts/udep_system_prompt_v6_1_refined.txt
  - type: file_kb
    path: kb/udep_catalog.json
```

## Próximos Pasos

1. **Probar en ambiente de desarrollo** con casos del 1-4 arriba
2. **Monitorear exports de leads** para verificar que `telefono` no sea `null`
3. **Si persisten errores**: Considerar agregar post-procesamiento en `tool_use_processor.py` para detectar números con 8 dígitos y agregar validación más estricta

## Notas Técnicas

- **Compatibilidad**: v6.2 mantiene 100% compatibilidad con v6.1 (solo agrega validación, no cambia comportamiento conversacional)
- **Performance**: La validación de conteo NO agrega latencia perceptible (es procesamiento mental del modelo)
- **Fallback**: Si Nova Sonic no puede contar correctamente, el usuario puede corregir en la confirmación

---

**Conclusión**: v6.2 refuerza la validación de teléfonos con **reglas explícitas**, **ejemplos anotados** y **validación en dos pasos** para eliminar el error de "treinta uno" = 31 en lugar de 3, 0, 1.
