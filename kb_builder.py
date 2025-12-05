# kb_builder.py - Construye índices FAISS desde JSONs separados
import os
import json
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.schema import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv

load_dotenv()

CLIENTES_KB = "clientes_kb"
GENERAL_KB = "GENERAL_KB"
FAISS_DIR = "faiss_indices"

class KBBuilder:
    def __init__(self):
        self.embeddings = OpenAIEmbeddings()
        self.splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=300)
        os.makedirs(FAISS_DIR, exist_ok=True)
    
    def json_to_text(self, data, nivel=0):
        """Convierte estructura JSON a texto legible y limpio"""
        texto = ""
        indent = "  " * nivel
        
        if isinstance(data, dict):
            for key, value in data.items():
                if key.startswith("_") or key == "metadata":
                    continue
                
                titulo = key.replace("_", " ").title()
                
                # Formato más limpio sin líneas ===
                if nivel == 0:
                    texto += f"\n## {titulo.upper()}\n\n"
                else:
                    texto += f"\n{indent}**{titulo}:** "
                
                if isinstance(value, (dict, list)):
                    texto += "\n" + self.json_to_text(value, nivel + 1)
                else:
                    if nivel > 0:
                        texto += f"{value}\n"
                    else:
                        texto += f"{indent}{value}\n"
        
        elif isinstance(data, list):
            for i, item in enumerate(data, 1):
                if isinstance(item, dict):
                    # Formateo especial para pasos
                    if "paso" in item:
                        texto += f"\n{indent}{item['paso']}. **{item.get('titulo', '')}**\n"
                        texto += f"{indent}   {item.get('descripcion', '')}\n"
                    elif "nombre" in item and "ip" in item:
                        # Impresoras - formato especial
                        texto += f"\n{indent}• **{item['nombre']}**\n"
                        texto += f"{indent}  - IP: {item['ip']}\n"
                        if "ubicacion" in item:
                            texto += f"{indent}  - Ubicación: {item['ubicacion']}\n"
                    else:
                        texto += f"\n{indent}Item {i}:\n"
                        texto += self.json_to_text(item, nivel + 1)
                else:
                    texto += f"{indent}- {item}\n"
        
        return texto
    
    def cargar_clientes_json(self):
        """Carga JSONs separados por cliente"""
        docs_por_cliente = {}
        
        if not os.path.exists(CLIENTES_KB):
            return docs_por_cliente
        
        # Buscar archivos kb_*.json
        for archivo in os.listdir(CLIENTES_KB):
            if not (archivo.startswith("kb_") and archivo.endswith(".json")):
                continue
            
            cliente = archivo.replace("kb_", "").replace(".json", "")
            path = os.path.join(CLIENTES_KB, archivo)
            
            with open(path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Convertir a texto
            texto = f"CONFIGURACIÓN TÉCNICA - {config.get('metadata', {}).get('nombre_completo', cliente.upper())}\n"
            texto += self.json_to_text(config)
            
            doc = Document(
                page_content=texto,
                metadata={"source": "cliente", "cliente": cliente, "tipo": "configuracion"}
            )
            
            docs_por_cliente[cliente] = [doc]
            print(f"   ✓ {cliente}")
        
        return docs_por_cliente
    
    def cargar_general_jsons(self):
        """Carga todos los JSONs de troubleshooting general"""
        docs_general = []
        
        if not os.path.exists(GENERAL_KB):
            print(f"⚠️ No existe carpeta {GENERAL_KB}")
            return docs_general
        
        for archivo in os.listdir(GENERAL_KB):
            if not archivo.endswith('.json'):
                continue
            
            path = os.path.join(GENERAL_KB, archivo)
            
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                categoria = data.get("categoria", "general")
                titulo = data.get("titulo", categoria.upper())
                
                texto = f"GUÍA DE SOLUCIÓN - {titulo}\n"
                texto += f"Última actualización: {data.get('ultima_actualizacion', 'N/A')}\n\n"
                
                # Descripción
                if "descripcion" in data:
                    texto += f"{data['descripcion']}\n\n"
                
                # Diagnóstico rápido
                if "diagnostico_rapido" in data:
                    texto += "PASOS DE DIAGNÓSTICO RÁPIDO:\n\n"
                    for paso in data["diagnostico_rapido"]:
                        texto += f"{paso.get('paso', '')}. **{paso.get('titulo', '')}**\n"
                        texto += f"   {paso.get('descripcion', '')}\n\n"
                
                # Problemas comunes
                if "problemas_comunes" in data:
                    texto += "\nPROBLEMAS COMUNES Y SOLUCIONES:\n\n"
                    for nombre_problema, detalles in data["problemas_comunes"].items():
                        texto += f"• **{detalles.get('sintoma', nombre_problema)}**\n"
                        texto += "  Solución:\n"
                        for sol in detalles.get("solucion", []):
                            texto += f"  - {sol}\n"
                        texto += "\n"
                
                # Escalamiento
                if "escalamiento" in data:
                    texto += f"\nESCALAMIENTO:\n{data['escalamiento']}\n"
                
                doc = Document(
                    page_content=texto,
                    metadata={
                        "source": "general",
                        "categoria": categoria,
                        "archivo": archivo
                    }
                )
                
                docs_general.append(doc)
                print(f"   ✓ {archivo}")
                
            except Exception as e:
                print(f"   ✗ Error en {archivo}: {e}")
        
        return docs_general
    
    def construir(self):
        """Construye todos los índices FAISS"""
        print("="*60)
        print("  🔨 CONSTRUYENDO KNOWLEDGE BASE")
        print("="*60)
        
        # Cargar documentos
        print("\n📚 Cargando troubleshooting general...")
        docs_general = self.cargar_general_jsons()
        print(f"   Total: {len(docs_general)} documentos")
        
        print("\n🏢 Cargando configuraciones de clientes...")
        docs_clientes = self.cargar_clientes_json()
        
        for cliente, docs in docs_clientes.items():
            print(f"   ✓ {cliente}: {len(docs)} documentos")
        
        # Crear índice GENERAL
        if docs_general:
            print(f"\n🔍 Creando índice GENERAL...")
            chunks = self.splitter.split_documents(docs_general)
            vectorstore = FAISS.from_documents(chunks, self.embeddings)
            path = os.path.join(FAISS_DIR, "general")
            vectorstore.save_local(path)
            print(f"   ✓ {len(chunks)} chunks guardados en {path}")
        
        # Crear índices por CLIENTE (específico + general)
        print(f"\n🔍 Creando índices por cliente...")
        for cliente, docs_cliente in docs_clientes.items():
            docs_combinados = docs_cliente + docs_general
            
            print(f"   📦 {cliente.upper()}: {len(docs_cliente)} específicos + {len(docs_general)} generales")
            chunks = self.splitter.split_documents(docs_combinados)
            vectorstore = FAISS.from_documents(chunks, self.embeddings)
            path = os.path.join(FAISS_DIR, cliente)
            vectorstore.save_local(path)
            print(f"      ✓ {len(chunks)} chunks guardados")
        
        print("\n" + "="*60)
        print("  ✅ KNOWLEDGE BASE CONSTRUIDA")
        print("="*60)
        print(f"\n📊 Resumen:")
        print(f"   - Índice general: {len(docs_general)} docs")
        print(f"   - Índices clientes: {len(docs_clientes)}")
        print(f"   - Total índices: {1 + len(docs_clientes)}")
        print(f"\n🚀 Listo para ejecutar: python app.py\n")

def main():
    builder = KBBuilder()
    
    try:
        builder.construir()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()