import sqlite3
import json
from pathlib import Path

# DB Configuration
DB_NAME = "quant_knowledge_graph.db"

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # Allows accessing columns by name
    return conn

def init_db():
    """Initializes the database with the Papers and Sections tables."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Table 1: Papers (Metadata)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE,
            title TEXT,
            author_text TEXT,
            processed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Table 2: Sections (Content chunks for your Graph)
    # We create a composite index on paper_id and section_type for fast filtering
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id INTEGER,
            section_code TEXT,
            section_name TEXT,
            content TEXT,
            page_number INTEGER,
            FOREIGN KEY (paper_id) REFERENCES papers (id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"Database '{DB_NAME}' initialized successfully.")

def insert_paper(filename, title, author_text="Unknown"):
    """Inserts a paper and returns its DB ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO papers (filename, title, author_text) 
            VALUES (?, ?, ?)
            RETURNING id
        ''', (filename, title, author_text))
        paper_id = cursor.fetchone()[0]
        conn.commit()
        return paper_id
    except sqlite3.IntegrityError:
        # If paper already exists, fetch its ID
        cursor.execute('SELECT id FROM papers WHERE filename = ?', (filename,))
        result = cursor.fetchone()
        return result[0] if result else None
    finally:
        conn.close()

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

# Initialize automatically when imported, or you can call it manually
if __name__ == "__main__":
    init_db()