import arxiv
import os
import json
import re
import requests
import tarfile
import io
import shutil

def sanitize_filename(title):
    """Clean the title to make it a valid filename."""
    clean = re.sub(r'[\\/*?:"<>|]', "", title)
    return clean[:150]

def download_and_extract_source(arxiv_id, save_dir):
    """
    Downloads the source tarball from arXiv and extracts it.
    Returns the path to the folder containing the .tex files.
    """
    url = f"https://arxiv.org/e-print/{arxiv_id}"
    paper_folder = os.path.join(save_dir, arxiv_id)
    
    # If folder exists and is not empty, skip (caching)
    if os.path.exists(paper_folder) and os.listdir(paper_folder):
        return paper_folder

    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        # Check content type. If it's PDF, source is missing.
        content_type = response.headers.get('content-type', '')
        if 'application/pdf' in content_type:
            print(f"  ❌ Skipped {arxiv_id}: Only PDF available, no source.")
            return None

        # Create folder
        os.makedirs(paper_folder, exist_ok=True)

        # Try to open as tarfile
        try:
            with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as tar:
                tar.extractall(path=paper_folder)
                return paper_folder
        except tarfile.ReadError:
            # Sometimes it's just a single .tex file, not a tarball
            # We save the raw content as 'main.tex'
            with open(os.path.join(paper_folder, "main.tex"), "wb") as f:
                f.write(response.content)
            return paper_folder

    except Exception as e:
        print(f"  ❌ Error downloading source for {arxiv_id}: {e}")
        # Cleanup empty folder
        if os.path.exists(paper_folder):
            shutil.rmtree(paper_folder)
        return None

def find_main_tex_file(folder_path):
    """
    Heuristic to find the 'main' .tex file in a folder.
    Returns the filename (e.g., 'paper.tex').
    """
    tex_files = [f for f in os.listdir(folder_path) if f.endswith('.tex')]
    
    if not tex_files:
        return None
    
    if len(tex_files) == 1:
        return tex_files[0]
        
    # If multiple, look for 'main.tex' or the largest file
    if "main.tex" in tex_files:
        return "main.tex"
    
    # Fallback: Return largest .tex file
    tex_files.sort(key=lambda x: os.path.getsize(os.path.join(folder_path, x)), reverse=True)
    return tex_files[0]

def fetch_volatility_papers():
    # 1. Setup specific directory
    base_dir = "./vol_surface_source"
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)

    # 2. Define the Search
    client = arxiv.Client()
    search = arxiv.Search(
        query = '"volatility surface" AND cat:q-fin.*',
        max_results = 50,
        sort_by = arxiv.SortCriterion.Relevance
    )

    metadata_list = []
    
    print("Searching arXiv for 'Volatility Surface' papers...")
    results = list(client.results(search))
    print(f"Found {len(results)} papers. Starting source download...")

    # 3. Download Loop
    for i, paper in enumerate(results):
        paper_id = paper.entry_id.split('/')[-1]
        print(f"[{i+1}/{len(results)}] Processing: {paper.title[:50]}...")
        
        # Download Source
        source_folder = download_and_extract_source(paper_id, base_dir)
        
        if source_folder:
            # Find the .tex file
            main_tex_file = find_main_tex_file(source_folder)
            
            if main_tex_file:
                # 4. Store Metadata
                paper_meta = {
                    "arxiv_id": paper_id,
                    "title": paper.title,
                    "authors": [a.name for a in paper.authors],
                    "published_date": str(paper.published),
                    "abstract": paper.summary,
                    "source_folder": source_folder,
                    "main_tex_file": main_tex_file,
                    "url": paper.pdf_url
                }
                metadata_list.append(paper_meta)
                print(f"  ✅ Saved source to {source_folder}")
            else:
                print(f"  ⚠️ Source downloaded, but no .tex files found.")
        
    # 5. Save Metadata
    with open(os.path.join(base_dir, "metadata.json"), "w") as f:
        json.dump(metadata_list, f, indent=4)
        
    print(f"\nSuccess! Processed {len(metadata_list)} papers with valid source code.")

if __name__ == "__main__":
    fetch_volatility_papers()