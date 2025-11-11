#!/usr/bin/env python3
"""
Script de validación pre-deploy para AWS App Runner/ECS.

Verifica que la configuración sea compatible con deployment en AWS.
"""

import os
import sys
from pathlib import Path

def check_files():
    """Verifica que existan los archivos necesarios."""
    required_files = [
        "app.py",
        "gunicorn_config.py",
        "requirements.txt",
        "Dockerfile",
        "apprunner.yaml"
    ]
    
    missing = []
    for file in required_files:
        if not Path(file).exists():
            missing.append(file)
    
    if missing:
        print(f"❌ Archivos faltantes: {', '.join(missing)}")
        return False
    
    print("✅ Todos los archivos necesarios presentes")
    return True

def check_credentials_config():
    """Verifica configuración de credenciales."""
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    
    if not access_key and not secret_key:
        print("ℹ️  No hay credenciales en .env (OK para App Runner con IAM role)")
        print("   Asegúrate de configurar un IAM role en App Runner con permisos Bedrock")
        return True
    
    if access_key and not secret_key:
        print("❌ AWS_ACCESS_KEY_ID definido pero falta AWS_SECRET_ACCESS_KEY")
        return False
    
    if not access_key and secret_key:
        print("❌ AWS_SECRET_ACCESS_KEY definido pero falta AWS_ACCESS_KEY_ID")
        return False
    
    print(f"✅ Credenciales configuradas: {access_key[:8]}...")
    print("   ⚠️  Considera usar IAM role en App Runner en lugar de credentials hardcodeadas")
    return True

def check_ffmpeg():
    """Verifica que FFmpeg esté instalado localmente."""
    import shutil
    if shutil.which("ffmpeg"):
        print("✅ FFmpeg instalado localmente")
        return True
    else:
        print("⚠️  FFmpeg no encontrado localmente (OK si usas Dockerfile)")
        return True

def check_requirements():
    """Verifica que requirements.txt contenga dependencias críticas."""
    req_file = Path("requirements.txt")
    if not req_file.exists():
        return False
    
    content = req_file.read_text(encoding='utf-8')
    critical_deps = [
        "flask",
        "flask-socketio",
        "eventlet",
        "gunicorn",
        "aws_sdk_bedrock_runtime"
    ]
    
    missing = []
    for dep in critical_deps:
        if dep not in content.lower():
            missing.append(dep)
    
    if missing:
        print(f"❌ Dependencias faltantes en requirements.txt: {', '.join(missing)}")
        return False
    
    print("✅ Todas las dependencias críticas en requirements.txt")
    return True

def check_dockerfile():
    """Verifica que Dockerfile tenga FFmpeg."""
    dockerfile = Path("Dockerfile")
    if not dockerfile.exists():
        return True  # Ya chequeado en check_files
    
    content = dockerfile.read_text(encoding='utf-8')
    if "ffmpeg" not in content.lower():
        print("❌ Dockerfile no instala FFmpeg (requerido para audio decoding)")
        return False
    
    print("✅ Dockerfile instala FFmpeg")
    return True

def check_apprunner_config():
    """Verifica apprunner.yaml."""
    apprunner = Path("apprunner.yaml")
    if not apprunner.exists():
        print("⚠️  apprunner.yaml no existe (opcional si usas Dockerfile)")
        return True
    
    content = apprunner.read_text(encoding='utf-8')
    if "port: 5000" not in content and "PORT" not in content:
        print("❌ apprunner.yaml no define puerto 5000")
        return False
    
    print("✅ apprunner.yaml configurado correctamente")
    return True

def check_websocket_config():
    """Verifica que app.py tenga configuración WebSocket."""
    app_file = Path("app.py")
    if not app_file.exists():
        return False
    
    content = app_file.read_text(encoding='utf-8')
    
    checks = [
        ("eventlet.monkey_patch", "Monkey patch de eventlet"),
        ("async_mode='eventlet'", "Async mode eventlet"),
        ("transports=['websocket']", "Transporte WebSocket")
    ]
    
    all_ok = True
    for pattern, description in checks:
        if pattern not in content:
            print(f"⚠️  {description} no encontrado en app.py")
            all_ok = False
    
    if all_ok:
        print("✅ Configuración WebSocket correcta en app.py")
    
    return all_ok

def main():
    """Ejecuta todas las validaciones."""
    print("🔍 Validando configuración para AWS deployment...\n")
    
    checks = [
        ("Archivos necesarios", check_files),
        ("Requirements.txt", check_requirements),
        ("Dockerfile", check_dockerfile),
        ("App Runner config", check_apprunner_config),
        ("Credenciales AWS", check_credentials_config),
        ("FFmpeg local", check_ffmpeg),
        ("Configuración WebSocket", check_websocket_config),
    ]
    
    results = []
    for name, check_func in checks:
        print(f"\n📋 {name}:")
        try:
            result = check_func()
            results.append(result)
        except Exception as e:
            print(f"❌ Error: {e}")
            results.append(False)
    
    print("\n" + "="*60)
    if all(results):
        print("✅ Todas las validaciones pasaron!")
        print("\n🚀 Listo para deploy a AWS App Runner")
        print("\nPróximos pasos:")
        print("1. Push a GitHub: git push origin main")
        print("2. Ir a AWS App Runner Console")
        print("3. Create service desde GitHub")
        print("4. Configurar IAM role con permisos Bedrock")
        print("5. Deploy!")
        return 0
    else:
        failed = sum(1 for r in results if not r)
        print(f"❌ {failed} validaciones fallaron")
        print("\nRevisa los errores arriba y corrígelos antes de deployar.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
