# Deployment a AWS - Nova Sonic UDEP

## ⚠️ Amplify NO es compatible
AWS Amplify Hosting **NO soporta WebSockets persistentes** necesarios para streaming bidireccional con Nova Sonic.

## ✅ Opciones Recomendadas

### Opción 1: AWS App Runner (Recomendado)
**Ventajas:**
- ✅ WebSockets persistentes
- ✅ Deploy desde GitHub automático
- ✅ Escala automático
- ✅ Configuración simple

**Pasos:**
1. Ir a AWS App Runner Console
2. Create service → Source: GitHub → Seleccionar `nova-sonic-novasys`
3. Build settings:
   - Configuration file: `apprunner.yaml`
   - O usar Dockerfile: `Dockerfile`
4. Service settings:
   - Port: 5000
   - Health check: `/` (HTTP 200)
5. Security:
   - Create IAM role con política `AmazonBedrockFullAccess`
   - **NO usar variables de entorno para credentials**, usar IAM role
6. Deploy!

**Variables de entorno en App Runner:**
```bash
PYTHONUNBUFFERED=1
PORT=5000
WEB_CONCURRENCY=2
WORKER_CONNECTIONS=1000
NOVA_SONIC_STARTUP_TIMEOUT_SEC=60
```

**IAM Role Policy:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-sonic-v1:0"
    }
  ]
}
```

### Opción 2: Elastic Beanstalk
**Ventajas:**
- ✅ WebSockets con ALB
- ✅ Deploy con CLI: `eb deploy`
- ✅ Configuración avanzada

**Pasos:**
1. Instalar EB CLI: `pip install awsebcli`
2. Inicializar: `eb init -p python-3.12 nova-sonic`
3. Configurar: Editar `.ebextensions/01_packages.config`:
```yaml
packages:
  yum:
    ffmpeg: []
```
4. Deploy: `eb create nova-sonic-prod`

### Opción 3: ECS Fargate + ALB
**Ventajas:**
- ✅ Control total
- ✅ Escalado granular
- ✅ Integración VPC

**Complejidad:** Alta (requiere configurar VPC, ALB, Target Groups, Task Definition)

## 🔧 Configuración de Credenciales AWS

### ❌ NO USAR (inseguro):
```bash
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
```

### ✅ USAR IAM Role:
En App Runner o ECS, asignar un **IAM Role** con permisos de Bedrock. El SDK de AWS detecta automáticamente las credenciales del role.

**Modificación necesaria en código:**
```python
# nova_sonic_es_sd.py - línea ~50
# Remover EnvironmentCredentialsResolver si usas IAM role
# El SDK lo detecta automáticamente
```

## 📊 Costos Estimados

### App Runner
- **Base**: $0.007/vCPU-hora + $0.0008/GB-memoria-hora
- **Ejemplo**: 1 vCPU, 2GB RAM → ~$15/mes
- **Tráfico**: Primer 1GB gratis, luego $0.15/GB

### Elastic Beanstalk
- **Base**: EC2 t3.small (~$15/mes) + ALB (~$22/mes)
- **Total**: ~$40-50/mes

### ECS Fargate
- **Similar a App Runner**: ~$15-20/mes para 1 task

## 🚀 Deployment Rápido (App Runner)

```bash
# 1. Push a GitHub
git add .
git commit -m "Configuración para App Runner"
git push origin main

# 2. En AWS Console:
# - Ir a App Runner
# - Create service
# - Source: GitHub -> nova-sonic-novasys
# - Build: Use Dockerfile
# - Service settings: Port 5000
# - Security: Attach IAM role con Bedrock access

# 3. Configurar health check:
# Path: /
# Protocol: HTTP
# Interval: 30s
# Timeout: 5s
# Unhealthy threshold: 3
```

## ⚡ Optimizaciones para Producción

### 1. Usar Redis para multi-worker (opcional)
```python
# app.py
socketio = SocketIO(
    app,
    message_queue='redis://redis-url:6379',
    # ... resto de config
)
```

### 2. CloudFront para assets estáticos
- Crear distribución CloudFront
- Origin: App Runner URL
- Cache policy: CachingDisabled para WebSocket paths
- Cache enabled para `/static/*`

### 3. Monitoreo
- **CloudWatch Logs**: Automático en App Runner
- **CloudWatch Metrics**: CPU, memoria, latencia
- **X-Ray**: Tracing de requests (opcional)

## 🔍 Troubleshooting

### WebSocket no conecta
- Verificar health check pasa
- Verificar Security Group permite puerto 5000
- Verificar logs: `aws apprunner list-operations`

### Timeout de conexión
- Aumentar `NOVA_SONIC_STARTUP_TIMEOUT_SEC=90`
- Verificar IAM role tiene permisos Bedrock
- Check región: `AWS_REGION=us-east-1`

### Audio choppy
- Aumentar recursos: 1→2 vCPUs en App Runner
- Aumentar workers: `WEB_CONCURRENCY=3`
- Reducir chunk_size a 1600 bytes si persiste

## 📝 Checklist Pre-Deploy

- [ ] `apprunner.yaml` creado
- [ ] `Dockerfile` actualizado
- [ ] IAM role con política Bedrock creado
- [ ] Código push a GitHub
- [ ] Variables de entorno sin credentials (usar IAM)
- [ ] Health check configurado en `/`
- [ ] Port 5000 expuesto
- [ ] FFmpeg instalado en imagen
- [ ] Gunicorn con eventlet configurado

## 🎯 Recomendación Final

**Para tu caso (WebSockets + streaming audio + Bedrock):**
👉 **AWS App Runner** es la mejor opción: balance entre simplicidad, costo y features.

**Evitar:** Amplify (no WebSockets), Lambda (timeout 15min, no streaming bidireccional).
