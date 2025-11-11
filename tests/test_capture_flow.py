import os
import sys

ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Test deprecated - PERulesV1 replaced by ToolUseProcessor
# from processors.tool_use_processor import ToolUseProcessor


def simulate_flow():
    # p = ToolUseProcessor()
    print("⚠️ Test deprecated: PERulesV1 replaced by ToolUseProcessor with AWS native Tool Use")
    return

    # Assistant asks for name
    p.on_assistant_text("¿Cuál es tu nombre completo?")
    # User provides name with fillers
    p.on_user_text("eh me llamo andré alata")
    # Assistant confirms
    p.on_assistant_text("Nombre: André Alata. ¿Es correcto?")
    # User confirms
    p.on_user_text("sí eso es correcto")

    # Assistant asks DNI
    p.on_assistant_text("Ahora necesito tu DNI en parejas de dígitos, por favor")
    # User provides DNI in words
    p.on_user_text("mi dni es setenta cuarenta y nueve ochenta y nueve setenta y ocho")
    # Assistant confirms DNI
    p.on_assistant_text("DNI: 70 49 89 78. ¿Es correcto?")
    # User confirms
    p.on_user_text("sí")

    # Assistant asks phone
    p.on_assistant_text("Ahora tu número de contacto, también en parejas de dígitos")
    # User provides phone
    # Include zero as spoken to reach 9 digits
    p.on_user_text("nueve cinco tres siete tres cero uno ocho nueve")
    # Assistant confirms phone (with pairs)
    p.on_assistant_text("Teléfono: 95 37 30 18 9. ¿Es correcto?")
    p.on_user_text("sí")

    # Assistant asks email
    p.on_assistant_text("¿Cuál es tu correo electrónico?")
    # User provides email with speech patterns
    p.on_user_text("anedre123 45 arroba gmail punto com")
    # Assistant confirms
    p.on_assistant_text("Correo: anedre12345@gmail.com. ¿Es correcto?")
    p.on_user_text("sí correcto")

    # Program interest
    p.on_assistant_text("¿En qué programa estás interesado? Tenemos MBA en Finanzas, Maestría en Data Science y Diplomado en Ciberseguridad")
    p.on_user_text("me interesa el mba en finanzas")

    # Modality
    p.on_assistant_text("¿Prefieres modalidad presencial, híbrida u online?")
    p.on_user_text("híbrida")

    # Schedule
    p.on_assistant_text("¿Qué horario te viene mejor? semana, fin de semana o intensivo online")
    p.on_user_text("fin de semana")

    # Consent
    p.on_assistant_text("¿Nos autorizas a compartir tus datos para que un asesor humano te contacte?")
    p.on_user_text("sí, doy mi consentimiento")

    return p.snapshot_lead()


if __name__ == "__main__":
    lead = simulate_flow()
    from pprint import pprint
    pprint(lead)
