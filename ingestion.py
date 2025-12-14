import os
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma

load_dotenv()

DATA_PATH = "data/company_policy.pdf"
DB_PATH = "chroma_db"

def ingest_docs():
    # 1. Check if file exists
    if not os.path.exists(DATA_PATH):
        print(f"❌ Error: File not found at {DATA_PATH}")
        return

    print("📄 Loading PDF...")
    loader = PyPDFLoader(DATA_PATH)
    docs = loader.load()

    # 2. Split Text
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=600, chunk_overlap=100)
    splits = text_splitter.split_documents(docs)

    # 3. Embed & Store
    print("💾 Saving to vector store...")
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    
    # This creates the folder 'chroma_db' in your project root
    Chroma.from_documents(
        documents=splits,
        embedding=embeddings,
        persist_directory=DB_PATH
    )
    
    print("✅ Success! Knowledge base saved locally.")

if __name__ == "__main__":
    ingest_docs()