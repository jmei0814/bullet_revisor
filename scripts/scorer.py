import json
import math
from sentence_transformers import SentenceTransformer, util


def _calibrate(raw: float) -> float:
    """
    Map raw cosine-similarity (typically 0.2–0.6) to an intuitive 0–1 display scale.
    Uses a linear stretch: 0.15 → 0 %, 0.70 → 100 %.
    Good bullets (~0.50 raw) display as ~65 %; weak ones (~0.30 raw) as ~27 %.
    """
    calibrated = (raw - 0.15) / 0.55
    return round(max(0.0, min(1.0, calibrated)), 4)

# Load model (you can change this to any SBERT variant)
model = SentenceTransformer('all-MiniLM-L6-v2')

def split_job_description(job_desc: str):
    """
    Split the job description into requirements.
    Here we split by periods or newlines; adjust for your text formatting.
    """
    lines = [line.strip() for line in job_desc.replace("\n", ". ").split(".") if line.strip()]
    return lines

def score_entry_bullets(entry: dict, req_embeddings, top_n: int):
    """
    Score bullets of a single entry using embedding similarity.
    Preserves {raw, clean} so formatting is intact.
    """
    bullets = entry.get("bullets", [])
    scored = []

    for bullet in bullets:
        if isinstance(bullet, dict):
            raw_text = bullet.get("raw") or bullet.get("clean", "")
            clean_text = bullet.get("clean", raw_text)
        else:
            # Backward-compatibility: treat plain strings as both raw+clean
            raw_text = str(bullet)
            clean_text = raw_text

        bullet_embedding = model.encode(clean_text, convert_to_tensor=True)
        similarities = util.cos_sim(bullet_embedding, req_embeddings)[0]
        best_score = float(similarities.max().item())

        scored.append((best_score, {"raw": raw_text, "clean": clean_text}))

    scored.sort(reverse=True, key=lambda x: x[0])
    max_bullets = entry.get("max_bullets", len(bullets))
    selected = [b for _, b in scored[:min(top_n, max_bullets)]]

    new_entry = dict(entry)
    new_entry["bullets"] = selected
    return new_entry

def score_all_bullets(data: dict, job_desc: str) -> dict:
    """
    Score every bullet and attach a similarity score without filtering.
    Returns a copy of data with bullets sorted by score descending,
    each bullet having an added 'score' field.
    """
    requirements = split_job_description(job_desc)
    req_embeddings = model.encode(requirements, convert_to_tensor=True)

    new_data = {"sections": {}}

    for section, entries in data["sections"].items():
        new_entries = []
        for entry in entries:
            if "bullets" not in entry or not entry["bullets"]:
                new_entries.append(entry)
                continue

            new_entry = dict(entry)
            scored_bullets = []

            for bullet in entry["bullets"]:
                if isinstance(bullet, dict):
                    raw_text = bullet.get("raw") or bullet.get("clean", "")
                    clean_text = bullet.get("clean", raw_text)
                else:
                    raw_text = str(bullet)
                    clean_text = raw_text

                # Empty bullets score 0 so they always rank last
                if not clean_text.strip():
                    scored_bullets.append({
                        "raw": raw_text,
                        "clean": clean_text,
                        "score": 0.0,
                    })
                    continue

                bullet_emb = model.encode(clean_text, convert_to_tensor=True)
                sims = util.cos_sim(bullet_emb, req_embeddings)[0]
                raw_score = float(sims.max().item())

                scored_bullets.append({
                    "raw": raw_text,
                    "clean": clean_text,
                    "score": _calibrate(raw_score),
                })

            scored_bullets.sort(key=lambda x: x["score"], reverse=True)
            new_entry["bullets"] = scored_bullets
            new_entries.append(new_entry)

        new_data["sections"][section] = new_entries

    return new_data


def select_best_bullets(data: dict, job_desc: str, top_n=5) -> dict:
    """
    Updates the structured JSON with only top-N bullets per entry based on embedding similarity.
    """
    requirements = split_job_description(job_desc)
    req_embeddings = model.encode(requirements, convert_to_tensor=True)

    new_data = {"sections": {}}

    for section, entries in data["sections"].items():
        new_entries = []
        for entry in entries:
            if "bullets" not in entry:
                new_entries.append(entry)
                continue
            scored_entry = score_entry_bullets(entry, req_embeddings, top_n)
            new_entries.append(scored_entry)
        new_data["sections"][section] = new_entries

    return new_data

# Example CLI usage
if __name__ == "__main__":
    with open("../data/bullet_points.json") as f:
        data = json.load(f)

    with open("../data/job.txt") as f:
        job_desc = f.read()

    best = select_best_bullets(data, job_desc, top_n=5)

    with open("../output/bullet_points_selected.json", "w") as f:
        json.dump(best, f, indent=2)

    print("✔ Selected top bullets based on embedding similarity → ../output/bullet_points_selected.json")
