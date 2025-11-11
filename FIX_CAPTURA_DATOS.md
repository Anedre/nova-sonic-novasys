# Corrección de Problemas de Captura de Datos

## Problemas Detectados en la Conversación Real

### Transcripción del Problema:
```
[12:51:42] Zhenia: Perfecto, Carlos Chang. Correcto? Cuál es tu DNI?
              ❌ Dos preguntas en un solo turno

[12:51:54] Zhenia: Confirmo: 7 0 4 9 8 9 7 8. Correcto?
[12:51:57] Zhenia: Cuál es tu número de teléfono?
              ❌ No esperó la respuesta antes de preguntar lo siguiente

[12:52:07] Zhenia: Confirmo: 9 5 3 7 3 1 8 9. Correcto?
[12:52:10] Zhenia: Cuál es tu correo electrónico?
              ❌ No esperó la respuesta (y el número estaba mal)

Usuario: noventa y cinco tres siete treinta y un ochenta y nueve
Bot interpretó: 9 5 3 7 3 1 8 9 (8 dígitos)
              ❌ Solo son 8 dígitos, debería detectarlo y pedir que repita
```

## Análisis del Error de Transcripción

**Lo que dijo el usuario:**
- "noventa y cinco" = 95 (2 dígitos)
- "tres" = 3 (1 dígito)
- "siete" = 7 (1 dígito)
- "treinta y un" = 31 (2 dígitos) ← apócope de "uno"
- "ochenta y nueve" = 89 (2 dígitos)
- **Total: 8 dígitos** ← Falta 1 dígito

**El bot debería:**
1. Contar y detectar que son solo 8 dígitos
2. Decir: "Me parece que son 8 dígitos. ¿Puedes repetir el número completo?"
3. NO pasar a la siguiente pregunta

## Correcciones Implementadas

### 1. ✅ Regla: UNA pregunta por turno

**Antes:**
```
Zhenia: Confirmo: 7 0 4 9 8 9 7 8. ¿Correcto? ¿Cuál es tu teléfono?
```

**Ahora:**
```
Zhenia: Confirmo: 7 0 4 9 8 9 7 8. ¿Correcto?
[ESPERA RESPUESTA DEL USUARIO]
Usuario: Sí correcto
Zhenia: Perfecto. ¿Cuál es tu número de teléfono?
```

**Cambio en el prompt (líneas 107-108):**
```
- **UNA pregunta por turno**: Después de preguntar "¿Correcto?", ESPERA la respuesta. NO agregues otra pregunta.
- **Escucha completa**: No interrumpas ni asumas que el usuario terminó. Espera el silencio completo.
```

### 2. ✅ Validación estricta de cantidad de dígitos

**Antes:**
```python
# El bot confirmaba aunque no fueran 9 dígitos
Zhenia: Confirmo: 9 5 3 7 3 1 8 9. ¿Correcto?
```

**Ahora:**
```python
# El bot valida ANTES de confirmar
Si detecta != 9 dígitos:
Zhenia: Me parece que son 8 dígitos. ¿Puedes repetir el número completo?
```

**Cambio en el prompt (líneas 83-86):**
```
- **VALIDACIÓN CRÍTICA**: Cuenta TODOS los dígitos al final. Si tienes menos de 9 o más de 9, NO confirmes.
- Si son exactamente 9 dígitos, confirma: "Confirmo: 9 5 3 4 5 6 7 8 9. ¿Correcto?"
- **Si NO son 9 dígitos:** "Me parece que son [N] dígitos. ¿Puedes repetir el número completo?"
```

### 3. ✅ Caso especial: "treinta y un"

**Explicación lingüística:**
- "treinta y uno" = 31 (número completo)
- "treinta y un" = 31 (apócope, forma acortada que se usa antes de sustantivos/números)
  - Ejemplo: "treinta y un mil" = 31,000
  - Ejemplo: "treinta y un ochenta y nueve" = 31 89

**Cambio en el prompt (línea 80):**
```
* "treinta y un" (apócope de "uno" antes de otra palabra) = 31 (dos dígitos: 3, 1)
```

**Nota:** El usuario en este caso dijo "treinta y un ochenta y nueve" = 31 89 (4 dígitos), pero en el contexto completo solo sumaban 8 dígitos totales.

### 4. ✅ Manejo de correcciones del usuario

**Nuevo ejemplo agregado (líneas 125-136):**
```
Zhenia: ¿Cuál es tu número de teléfono?
Usuario: noventa y cinco tres siete treinta y un ochenta y nueve
Zhenia: Confirmo: 9 5 3 7 3 1 8 9. ¿Correcto?
[ESPERA RESPUESTA]
Usuario: No, mi teléfono es noventa y cinco tres siete treinta uno ochenta y nueve
Zhenia: Entiendo. Confirmo: 9 5 3 7 3 0 1 8 9. ¿Correcto?
[ESPERA RESPUESTA]
Usuario: Sí correcto
Zhenia: Perfecto. ¿Cuál es tu correo electrónico?
```

### 5. ✅ Ejemplos de BAD flows ampliados

**Agregados (líneas 210-226):**
```
❌ Zhenia: Confirmo: 7 0 4 9 8 9 7 8. ¿Correcto? ¿Cuál es tu teléfono? [STOP - Two questions]
❌ Zhenia: Perfecto, Carlos Chang. ¿Correcto? ¿Cuál es tu DNI? [STOP - Wait for confirmation]
❌ Zhenia: Confirmo: 9 5 3 7 3 1 8 9. ¿Correcto? ¿Cuál es tu correo? [STOP - Wait for response]

✅ CORRECTO:
Zhenia: Confirmo: 7 0 4 9 8 9 7 8. ¿Correcto?
[ESPERA RESPUESTA]
Usuario: Sí correcto
Zhenia: Perfecto. ¿Cuál es tu número de teléfono?
```

### 6. ✅ Espera explícita después de confirmar

**DNI - agregado (líneas 62-64):**
```
- Confirma repitiendo los dígitos: "Confirmo: 7 0 4 9 8 9 7 8. ¿Correcto?"
- **IMPORTANTE: Después de confirmar, ESPERA la respuesta del usuario. NO hagas otra pregunta en el mismo turno.**
- Si el usuario dice "no" o corrige el número, escucha el número completo nuevamente
```

**Teléfono - agregado (líneas 88-90):**
```
- **IMPORTANTE: Después de confirmar, ESPERA la respuesta del usuario. NO hagas otra pregunta en el mismo turno.**
- Si el usuario dice "no" o corrige el número, escucha el número completo nuevamente
```

## Comportamiento Esperado Después del Fix

### Escenario 1: Número con dígitos faltantes

**Usuario dice:**
```
noventa y cinco tres siete treinta y un ochenta y nueve
= 95 + 3 + 7 + 31 + 89 = 8 dígitos (falta 1)
```

**Bot responde:**
```
Zhenia: Me parece que son 8 dígitos. ¿Puedes repetir el número completo?
[ESPERA RESPUESTA COMPLETA]
Usuario: noventa y cinco tres siete treinta uno ochenta y nueve
= 95 + 3 + 7 + 30 + 1 + 89 = 9 dígitos ✓
Zhenia: Confirmo: 9 5 3 7 3 0 1 8 9. ¿Correcto?
[ESPERA RESPUESTA]
Usuario: Sí
Zhenia: Perfecto. ¿Cuál es tu correo electrónico?
```

### Escenario 2: Confirmación seguida de otra pregunta

**Antes (MAL):**
```
Zhenia: Confirmo: 7 0 4 9 8 9 7 8. ¿Correcto? ¿Cuál es tu teléfono?
```

**Ahora (BIEN):**
```
Zhenia: Confirmo: 7 0 4 9 8 9 7 8. ¿Correcto?
[ESPERA]
Usuario: Sí correcto
Zhenia: ¿Cuál es tu número de teléfono?
```

### Escenario 3: Usuario corrige el número

**Flujo completo:**
```
Zhenia: ¿Cuál es tu teléfono?
Usuario: noventa y cinco tres siete treinta y un ochenta y nueve
Zhenia: Me parece que son 8 dígitos. ¿Puedes repetir el número completo?
[ESPERA]
Usuario: sí mi teléfono es noventa y cinco tres siete treinta uno ochenta y nueve
Zhenia: Confirmo: 9 5 3 7 3 0 1 8 9. ¿Correcto?
[ESPERA]
Usuario: no es noventa y cinco tres siete treinta y uno ochenta y nueve
Zhenia: Entiendo. Confirmo: 9 5 3 7 3 1 8 9. ¿Correcto?
[ESPERA]
Usuario: sí correcto
Zhenia: Perfecto. ¿Cuál es tu correo electrónico?
```

## Diferencias Clave: "treinta uno" vs "treinta y uno" vs "treinta y un"

| Expresión | Contexto | Interpretación | Dígitos | Ejemplo |
|-----------|----------|---------------|---------|---------|
| treinta uno | Sin "y" entre palabras | 30 + 1 separados | 3 | "tres siete treinta uno" = 3 7 3 0 1 |
| treinta y uno | Con "y" completo | 31 junto | 2 | "tres siete treinta y uno" = 3 7 3 1 |
| treinta y un | Apócope antes de número | 31 junto | 2 | "treinta y un ochenta" = 3 1 8 0 |

## Testing del Fix

### Casos de prueba:

1. **Test: Dos preguntas en un turno**
   - Esperado: Bot solo hace UNA pregunta, espera respuesta
   - Verificar: No aparece "¿Correcto? ¿Cuál...?" en un solo mensaje

2. **Test: Número con 8 dígitos (falta 1)**
   - Dí: "noventa y cinco tres siete treinta y un ochenta y nueve"
   - Esperado: Bot dice "Me parece que son 8 dígitos..."
   - Verificar: NO confirma números incorrectos

3. **Test: Número con 9 dígitos correctos**
   - Dí: "noventa y cinco tres siete treinta uno ochenta y nueve"
   - Esperado: Bot confirma "9 5 3 7 3 0 1 8 9. ¿Correcto?"
   - Verificar: Cuenta correctamente "treinta uno" = 3 + 0 + 1

4. **Test: Corrección de usuario**
   - Bot confirma algo incorrecto
   - Usuario dice "no, es..."
   - Esperado: Bot escucha completo, vuelve a confirmar
   - Verificar: No pasa a siguiente pregunta sin confirmar

5. **Test: Espera después de confirmación**
   - Bot dice "¿Correcto?"
   - Esperado: Espera respuesta antes de siguiente pregunta
   - Verificar: Usuario puede responder "sí" o "no"

## Archivos Modificados

**`context/prompts/udep_system_prompt_original_v6.txt`**

Líneas modificadas:
- 48-64: DNI - Agregada validación y espera
- 68-91: Teléfono - Agregada validación, "treinta y un", espera
- 107-113: Reglas críticas - Énfasis en UNA pregunta por turno
- 125-136: Nuevo ejemplo de corrección
- 210-226: BAD flows ampliados

Total de cambios: ~40 líneas modificadas/agregadas

## Resumen de Mejoras

✅ **Una pregunta por turno** - El bot espera respuesta antes de continuar
✅ **Validación estricta** - Cuenta dígitos ANTES de confirmar
✅ **Detección de errores** - Identifica cuando faltan o sobran dígitos
✅ **Manejo de correcciones** - Escucha completo cuando usuario corrige
✅ **Casos especiales** - "treinta y un" interpretado correctamente
✅ **Ejemplos claros** - BAD flows muestran lo que NO debe hacer

El bot ahora es más preciso, paciente y no salta preguntas sin confirmar.
