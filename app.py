# app.py - VERSIÓN FUNCIONAL CON GLPI 10.18
import os
import json
from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
from dotenv import load_dotenv

from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain.chains import RetrievalQA

import requests
from datetime import datetime
import re

load_dotenv()

AFFIRMATIVE = ["sí", "si", "ok", "gracias", "funciona", "arreglado", "resuelto", "perfecto", "listo"]
NEGATIONS = ["no ", "no,", "no.", "nunca", "sin ", "no se", "no me"]

def contains_word(text, word):
    return re.search(rf"\b{re.escape(word)}\b", text, re.IGNORECASE) is not None

def is_affirmative(text):
    text = text.lower()
    for a in AFFIRMATIVE:
        if contains_word(text, a):
            tokens = re.findall(r"\b\w+\b", text)
            for i, t in enumerate(tokens):
                if t == a.replace("í","i"):
                    window = " ".join(tokens[max(0, i-3):i]).lower()
                    if any(neg.strip() in window for neg in NEGATIONS):
                        return False
                    return True
    return False

def is_negative(text):
    text = text.lower()
    neg_patterns = ["no", "sigue sin funcionar", "no funciona", "nada", "no puedo", "no puedo acceder", "fallando"]
    return any(pat in text for pat in neg_patterns)

PASOS_TROUBLESHOOTING = {
    "vpn": [
        {
            "paso": 1,
            "pregunta": "¿Tienes **conexión a internet** activa?\n\n👉 Responde: **tengo internet** / **no tengo internet**",
            "si_falla": "paso_2"
        },
        {
            "paso": 2,
            "pregunta": "Verifica la configuración y intenta conectar:\n• Servidor correcto\n• Usuario y contraseña de red\n\n👉 Responde: **ya conectó** / **no conecta**",
            "datos_cliente": True,
            "si_falla": "paso_3"
        },
        {
            "paso": 3,
            "pregunta": "Último intento:\n1. Cierra el cliente VPN\n2. Reinicia tu equipo\n3. Vuelve a conectar\n\n👉 Responde: **funcionó** / **no funcionar**",
            "si_falla": "ticket"
        }
    ],
    
    "impresora": [
        {
            "paso": 1,
            "pregunta": "¿La impresora está **encendida** y tiene **papel**?\n\n👉 Responde: **sí está** / **no está**",
            "si_falla": "paso_2"
        },
        {
            "paso": 2,
            "pregunta": "Verifica la conexión:\n• Si es USB: desconecta y reconecta\n• Si es red: verifica que esté en la misma red\n\n👉 Responde: **ya imprime** / **sigue sin imprimir**",
            "datos_cliente": True,
            "si_falla": "paso_3"
        },
        {
            "paso": 3,
            "pregunta": "Cancela trabajos pendientes:\n1. Panel de Control > Impresoras\n2. Cancelar todos los documentos\n\n👉 Responde: **ya funciona** / **no funciona**",
            "si_falla": "paso_4"
        },
        {
            "paso": 4,
            "pregunta": "Reinicia el servicio:\n1. Busca 'Servicios'\n2. 'Cola de impresión' > Reiniciar\n\n👉 Responde: **resuelto** / **sigue igual**",
            "si_falla": "ticket"
        }
    ],
    "lentitud": [
        {
            "paso": 1,
            "pregunta": "¿Has cerrado todas las aplicaciones y pestañas innecesarias del navegador?\n\n👉 Responde: **ya cerré todo** / **no he cerrado**",
            "si_falla": "paso_2"
        },
        {
            "paso": 2,
            "pregunta": "Reinicia tu equipo ahora:\n1. Guarda tu trabajo\n2. Reinicia completamente\n\n👉 Responde: **ya reinicié** / **no puedo reiniciar**",
            "si_falla": "paso_3"
        },
        {
            "paso": 3,
            "pregunta": "Verifica tu conexión VPN o WiFi:\nLa lentitud suele venir por conexión inestable.\n\n👉 Responde: **conexión buena** / **conexión mala**",
            "datos_cliente": True,
            "si_falla": "paso_4"
        },
        {
            "paso": 4,
            "pregunta": "Limpia espacio en disco:\n1. Busca 'Liberador de espacio en disco'\n2. Selecciona unidad C: y limpia archivos temporales\n\n👉 Responde: **ya limpié** / **no mejoró**",
            "si_falla": "paso_5"
        },
        {
            "paso": 5,
            "pregunta": "Último intento:\n1. Cierra sesión de Windows\n2. Vuelve a iniciar sesión\n\n👉 Responde: **mejoró** / **sigue lento**",
            "si_falla": "ticket"
        }
    ]
}



def create_glpi_ticket(ticket_data, cliente):
    """Crea ticket en GLPI 10.18 LOCAL con XAMPP"""
    
    # 🔗 VERSION LOCAL
    GLPI_BASE = "https://springily-unshivered-belkis.ngrok-free.dev"
    GLPI_API = f"{GLPI_BASE}/glpi/apirest.php"
    
    # 🔑 Credenciales + App-Token REAL
    APP_TOKEN = "3hhObE3m2ODPr93CNiK0HdgFIdtbyLvlQjLrclQn"  # ✅ TU TOKEN
    USERNAME = "glpi"
    PASSWORD = "glpi"
    
    try:
        print(f"🔌 Conectando a GLPI LOCAL: {GLPI_API}")
        
        # 1️⃣ INICIAR SESIÓN
        session_response = requests.get(
            f"{GLPI_API}/initSession",
            auth=(USERNAME, PASSWORD),
            headers={
                "Content-Type": "application/json",
                "App-Token": APP_TOKEN
            },
            timeout=10
        )
        
        if session_response.status_code != 200:
            print(f"❌ Error initSession ({session_response.status_code})")
            print(f"Respuesta: {session_response.text[:500]}")
            return {
                "success": False,
                "message": f"Error de autenticación: {session_response.status_code}"
            }
        
        session_token = session_response.json().get("session_token")
        print(f"✅ Sesión iniciada: {session_token}")
        
        # 2️⃣ HEADERS
        headers = {
            "Session-Token": session_token,
            "App-Token": APP_TOKEN,
            "Content-Type": "application/json"
        }
        
        # 3️⃣ DESCRIPCIÓN
        descripcion = f"""🤖 TICKET GENERADO POR SOPORTE-AVI
════════════════════════════════════════

👤 Usuario: {ticket_data.get('nombre', 'N/A')}
📧 Correo: {ticket_data.get('correo', 'N/A')}
📞 Teléfono: {ticket_data.get('telefono', 'N/A')}
🏢 Empresa: {cliente}

❌ Problema:
{ticket_data.get('problema', 'No especificado')}

📝 Contexto: {ticket_data.get('contexto', 'N/A')}
⏰ Fecha: {ticket_data.get('fecha', 'N/A')}
════════════════════════════════════════
"""
        
        # 4️⃣ PAYLOAD
        problema_corto = ticket_data.get('problema', 'Problema técnico')[:60]
        
        payload = {
            "input": {
                "name": f"[{cliente}] {problema_corto}",
                "content": descripcion,
                "entities_id": 0,
                "type": 1,
                "urgency": 3,
                "impact": 3,
                "priority": 3,
                "requesttypes_id": 1,
                "status": 1
            }
        }
        
        print(f"📤 Creando ticket: {payload['input']['name']}")
        
        # 5️⃣ CREAR TICKET
        create_response = requests.post(
            f"{GLPI_API}/Ticket",
            headers=headers,
            json=payload,
            timeout=10
        )
        
        print(f"📬 Respuesta: {create_response.status_code}")
        print(f"📄 Contenido: {create_response.text[:500]}")
        
        # 6️⃣ CERRAR SESIÓN
        try:
            requests.get(f"{GLPI_API}/killSession", headers=headers)
            print("🔒 Sesión cerrada")
        except:
            pass
        
        # 7️⃣ VERIFICAR RESULTADO
        if create_response.status_code in [200, 201]:
            ticket_info = create_response.json()
            ticket_id = ticket_info.get("id")
            
            if ticket_id:
                print(f"✅ Ticket #{ticket_id} creado exitosamente")
                return {
                    "success": True,
                    "ticket_id": ticket_id,
                    "message": "Ticket creado exitosamente"
                }
        
        # Error
        print(f"❌ Error creando ticket: {create_response.text[:500]}")
        return {
            "success": False,
            "message": f"No se pudo crear el ticket (código {create_response.status_code})"
        }
            
    except requests.exceptions.ConnectionError:
        print("❌ Error de conexión a GLPI local")
        return {
            "success": False,
            "message": "No se pudo conectar a GLPI. Verifica que XAMPP esté ejecutándose."
        }
    except Exception as e:
        print(f"❌ Excepción: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }


def get_paso_troubleshooting(categoria, paso_num, cliente=None):
    """Obtiene el paso específico de troubleshooting"""
    if categoria not in PASOS_TROUBLESHOOTING:
        return None
    
    pasos = PASOS_TROUBLESHOOTING[categoria]
    
    if paso_num > len(pasos):
        return None
    
    paso = pasos[paso_num - 1]
    pregunta = paso["pregunta"]
    
    # Insertar datos del cliente si es necesario
    if paso.get("datos_cliente") and cliente:
        cliente_lower = cliente.lower()
        if cliente_lower in CLIENTES_CONFIG:
            config = CLIENTES_CONFIG[cliente_lower]
            
            if categoria == "impresora" and "impresoras" in config:
                pregunta += f"\n\n📌 **Tu impresora:**"
                for imp in config["impresoras"]:
                    pregunta += f"\n- {imp['nombre']}: `{imp['ip']}`"
            
            elif categoria == "vpn" and "vpn" in config:
                vpn = config["vpn"]
                pregunta += f"\n\n📌 **Tu configuración VPN:**"
                pregunta += f"\n- Servidor: `{vpn['servidor']}`"
                pregunta += f"\n- Puerto: `{vpn['puerto']}`"
            
            elif categoria == "wifi" and "wifi" in config:
                wifi = config["wifi"]
                pregunta += f"\n\n📌 **Tu red WiFi:**"
                pregunta += f"\n- SSID: `{wifi['ssid']}`"
                pregunta += f"\n- Contraseña: `{wifi['password']}`"
    
    return {
        "pregunta": pregunta,
        "siguiente": paso["si_falla"],
        "paso_actual": paso_num
    }

def limpiar_respuesta(texto):
    """Limpia caracteres especiales y formato feo"""
    reemplazos = {
        '\u0000': '0', '\x00': '',
        'ï¬': 'fi', 'ï¬‚': 'fl', 'oï¬': 'of',
        'Ã¡': 'á', 'Ã©': 'é', 'Ã­': 'í', 'Ã³': 'ó', 'Ãº': 'ú',
        'Ã±': 'ñ',
    }
    
    for viejo, nuevo in reemplazos.items():
        texto = texto.replace(viejo, nuevo)
    
    texto = re.sub(r'={40,}', '', texto)
    texto = re.sub(r'===\s*\w+\s*===', '', texto)
    texto = re.sub(r'\n{3,}', '\n\n', texto)
    
    return texto.strip()

def cargar_config_clientes():
    """Carga JSONs separados de cada cliente"""
    config_dir = "clientes_kb"
    clientes = {}
    
    if not os.path.exists(config_dir):
        print(f"⚠️ No existe carpeta {config_dir}")
        return {}
    
    for archivo in os.listdir(config_dir):
        if archivo.startswith("kb_") and archivo.endswith(".json"):
            cliente_nombre = archivo.replace("kb_", "").replace(".json", "")
            
            path = os.path.join(config_dir, archivo)
            with open(path, 'r', encoding='utf-8') as f:
                clientes[cliente_nombre] = json.load(f)
            
            print(f"✓ {cliente_nombre} cargado desde {archivo}")
    
    return clientes

CLIENTES_CONFIG = cargar_config_clientes()

def enriquecer_con_datos_reales(texto, cliente):
    """Agrega datos reales del JSON cuando faltan en la respuesta"""
    cliente_lower = cliente.lower()
    
    if cliente_lower not in CLIENTES_CONFIG:
        return texto
    
    config = CLIENTES_CONFIG[cliente_lower]
    
    if "impresora" in texto.lower() and "impresoras" in config:
        if not re.search(r'\d+\.\d+\.\d+\.\d+', texto):
            texto += "\n\n**📌 Impresoras de " + cliente.title() + ":**\n"
            
            for imp in config["impresoras"]:
                texto += f"\n• **{imp['nombre']}**"
                texto += f"\n  IP: `{imp['ip']}`"
                texto += f"\n  Ubicación: {imp['ubicacion']}\n"
    
    if "vpn" in texto.lower() and "vpn" in config:
        if "servidor" not in texto.lower():
            vpn = config["vpn"]
            texto += f"\n\n**📡 Configuración VPN:**"
            texto += f"\n- Servidor: `{vpn['servidor']}`"
            texto += f"\n- Puerto: `{vpn['puerto']}`"
            texto += f"\n- Cliente: {vpn['nombre']}\n"
    
    if "wifi" in texto.lower() and "wifi" in config:
        if "contraseña" not in texto.lower() or "password" not in texto.lower():
            wifi = config["wifi"]
            texto += f"\n\n**📶 Red WiFi:**"
            texto += f"\n- SSID: `{wifi['ssid']}`"
            texto += f"\n- Contraseña: `{wifi['password']}`\n"
    
    return texto

app = Flask(__name__)
app.secret_key = "andres_mora_soporte_avi_2025_final_100"
CORS(app)

FAISS_DIR = "faiss_indices"

embeddings = OpenAIEmbeddings()
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1)
vectorstores_cache = {}

def get_qa_chain_for_client(cliente):
    """Carga el índice FAISS del cliente"""
    cliente_lower = cliente.lower() if cliente else "general"
    
    if cliente_lower in vectorstores_cache:
        return vectorstores_cache[cliente_lower]
    
    index_path = os.path.join(FAISS_DIR, cliente_lower)
    
    if not os.path.exists(index_path):
        print(f"⚠️ No existe índice para {cliente_lower}, usando 'general'")
        index_path = os.path.join(FAISS_DIR, "general")
    
    try:
        vectorstore = FAISS.load_local(
            index_path, 
            embeddings, 
            allow_dangerous_deserialization=True
        )
        retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
        qa_chain = RetrievalQA.from_chain_type(
            llm=llm, 
            chain_type="stuff", 
            retriever=retriever
        )
        
        vectorstores_cache[cliente_lower] = qa_chain
        print(f"✓ Índice {cliente_lower} cargado")
        
        return qa_chain
    
    except Exception as e:
        print(f"❌ Error cargando índice {cliente_lower}: {e}")
        raise

try:
    get_qa_chain_for_client(None)
    rag_ready = True
    print("RAG cargado correctamente")
except Exception as e:
    print(f"ERROR RAG: {e}")
    rag_ready = False

@app.route("/chat", methods=["POST"])
def chat():
    if not rag_ready:
        return jsonify({"response": "Base de conocimiento no disponible"}), 500

    mensaje = request.get_json().get("message", "").strip()
    mensaje_lower = mensaje.lower()

    cliente = session.get("cliente")
    estado = session.get("estado", "inicio")

    palabras_clave = ["vpn", "wifi", "impresora", "imprime", "office", "siigo", "autocad", 
                      "contabilidad", "licencia", "configuración", "acceso", "lento", "lentitud"]

    # 1. DETECTAR PROBLEMA TÉCNICO → PREGUNTAR EMPRESA
    if not cliente and any(pal in mensaje_lower for pal in palabras_clave):
        session["problema_original"] = mensaje
        session["estado"] = "esperando_cliente"
        return jsonify({"response": "Entendido, te ayudo con eso.\n\n¿A qué empresa perteneces?\n\nOpciones: **Ventura**, **Axia**, **Setri**"})

    # 2. DETECTAR EMPRESA → INICIAR TROUBLESHOOTING O RESPUESTA DIRECTA
    if estado == "esperando_cliente":
        if "ventura" in mensaje_lower:
            cliente_nombre = "Ventura"
        elif "axia" in mensaje_lower:
            cliente_nombre = "Axia"
        elif "setri" in mensaje_lower:
            cliente_nombre = "Setri"
        else:
            return jsonify({"response": "Por favor escribe: **Ventura**, **Axia** o **Setri**"})

        session["cliente"] = cliente_nombre
        problema = session.get('problema_original', '').lower()
        
        if any(w in problema for w in ["impresora", "imprimir", "imprime"]):
            categoria = "impresora"
        elif any(w in problema for w in ["vpn", "conexión remota", "remoto"]):
            categoria = "vpn"
        elif any(w in problema for w in ["wifi", "red", "internet"]):
            categoria = "wifi"
        else:
            categoria = None
        
        if categoria and categoria in PASOS_TROUBLESHOOTING:
            session["estado"] = "troubleshooting"
            session["categoria"] = categoria
            session["paso_actual"] = 1
            
            primer_paso = get_paso_troubleshooting(categoria, 1, cliente_nombre)
            return jsonify({"response": primer_paso["pregunta"]})
        
        else:
            session["estado"] = "resolviendo"
            qa_chain = get_qa_chain_for_client(cliente_nombre)
            
            prompt = f"""Eres Soporte-AVI de {cliente_nombre}.
Usuario reporta: "{session.get('problema_original', '')}"
Respuesta clara con pasos numerados.
Al final: ¿Se solucionó tu problema? (sí/no)"""
            
            result = qa_chain.invoke({"query": prompt})
            respuesta = limpiar_respuesta(result["result"])
            respuesta = enriquecer_con_datos_reales(respuesta, cliente_nombre)
            
            return jsonify({"response": respuesta})

    # 3. TROUBLESHOOTING PASO A PASO
    if estado == "troubleshooting":
        categoria = session.get("categoria")
        paso_actual = session.get("paso_actual", 1)
        
        exito = ["funcionó", "funciona", "ya conectó", "conectó", "ya imprime", 
                "resuelto", "listo", "ya está", "ya funciona"]
        
        falla = ["no conecta", "sigue sin", "no funciona", "no imprime", 
                "sigue igual", "no tengo", "no está"]
        
        if any(palabra in mensaje_lower for palabra in exito):
            session.clear()
            return jsonify({"response": "¡Perfecto! 🎉 Me alegra que funcionara.\n\n✨ *Conversación cerrada*"})
        
        if any(palabra in mensaje_lower for palabra in falla):
            paso_info = get_paso_troubleshooting(categoria, paso_actual, cliente)
            
            if paso_info and paso_info["siguiente"] == "ticket":
                session["estado"] = "ticket_nombre"
                return jsonify({"response": "Entendido. Crearemos un ticket.\n\n📋 **1.** ¿Nombre completo?"})
            else:
                session["paso_actual"] += 1
                siguiente = get_paso_troubleshooting(categoria, session["paso_actual"], cliente)
                return jsonify({"response": siguiente["pregunta"]})
        
        else:
            return jsonify({"response": "⚠️ No entendí.\n\nPor favor responde:\n• Si funcionó: **ya funciona** / **resuelto**\n• Si no: **no funciona** / **sigue sin funcionar**"})

    # 4. ¿SE SOLUCIONÓ? (flujo normal - sin troubleshooting)
    if cliente and estado == "resolviendo":
        if is_affirmative(mensaje_lower):
            session.clear()
            return jsonify({"response": "¡Genial! Me alegra haber ayudado.\nQue tengas un excelente día ✨\n*Conversación cerrada*"})
        if is_negative(mensaje_lower):
            session["estado"] = "ticket_nombre"
            return jsonify({"response": "Lo siento. Vamos a crear un ticket.\n\n📋 **1.** ¿Nombre completo?"})

    # 5. CAPTURA TICKET - NOMBRE
    if estado == "ticket_nombre":
        session["ticket_nombre"] = mensaje
        session["estado"] = "ticket_correo"
        return jsonify({"response": f"Gracias {mensaje}.\n\n📧 **2.** ¿Cuál es tu correo electrónico?"})
    
    # 6. CAPTURA TICKET - CORREO
    if estado == "ticket_correo":
        if "@" not in mensaje:
            return jsonify({"response": "⚠️ Por favor ingresa un correo válido (con @)"})
        
        session["ticket_correo"] = mensaje
        session["estado"] = "ticket_tel"
        return jsonify({"response": "📞 **3.** ¿Tu número de teléfono?"})
    
    # 7. CAPTURA TICKET - TELÉFONO Y CREACIÓN
    if estado == "ticket_tel":
        session["telefono"] = mensaje.strip()
        
        ticket_data = {
            "nombre": session.get("ticket_nombre"),
            "correo": session.get("ticket_correo"),
            "telefono": session.get("telefono"),
            "problema": session.get("problema_original", "No especificado"),
            "contexto": f"Categoría: {session.get('categoria', 'N/A')} | Paso alcanzado: {session.get('paso_actual', 'N/A')}",
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        resultado = create_glpi_ticket(ticket_data, cliente)
        
        session.clear()
        
        if resultado["success"]:
            return jsonify({
                "response": f"""✅ **¡Ticket creado exitosamente!**

🎫 Ticket #{resultado['ticket_id']}
👤 {ticket_data['nombre']}
📧 {ticket_data['correo']}

Nuestro equipo se pondrá en contacto pronto.

*Conversación cerrada*"""
            })
        else:
            return jsonify({
                "response": f"""⚠️ **Hubo un problema al crear el ticket:**

{resultado['message']}

Por favor contacta directamente a soporte.

*Conversación cerrada*"""
            })

    # 8. RESPUESTA GENÉRICA
    qa_chain = get_qa_chain_for_client(None)
    result = qa_chain.invoke({"query": mensaje})
    respuesta = limpiar_respuesta(result["result"])
    return jsonify({"response": respuesta + "\n\n¿Algo más en lo que te ayude?"})

@app.route("/health")
def health():
    return jsonify({"status": "healthy", "rag": rag_ready})

@app.route("/")
def home():
    session.clear()
    return render_template("index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)