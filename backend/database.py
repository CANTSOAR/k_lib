import sqlite3
from pathlib import Path

# DB Configuration
DB_NAME = "quant_knowledge_graph.db"

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # Allows accessing columns by name
    return conn

def init_db(nuke=False):
    """
    Initializes the database.
    :param nuke: If True, DROPS all existing tables before creating them (Clears DB).
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # --- THE NUKE TOGGLE ---
    if nuke:
        print("☢️  NUKING DATABASE... Deleting all data.")
        cursor.execute("DROP TABLE IF EXISTS edges")
        cursor.execute("DROP TABLE IF EXISTS sections")
        cursor.execute("DROP TABLE IF EXISTS papers")
        conn.commit()
        print("✅ Database cleared.")

    # Table 1: Papers (Metadata)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE,
            title TEXT,
            author_text TEXT,
            arxiv_url TEXT,
            processed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Table 2: Sections (Content chunks for your Graph)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id INTEGER,
            section_code TEXT,
            section_name TEXT,
            content TEXT,
            page_number INTEGER,
            FOREIGN KEY (paper_id) REFERENCES papers (id) ON DELETE CASCADE
        )
    ''')

    # Table 3: Edges (Graph Connections)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_paper_id INTEGER,
            target_paper_id INTEGER,
            edge_type TEXT,        -- 'CITES', 'SIMILAR_MODEL', 'SIMILAR_RESULT'
            weight REAL,           -- 1.0 for citations, 0.0-1.0 for similarity
            metadata TEXT,         -- Store snippets or proof
            FOREIGN KEY (source_paper_id) REFERENCES papers (id) ON DELETE CASCADE,
            FOREIGN KEY (target_paper_id) REFERENCES papers (id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"Database '{DB_NAME}' initialized successfully (Nuke={nuke}).")

def insert_paper(filename, title, author_text="Unknown", arxiv_url=None):
    """
    Inserts a paper or updates its title if it already exists.
    Returns the paper's DB ID.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Try to Insert
        cursor.execute('''
            INSERT INTO papers (filename, title, author_text, arxiv_url) 
            VALUES (?, ?, ?, ?)
        ''', (filename, title, author_text, arxiv_url))
        paper_id = cursor.lastrowid
        conn.commit()
        return paper_id

    except sqlite3.IntegrityError:
        # 2. If it exists, UPDATE the title (in case we have better metadata now)
        cursor.execute('''
            UPDATE papers 
            SET title = ?, author_text = ?, arxiv_url = ?
            WHERE filename = ?
        ''', (title, author_text, arxiv_url, filename))
        conn.commit()

        # 3. Fetch the ID of the existing paper
        cursor.execute('SELECT id FROM papers WHERE filename = ?', (filename,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None

    finally:
        # Ensure connection is closed if it wasn't closed in the except block
        try:
            conn.close()
        except:
            pass

def insert_section(paper_id, section_code, section_name, content, page_num):
    """Inserts a specific text block into the Sections table."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO sections (paper_id, section_code, section_name, content, page_number)
        VALUES (?, ?, ?, ?, ?)
    ''', (paper_id, section_code, section_name, content, page_num))
    
    conn.commit()
    conn.close()

def insert_edge(source_id, target_id, edge_type, weight=1.0, metadata=""):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Prevent duplicate edges
    cursor.execute('''
        SELECT id FROM edges 
        WHERE source_paper_id=? AND target_paper_id=? AND edge_type=?
    ''', (source_id, target_id, edge_type))
    
    if not cursor.fetchone():
        cursor.execute('''
            INSERT INTO edges (source_paper_id, target_paper_id, edge_type, weight, metadata)
            VALUES (?, ?, ?, ?, ?)
        ''', (source_id, target_id, edge_type, weight, metadata))
    
    conn.commit()
    conn.close()

# Usage Example
if __name__ == "__main__":
    init_db(nuke=False)