"""
vector_store.py — ChromaDB wrapper for persistent embedding storage.

Each section type (ME, RE, EQ, AB, IN, LR, CO, FU) gets its own collection.
Embeddings are computed once per section and stored permanently.
"""
import chromadb
import numpy as np
import os

# --- CONFIGURATION ---
CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(__file__), "chroma_store")
COLLECTION_PREFIX = "sections_"

# Nomic requires this prefix for document embeddings
PREFIX_DOC = "search_document: "


class VectorStore:
    def __init__(self, persist_dir=CHROMA_PERSIST_DIR):
        """Initialize persistent ChromaDB client."""
        self.persist_dir = persist_dir
        self.client = chromadb.PersistentClient(path=persist_dir)
        print(f"📦 ChromaDB initialized at: {persist_dir}")

    def _collection_name(self, section_code):
        """Convert section code to ChromaDB collection name."""
        return f"{COLLECTION_PREFIX}{section_code}"

    def get_collection(self, section_code):
        """Get or create a collection for a section type."""
        return self.client.get_or_create_collection(
            name=self._collection_name(section_code),
            metadata={"hnsw:space": "cosine"}  # Use cosine similarity
        )

    def get_existing_ids(self, section_code):
        """Get all section IDs already stored in a collection."""
        collection = self.get_collection(section_code)
        if collection.count() == 0:
            return set()
        
        # Fetch all IDs from the collection
        result = collection.get()
        return set(result["ids"])

    def store_embeddings(self, sections, model, section_code):
        """
        Embed sections and store in ChromaDB. Skips already-stored sections.
        
        Args:
            sections: List of SQLite Row objects with 'id', 'paper_id', 'content'
            model: SentenceTransformer model instance
            section_code: e.g. 'ME', 'RE', 'AB'
        
        Returns:
            Number of NEW embeddings stored
        """
        collection = self.get_collection(section_code)
        existing_ids = self.get_existing_ids(section_code)

        # Filter to only new sections
        new_sections = [
            s for s in sections
            if str(s['id']) not in existing_ids
        ]

        if not new_sections:
            print(f"   ⏭️  All {len(sections)} sections already embedded. Skipping.")
            return 0

        print(f"   📝 Embedding {len(new_sections)} new sections "
              f"({len(sections) - len(new_sections)} already stored)...")

        # Prepare texts with Nomic prefix
        texts = [PREFIX_DOC + s['content'] for s in new_sections]

        # Compute embeddings (batch_size=4 for Intel Mac RAM)
        embeddings = model.encode(
            texts,
            batch_size=4,
            show_progress_bar=True,
            convert_to_numpy=True
        )

        # Store in ChromaDB (batch to avoid hitting limits)
        BATCH_SIZE = 100
        for i in range(0, len(new_sections), BATCH_SIZE):
            batch_end = min(i + BATCH_SIZE, len(new_sections))
            batch_sections = new_sections[i:batch_end]
            batch_embeddings = embeddings[i:batch_end]

            collection.add(
                ids=[str(s['id']) for s in batch_sections],
                embeddings=[emb.tolist() for emb in batch_embeddings],
                metadatas=[{
                    "paper_id": s['paper_id'],
                    "section_code": section_code
                } for s in batch_sections],
                documents=[s['content'][:1000] for s in batch_sections]  # Store preview
            )

        print(f"   ✅ Stored {len(new_sections)} new embeddings in ChromaDB.")
        return len(new_sections)

    def get_all_embeddings_with_metadata(self, section_code):
        """
        Retrieve all stored embeddings + metadata for a section type.
        
        Returns:
            tuple: (embeddings_np_array, paper_ids_list, section_ids_list)
                   or (None, None, None) if collection is empty
        """
        collection = self.get_collection(section_code)
        
        if collection.count() == 0:
            return None, None, None

        result = collection.get(include=["embeddings", "metadatas"])

        embeddings = np.array(result["embeddings"])
        paper_ids = [m["paper_id"] for m in result["metadatas"]]
        section_ids = result["ids"]

        return embeddings, paper_ids, section_ids

    def reset_collection(self, section_code):
        """Delete and recreate a collection (for re-indexing)."""
        name = self._collection_name(section_code)
        try:
            self.client.delete_collection(name)
            print(f"   🗑️  Deleted collection: {name}")
        except Exception:
            pass
        return self.get_collection(section_code)

    def reset_all(self):
        """Delete all section collections."""
        for col in self.client.list_collections():
            if col.startswith(COLLECTION_PREFIX):
                self.client.delete_collection(col)
        print("🗑️  All vector store collections deleted.")

    def stats(self):
        """Print stats for all collections."""
        print("\n📊 Vector Store Stats:")
        total = 0
        for col_name in self.client.list_collections():
            if col_name.startswith(COLLECTION_PREFIX):
                col = self.client.get_collection(col_name)
                count = col.count()
                code = col_name.replace(COLLECTION_PREFIX, "")
                print(f"   {code}: {count} embeddings")
                total += count
        print(f"   Total: {total} embeddings")


# --- Standalone test ---
if __name__ == "__main__":
    vs = VectorStore()
    vs.stats()
