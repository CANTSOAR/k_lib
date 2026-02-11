from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import sqlite3
import database as db  # Ensure your database.py is in the same folder
import parser # Import the parser module
import os
app = FastAPI()

# Serve PDFs from vol_surface_source directory
app.mount("/pdfs", StaticFiles(directory="vol_surface_source"), name="pdfs")

# Enable CORS so your React Frontend (port 5173) can talk to Backend (port 8000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db_connection():
    conn = sqlite3.connect("quant_knowledge_graph.db")
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/graph")
async def get_graph():
    """
    Returns the entire graph structure (nodes and links) for visualization.
    Deduplicates bidirectional edges so only one visual line appears per pair.
    """
    conn = get_db_connection()
    
    # 1. Fetch Nodes (Papers)
    papers = conn.execute("SELECT id, title FROM papers").fetchall()
    nodes = [{"id": p["id"], "name": p["title"], "val": 1} for p in papers]
    
    # 2. Fetch Edges (filter out self-loops)
    edges = conn.execute("""
        SELECT source_paper_id, target_paper_id, edge_type, weight 
        FROM edges 
        WHERE source_paper_id != target_paper_id
    """).fetchall()
    
    # 3. Deduplicate bidirectional edges for visualization
    # Use a set to track which pairs we've already added
    seen_pairs = set()
    links = []
    
    for e in edges:
        source = e["source_paper_id"]
        target = e["target_paper_id"]
        edge_type = e["edge_type"]
        
        # Create a canonical pair key (smaller id first) with edge type
        pair_key = (min(source, target), max(source, target), edge_type)
        
        if pair_key not in seen_pairs:
            seen_pairs.add(pair_key)
            links.append({
                "source": source,
                "target": target,
                "type": edge_type,
                "weight": e["weight"]
            })
    
    conn.close()
    return {"nodes": nodes, "links": links}

@app.get("/paper/{paper_id}")
async def get_paper_details(paper_id: int):
    """
    Fetches the content sections for a specific paper when clicked.
    """
    conn = get_db_connection()
    
    # Get Metadata
    paper = conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
        
    # Get Sections
    sections = conn.execute("""
        SELECT section_name, section_code, content 
        FROM sections 
        WHERE paper_id = ?
    """, (paper_id,)).fetchall()
    
    conn.close()
    
    return {
        "title": paper["title"],
        "arxiv_url": paper["arxiv_url"],
        "filename": paper["filename"],  # arxiv_id for PDF URL construction
        "sections": [dict(s) for s in sections]
    }

@app.get("/paper/{paper_id}/connections")
async def get_paper_connections(paper_id: int):
    """
    Fetches connected papers AND the specific sections that triggered the match.
    Example: If connected via SIMILAR_METHODOLOGY, return the Methodology text 
    of the target paper so the user can compare.
    """
    conn = get_db_connection()
    
    # 1. Get all edges where this paper is the source
    edges = conn.execute("""
        SELECT e.target_paper_id, e.edge_type, e.weight, p.title as target_title
        FROM edges e
        JOIN papers p ON e.target_paper_id = p.id
        WHERE e.source_paper_id = ?
        ORDER BY e.weight DESC
    """, (paper_id,)).fetchall()
    
    results = []
    
    # Map Edge Types to Section Codes (for fetching the text)
    # This assumes your graph builder used these codes to generate the edges
    EDGE_TO_SECTION_CODE = {
        "SIMILAR_MODEL": "EQ",
        "SIMILAR_METHODOLOGY": "ME",
        "SIMILAR_RESULTS": "RE",
        "SIMILAR_DATA_DESCRIPTION": "DA",
        "SIMILAR_ABSTRACT": "AB",
        "SIMILAR_INTRODUCTION": "IN",
        "SIMILAR_CONCLUSION": "CO"
    }
    
    for e in edges:
        edge_data = dict(e)
        target_id = edge_data["target_paper_id"]
        edge_type = edge_data["edge_type"]
        
        # Determine which section to fetch from the TARGET paper
        # If it's a CITATION, we might not have a specific matching section text, 
        # but for semantic edges, we do.
        target_section_content = None
        
        # Strip "SIMILAR_" prefix to handle raw types if needed, but dictionary is safer
        section_code = EDGE_TO_SECTION_CODE.get(edge_type)
        
        if section_code:
            # Fetch the specific section text from the target paper
            sec = conn.execute("""
                SELECT content FROM sections 
                WHERE paper_id = ? AND section_code = ? 
                LIMIT 1
            """, (target_id, section_code)).fetchone()
            
            if sec:
                target_section_content = sec["content"]
        
        results.append({
            "target_id": target_id,
            "target_title": edge_data["target_title"],
            "edge_type": edge_type,
            "similarity_score": edge_data["weight"],
            "matching_section_content": target_section_content
        })
    
    conn.close()
    return results

@app.get("/paper/{paper_id}/full_source")
async def get_full_paper_source(paper_id: int):
    """
    Returns the FULL reconstructed LaTeX source for the paper.
    Stitches together the main file and all inputs.
    """
    conn = get_db_connection()
    
    # 1. Get filename (arxiv_id)
    paper = conn.execute("SELECT filename FROM papers WHERE id = ?", (paper_id,)).fetchone()
    conn.close()
    
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
        
    arxiv_id = paper['filename']
    folder_path = os.path.join(".", "vol_surface_source", arxiv_id)
    
    if not os.path.exists(folder_path):
        raise HTTPException(status_code=404, detail=f"Source folder not found for {arxiv_id}")
        
    # 2. Find Main File
    main_tex = parser.find_main_tex_file(folder_path)
    if not main_tex:
         raise HTTPException(status_code=404, detail="Main .tex file not found")
         
    # 3. Flatten
    full_path = os.path.join(folder_path, main_tex)
    full_content = parser.flatten_tex(folder_path, full_path)
    
    return {"content": full_content}