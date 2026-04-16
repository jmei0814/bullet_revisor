import json
from pathlib import Path
from parsers.latex_parser import parse_resume, save_json
from scripts.scorer import select_best_bullets
from parsers.renderer import replace_bullets, compile_pdf

# Paths
RESUME_TEX = "data/resume.tex"
BULLETS_JSON = "data/bullet_points.json"
OUTPUT_TEX = "output/resume_updated.tex"
OUTPUT_PDF = "output/resume_updated.pdf"

def edit_json(data):
    """
    CLI to let user edit bullets and max_bullets per entry.
    """
    print("✏️  Editing bullet points...\n")
    for section, entries in data["sections"].items():
        print(f"--- {section} ---")
        for i, entry in enumerate(entries):
            if "bullets" not in entry:
                continue
            print(f"\nEntry {i+1}: {entry.get('company') or entry.get('title') or entry.get('school')}")
            print("Current bullets:")
            for j, b in enumerate(entry["bullets"]):
                print(f"  {j+1}. {b}")
            # Option to add new bullets
            while True:
                new_b = input("Add a new bullet (or press Enter to skip): ")
                if not new_b.strip():
                    break
                entry["bullets"].append(new_b.strip())
            # Option to set max_bullets
            max_b = input(f"Max bullets to show for this entry (default {len(entry['bullets'])}): ")
            if max_b.strip().isdigit():
                entry["max_bullets"] = int(max_b.strip())
            else:
                entry["max_bullets"] = len(entry["bullets"])
    return data

def main():
    Path(OUTPUT_TEX).parent.mkdir(parents=True, exist_ok=True)

    # 1️⃣ Parse LaTeX → JSON
    print("📄 Parsing LaTeX resume...")
    data = parse_resume(RESUME_TEX)

    # Ensure max_bullets is set
    for section_entries in data["sections"].values():
        for entry in section_entries:
            if "bullets" in entry and "max_bullets" not in entry:
                entry["max_bullets"] = len(entry["bullets"])

    save_json(data, BULLETS_JSON)
    print(f"✔ Parsed bullets saved → {BULLETS_JSON}")

    # 2️⃣ Let user edit bullets and max_bullets
    data = edit_json(data)

    # Save edited JSON
    save_json(data, BULLETS_JSON)
    print(f"✔ Edited bullets saved → {BULLETS_JSON}")

    # 3️⃣ Input job description
    job_desc = input("\nPaste the job description (end with an empty line):\n")
    lines = []
    while True:
        line = input()
        if not line.strip():
            break
        lines.append(line)
    job_desc += "\n" + "\n".join(lines)

    # 4️⃣ Score bullets using embeddings
    print("\n🤖 Selecting best bullets for this job...")
    best_data = select_best_bullets(data, job_desc, top_n=5)

    # Save selected bullets JSON
    selected_json_path = "../output/bullet_points_selected.json"
    save_json(best_data, selected_json_path)
    print(f"✔ Selected top bullets saved → {selected_json_path}")

    # 5️⃣ Replace bullets in LaTeX
    with open(RESUME_TEX) as f:
        tex = f.read()
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
