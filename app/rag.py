import os
# --- ADD THESE TWO LINES AT THE VERY TOP ---
from dotenv import load_dotenv
load_dotenv()  # This loads OPENAI_API_KEY immediately

from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings

# Define the path to the database folder
DB_PATH = "chroma_db"

print("⏳ Loading Database into Memory... (Runs once)")

# Now this will work because the key is loaded
embedding_function = OpenAIEmbeddings(model="text-embedding-3-small")
db = Chroma(persist_directory=DB_PATH, embedding_function=embedding_function)

print("✅ Database Loaded!")

def retrieve_info(query: str):
    results = db.similarity_search(query, k=3)
    if results:
        return "\n\n".join([doc.page_content for doc in results])
    else:
        return "No relevant company policy found."