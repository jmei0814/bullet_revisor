import json
from pathlib import Path
from parsers.latex_parser import parse_resume, save_json
from scripts.scorer import select_best_bullets
from parsers.renderer import replace_bullets, compile_pdf

# Paths
RESUME_TEX = "../data/resume.tex"
BULLETS_JSON = "../data/bullet_points.json"
JOB_FILE = "../data/job.txt"
OUTPUT_TEX = "../output/resume_updated.tex"
OUTPUT_PDF = "../output/resume_updated.pdf"

def main():
    # Ensure output directory exists
    Path(OUTPUT_TEX).parent.mkdir(parents=True, exist_ok=True)

    # 1️⃣ Parse LaTeX → JSON
    print("📄 Parsing LaTeX resume...")
    data = parse_resume(RESUME_TEX)
    
    # Automatically set max_bullets = len(bullets) if not already present
    for section_entries in data["sections"].values():
        for entry in section_entries:
            if "bullets" in entry and "max_bullets" not in entry:
                entry["max_bullets"] = len(entry["bullets"])

    save_json(data, BULLETS_JSON)
    print(f"✔ Saved bullet_points.json → {BULLETS_JSON}")

    # 2️⃣ Load job description
    with open(JOB_FILE) as f:
        job_desc = f.read()

    # 3️⃣ Select best bullets per entry using embeddings
    print("🤖 Scoring bullets against job description...")
    best_data = select_best_bullets(data, job_desc, top_n=5)

    # Save selected bullets JSON
    selected_json_path = "../output/bullet_points_selected.json"
    save_json(best_data, selected_json_path)
    print(f"✔ Saved top bullets → {selected_json_path}")

    # 4️⃣ Load original LaTeX template
    with open(RESUME_TEX) as f:
        tex = f.read()

    # 5️⃣ Replace bullets in LaTeX
    print("✏️ Replacing bullets in LaTeX template...")
    updated_tex = replace_bullets(tex, best_data)

    with open(OUTPUT_TEX, "w") as f:
        f.write(updated_tex)
    print(f"✔ Updated LaTeX saved → {OUTPUT_TEX}")

    # 6️⃣ Compile PDF
    print("📦 Compiling PDF...")
    compile_pdf(OUTPUT_TEX)
    print(f"✅ Done! Tailored resume PDF saved → {OUTPUT_PDF}")

if __name__ == "__main__":
    main()
