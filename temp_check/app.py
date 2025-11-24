""" Chatbot Soporte-AVI - RAG con OpenAI + Flask para Microsoft Teams (FIX 2025: proxies + key) """
import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from flask import render_template

# IMPORTS ESTABLES con langchain-classic para RetrievalQA (si instalado; sino, usa nueva API)
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import PromptTemplate
try:
    from langchain_classic.chains import RetrievalQA
    USE_LEGACY = True
except ImportError:
    from langchain.chains import create_retrieval_chain
    from langchain.chains.combine_documents import create_stuff_documents_chain
    from langchain_core.prompts import ChatPromptTemplate
    USE_LEGACY = False

# --- CONFIG ---
load_dotenv()
app = Flask(__name__)
CORS(app)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
FAISS_INDEX_PATH = "faiss_index"

vectorstore = None
qa_chain = None

def initialize_rag():
    global vectorstore, qa_chain
    if not OPENAI_API_KEY:
        print("ERROR: OPENAI_API_KEY no configurada – verifica .env")
        return False

    if not os.path.exists(FAISS_INDEX_PATH):
        print(f"ERROR: No existe la carpeta {FAISS_INDEX_PATH}. Ejecuta index_pdfs.py primero")
        return False

    try:
        # Explicit api_key para evitar OpenAIError
        embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
        vectorstore = FAISS.load_local(
            FAISS_INDEX_PATH,
            embeddings,
            allow_dangerous_deserialization=True
        )

        llm = ChatOpenAI(
            model="gpt-3.5-turbo",
            temperature=0.1,
            openai_api_key=OPENAI_API_KEY  # Explicit para fix key error
        )

        prompt_template = """Eres Soporte-AVI, un asistente técnico profesional y amable.
Responde ÚNICAMENTE basándote en el contexto que se te proporciona.
Si no sabes la respuesta, di: "Lo siento, esa información no está en mi base de conocimiento de TI. ¿Quieres que cree un ticket para que un técnico te ayude?"

Contexto:
{context}

Pregunta del usuario: {question}
Respuesta útil y clara:"""

        if USE_LEGACY:
            PROMPT = PromptTemplate(
                template=prompt_template,
                input_variables=["context", "question"]
            )

            qa_chain = RetrievalQA.from_chain_type(
                llm=llm,
                chain_type="stuff",
                retriever=vectorstore.as_retriever(search_kwargs={"k": 4}),
                chain_type_kwargs={"prompt": PROMPT},
                return_source_documents=False
            )
        else:
            system_prompt = prompt_template.replace("{question}", "{input}")
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("human", "{input}")
            ])

            question_answer_chain = create_stuff_documents_chain(llm, prompt)
            retriever = vectorstore.as_retriever(search_kwargs={"k": 4})
            qa_chain = create_retrieval_chain(retriever, question_answer_chain)

        print("Sistema RAG inicializado correctamente (con fix proxies y key)")
        return True

    except Exception as e:
        print(f"Error inicializando RAG: {e}")
        return False

# Inicializar al arrancar
rag_ready = initialize_rag()

# --- RUTAS FLASK ---
@app.route("/")
def home():
     return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    if not rag_ready:
        return jsonify({"response": "Error interno: RAG no inicializado. Verifica logs."}), 500

    data = request.get_json()
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"response": "Por favor escribe tu duda técnica"}), 400

    try:
        if USE_LEGACY:
            result = qa_chain.invoke({"query": message})
            respuesta = result["result"]
        else:
            result = qa_chain.invoke({"input": message})
            respuesta = result["answer"]
        return jsonify({"response": respuesta})
    except Exception as e:
        print(f"Error en chat: {e}")
        return jsonify({"response": "Ups, algo falló. Inténtalo de nuevo en unos segundos."}), 500

# Rutas obligatorias para Teams
@app.route("/privacy")
def privacy():
    return "Política de privacidad: Tus consultas se procesan con OpenAI y no se almacenan."

@app.route("/terms")
def terms():
    return "Términos: Soporte-AVI es un proyecto universitario para mejorar la atención IT."

@app.route("/health")
def health():
    return jsonify({"status": "healthy", "rag": rag_ready})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)