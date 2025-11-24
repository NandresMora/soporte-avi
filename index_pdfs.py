import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS

# --- CONFIGURACIÓN ---
# Asegúrate de que tu clave de API de OpenAI esté configurada como variable de entorno
# set OPENAI_API_KEY='TU_CLAVE_DE_API_AQUI' (ya lo tienes temporal)

# Directorio donde se encuentran tus PDFs de TI
PDF_DIR = "IT_FAQ_Docs"

# Nombre del archivo de índice vectorial que se creará
FAISS_INDEX_PATH = "faiss_index_soporte_avi"

def create_vector_index():
    """ Carga PDFs, los divide en fragmentos, crea embeddings y guarda el índice FAISS. """
    if not os.path.exists(PDF_DIR):
        print(f"Error: El directorio '{PDF_DIR}' no existe. Por favor, créalo y coloca tus PDFs dentro.")
        return

    documents = []
    for filename in os.listdir(PDF_DIR):
        if filename.endswith(".pdf"):
            filepath = os.path.join(PDF_DIR, filename)
            print(f"Cargando {filename}...")
            loader = PyPDFLoader(filepath)
            documents.extend(loader.load())

    if not documents:
        print("No se encontraron PDFs para indexar.")
        return

    # 1. Dividir documentos en fragmentos (chunks)
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
    )
    texts = text_splitter.split_documents(documents)
    print(f"Documentos divididos en {len(texts)} fragmentos.")

    # 2. Crear Embeddings
    print("Creando embeddings (esto puede tardar y consumir tokens de OpenAI)...")
    embeddings = OpenAIEmbeddings()

    # 3. Crear y guardar el índice vectorial FAISS
    vectorstore = FAISS.from_documents(texts, embeddings)
    vectorstore.save_local(FAISS_INDEX_PATH)
    print(f"\n✅ Índice vectorial creado y guardado en: {FAISS_INDEX_PATH}")

if __name__ == "__main__":
    create_vector_index()