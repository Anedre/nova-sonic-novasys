# Fix Conversación Andre - Correcciones Críticas

## Fecha
5 de noviembre de 2025

## Errores Detectados en Conversación Real

### Conversación Analizada
Usuario: Andre Alata (masculino)
Fecha: 01:24 p.m. - 01:27 p.m.

---

## 🔴 ERRORES CRÍTICOS IDENTIFICADOS

### 1. Error de Género - RESUELTO ✅
**Problema:**
- Usuario se llama "Andre" (masculino)
- Zhenia lo trata como "Andrea" (femenino) durante toda la conversación

**Causa:**
- ASR transcribió "andre" como "andrea"
- El prompt no tenía reglas para validar género o usar lenguaje neutro

**Solución Implementada:**
```markdown
## 2. Nombre Completo
- **IMPORTANTE - Género:**
  * Escucha atentamente: "Andrea" (femenino) vs "Andre" (masculino)
  * Si no estás 100% seguro del género, usa lenguaje neutro: "Perfecto, gracias"
  * O pregunta: "¿Cómo prefieres que te llame?"
```

---

### 2. Error en Transcripción de Teléfono (Omisión del 0 en "treinta") - RESUELTO ✅
**Problema:**
```
Usuario: "nueve cinco tres siete treinta uno ocho nueve"
Esperado: 9,5,3,7,3,0,1,8,9 (9 dígitos)
Captado: 9,5,3,7,3,1,8,9 (8 dígitos - SE COMIÓ EL 0)
```

**Causa:**
- El prompt no especificaba que "treinta" = 3,0 (DOS dígitos)
- Zhenia interpretó "treinta uno" como dos números separados: "3" + "1"

**Solución Implementada:**
```markdown
**REGLAS DE TRANSCRIPCIÓN (APLICA SIEMPRE):**
  * **"treinta" = 3, 0 (DOS dígitos: el "treinta" incluye el cero implícito)**
  * **"treinta uno" SIN "y" = 3, 0, 1 (TRES dígitos: treinta=30 + uno=1)**
  * "treinta y uno" CON "y" = 3, 1 (dos dígitos: treinta y uno = 31)
  * **CUIDADO:** "treinta" nunca puede ser solo "3", siempre es "3, 0"
```

**Ejemplos Agregados:**
- ✅ "nueve cinco tres siete treinta uno ocho nueve" = 9,5,3,7,3,0,1,8,9 (9 dígitos)
- ✅ "nueve cinco tres siete tres cero uno ocho nueve" = 9,5,3,7,3,0,1,8,9 (9 dígitos)

---

### 3. Error en Captura de Email (Números Omitidos) - RESUELTO ✅
**Problema:**
```
Usuario: "anedre1234567890 arroba gmail"
Esperado: anedre1234567890@gmail.com (10 dígitos)
Captado: anedre123456789@gmail (9 dígitos - FALTA EL 0 FINAL)
```

**Causa:**
- El prompt no especificaba que debía capturar **todos los números sin omitir**
- Zhenia asumió que terminó antes del "0" final

**Solución Implementada:**
```markdown
## 5. Email
- **Captura EXACTAMENTE lo que dice, número por número:**
  * Si deletrea: "anedre uno dos tres cuatro cinco seis siete ocho nueve cero" = anedre1234567890 (10 números)
  * **NO omitas números al final**
  * **NO asumas que terminó si sigue hablando**
```

---

### 4. Error en Confirmación de Email (Dominio Incompleto) - RESUELTO ✅
**Problema:**
```
Zhenia: "Confirmo: anedre123456789 arroba gmail. ¿Correcto?"
Falta: .com
```

**Causa:**
- Usuario dijo "arroba gmail" sin mencionar "punto com"
- Zhenia no preguntó por la extensión del dominio

**Solución Implementada:**
```markdown
- **Captura el dominio COMPLETO:**
  * "arroba gmail punto com" = @gmail.com
  * "arroba gmail" SIN "punto com" = @gmail (INCOMPLETO, pregunta: "¿punto com?")
- **Confirmación COMPLETA:**
  * "Confirmo: anedre1234567890 arroba gmail punto com. ¿Correcto?"
  * NO confirmes solo "arroba gmail", SIEMPRE incluye ".com"
```

---

### 5. Confirmaciones Repetitivas (Loop Infinito) - RESUELTO ✅
**Problema:**
```
[01:25:35] Usuario: "mi correo es anedre1234567890 arroba gmail"
[01:25:38] Zhenia: "Confirmo: anedre1234567890 arroba gmail. ¿Correcto?"
[01:25:50] Usuario: "no es anedre1234567890 arroba gmail"
[01:25:53] Zhenia: "Confirmo: anedre1234567890 arroba gmail. ¿Correcto?" ← REPITIÓ LO MISMO
[01:26:06] Usuario: "no es anedre1234567890 arroba gmail"
[01:26:08] Zhenia: "Confirmo: anedre1234567890 arroba gmail. ¿Correcto?" ← OTRA VEZ
```

**Causa:**
- El prompt no tenía estrategia de re-confirmación
- Zhenia repetía la misma confirmación sin entender la corrección

**Solución Implementada:**
```markdown
**Estrategia de Re-confirmación:**
1. **Primera confirmación:** Lee el dato completo
2. **Si dice "no":** Pregunta: "¿Me lo puedes repetir completo?"
3. **Segunda confirmación:** Lee el nuevo dato completo
4. **Si dice "no" OTRA VEZ:** 
   - **NO repitas la misma confirmación por tercera vez**
   - Di: "Disculpa, ¿me lo deletreas MUY despacio, número por número?"
   - **Escucha CON ATENCIÓN todo desde cero**

**NUNCA repitas la misma confirmación errónea más de 2 veces:**
  * Si el usuario dice "no" dos veces, di: "Perfecto, ¿me lo deletreas letra por letra y número por número desde el inicio?"
```

---

### 6. Preguntas Sin Información (Genéricas) - RESUELTO ✅
**Problema:**
```
Zhenia: "Tenemos MBA en Finanzas, Maestría en Data Science o Diplomado en Ciberseguridad"
```
Falta información completa de los programas (nombres oficiales completos).

**Solución Implementada:**
```markdown
## 6. Programa de Interés
- **Si pregunta "qué programas hay":** Responde con información COMPLETA del catálogo:
  * "Tenemos MBA en Finanzas Corporativas, Maestría en Data Science e Inteligencia Artificial, y Diplomado en Ciberseguridad Empresarial. ¿Cuál te interesa?"
  * **NO digas solo "MBA en Finanzas" sin especificar**
```

---

### 7. Usuario Corrige pero Sistema No Escucha - RESUELTO ✅
**Problema:**
- Usuario intenta corregir el email 3 veces
- Zhenia no escucha la corrección, repite el mismo dato erróneo

**Solución Implementada:**
```markdown
- **Si el usuario corrige:**
  * Escucha TODO el nuevo email completo desde el inicio
  * NO asumas que repitió lo mismo
  * Usuario dice: "no es anedre12345 arroba gmail" → Captura EXACTAMENTE: anedre12345@gmail
  * **Si falta algo, pregunta:** "¿Y después de gmail va punto com?"
```

---

## 📊 RESUMEN DE CAMBIOS

| Archivo | Sección | Cambio |
|---------|---------|--------|
| `udep_system_prompt_consolidated.txt` | §2 Nombre Completo | ✅ Agregado: Validación de género y lenguaje neutro |
| `udep_system_prompt_consolidated.txt` | §4 Teléfono | ✅ Actualizado: "treinta" = 3,0 (DOS dígitos) |
| `udep_system_prompt_consolidated.txt` | §5 Email | ✅ Actualizado: Captura número por número sin omitir |
| `udep_system_prompt_consolidated.txt` | §5 Email | ✅ Agregado: Validación de dominio completo (.com) |
| `udep_system_prompt_consolidated.txt` | §5 Email | ✅ Agregado: Estrategia anti-loop (max 2 intentos) |
| `udep_system_prompt_consolidated.txt` | §6 Programa | ✅ Actualizado: Respuesta con nombres completos |
| `udep_system_prompt_consolidated.txt` | Confirmaciones | ✅ Agregado: Estrategia de re-confirmación en 4 pasos |

---

## 🧪 PRUEBAS RECOMENDADAS

### Test Case 1: Nombre con Género Ambiguo
- Usuario dice: "Andrea" o "Andre"
- Verificar que Zhenia use lenguaje neutro o pregunte

### Test Case 2: Teléfono con "treinta"
- Usuario: "nueve cinco tres siete treinta uno ocho nueve"
- Esperado: 9,5,3,7,3,0,1,8,9 ✅
- Verificar conteo correcto de dígitos

### Test Case 3: Email con 10 Dígitos
- Usuario: "anedre1234567890 arroba gmail punto com"
- Esperado: anedre1234567890@gmail.com ✅
- Verificar que no se coma el último dígito

### Test Case 4: Email sin Extensión
- Usuario: "anedre12345 arroba gmail" (sin "punto com")
- Esperado: Zhenia pregunta "¿punto com?" ✅

### Test Case 5: Corrección de Email
- Usuario corrige 2 veces
- Esperado: En la tercera, Zhenia pide deletreo completo ✅
- Verificar que NO repita la misma confirmación errónea

### Test Case 6: Programas
- Usuario: "qué programas hay"
- Esperado: Respuesta con nombres completos (MBA en Finanzas **Corporativas**) ✅

---

## 🎯 PRÓXIMOS PASOS

1. **Reiniciar servidor Flask:**
   ```powershell
   python app.py
   ```

2. **Probar con prompt "UDEP Original"** (usa consolidated)

3. **Realizar 5-10 conversaciones de prueba** con casos como:
   - Nombres ambiguos: "Alex", "Andrea/Andre", "Sam"
   - Teléfonos con "treinta", "cuarenta", "cincuenta"
   - Emails largos con 10+ dígitos
   - Correcciones de email

4. **Monitorear métricas:**
   - Tasa de errores en captura de teléfono (debe bajar a <5%)
   - Tasa de loops de confirmación (debe ser 0%)
   - Completitud de emails (debe ser 100%)

5. **Si persisten errores:** Revisar logs de transcripción de Nova Sonic para detectar nuevos patrones

---

## 📌 NOTAS TÉCNICAS

- **ASR (Automatic Speech Recognition) de Nova Sonic** tiene dificultades con:
  - Números largos dictados rápido
  - Nombres no-Peruanos (Andre → Andrea)
  - Emails con muchos números (tiende a omitir los últimos)

- **Estrategias de Mitigación:**
  - Confirmación dígito por dígito para teléfonos/DNI
  - Pedir deletreo lento para emails
  - Lenguaje neutro para nombres ambiguos
  - Máximo 2 intentos de confirmación antes de pedir deletreo completo

---

## ✅ VALIDACIÓN FINAL

- [x] Error de género corregido con lenguaje neutro
- [x] Transcripción de "treinta" = 3,0 especificada
- [x] Captura completa de emails (número por número)
- [x] Validación de dominio completo (.com)
- [x] Estrategia anti-loop implementada (max 2 intentos)
- [x] Nombres completos de programas agregados
- [x] Prompt consolidado actualizado

**Estado:** ✅ Listo para testing en producción
