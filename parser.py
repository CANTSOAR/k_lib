import os
import re
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

def flatten_tex(base_dir, main_file_path, processed_files=None):
    if processed_files is None: processed_files = set()
    if main_file_path in processed_files: return "" # Prevent loops
    
    processed_files.add(main_file_path)
    full_content = []
    
    try:
        with open(main_file_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
            
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

    return "".join(full_content)

# --- 4. The Latex Section Parser ---
def analyze_section_content(text):
    """
    Returns a probable SectionType based on the raw text content (equations, keywords).
    """
    text_lower = text.lower()
    
    # 1. Equation Density Check (The "Quant" Signature)
    # Count occurrences of latex math markers
    math_count = text.count('$') + text.count(r'\begin{equation}')
    # Rough heuristic: If > 2% of chars are math or > 5 equations, it's likely Model/Theory
    if math_count > 10 or (len(text) > 0 and math_count / len(text) > 0.02):
        return SectionType.MODEL_FRAMEWORK
        
    # 2. Data Keywords
    data_keywords = ['dataset', 'sample period', 'bloomberg', 'daily closing', 'tick data', 'observations', 'summary statistics']
    if any(k in text_lower for k in data_keywords):
        return SectionType.DATA_DESCRIPTION

    # 3. Proof/Appendix Keywords
    proof_keywords = ['proof of', 'lemma', 'proposition', 'theorem', 'corollary']
    if any(k in text_lower for k in proof_keywords):
        # In finance, if this is main text, it's Model. If at end, it's Appendix.
        # We'll default to Model Framework for now as it contains the math logic.
        return SectionType.MODEL_FRAMEWORK

    return None

def infer_unknown_sections(sections):
    """
    Applies Content-Aware + Positional labeling to UNKNOWN sections.
    """
    # Define anchors
    early_anchors = {SectionType.INTRODUCTION, SectionType.LITERATURE_REVIEW, SectionType.ABSTRACT}
    late_anchors = {SectionType.RESULTS, SectionType.CONCLUSION, SectionType.REFERENCES}
    
    for i, section in enumerate(sections):
        if section['type'] != SectionType.UNKNOWN:
            continue
        
        # --- STRATEGY 1: CONTENT ANALYSIS (Look inside the box) ---
        # Don't guess based on neighbors if the text screams "I AM DATA"
        content_type = analyze_section_content(section['body'])
        if content_type:
            section['type'] = content_type
            print(f"    -> Inferred '{section['title']}' as {content_type.name} (Content Analysis)")
            continue

        # --- STRATEGY 2: POSITIONAL INFERENCE (The Sandwich) ---
        prev_type = None
        next_type = None
        
        # Find nearest classified neighbors
        for j in range(i - 1, -1, -1):
            if sections[j]['type'] != SectionType.UNKNOWN:
                prev_type = sections[j]['type']
                break
        
        for j in range(i + 1, len(sections)):
            if sections[j]['type'] != SectionType.UNKNOWN:
                next_type = sections[j]['type']
                break
        
        # Rule A: Unknown between Intro and Data/Method -> Likely MODEL (Theory comes first)
        if prev_type in early_anchors and next_type in {SectionType.DATA_DESCRIPTION, SectionType.METHODOLOGY}:
            section['type'] = SectionType.MODEL_FRAMEWORK
            print(f"    -> Inferred '{section['title']}' as MODEL_FRAMEWORK (Position: Early)")
            
        # Rule B: Unknown between Model and Results -> Likely METHODOLOGY (Implementation comes last)
        elif prev_type == SectionType.MODEL_FRAMEWORK and next_type in late_anchors:
            section['type'] = SectionType.METHODOLOGY
            print(f"    -> Inferred '{section['title']}' as METHODOLOGY (Position: Late)")

        # Rule C: The default 'Middle' logic (Your original logic, but safer now)
        elif prev_type in early_anchors and next_type in late_anchors:
            # If we still don't know, it's usually the Model/Theory in Finance papers
            section['type'] = SectionType.MODEL_FRAMEWORK
            print(f"    -> Inferred '{section['title']}' as MODEL_FRAMEWORK (Default Middle)")
            
    return sections

def parse_flattened_latex(paper_id, latex_content):
    """
    Splits a giant LaTeX string into sections using Regex.
    Uses intelligent labelling to infer UNKNOWN sections from context.
    """
    # 1. Extract Abstract - try multiple formats
    abstract_text = None
    
    # Method 1: \begin{abstract}...\end{abstract}
    abstract_match = re.search(r'\\begin\{abstract\}(.*?)\\end\{abstract\}', latex_content, re.DOTALL)
    if abstract_match:
        abstract_text = abstract_match.group(1).strip()
    
    # Method 2: \abstract{...} command
    if not abstract_text:
        abstract_cmd_match = re.search(r'\\abstract\{([^}]+)\}', latex_content, re.DOTALL)
        if abstract_cmd_match:
            abstract_text = abstract_cmd_match.group(1).strip()
    
    # Method 3: Text between \maketitle and first \section (the "unlabeled blob")
    if not abstract_text:
        # Prioritize \maketitle as it typically precedes the abstract immediately
        start_match = re.search(r'\\maketitle', latex_content)
        
        # Fallback to \begin{document} if no \maketitle
        if not start_match:
            start_match = re.search(r'\\begin\{document\}', latex_content)
            
        # Find first \section
        first_section = re.search(r'\\section\*?\{', latex_content)
        
        if start_match and first_section and start_match.end() < first_section.start():
            potential_abstract = latex_content[start_match.end():first_section.start()].strip()
            
            # Aggressive cleanup of frontmatter commands
            # Remove title/author if we started from begin{document} and they are after it
            potential_abstract = re.sub(r'\\(title|author|date|address|email|institute|affiliation|thanks|keywords|subjclass)\{([^{}]*(\{[^}]*\}[^{}]*)*)\}', '', potential_abstract, flags=re.DOTALL)
            
            # Remove common styling/structural commands often found before abstract text
            potential_abstract = re.sub(r'\\(thispagestyle|pagestyle|setcounter|vspace|hspace|newpage|clearpage|tableofcontents|listoffigures|listoftables)\{[^}]*\}', '', potential_abstract)
            potential_abstract = re.sub(r'\\(centering|raggedright|raggedleft|noindent|small|large|Large|LARGE|huge|Huge)', '', potential_abstract)
            
            potential_abstract = potential_abstract.strip()
            
            # Only use if it's substantial (>100 chars) and NOT just a pile of commands
            # (We relax the startswith check but ensure we have actual text)
            if len(potential_abstract) > 100:
                 # Check if it looks like latex source code (too many backslashes)
                 backslash_ratio = potential_abstract.count('\\') / len(potential_abstract)
                 if backslash_ratio < 0.2: # Mostly text
                      abstract_text = potential_abstract
                      print(f"    -> Extracted unlabeled abstract ({len(abstract_text)} chars)")
    
    if abstract_text:
        db.insert_section(paper_id, SectionType.ABSTRACT.value, "Abstract", abstract_text, 1)
        print(f"    -> Saved Section: Abstract (AB)")
    
    # 2. Find all \section{Title} and \subsection{Title} commands
    # Matches: \section{...}, \section*{...}, \subsection{...}, \subsection*{...}
    # Captures: 1=sub?, 2=Title
    section_pattern = re.compile(r'\\(sub)?section\*?\{([^}]+)\}', re.IGNORECASE)
    
    matches = list(section_pattern.finditer(latex_content))
    
    # First pass: collect all sections with initial classification
    sections = []
    
    # Track the current parent section to append generic subsections to
    current_parent_index = -1
    
    for i, match in enumerate(matches):
        is_subsection = bool(match.group(1)) # 'sub' or None
        section_title = match.group(2)
        start_idx = match.end()
        end_idx = matches[i+1].start() if i + 1 < len(matches) else len(latex_content)
        section_body = latex_content[start_idx:end_idx].strip()
        
        if len(section_body) > 50:  # Ignore empty/tiny sections
            section_type = classify_header_text(section_title)
            
            # LOGIC:
            # 1. If it's a top-level SECTION, add it normally.
            # 2. If it's a SUBSECTION:
            #    a. If it has a KNOWN TYPE (e.g. "Related Work" -> LIT_REVIEW), promote it to a top-level section.
            #    b. If it is UNKNOWN/GENERIC, append it to the current parent section so we don't lose the text.
            
            if not is_subsection:
                # New Top-Level Section
                sections.append({
                    'title': section_title,
                    'body': section_body,
                    'type': section_type
                })
                current_parent_index = len(sections) - 1
            else:
                # It is a Subsection
                if section_type != SectionType.UNKNOWN:
                     # 2a. Promote relevant subsections (e.g. Intro -> Related Work)
                     print(f"    -> Promoting Subsection '{section_title}' to {section_type.value}")
                     sections.append({
                        'title': section_title,
                        'body': section_body,
                        'type': section_type
                    })
                     # Update parent index? No, usually we want subsequent sub-subsections to fall under this new promoted section
                     # OR keep old parent. Let's make this the new parent for safety.
                     current_parent_index = len(sections) - 1
                else:
                    # 2b. Merge generic subsection into parent
                    if current_parent_index >= 0:
                        # Append title + body to parent
                        parent = sections[current_parent_index]
                        parent['body'] += f"\n\n### {section_title}\n{section_body}"
                    else:
                        # Orphan component (subsection before any section). Treat as independent.
                        sections.append({
                            'title': section_title,
                            'body': section_body,
                            'type': section_type
                        })
                        current_parent_index = len(sections) - 1
    
    # Second pass: apply intelligent labelling to infer UNKNOWN sections
    sections = infer_unknown_sections(sections)
    
    # Third pass: save to database and count unknowns
    unknown_counter = 0
    section_counter = len(sections)
    
    for section in sections:
        # Skip references (we handle those via .bbl usually)
        if section['type'] != SectionType.REFERENCES:
            db.insert_section(
                paper_id,
                section['type'].value,
                section['title'],
                section['body'],  # The raw LaTeX string of that section
                1  # Page number is irrelevant in raw LaTeX
            )
            print(f"    -> Saved Section: {section['title']} ({section['type'].value})")
        
        if section['type'] == SectionType.UNKNOWN:
            unknown_counter += 1

    return unknown_counter, section_counter

# --- 5. Main Processing Logic ---
def find_main_tex_file(folder_path):
    """
    Identifies the main LaTeX driver file by looking for '\documentclass'.
    """
    tex_files = [f for f in os.listdir(folder_path) if f.endswith('.tex')]
    
    # 1. Check for specific keywords in the content
    for f in tex_files:
        path = os.path.join(folder_path, f)
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as file:
                content = file.read()
                # The presence of \documentclass is the 'smoking gun' for a main file
                if r"\documentclass" in content:
                    return f
        except Exception:
            continue
            
    # 2. Fallback: If no documentclass found (rare), check for .bbl match
    # If we have 'paper.bbl', the main file is likely 'paper.tex'
    bbl_files = [f for f in os.listdir(folder_path) if f.endswith('.bbl')]
    if bbl_files:
        likely_name = bbl_files[0].replace('.bbl', '.tex')
        if likely_name in tex_files:
            return likely_name

    # 3. Last Resort: Return the largest file (what we did before)
    if tex_files:
        tex_files.sort(key=lambda x: os.path.getsize(os.path.join(folder_path, x)), reverse=True)
        return tex_files[0]
        
    return None

def process_paper_folder(arxiv_id, folder_path):
    print(f"Processing Folder: {arxiv_id}")
    
    # --- NEW LOGIC START ---
    main_tex = find_main_tex_file(folder_path)
    
    if not main_tex:
        print(f"    ⚠️ Could not identify main .tex file in {folder_path}")
        return 0, 0
        
    print(f"    -> Identified Main File: {main_tex}")
    # --- NEW LOGIC END ---

    # 1. Flatten
    full_path = os.path.join(folder_path, main_tex)
    flattened_content = flatten_tex(folder_path, full_path)
    
    # 2. Create Paper Entry
    paper_id = db.insert_paper(arxiv_id, f"ArXiv Paper {arxiv_id}") 
    
    # 3. Parse Sections
    unknown_counter, section_counter = parse_flattened_latex(paper_id, flattened_content)
    print(f"    -> Unknown Sections: {unknown_counter}/{section_counter}")

    return unknown_counter, section_counter

def process_all_folders(root_dir):
    """Iterates through every folder in the root directory."""
    
    # Initialize DB once
    db.init_db()
    
    if not os.path.exists(root_dir):
        print(f"Directory not found: {root_dir}")
        return

    # List all subfolders (each one is a paper)
    subfolders = [f for f in os.listdir(root_dir) if os.path.isdir(os.path.join(root_dir, f))]
    
    print(f"Found {len(subfolders)} paper folders.")
    
    total_unknowns = 0
    total_sections = 0
    for arxiv_id in subfolders:
        folder_path = os.path.join(root_dir, arxiv_id)
        unknown_counter, section_counter = process_paper_folder(arxiv_id, folder_path)
        total_unknowns += unknown_counter
        total_sections += section_counter

    print(f"Total Unknown Sections: {total_unknowns}/{total_sections}")
    print(f"Success Rate: {1 - total_unknowns/total_sections}")

# --- 6. Execution ---
if __name__ == "__main__":
    # Point this to your SOURCE directory (not the PDF directory)
    SOURCE_DIR = "./vol_surface_source" 
    process_all_folders(SOURCE_DIR)