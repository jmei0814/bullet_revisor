import json
import math
import re
from pathlib import Path
from sentence_transformers import SentenceTransformer, util


def _calibrate(raw: float) -> float:
    """
    Map raw cosine-similarity (typically 0.2–0.6) to an intuitive 0–1 display scale.
    Uses a linear stretch: 0.15 → 0 %, 0.70 → 100 %.
    Good bullets (~0.50 raw) display as ~65 %; weak ones (~0.30 raw) as ~27 %.
    """
    calibrated = (raw - 0.15) / 0.55
    return round(max(0.0, min(1.0, calibrated)), 4)


# ---- gibberish guard -------------------------------------------------------
# Embedding models happily produce moderate similarity for keyboard mash
# ("eoijsdf"), which would outrank real sentences. Gate scores by a text
# validity factor: bullets made of unrecognizable tokens score 0.

_WORDS_FILE = Path("/usr/share/dict/words")
_word_set = None

def _load_words():
    global _word_set
    if _word_set is None:
        try:
            _word_set = {w.strip().lower() for w in _WORDS_FILE.read_text().split("\n") if w.strip()}
        except OSError:
            _word_set = set()
    return _word_set

_VOWEL_RE = re.compile(r"[aeiouy]")
_CONSONANT_RUN_RE = re.compile(r"[bcdfghjklmnpqrstvwxz]{4,}")

# Lowercase tech terms that aren't in the dictionary and have no vowels /
# unusual structure, so the heuristic below would otherwise reject them.
_TECH_ALLOWLIST = {
    "nginx", "kubectl", "webpack", "pnpm", "npm", "yarn", "grpc", "graphql",
    "frontend", "backend", "fullstack", "microservices", "microservice",
    "serverless", "async", "await", "middleware", "stdlib", "plpgsql",
    "procs", "kubernetes", "kafka", "redis", "mongodb", "postgres", "postgresql",
    "sql", "css", "html", "json", "yaml", "toml", "http", "https", "rest",
    "grpc", "oauth", "jwt", "ssr", "csr", "cdn", "cli", "sdk", "api", "apis",
    "devops", "cicd", "terraform", "ansible", "pytorch", "tensorflow", "numpy",
    "pandas", "matplotlib", "sklearn", "scikit", "flask", "django", "fastapi",
    "nodejs", "typescript", "javascript", "golang", "rustlang", "webrtc",
    "websocket", "websockets", "ffmpeg", "opencv", "cuda", "vue", "svelte",
    "eslint", "prettier", "jest", "pytest", "gradle", "maven", "gitlab",
    "github", "bitbucket", "jira", "datadog", "prometheus", "grafana",
}

def _token_is_recognizable(tok: str) -> bool:
    """A token counts as real if it: contains digits (ROS2), is a known tech
    term, is a dictionary word, is a short acronym (SQL), is mixed-case
    (FastAPI), or simply has plausible word structure (a vowel and no run of
    4+ consonants), which admits jargon like nginx/webpack/middleware while
    still rejecting keyboard mash like 'eoijsdf' (run 'jsdf')."""
    if any(c.isdigit() for c in tok):
        return True
    low = tok.lower()
    # A single letter repeated (aaaa, qqq) is never a real word.
    if len(set(low)) == 1 and len(low) > 1:
        return False
    if low in _TECH_ALLOWLIST or (low.endswith("s") and low[:-1] in _TECH_ALLOWLIST):
        return True
    if tok.isupper():
        return len(tok) <= 6
    words = _load_words()
    if low in words or (low.endswith("s") and low[:-1] in words):
        return True
    if any(c.isupper() for c in tok[1:]):
        return True  # internal caps => product name (PostgreSQL, FastAPI)
    # Plausible word structure: has a vowel, no long consonant run.
    return bool(_VOWEL_RE.search(low)) and not _CONSONANT_RUN_RE.search(low)

def _text_validity(text: str) -> float:
    """1.0 for normal prose, scaling toward 0.0 as the share of gibberish
    tokens grows. A bullet with no word tokens scores 0."""
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9+#./-]*", text)
    if not tokens:
        return 0.0
    recognized = sum(1 for t in tokens if _token_is_recognizable(t))
    frac = recognized / len(tokens)
    # Forgiving plateau: only penalize when most tokens are unrecognizable,
    # so a jargon-dense real bullet isn't dragged down.
    if frac >= 0.5:
        return 1.0
    return round(frac / 0.5, 4)

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
                    "score": round(_calibrate(raw_score) * _text_validity(clean_text), 4),
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
