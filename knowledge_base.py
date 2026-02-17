import os
import json
import numpy as np
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

KNOWLEDGE_DIR = "knowledge"
EMBEDDINGS_CACHE = "knowledge_embeddings.json"


def load_documents():
    """Load all text files from the knowledge directory and split into chunks."""
    chunks = []

    for filename in os.listdir(KNOWLEDGE_DIR):
        if not filename.endswith(".txt"):
            continue

        filepath = os.path.join(KNOWLEDGE_DIR, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # Split by double newlines to get natural sections
        sections = content.split("\n\n")

        for section in sections:
            section = section.strip()
            if len(section) < 20:  # Skip tiny fragments
                continue

            chunks.append({
                "source": filename,
                "content": section
            })

    return chunks


def get_embedding(text):
    """Get an embedding vector for a piece of text."""
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding


def cosine_similarity(a, b):
    """Calculate cosine similarity between two vectors."""
    a = np.array(a)
    b = np.array(b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def build_knowledge_base():
    """Load documents, generate embeddings, and cache them.

    This only needs to run once (or when documents change).
    Embeddings are cached to avoid re-calling the API.
    """
    # Check if cache exists
    if os.path.exists(EMBEDDINGS_CACHE):
        print("Loading cached embeddings...")
        with open(EMBEDDINGS_CACHE, "r") as f:
            return json.load(f)

    print("Building knowledge base (generating embeddings)...")
    chunks = load_documents()

    for chunk in chunks:
        print(f"  Embedding: {chunk['content'][:60]}...")
        chunk["embedding"] = get_embedding(chunk["content"])

    # Cache to disk
    with open(EMBEDDINGS_CACHE, "w") as f:
        json.dump(chunks, f)

    print(f"Knowledge base built: {len(chunks)} chunks embedded and cached.")
    return chunks


def search_knowledge(query, top_k=3):
    """Search the knowledge base for chunks most relevant to the query.

    Args:
        query: The user's question or search term
        top_k: Number of results to return

    Returns:
        List of the most relevant chunks with similarity scores
    """
    # Load the knowledge base (from cache if available)
    knowledge = build_knowledge_base()

    # Embed the query
    query_embedding = get_embedding(query)

    # Calculate similarity for each chunk
    results = []
    for chunk in knowledge:
        similarity = cosine_similarity(query_embedding, chunk["embedding"])
        results.append({
            "content": chunk["content"],
            "source": chunk["source"],
            "similarity": float(similarity)
        })

    # Sort by similarity (highest first) and return top_k
    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:top_k]


if __name__ == "__main__":
    # Run this directly to build/rebuild the knowledge base
    build_knowledge_base()
    print("\nTesting search...")
    results = search_knowledge("What is your warranty policy?")
    for r in results:
        print(f"\n[{r['similarity']:.3f}] ({r['source']})")
        print(f"  {r['content'][:100]}...")
