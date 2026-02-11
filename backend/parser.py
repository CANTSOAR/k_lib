import os
import re
import json
import database as db
from enum import Enum

# --- 1. The Schema (Enum) ---
class SectionType(str, Enum):
    ABSTRACT = "AB"
    INTRODUCTION = "IN"
    LITERATURE_REVIEW = "LR"
    MODEL_FRAMEWORK = "EQ"  # Equations / Theory
    DATA_DESCRIPTION = "DA"
    METHODOLOGY = "ME"      # Implementation
    RESULTS = "RE"          # Empirical Analysis
    LIMITATIONS = "LI"      
    CONCLUSION = "CO"
    FUTURE_WORK = "FU"
    REFERENCES = "REF"      # To filter out later
    APPENDIX = "AP"
    ACKNOWLEDGEMENTS = "AK"
    UNKNOWN = "UNK"         # Default catch-all

# --- 2. The Mapper Logic ---
def classify_header_text(text):
    """Maps raw LaTeX header text (e.g., 'Methodology') to your Enum code."""
    text = text.lower().strip()
    
    if "abstract" in text: return SectionType.ABSTRACT
    if "introduction" in text: return SectionType.INTRODUCTION
    if "literature" in text or "related work" in text: return SectionType.LITERATURE_REVIEW
    if "model" in text or "framework" in text or "formulation" in text or "notation" in text or "preliminaries" in text or "background" in text: return SectionType.MODEL_FRAMEWORK
    if "data" in text or "dataset" in text: return SectionType.DATA_DESCRIPTION
    if "method" in text or "implementation" in text or "algorithm" in text: return SectionType.METHODOLOGY
    if "result" in text or "empirical" in text or "performance" in text or "experiment" in text or "numerical" in text or "simulation" in text or "calibration" in text: return SectionType.RESULTS
    if "conclusion" in text or "summary" in text or "discussion" in text: return SectionType.CONCLUSION
    if "reference" in text or "bibliography" in text: return SectionType.REFERENCES
    if "appendix" in text or "proof" in text: return SectionType.APPENDIX
    if "acknowledgement" in text or "acknowledgment" in text or "funding" in text: return SectionType.ACKNOWLEDGEMENTS
    if "limitation" in text: return SectionType.LIMITATIONS
    
    return SectionType.UNKNOWN

# --- 3. The Flattener (Merges multiple .tex files) ---
def resolve_path(base_dir, current_file_path, included_filename):
    if not included_filename.endswith('.tex'):
        included_filename += '.tex'
    
    # Check relative to current file location
    current_dir = os.path.dirname(current_file_path)
    candidate_1 = os.path.join(current_dir, included_filename)
    if os.path.exists(candidate_1): return candidate_1
        
    # Check relative to base project root
    candidate_2 = os.path.join(base_dir, included_filename)
    if os.path.exists(candidate_2): return candidate_2
        
    return None

def read_tex_file(path):
    """
    Robustly reads a text file. 
    1. Checks if file is binary (contains null bytes).
    2. Tries multiple encodings.
    """
    # Quick check: Read first 1024 bytes in binary mode
    try:
        with open(path, 'rb') as f:
            chunk = f.read(1024)
            # If we find a null byte, it's likely a binary file (image, pdf, etc.)
            if b'\x00' in chunk:
                return "" # Skip binary files
    except Exception:
        return ""

    # If it passes the binary check, try to decode as text
    encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
    
    for enc in encodings:
        try:
            with open(path, 'r', encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue 
            
    # Last resort: Force read ignoring errors
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception:
        return ""

def flatten_tex(base_dir, main_file_path, processed_files=None):
    if processed_files is None: processed_files = set()
    if main_file_path in processed_files: return "" # Prevent loops
    
    processed_files.add(main_file_path)
    full_content = []
    
    try:
        lines = read_tex_file(main_file_path).splitlines()
        
        # Regex to match \input{...} or \include{...}
        input_pattern = re.compile(r'\\(input|include)\{([^}]+)\}')
        
        for line in lines:
            # Remove comments (%)
            clean_line = line.split('%')[0]
            if not clean_line.strip(): continue # Skip empty lines

            match = input_pattern.search(clean_line)
            if match:
                included_fname = match.group(2).strip()
                resolved_path = resolve_path(base_dir, main_file_path, included_fname)
                if resolved_path:
                    full_content.append(flatten_tex(base_dir, resolved_path, processed_files))
                else:
                    full_content.append(line) # Keep original if file not found
            else:
                full_content.append(line)
    except Exception as e:
        print(f"Error reading {main_file_path}: {e}")
        return ""

    return "\n".join(full_content) # Join with newlines for cleaner text

# --- 4. The Latex Section Parser ---
def analyze_section_content(text):
    """
    Returns a probable SectionType based on the raw text content (equations, keywords).
    """
    text_lower = text.lower()
    
    # 1. Equation Density Check (The "Quant" Signature)
    math_count = text.count('$') + text.count(r'\begin{equation}')
    if math_count > 10 or (len(text) > 0 and math_count / len(text) > 0.02):
        return SectionType.MODEL_FRAMEWORK
        
    # 2. Data Keywords
    data_keywords = ['dataset', 'sample period', 'bloomberg', 'daily closing', 'tick data', 'observations', 'summary statistics']
    if any(k in text_lower for k in data_keywords):
        return SectionType.DATA_DESCRIPTION

    # 3. Proof/Appendix Keywords
    proof_keywords = ['proof of', 'lemma', 'proposition', 'theorem', 'corollary']
    if any(k in text_lower for k in proof_keywords):
        return SectionType.MODEL_FRAMEWORK

    return None

def infer_unknown_sections(sections):
    """
    Applies Content-Aware + Positional labeling to UNKNOWN sections.
    """
    early_anchors = {SectionType.INTRODUCTION, SectionType.LITERATURE_REVIEW, SectionType.ABSTRACT}
    late_anchors = {SectionType.RESULTS, SectionType.CONCLUSION, SectionType.REFERENCES}
    
    for i, section in enumerate(sections):
        if section['type'] != SectionType.UNKNOWN:
            continue
        
        # STRATEGY 1: CONTENT ANALYSIS
        content_type = analyze_section_content(section['body'])
        if content_type:
            section['type'] = content_type
            continue

        # STRATEGY 2: POSITIONAL INFERENCE
        prev_type = None
        next_type = None
        
        # Find neighbors
        for j in range(i - 1, -1, -1):
            if sections[j]['type'] != SectionType.UNKNOWN:
                prev_type = sections[j]['type']
                break
        
        for j in range(i + 1, len(sections)):
            if sections[j]['type'] != SectionType.UNKNOWN:
                next_type = sections[j]['type']
                break
        
        if prev_type in early_anchors and next_type in {SectionType.DATA_DESCRIPTION, SectionType.METHODOLOGY}:
            section['type'] = SectionType.MODEL_FRAMEWORK
            
        elif prev_type == SectionType.MODEL_FRAMEWORK and next_type in late_anchors:
            section['type'] = SectionType.METHODOLOGY

        elif prev_type in early_anchors and next_type in late_anchors:
            section['type'] = SectionType.MODEL_FRAMEWORK
            
    return sections

def parse_flattened_latex(paper_id, latex_content):
    """
    Splits a giant LaTeX string into sections using Regex.
    """
    # 1. Extract Abstract
    abstract_text = None
    abstract_match = re.search(r'\\begin\{abstract\}(.*?)\\end\{abstract\}', latex_content, re.DOTALL)
    if abstract_match:
        abstract_text = abstract_match.group(1).strip()
    
    if not abstract_text:
        abstract_cmd_match = re.search(r'\\abstract\{([^}]+)\}', latex_content, re.DOTALL)
        if abstract_cmd_match:
            abstract_text = abstract_cmd_match.group(1).strip()
    
    if not abstract_text:
        start_match = re.search(r'\\maketitle', latex_content)
        if not start_match:
            start_match = re.search(r'\\begin\{document\}', latex_content)
        first_section = re.search(r'\\section\*?\{', latex_content)
        
        if start_match and first_section and start_match.end() < first_section.start():
            potential_abstract = latex_content[start_match.end():first_section.start()].strip()
            potential_abstract = re.sub(r'\\(title|author|date|thanks|keywords|subjclass)\{([^{}]*(\{[^}]*\}[^{}]*)*)\}', '', potential_abstract, flags=re.DOTALL)
            if len(potential_abstract) > 100:
                 if potential_abstract.count('\\') / len(potential_abstract) < 0.2:
                      abstract_text = potential_abstract
    
    if abstract_text:
        db.insert_section(paper_id, SectionType.ABSTRACT.value, "Abstract", abstract_text, 1)
    
    # 2. Find Sections
    section_pattern = re.compile(r'\\(sub)?section\*?\{([^}]+)\}', re.IGNORECASE)
    matches = list(section_pattern.finditer(latex_content))
    
    sections = []
    current_parent_index = -1
    
    for i, match in enumerate(matches):
        is_subsection = bool(match.group(1))
        section_title = match.group(2)
        start_idx = match.end()
        end_idx = matches[i+1].start() if i + 1 < len(matches) else len(latex_content)
        section_body = latex_content[start_idx:end_idx].strip()
        
        if len(section_body) > 50:
            section_type = classify_header_text(section_title)
            
            if not is_subsection:
                sections.append({'title': section_title, 'body': section_body, 'type': section_type})
                current_parent_index = len(sections) - 1
            else:
                if section_type != SectionType.UNKNOWN:
                     sections.append({'title': section_title, 'body': section_body, 'type': section_type})
                     current_parent_index = len(sections) - 1
                else:
                    if current_parent_index >= 0:
                        parent = sections[current_parent_index]
                        parent['body'] += f"\n\n### {section_title}\n{section_body}"
                    else:
                        sections.append({'title': section_title, 'body': section_body, 'type': section_type})
                        current_parent_index = len(sections) - 1
    
    sections = infer_unknown_sections(sections)
    
    unknown_counter = 0
    section_counter = len(sections)
    
    for section in sections:
        if section['type'] != SectionType.REFERENCES:
            db.insert_section(
                paper_id,
                section['type'].value,
                section['title'],
                section['body'],
                1
            )
        
        if section['type'] == SectionType.UNKNOWN:
            unknown_counter += 1

    return unknown_counter, section_counter

# --- 5. Main Processing Logic ---
def find_main_tex_file(folder_path):
    """
    Identifies the main LaTeX driver file.
    """
    tex_files = [f for f in os.listdir(folder_path) if f.endswith('.tex')]
    
    for f in tex_files:
        path = os.path.join(folder_path, f)
        if f.endswith('.tex0'): continue

        try:
            content = read_tex_file(path)
            if not content: continue
            if re.search(r'^\s*\\documentclass', content, re.MULTILINE):
                return f
        except Exception:
            continue
            
    bbl_files = [f for f in os.listdir(folder_path) if f.endswith('.bbl')]
    if bbl_files:
        likely_name = bbl_files[0].replace('.bbl', '.tex')
        if likely_name in tex_files:
            return likely_name

    if tex_files:
        tex_files.sort(key=lambda x: os.path.getsize(os.path.join(folder_path, x)), reverse=True)
        return tex_files[0]
        
    return None

def process_paper_folder(arxiv_id, folder_path, title, arxiv_url=None):
    print(f"Processing: {arxiv_id} | {title[:40]}...")
    
    main_tex = find_main_tex_file(folder_path)
    
    if not main_tex:
        print(f"    ⚠️ Could not identify main .tex file in {folder_path}")
        return 0, 0
        
    full_path = os.path.join(folder_path, main_tex)
    flattened_content = flatten_tex(folder_path, full_path)
    
    if len(flattened_content) == 0:
        print(f"    ⚠️ Empty content in {full_path}")
        return 0, 0

    # Pass the title and arxiv_url to the DB insert function
    paper_id = db.insert_paper(arxiv_id, title, arxiv_url=arxiv_url) 
    unknown_counter, section_counter = parse_flattened_latex(paper_id, flattened_content)
    
    print(f"    -> Parsed {section_counter} sections ({unknown_counter} unknown)")
    return unknown_counter, section_counter

# --- NEW: Metadata Loader ---
def load_metadata_map(source_dir):
    """
    Reads metadata.json and returns a dict: { 'arxiv_id': { 'title': ..., 'arxiv_url': ... } }
    """
    meta_path = os.path.join(source_dir, "metadata.json")
    if not os.path.exists(meta_path):
        print("⚠️ metadata.json not found in source directory.")
        return {}
        
    try:
        with open(meta_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # Handle if JSON is a list of objects or a dict
        mapping = {}
        if isinstance(data, list):
            for item in data:
                # Adjust keys based on your actual json structure (e.g. 'id', 'arxiv_id')
                key = item.get('id') or item.get('arxiv_id') 
                if key:
                    mapping[str(key)] = {
                        'title': item.get('title', f"ArXiv Paper {key}"),
                        'arxiv_url': item.get('arxiv_url', f"https://arxiv.org/abs/{key}")
                    }
        elif isinstance(data, dict):
            # If it's already {id: title} format, convert
            for k, v in data.items():
                if isinstance(v, str):
                    mapping[k] = {'title': v, 'arxiv_url': f"https://arxiv.org/abs/{k}"}
                else:
                    mapping[k] = v
            
        print(f"Loaded metadata for {len(mapping)} papers from metadata.json")
        return mapping
    except Exception as e:
        print(f"Error loading metadata.json: {e}")
        return {}

def process_all_folders(root_dir):
    """Iterates through every folder in the root directory."""
    
    db.init_db(nuke=True)
    
    if not os.path.exists(root_dir):
        print(f"Directory not found: {root_dir}")
        return

    # 1. Load Metadata Map
    metadata_map = load_metadata_map(root_dir)

    subfolders = [f for f in os.listdir(root_dir) if os.path.isdir(os.path.join(root_dir, f))]
    print(f"Found {len(subfolders)} paper folders.")
    
    total_unknowns = 0
    total_sections = 0
    for arxiv_id in subfolders:
        folder_path = os.path.join(root_dir, arxiv_id)
        
        # 2. Get Metadata or Fallback
        paper_meta = metadata_map.get(arxiv_id, {
            'title': f"ArXiv Paper {arxiv_id}",
            'arxiv_url': f"https://arxiv.org/abs/{arxiv_id}"
        })
        
        unknown_counter, section_counter = process_paper_folder(
            arxiv_id, 
            folder_path, 
            paper_meta['title'],
            paper_meta.get('arxiv_url')
        )
        total_unknowns += unknown_counter
        total_sections += section_counter

    if total_sections > 0:
        print("------------------------------------------------")
        print(f"Total Unknown Sections: {total_unknowns}/{total_sections}")
        print(f"Global Success Rate: {1 - total_unknowns/total_sections:.2%}")

# --- 6. Execution ---
if __name__ == "__main__":
    SOURCE_DIR = "./vol_surface_source" 
    process_all_folders(SOURCE_DIR)