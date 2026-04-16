import re
import json
from collections import defaultdict

def clean_latex(s: str) -> str:
    """Remove LaTeX formatting for NLP scoring use."""
    s = re.sub(r"\\textbf{([^}]*)}", r"\1", s)
    s = re.sub(r"\\emph{([^}]*)}", r"\1", s)
    s = re.sub(r"\\%","%",s)
    s = re.sub(r"\\[a-zA-Z]+\*?{([^}]*)}", r"\1", s)  # remove most commands with braces
    s = re.sub(r"\\[a-zA-Z]+\*?", "", s)  # drop leftover commands
    return s.strip()

def _find_command_args(text: str, command: str, num_args: int):
    """
    Find all occurrences of `command` in `text` and extract its brace-delimited
    arguments, correctly handling nested braces.
    Returns a list of arg-lists (each arg-list has `num_args` strings).
    """
    results = []
    search_start = 0

    while True:
        idx = text.find(command, search_start)
        if idx == -1:
            break

        # Make sure the character immediately after the command is not a letter
        # (to avoid matching \resumeSubheading inside \resumeSubSubheading, etc.)
        after = idx + len(command)
        if after < len(text) and (text[after].isalpha() or text[after] == '*'):
            search_start = idx + 1
            continue

        j = after
        args = []
        valid = True

        for _ in range(num_args):
            # Skip whitespace to find the opening {
            while j < len(text) and text[j] in ' \t\n\r':
                j += 1

            if j >= len(text) or text[j] != '{':
                valid = False
                break

            j += 1  # skip opening {
            depth = 1
            buf = []

            while j < len(text) and depth > 0:
                if text[j] == '{':
                    depth += 1
                elif text[j] == '}':
                    depth -= 1
                    if depth == 0:
                        break
                buf.append(text[j])
                j += 1

            args.append("".join(buf).strip())
            j += 1  # skip closing }

        if valid and len(args) == num_args:
            results.append(args)

        search_start = idx + len(command)

    return results

def extract_brace_content(text: str, command="\\resumeItem"):
    """
    Extract content inside braces for a LaTeX command, handling nested {}.
    Example: \\resumeItem{foo \\textbf{bar}} -> ["foo \\textbf{bar}"]
    """
    results = _find_command_args(text, command, 1)
    return [r[0] for r in results]

def extract_itemize_bullets(text: str):
    """
    Extract \\item bullets from plain LaTeX itemize/enumerate blocks.
    """
    bullets = []
    matches = re.findall(r"\\item\s+([^\n]*)", text)
    for m in matches:
        bullets.append(m.strip())
    return bullets

def parse_resume(path: str):
    with open(path, "r") as f:
        tex = f.read()

    sections = defaultdict(list)

    # split into sections
    raw_sections = re.split(r"\\section{([^}]*)}", tex)

    for i in range(1, len(raw_sections), 2):
        section_name = clean_latex(raw_sections[i])
        content = raw_sections[i + 1]
        entries = []

        # ---- Experience / Work entries ----
        # \resumeSubheading{role}{date}{company}{location}  — 4 args
        sub_matches = _find_command_args(content, "\\resumeSubheading", 4)
        for args in sub_matches:
            raw_role    = args[0]
            raw_date    = args[1]
            raw_company = args[2]
            raw_loc     = args[3]

            entry = {
                "role":     clean_latex(raw_role),
                "date":     clean_latex(raw_date),
                "company":  clean_latex(raw_company),
                "location": clean_latex(raw_loc),
                "bullets":  []
            }

            # Anchor on the role (first arg) which appears before \resumeItemListStart
            bullets_match = re.search(
                rf"{re.escape(raw_role)}.*?\\resumeItemListStart(.*?)\\resumeItemListEnd",
                content,
                re.S,
            )
            if bullets_match:
                raw_bullets = extract_brace_content(bullets_match.group(1), "\\resumeItem")
                if not raw_bullets:
                    raw_bullets = extract_itemize_bullets(bullets_match.group(1))
                entry["bullets"] = [
                    {"raw": b.strip(), "clean": clean_latex(b)} for b in raw_bullets
                ]
            entries.append(entry)

        # ---- Projects ----
        # \resumeProjectHeading{title (may contain nested braces)}{date}  — 2 args
        proj_matches = _find_command_args(content, "\\resumeProjectHeading", 2)
        for args in proj_matches:
            raw_title = args[0]   # keep raw for renderer anchoring
            raw_date  = args[1]

            entry = {
                "title":     clean_latex(raw_title),
                "title_raw": raw_title,             # needed by renderer to find the block
                "date":      clean_latex(raw_date),
                "bullets":   []
            }

            bullets_match = re.search(
                rf"{re.escape(raw_title)}.*?\\resumeItemListStart(.*?)\\resumeItemListEnd",
                content,
                re.S,
            )
            if bullets_match:
                raw_bullets = extract_brace_content(bullets_match.group(1), "\\resumeItem")
                if not raw_bullets:
                    raw_bullets = extract_itemize_bullets(bullets_match.group(1))
                entry["bullets"] = [
                    {"raw": b.strip(), "clean": clean_latex(b)} for b in raw_bullets
                ]
            entries.append(entry)

        # ---- Skills / SubItems ----
        subitems = extract_brace_content(content, "\\resumeSubItem")
        if not subitems:  # fallback: check for \item inside Skills
            subitems = extract_itemize_bullets(content)
        for si in subitems:
            entries.append({
                "item": clean_latex(si),
                "raw": si.strip(),
                "bullets": []
            })

        if entries:
            sections[section_name].extend(entries)

    return {"sections": dict(sections)}

def save_json(data, path: str):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

if __name__ == "__main__":
    parsed = parse_resume("../data/resume.tex")
    save_json(parsed, "../data/bullet_points.json")
    print("✔ Parsed resume → bullet_points.json")
