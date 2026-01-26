import streamlit as st
import database as db
import sqlite3

# --- 1. CONFIGURATION & STYLING ---
st.set_page_config(page_title="Quant Graph Explorer", layout="wide")

# Your Color Palette
COLORS = {
    "bg_light": "#e8e0d4",    # Main Background
    "bg_dark": "#dcc9a8",     # Sidebar / Inputs
    "accent": "#b2a68c",      # Borders / Highlights
    "text_main": "#50483b",   # Primary Text
    "text_dark": "#141215"    # Headers
}

# Inject Custom CSS to enforce your theme
st.markdown(f"""
    <style>
        /* Main Background */
        .stApp {{
            background-color: {COLORS['bg_light']};
            color: {COLORS['text_main']};
        }}
        
        /* Sidebar Background */
        section[data-testid="stSidebar"] {{
            background-color: {COLORS['bg_dark']};
        }}
        
        /* Headers */
        h1, h2, h3 {{
            color: {COLORS['text_dark']} !important;
            font-family: 'Courier New', monospace; 
        }}
        
        /* Text Area / Input Backgrounds */
        .stTextInput > div > div > input {{
            background-color: {COLORS['bg_dark']}; 
            color: {COLORS['text_dark']};
            border: 1px solid {COLORS['accent']};
        }}
        
        /* Chat Message Bubbles */
        .stChatMessage {{
            background-color: {COLORS['bg_light']};
            border: 1px solid {COLORS['accent']};
            border-radius: 10px;
        }}
        
        /* Cards for Sections */
        .section-card {{
            background-color: #f5f0e6; /* Slightly lighter than bg */
            padding: 20px;
            border-radius: 5px;
            border-left: 5px solid {COLORS['text_main']};
            margin-bottom: 20px;
            color: {COLORS['text_main']};
        }}
    </style>
""", unsafe_allow_html=True)

# --- 2. HELPER FUNCTIONS ---
def get_all_papers():
    conn = db.get_db_connection()
    papers = conn.execute("SELECT id, title FROM papers").fetchall()
    conn.close()
    return papers

def get_sections_for_paper(paper_id):
    conn = db.get_db_connection()
    sections = conn.execute("""
        SELECT section_name, section_code, content 
        FROM sections 
        WHERE paper_id = ? 
        ORDER BY id ASC
    """, (paper_id,)).fetchall()
    conn.close()
    return sections

def search_database(query):
    conn = db.get_db_connection()
    # Simple SQL LIKE search for the MVP (later this will be Vector Search)
    results = conn.execute("""
        SELECT p.title, s.section_name, s.content 
        FROM sections s
        JOIN papers p ON s.paper_id = p.id
        WHERE s.content LIKE ? 
        LIMIT 5
    """, (f'%{query}%',)).fetchall()
    conn.close()
    return results

# --- 3. THE UI LAYOUT ---

st.title("📚 Quant Graph Explorer")

# --- SIDEBAR: Paper Browser ---
with st.sidebar:
    st.header("🗄️ Paper Browser")
    papers = get_all_papers()
    
    if not papers:
        st.warning("No papers found in database. Run parser.py first!")
        selected_paper_id = None
    else:
        # Create a dropdown to select a paper
        paper_options = {p['title']: p['id'] for p in papers}
        selected_title = st.selectbox("Select a Paper:", list(paper_options.keys()))
        selected_paper_id = paper_options[selected_title]

    st.markdown("---")
    st.markdown(f"**Database Status:** {len(papers)} papers indexed.")

# --- MAIN AREA: Tabs for Viewing vs. Chatting ---
tab1, tab2 = st.tabs(["📖 Read Paper", "💬 Chat / Search"])

# TAB 1: Section Browser (The "Reader")
with tab1:
    if selected_paper_id:
        sections = get_sections_for_paper(selected_paper_id)
        
        st.subheader(f"Analyzing: {selected_title}")
        
        # Filter by Section Type
        section_types = list(set([s['section_name'] for s in sections]))
        selected_section_filter = st.multiselect("Filter Sections:", section_types, default=section_types)
        
        for s in sections:
            if s['section_name'] in selected_section_filter:
                # Custom HTML Card for better reading experience
                st.markdown(f"""
                <div class="section-card">
                    <h4 style="margin-top:0;">{s['section_name']} <small>({s['section_code']})</small></h4>
                    <hr style="border-top: 1px solid #b2a68c;">
                    <p style="white-space: pre-wrap;">{s['content'][:1000]}...</p> 
                </div>
                """, unsafe_allow_html=True)
                # Note: I truncated text to 1000 chars for UI cleanliness, remove [:1000] to see all.
    else:
        st.info("Select a paper from the sidebar to begin reading.")

# TAB 2: Chat Interface
with tab2:
    st.subheader("Ask the Knowledge Graph")
    
    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat messages from history on app rerun
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # React to user input
    if prompt := st.chat_input("Search for concepts (e.g. 'stochastic volatility')..."):
        # Display user message
        st.chat_message("user").markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        # SEARCH LOGIC
        results = search_database(prompt)
        
        if results:
            response = f"Found **{len(results)}** relevant excerpts:\n\n"
            for r in results:
                response += f"> **{r['title']}** ({r['section_name']})\n> *{r['content'][:200]}...*\n\n"
        else:
            response = "No exact matches found in the text database."

        # Display assistant response
        with st.chat_message("assistant"):
            st.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})