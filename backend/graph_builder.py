import sqlite3
import numpy as np
import os
import re
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from tqdm import tqdm  # Progress bar library
import database as db
from vector_store import VectorStore

# --- CONFIGURATION ---
# Using Nomic for 8192 token context window (prevents cutting off long sections)
# NOTE: This model requires 'trust_remote_code=True'
MODEL_NAME = 'nomic-ai/nomic-embed-text-v1.5'

# --- DYNAMIC THRESHOLDS ---
# Stricter for technical sections, looser for prose
SECTION_THRESHOLDS = {
    "ME": 0.82,  # Methodology: High threshold (structure matters)
    "EQ": 0.85,  # Models/Equations: Very High (math is specific)
    "RE": 0.85,  # Results: Very High (avoid matching generic "it worked")
    "AB": 0.75,  # Abstract: Medium 
    "IN": 0.75,  # Intro: Medium
    "LR": 0.78,  # Lit Review: Medium-High
    "default": 0.75
}

print(f"⏳ Loading High-Context Model: {MODEL_NAME}...")
# trust_remote_code=True is required for Nomic
model = SentenceTransformer(MODEL_NAME, trust_remote_code=True)

# Initialize persistent vector store
vector_store = VectorStore()

def get_threshold(section_code):
    return SECTION_THRESHOLDS.get(section_code, SECTION_THRESHOLDS["default"])

def get_all_sections(section_type=None):
    """Fetch sections from DB."""
    conn = db.get_db_connection()
    query = "SELECT id, paper_id, content, section_code FROM sections"
    if section_type:
        query += f" WHERE section_code = '{section_type}'"
    
    results = conn.execute(query).fetchall()
    conn.close()
    return results

def build_semantic_edges(section_code, edge_name):
    """
    Compare ALL sections of a specific type using persistent ChromaDB embeddings.
    New sections are embedded and stored; existing embeddings are reused.
    """
    current_threshold = get_threshold(section_code)
    print(f"\n🤖 Processing '{edge_name}' (Threshold: {current_threshold}) for: {section_code}")
    
    sections = get_all_sections(section_code)
    if not sections:
        print("   ⚠️ No sections found. Skipping.")
        return

    # 1. STORE: Embed new sections into ChromaDB (skips already-stored)
    new_count = vector_store.store_embeddings(sections, model, section_code)
    
    # 2. RETRIEVE: Get all embeddings from ChromaDB
    embeddings, paper_ids, section_ids = vector_store.get_all_embeddings_with_metadata(section_code)
    
    if embeddings is None or len(embeddings) < 2:
        print("   ⚠️ Not enough embeddings for comparison. Skipping.")
        return
    
    print(f"   📊 Comparing {len(embeddings)} stored embeddings...")
    
    # 3. Calculate similarity matrix
    sim_matrix = cosine_similarity(embeddings)
    
    edge_count = 0
    num_papers = len(paper_ids)
    
    # Progress bar for the linking phase
    pbar = tqdm(total=(num_papers * (num_papers - 1)) // 2, desc="   Linking", unit="pair")
    
    for i in range(num_papers):
        for j in range(i + 1, num_papers): 
            if paper_ids[i] == paper_ids[j]: 
                pbar.update(1)
                continue
            
            score = sim_matrix[i][j]
            
            if score > current_threshold:
                # 1. Forward Link
                db.insert_edge(
                    source_id=paper_ids[i], 
                    target_id=paper_ids[j], 
                    edge_type=edge_name, 
                    weight=float(score)
                )
                
                # 2. Reverse Link
                db.insert_edge(
                    source_id=paper_ids[j], 
                    target_id=paper_ids[i], 
                    edge_type=edge_name, 
                    weight=float(score)
                )
                edge_count += 2
            pbar.update(1)
            
    pbar.close()
    print(f"   ✅ Created {edge_count} edges.")

def parse_bbl_citations(source_folder):
    """
    Reads .bbl files to find Explicit Citations.
    """
    print("\n🔎 Scanning for Citations (.bbl)...")
    conn = db.get_db_connection()
    
    try:
        papers = conn.execute("SELECT id, title FROM papers").fetchall()
        # Create a lookup for titles (normalized)
        paper_lookup = {}
        for p in papers:
            # First 50 chars, lowercase, stripped
            clean_title = p['title'].lower().strip()[:50] 
            if len(clean_title) > 5:
                paper_lookup[clean_title] = p['id']
        
        count = 0
        if os.path.exists(source_folder):
            # Iterate through folders
            for paper_id_dir in tqdm(os.listdir(source_folder), desc="   Parsing BBLs"):
                full_dir = os.path.join(source_folder, paper_id_dir)
                if not os.path.isdir(full_dir): continue
                
                bbl_files = [f for f in os.listdir(full_dir) if f.endswith('.bbl')]
                if not bbl_files: continue
                
                # Find the source paper ID in DB
                source_paper = conn.execute(
                    "SELECT id FROM papers WHERE title LIKE ?", 
                    (f"%{paper_id_dir}%",)
                ).fetchone()
                
                if not source_paper: continue
                source_db_id = source_paper[0]
                
                try:
                    with open(os.path.join(full_dir, bbl_files[0]), 'r', errors='ignore') as f:
                        content = f.read().lower()
                        
                    for target_title_stub, target_db_id in paper_lookup.items():
                        if target_db_id == source_db_id: continue 
                        
                        if target_title_stub in content:
                            db.insert_edge(source_db_id, target_db_id, "CITES", 1.0)
                            db.insert_edge(target_db_id, source_db_id, "CITED_BY", 1.0)
                            count += 2
                except Exception as e:
                    print(f"Error reading BBL for {paper_id_dir}: {e}")

        print(f"   ✅ Found {count} citation connections.")
    finally:
        conn.close()

if __name__ == "__main__":
    # 1. Initialize Table
    db.init_db()
    
    # 2. Build Semantic Graph (Implicit)
    # Technical sections first (most important)
    build_semantic_edges("ME", "SIMILAR_METHODOLOGY")
    build_semantic_edges("RE", "SIMILAR_RESULTS")
    build_semantic_edges("EQ", "SIMILAR_MODEL")
    
    # Prose sections
    build_semantic_edges("AB", "SIMILAR_ABSTRACT")
    build_semantic_edges("IN", "SIMILAR_INTRODUCTION")
    build_semantic_edges("LR", "SIMILAR_LITERATURE_REVIEW")
    
    # Optional / Less Critical
    build_semantic_edges("CO", "SIMILAR_CONCLUSION")
    build_semantic_edges("FU", "SIMILAR_FUTURE_WORK")
    
    # 3. Build Citation Graph (Explicit)
    parse_bbl_citations("./vol_surface_source")
    
    # 4. Print vector store stats
    vector_store.stats()