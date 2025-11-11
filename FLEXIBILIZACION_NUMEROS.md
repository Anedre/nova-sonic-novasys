# Flexibilización de Captura de DNI y Teléfono

## Cambio Implementado

Se modificó el prompt `udep_system_prompt_original_v6.txt` para que el bot NO restrinja cómo el usuario dice los números de DNI y teléfono.

## Antes vs Después

### ❌ ANTES (Restrictivo)

**DNI:**
```
Zhenia: ¿Me puedes dar tu DNI en 4 pares de dígitos?
```

**Teléfono:**
```
Zhenia: ¿Me das tu teléfono en pares de dígitos?
```

**Problema:** El bot imponía un formato específico, lo cual no es natural en la conversación.

### ✅ DESPUÉS (Flexible)

**DNI:**
```
Zhenia: ¿Cuál es tu DNI?
```

**Teléfono:**
```
Zhenia: ¿Cuál es tu número de teléfono?
```

**Ventaja:** El usuario dice los números como le resulte natural, y el bot los interpreta correctamente.

## Cómo Funciona Ahora

### El usuario puede decir los números de CUALQUIER forma:

#### DNI (8 dígitos) - Ejemplos aceptados:

1. **Uno por uno:**
   - "siete cero cuatro nueve ocho nueve siete ocho"
   - → Bot transcribe: 70498978

2. **De dos en dos (pares):**
   - "setenta cuarenta y nueve ochenta y nueve setenta y ocho"
   - → Bot transcribe: 70498978

3. **Mezclado:**
   - "setenta cuatro nueve ochenta y nueve setenta y ocho"
   - → Bot transcribe: 70498978 (par + individual + individual + par + par)

4. **Otro mezclado:**
   - "siete cero cuarenta y nueve ochenta y nueve siete ocho"
   - → Bot transcribe: 70498978

#### Teléfono (9 dígitos) - Ejemplos aceptados:

1. **Uno por uno:**
   - "nueve cinco tres cuatro cinco seis siete ocho nueve"
   - → Bot transcribe: 953456789

2. **De dos en dos:**
   - "noventa y cinco treinta y cuatro cincuenta y seis setenta y ocho nueve"
   - → Bot transcribe: 953456789

3. **De tres en tres y mezclado:**
   - "novecientos cincuenta y tres cuarenta y cinco sesenta y siete ochenta y nueve"
   - → Bot transcribe: 953456789

4. **Mezclado complejo:**
   - "nueve cinco tres siete treinta uno ocho nueve"
   - → Bot transcribe: 953731089
   - **Nota crítica:** "treinta uno" SIN "y" = 30 + 1 (dos dígitos separados)

5. **Con "y":**
   - "noventa y cinco treinta y uno ochenta y cuatro tres dos"
   - → Bot transcribe: 953184032
   - **Nota:** "treinta y uno" CON "y" = 31 (un par)

## Reglas de Transcripción (para el bot)

### Números compuestos:

- **"setenta"** = 70 (dos dígitos: 7 y 0)
- **"cuarenta y nueve"** = 49 (dos dígitos: 4 y 9)
- **"novecientos cincuenta y tres"** = 953 (tres dígitos: 9, 5 y 3)
- **"siete"** = 7 (un solo dígito)

### Caso especial: "treinta uno" vs "treinta y uno"

- **SIN "y":** "treinta uno" = 30 + 1 = dos dígitos separados (3, 0, 1)
- **CON "y":** "treinta y uno" = 31 = un par de dígitos (3, 1)

Esto es importante para teléfonos que empiezan con operadores como 953-**31**-XXX vs 953-**30-1**-XXX.

## Validación

El bot siempre:

1. **Cuenta mentalmente** que el total de dígitos sea correcto:
   - DNI: exactamente 8 dígitos
   - Teléfono: exactamente 9 dígitos

2. **Repite los dígitos para confirmar:**
   - DNI: "Confirmo: 7 0 4 9 8 9 7 8. ¿Correcto?"
   - Teléfono: "Confirmo: 9 5 3 4 5 6 7 8 9. ¿Correcto?"

3. **Pide repetir si falta algún dígito:**
   - "Creo que falta un dígito, ¿puedes repetirlo?"
   - "Me falta un dígito, ¿puedes repetir el número completo?"

## Ejemplos de Conversación Natural

### Ejemplo 1: Usuario dice uno por uno
```
Zhenia: ¿Cuál es tu DNI?
Usuario: siete cero cuatro nueve ocho nueve siete ocho
Zhenia: Confirmo: 7 0 4 9 8 9 7 8. ¿Correcto?
Usuario: Sí
```

### Ejemplo 2: Usuario dice de dos en dos
```
Zhenia: ¿Cuál es tu teléfono?
Usuario: noventa y cinco treinta y cuatro cincuenta y seis setenta y ocho nueve
Zhenia: Confirmo: 9 5 3 4 5 6 7 8 9. ¿Correcto?
Usuario: Correcto
```

### Ejemplo 3: Usuario mezcla formatos
```
Zhenia: ¿Cuál es tu DNI?
Usuario: setenta cuatro nueve ochenta y nueve setenta y ocho
Zhenia: Confirmo: 7 0 4 9 8 9 7 8. ¿Correcto?
Usuario: Sí
```

### Ejemplo 4: Caso especial "treinta uno"
```
Zhenia: ¿Cuál es tu teléfono?
Usuario: nueve cinco tres siete treinta uno ocho nueve
Zhenia: Confirmo: 9 5 3 7 3 0 1 8 9. ¿Correcto?
Usuario: Sí
```

## Secciones del Prompt Modificadas

### Líneas 48-62 (DNI)
- Cambió de "Pide en PARES" a "Pregunta simple"
- Agregados 4 ejemplos de diferentes formas de decir el DNI
- Enfoque en transcripción flexible, no en restricción

### Líneas 64-83 (Teléfono)
- Cambió de "Pide en PARES" a "Pregunta simple"
- Agregados 5 ejemplos incluyendo caso especial "treinta uno"
- Reglas detalladas de transcripción

### Línea 110 (Primer turno)
- Removido "en pares" de la frase de seguimiento

### Líneas 227-228 (Important Notes)
- Actualizado: "NO les digas cómo decirlos - acepta cualquier formato"

## Testing

Para probar los cambios:

1. **Inicia el servidor:**
   ```bash
   python app.py
   ```

2. **Abre el navegador:**
   ```
   http://localhost:5000
   ```

3. **Prueba diferentes formatos:**
   - Dí tu DNI de dos en dos
   - Dí tu teléfono uno por uno
   - Mezcla formatos (dos en dos + uno por uno)
   - Usa "treinta uno" sin "y"

4. **Verifica que el bot:**
   - NO dice "en pares de dígitos"
   - Solo pregunta: "¿Cuál es tu DNI?" / "¿Cuál es tu teléfono?"
   - Repite correctamente los dígitos para confirmar
   - Detecta si faltan dígitos

## Beneficios

✅ **Conversación más natural** - No impone restricciones al usuario
✅ **Más flexible** - Acepta cualquier forma de decir los números
✅ **Menos fricción** - Usuario no tiene que pensar en "cómo" decir los números
✅ **Más inteligente** - El bot interpreta correctamente diferentes formatos
✅ **Misma precisión** - Sigue validando que sean exactamente 8 o 9 dígitos

## Casos Edge Cubiertos

- ✅ Números mezclados (pares + individuales)
- ✅ "treinta uno" sin "y" = 30 + 1
- ✅ "treinta y uno" con "y" = 31
- ✅ Números de tres en tres (novecientos cincuenta y tres)
- ✅ Detección de dígitos faltantes
- ✅ Confirmación dígito por dígito para verificar

## Notas Importantes

- El prompt mantiene las **reglas de transcripción** para que el bot entienda correctamente
- Los **ejemplos en el prompt** son para entrenar al modelo, no para decirle al usuario
- La **validación de cantidad de dígitos** sigue siendo estricta (8 para DNI, 9 para teléfono)
- La **confirmación verbal** se hace siempre dígito por dígito para evitar errores
