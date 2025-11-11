#!/usr/bin/env python3
"""
Pre-flight diagnostics para Nova Sonic UDEP.
Verifica todos los requisitos del sistema antes de ejecutar.
"""
import os
import sys
import shutil
from pathlib import Path

def check_python_version():
    """Verifica versión mínima de Python."""
    version = sys.version_info
    min_version = (3, 10)
    
    if version >= min_version:
        print(f"✅ Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"❌ Python {version.major}.{version.minor} (se requiere >= 3.10)")
        return False

def check_ffmpeg():
    """Verifica que FFmpeg esté instalado y en PATH."""
    ffmpeg_path = shutil.which('ffmpeg')
    
    if ffmpeg_path:
        print(f"✅ FFmpeg encontrado: {ffmpeg_path}")
        return True
    else:
        print("❌ FFmpeg NO encontrado en PATH")
        print("   Instalar desde: https://ffmpeg.org/download.html")
        print("   Windows (Chocolatey): choco install ffmpeg")
        print("   Linux: sudo apt install ffmpeg")
        print("   macOS: brew install ffmpeg")
        return False

def check_aws_credentials():
    """Verifica configuración de credenciales AWS."""
    access_key = os.getenv('AWS_ACCESS_KEY_ID')
    secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    region = os.getenv('AWS_REGION') or os.getenv('AWS_DEFAULT_REGION')
    
    all_ok = True
    
    if access_key:
        masked = access_key[:8] + '...' if len(access_key) > 8 else '***'
        print(f"✅ AWS_ACCESS_KEY_ID: {masked}")
    else:
        print("⚠️  AWS_ACCESS_KEY_ID no configurado")
        all_ok = False
    
    if secret_key:
        print("✅ AWS_SECRET_ACCESS_KEY: configurado")
    else:
        print("⚠️  AWS_SECRET_ACCESS_KEY no configurado")
        all_ok = False
    
    if region:
        print(f"✅ AWS_REGION: {region}")
    else:
        print("⚠️  AWS_REGION no configurado (se usará us-east-1 por defecto)")
    
    return all_ok

def check_dependencies():
    """Verifica que las dependencias de Python estén instaladas."""
    required_packages = [
        'flask',
        'flask_socketio',
        'dotenv',
        'aws_sdk_bedrock_runtime',
        'reactivex'
    ]
    
    missing = []
    
    for package in required_packages:
        try:
            __import__(package.replace('_', '.').replace('-', '_'))
            print(f"✅ {package}")
        except ImportError:
            print(f"❌ {package} no instalado")
            missing.append(package)
    
    if missing:
        print(f"\n📦 Para instalar dependencias faltantes:")
        print(f"   pip install -r requirements.txt")
        return False
    
    return True

def check_config_files():
    """Verifica que existan los archivos de configuración críticos."""
    critical_files = [
        'config/context_udep_original.yaml',
        'context/prompts/udep_system_prompt_original_v6.txt',
        'kb/udep_catalog.json',
        '.env'
    ]
    
    all_ok = True
    
    for file_path in critical_files:
        path = Path(file_path)
        if path.exists():
            print(f"✅ {file_path}")
        else:
            print(f"⚠️  {file_path} no encontrado")
            if file_path == '.env':
                print("   Copia .env.example a .env y configura tus credenciales")
            all_ok = False
    
    return all_ok

def check_port_availability():
    """Verifica que el puerto 5000 esté disponible."""
    import socket
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', 5000))
        sock.close()
        
        if result == 0:
            print("⚠️  Puerto 5000 en uso (puede requerir detener otra instancia)")
            return False
        else:
            print("✅ Puerto 5000 disponible")
            return True
    except Exception as e:
        print(f"⚠️  No se pudo verificar puerto 5000: {e}")
        return True  # No bloquear por esto

def main():
    """Ejecuta todos los checks de diagnóstico."""
    print("🔍 Diagnóstico del Sistema Nova Sonic UDEP")
    print("=" * 60)
    
    # Load .env if exists
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    
    checks = [
        ("Python", check_python_version),
        ("FFmpeg", check_ffmpeg),
        ("Credenciales AWS", check_aws_credentials),
        ("Dependencias Python", check_dependencies),
        ("Archivos de configuración", check_config_files),
        ("Puerto 5000", check_port_availability)
    ]
    
    results = []
    
    for name, check_func in checks:
        print(f"\n📋 Verificando {name}...")
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ Error durante verificación: {e}")
            results.append((name, False))
    
    # Resumen
    print("\n" + "=" * 60)
    print("📊 Resumen de Diagnóstico")
    print("=" * 60)
    
    all_critical_passed = all(result for name, result in results if name in ["Python", "FFmpeg", "Dependencias Python"])
    
    for name, result in results:
        status = "✅" if result else "⚠️"
        print(f"{status} {name}")
    
    print()
    
    if all_critical_passed:
        print("✅ Sistema listo para ejecutar")
        print("\n🚀 Para iniciar el servidor:")
        print("   python app.py")
        return 0
    else:
        print("⚠️  Algunos checks fallaron. Revisa los errores arriba.")
        print("\n📚 Para más ayuda, consulta README.md sección Troubleshooting")
        return 1

if __name__ == '__main__':
    sys.exit(main())
