# Prompt Simple de Test - Diagnóstico de Latencia

**Objetivo**: Aislar si la latencia viene del contenido del prompt o de otro componente del sistema.

## El Prompt de Test

**Archivo**: `context/prompts/simple_math_tutor.txt`

**Contenido completo** (solo 6 líneas, ~50 tokens):
```
You are a friendly math tutor. Help students with basic math problems.

Keep answers very short - one or two sentences maximum.

If they ask a math question, solve it and explain briefly.

If they ask something else, say: "I only help with math. What math problem can I solve for you?"

That's it. Be warm, brief, and helpful.
```

**Características**:
- ✅ Solo 50 tokens (vs 480 de V8, 1,150 de V7)
- ✅ Sin knowledge base (kb)
- ✅ Sin instrucciones de captura de datos
- ✅ Sin tool use
- ✅ Sin validaciones complejas
- ✅ Contexto mínimo absoluto

---

## Comparación de Tokens

```
Simple Test:  ████ 50 tokens
V8 Mínimo:    ███████████████████ 480 tokens (10x más)
V7 Conv:      ██████████████████████████████ 1,150 tokens (23x más)
V6 Struct:    ████████████████████████████████████████ 1,850 tokens (37x más)
```

---

## Cómo Usar para Diagnóstico

### Paso 1: Probar Simple Test

1. Selecciona "🧪 Test Simple (math)" en el dropdown
2. Inicia llamada
3. Di: "¿Cuánto es dos más dos?"
4. **Observa logs de timing**:
   ```
   ⏱️ LATENCIA: X.XXs desde fin audio usuario hasta contentStart
   ⏱️ TTS: X.XXs desde contentStart hasta primer audioOutput
   ```

### Paso 2: Interpretar Resultados

#### **Escenario A: Simple Test es RÁPIDO (<1s latencia)**
```
⏱️ LATENCIA: 0.6s  ← Rápido
⏱️ TTS: 0.4s
```
**Conclusión**: ✅ El problema está en el **contenido del prompt UDEP**
- Los prompts V6/V7/V8 tienen instrucciones muy complejas
- Knowledge base agrega contexto extra
- Tool use añade overhead

**Solución**: 
- Simplificar más el prompt UDEP
- Considerar eliminar knowledge base durante captura inicial
- Optimizar instrucciones de validación

---

#### **Escenario B: Simple Test TAMBIÉN es LENTO (>2s latencia)**
```
⏱️ LATENCIA: 2.3s  ← Lento igual
⏱️ TTS: 0.5s
```
**Conclusión**: ❌ El problema NO está en el prompt, está en:
1. **Infraestructura de red**: Latencia AWS/conexión
2. **Audio processing**: FFmpeg decode/encode
3. **Nova Sonic streaming**: Overhead del modelo base
4. **Región AWS**: Distancia geográfica (us-east-1 desde Perú)

**Solución**:
- Verificar conexión a AWS
- Considerar región más cercana (us-west-2)
- Revisar tamaño de chunks de audio
- Optimizar pipeline FFmpeg

---

#### **Escenario C: Simple Test tiene LATENCIA VARIABLE**
```
Primera pregunta: ⏱️ LATENCIA: 2.1s
Segunda pregunta: ⏱️ LATENCIA: 0.7s
Tercera pregunta: ⏱️ LATENCIA: 0.6s
```
**Conclusión**: ⚠️ **Cold start** de Nova Sonic
- Primera llamada carga el modelo
- Llamadas subsecuentes son más rápidas

**Solución**: Normal, esperar warmup

---

## Prueba Comparativa Sugerida

1. **Test Simple**:
   - Pregunta: "¿Cuánto es 5 + 3?"
   - Medir latencia
   - Anotar tiempo

2. **V8 Mínimo**:
   - Cambiar a V8
   - Nueva llamada
   - Decir: "Hola"
   - Medir latencia
   - Comparar

3. **Analizar diferencia**:
   ```
   Si diferencia > 1s → Problema en prompt
   Si diferencia < 0.5s → Problema en infraestructura
   ```

---

## Selector Actualizado

```
┌────────────────────────────────────────┐
│ 🧪 Test Simple (math)           ▼     │  ← NUEVO (50 tokens, diagnóstico)
│ V8 Mínimo (ultra-rápido)               │  (480 tokens)
│ V7 Conversacional                      │  (1,150 tokens)
│ V6 Estructurado                        │  (1,850 tokens)
└────────────────────────────────────────┘
```

---

## Qué Esperar

### Si Nova Sonic funciona normalmente:

**Simple Test**: 
- Latencia: 0.5-0.8s
- TTS: 0.3-0.5s
- **Total**: ~1s

**V8 Mínimo**:
- Latencia: 1.0-1.3s
- TTS: 0.4-0.6s
- **Total**: ~1.5s

**Diferencia esperada**: ~0.5s (razonable por el contexto adicional)

---

## Archivos Creados

- ✅ `context/prompts/simple_math_tutor.txt` (prompt mínimo)
- ✅ `config/context_simple_test.yaml` (config sin kb)
- ✅ `app.py` (mapeo actualizado)
- ✅ `templates/index.html` (dropdown con test)

---

## Cómo Desactivar Test

Una vez terminado el diagnóstico, puedes:

1. **Dejar visible**: No estorba, útil para pruebas futuras
2. **Ocultar**: Comentar línea en `index.html`:
   ```html
   <!-- <option value="simple_test">🧪 Test Simple (math)</option> -->
   ```
3. **Eliminar**: Borrar opción del HTML y entrada del mapeo en `app.py`

---

## Siguiente Paso Después del Diagnóstico

1. **Ejecuta test**: `python app.py`
2. **Abre**: http://localhost:5000
3. **Selecciona**: "🧪 Test Simple (math)"
4. **Pregunta**: "¿Cuánto es 10 más 5?"
5. **Anota latencia** de los logs
6. **Repórtame el resultado** y ajustamos según escenario A, B o C
