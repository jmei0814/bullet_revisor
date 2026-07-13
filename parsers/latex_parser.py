import re
import json
from collections import defaultdict

def clean_latex(s: str) -> str:
    """Strip LaTeX formatting to plain text (for display and NLP scoring)."""
    # Protect escaped braces so they survive command/group stripping
    s = s.replace(r"\{", "\x00").replace(r"\}", "\x01")
    # \href{url}{text}: drop the url argument entirely, keep the text group
    s = re.sub(r"\\href\{[^{}]*\}", "", s)
    # Strip formatting commands innermost-first until stable
    # (handles \textbf{nested \emph{deep}} etc.)
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"\\[a-zA-Z]+\*?\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\([%&$#_])", r"\1", s)  # unescape special chars: \% \& \$ \# \_
    s = re.sub(r"\\[a-zA-Z]+\*?", "", s)  # drop leftover bare commands
    s = s.replace("$|$", "|")             # common separator idiom
    s = s.replace("{", "").replace("}", "")  # drop leftover grouping braces
    s = s.replace("\x00", "{").replace("\x01", "}")  # restore escaped braces
    return re.sub(r"\s+", " ", s).strip()


# A string "looks like a date" if it has a year, a month name, or a
# present/expected marker. Used to place date vs. location correctly
# regardless of which argument slot the resume author used.
_DATE_RE = re.compile(
    r"\b(?:19|20)\d{2}\b"                                  # 1999 / 2026
    r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\.?\b"  # month
    r"|\bpresent\b|\bcurrent\b|\bexpected\b|\bongoing\b",
    re.I,
)


def _is_date(s: str) -> bool:
    return bool(s) and bool(_DATE_RE.search(s))


def _split_date_location(vals):
    """Given the two right-column items of a subheading, decide which is the
    date and which is the location. Keys off date-like content; falls back to
    the common Jake ordering (location, date) when it can't tell."""
    vals = [v.strip() for v in vals]
    dated = [v for v in vals if _is_date(v)]
    if len(dated) == 1:
        date = dated[0]
        location = next((v for v in vals if v != date), "")
        return date, location
    # 0 or 2 look date-like: fall back to Jake's {location}{date} order.
    top, bottom = vals[0], vals[1]
    return bottom, top


def _subheading_fields(a):
    """Map a 4-arg \\resumeSubheading to display fields by VISUAL position,
    not assumed semantics. Layout is:
        [ #1 bold      ] [ #2 (right) ]
        [ #3 italic    ] [ #4 (right) ]
    so #1 is always the card title and #3 the subtitle; #2/#4 are the
    date/location pair (order varies by author, so detect it)."""
    date, location = _split_date_location([a[1], a[3]])
    return {
        "company": clean_latex(a[0]),   # bold heading -> card title
        "title_raw": a[0],              # raw form for renderer anchoring
        "role": clean_latex(a[2]),      # italic line -> subtitle
        "date": date,
        "location": location,
    }


def _strip_comments(tex: str) -> str:
    """
    Remove LaTeX line comments (unescaped ``%`` to end of line) while preserving
    escaped percents (``\\%``). This prevents commented-out constructs (e.g. an
    entirely commented ``\\section{Projects}`` block) from being parsed.
    """
    out = []
    for line in tex.split("\n"):
        buf = []
        i = 0
        n = len(line)
        while i < n:
            c = line[i]
            if c == "\\" and i + 1 < n:
                buf.append(line[i])
                buf.append(line[i + 1])
                i += 2
                continue
            if c == "%":
                break
            buf.append(c)
            i += 1
        out.append("".join(buf))
    return "\n".join(out)


def _find_command_args_pos(text: str, command: str, num_args: int):
    """
    Like :func:`_find_command_args` but also returns positional information.

    Returns a list of ``(args, start, end)`` tuples where ``start`` is the index
    of the command in ``text`` and ``end`` is the index just past the closing
    brace of the last consumed argument.
    """
    results = []
    search_start = 0

    while True:
        idx = text.find(command, search_start)
        if idx == -1:
            break

        # Make sure the character immediately after the command is not a letter
        # (to avoid matching \resumeSubheading inside \resumeSubheadingS, etc.)
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
            results.append((args, idx, j))

        search_start = idx + len(command)

    return results


def _find_command_args(text: str, command: str, num_args: int):
    """
    Find all occurrences of `command` in `text` and extract its brace-delimited
    arguments, correctly handling nested braces.
    Returns a list of arg-lists (each arg-list has `num_args` strings).
    """
    return [args for args, _s, _e in _find_command_args_pos(text, command, num_args)]

def extract_brace_content(text: str, command="\\resumeItem"):
    """
    Extract content inside braces for a LaTeX command, handling nested {}.
    Example: \\resumeItem{foo \\textbf{bar}} -> ["foo \\textbf{bar}"]
    """
    results = _find_command_args(text, command, 1)
    return [r[0] for r in results]

def extract_itemize_bullets(text: str):
    """
    Extract \\item bullets from plain LaTeX itemize/enumerate blocks (single line).
    """
    bullets = []
    matches = re.findall(r"\\item\s+([^\n]*)", text)
    for m in matches:
        bullets.append(m.strip())
    return bullets


def extract_itemize_multiline(inner: str):
    """
    Extract \\item bullets from a plain itemize block where an individual \\item
    may span multiple lines. Splits on \\item boundaries and trims whitespace.
    """
    bullets = []
    parts = re.split(r"\\item\b", inner)
    for p in parts[1:]:
        text = p.strip()
        if text:
            bullets.append(text)
    return bullets


def extract_skill_items(content: str):
    """
    Extract skill lines from a ``\\item{ ... }`` block as used in the Technical
    Skills section (``\\small{\\item{ \\textbf{Languages}{: ...} \\\\ ... }}``).
    Each line separated by ``\\\\`` becomes one item.
    """
    items = []
    for arg in _find_command_args(content, "\\item", 1):
        block = arg[0]
        for part in re.split(r"\\\\", block):
            part = part.strip()
            if part:
                items.append(part)
    return items


def _bullets_from_inner(inner: str):
    """Turn the inner text of an item-list block into bullet dicts."""
    if inner is None:
        return []
    raw_bullets = extract_brace_content(inner, "\\resumeItem")
    if not raw_bullets:
        raw_bullets = extract_itemize_bullets(inner)
    return [{"raw": b.strip(), "clean": clean_latex(b)} for b in raw_bullets]


def _parse_article(tex: str):
    """Parse an article-class (Jake-style) resume."""
    tex = _strip_comments(tex)
    sections = defaultdict(list)

    raw_sections = re.split(r"\\section\*?\{([^}]*)\}", tex)

    for i in range(1, len(raw_sections), 2):
        section_raw = raw_sections[i]
        section_name = clean_latex(section_raw)
        content = raw_sections[i + 1]
        entries = []

        # ---- gather structured entry commands with positions ----
        occ = []
        for args, s, e in _find_command_args_pos(content, "\\resumeSubheading", 4):
            occ.append({"kind": "subheading", "args": args, "start": s, "end": e, "il": None})
        for args, s, e in _find_command_args_pos(content, "\\resumeSubheadingS", 2):
            occ.append({"kind": "subheadingS", "args": args, "start": s, "end": e, "il": None})
        for args, s, e in _find_command_args_pos(content, "\\resumeProjectHeading", 2):
            occ.append({"kind": "project", "args": args, "start": s, "end": e, "il": None})
        occ.sort(key=lambda o: o["start"])

        # ---- locate every item-list block; anchor by position ----
        item_lists = [
            (m.start(), m.group(1))
            for m in re.finditer(r"\\resumeItemListStart(.*?)\\resumeItemListEnd", content, re.S)
        ]
        orphan_inners = []
        for il_start, inner in item_lists:
            owner = None
            for o in occ:
                if o["start"] < il_start:
                    owner = o  # greatest start still before this item list
                else:
                    break
            if owner is None:
                # No entry precedes this item list -> orphan (e.g. Honors & Awards)
                orphan_inners.append(inner)
            elif owner["il"] is None:
                owner["il"] = inner  # first item list belongs to the entry

        # ---- build structured entries ----
        for o in occ:
            bullets = _bullets_from_inner(o["il"])
            a = o["args"]
            if o["kind"] == "subheading":
                entry = _subheading_fields(a)
                entry["bullets"] = bullets
            elif o["kind"] == "subheadingS":
                # {#1 bold heading}{#2 right}: #2 is a date or a location.
                second = clean_latex(a[1])
                entry = {
                    "company": clean_latex(a[0]),
                    "title_raw": a[0],
                    "date": second if _is_date(second) else "",
                    "location": "" if _is_date(second) else second,
                    "bullets": bullets,
                }
            else:  # project
                entry = {
                    "title": clean_latex(a[0]),
                    "title_raw": a[0],
                    "date": clean_latex(a[1]),
                    "bullets": bullets,
                }
            entries.append(entry)

        # ---- orphan item list(s): editable bullets anchored by section ----
        if orphan_inners:
            ob = []
            for inner in orphan_inners:
                ob.extend(_bullets_from_inner(inner))
            entries.append({"title": section_name, "section_raw": section_raw, "orphan": True, "bullets": ob})

        # ---- plain-LaTeX entries: \textbf{Org} heading + plain itemize ----
        # (resumes that use no template commands at all, e.g. \section*{...}
        #  followed by \textbf{...} \hfill dates \\ \textit{Role} + itemize)
        if not occ and not item_lists:
            plain_itemizes = [
                (m.start(), m.group(1))
                for m in re.finditer(r"\\begin\{itemize\}(.*?)\\end\{itemize\}", content, re.S)
            ]
            if plain_itemizes:
                bolds = _find_command_args_pos(content, "\\textbf", 1)
                consumed = set()
                orphan_plain = []
                for it_start, inner in plain_itemizes:
                    heading = None
                    for args, s, e in bolds:
                        if s < it_start and s not in consumed:
                            heading = (args[0], s, e)
                    raw_bullets = extract_itemize_multiline(inner)
                    bullets = [{"raw": b.strip(), "clean": clean_latex(b)} for b in raw_bullets]
                    if heading is None:
                        # No heading before the itemize. Could be a genuine orphan
                        # list (Awards as bare bullets) or a skills-style block
                        # (\textbf labels inside the itemize) -- defer the decision.
                        orphan_plain.append(bullets)
                        continue
                    raw_head, h_start, h_end = heading
                    consumed.add(h_start)
                    # heading line tail: ", Location \hfill Date \\" then maybe \textit{Role}
                    between = content[h_end:it_start]
                    date_m = re.search(r"\\hfill\s*([^\\\n]+)", between)
                    role_m = re.search(r"\\textit\{([^}]*)\}", between)
                    loc_m = re.match(r"\s*,\s*([^\\\n]+?)\s*(?:\\hfill|\\\\|\n)", between)
                    entries.append({
                        "company": clean_latex(raw_head),
                        "title_raw": raw_head,
                        "role": clean_latex(role_m.group(1)) if role_m else "",
                        "date": date_m.group(1).strip() if date_m else "",
                        "location": loc_m.group(1).strip() if loc_m else "",
                        "plain": True,
                        "bullets": bullets,
                    })

                # Headingless itemizes: treat as editable orphan bullets only if
                # this isn't a skills-style section (labels inside the itemize).
                if orphan_plain and not extract_skill_items(content):
                    for bullets in orphan_plain:
                        entries.append({
                            "title": section_name, "section_raw": section_raw,
                            "orphan": True, "plain": True, "bullets": bullets,
                        })

        # ---- flat item / skill entries (only for unstructured sections) ----
        if not occ and not orphan_inners and not any(e.get("plain") for e in entries):
            subitems = extract_brace_content(content, "\\resumeSubItem")
            if subitems:
                for si in subitems:
                    entries.append({"item": clean_latex(si), "raw": si.strip(), "bullets": []})
            else:
                skill_items = extract_skill_items(content)
                if skill_items:
                    for si in skill_items:
                        entries.append({"item": clean_latex(si), "raw": si.strip(), "bullets": []})
                else:
                    for si in extract_itemize_bullets(content):
                        entries.append({"item": clean_latex(si), "raw": si.strip(), "bullets": []})

        if entries:
            sections[section_name].extend(entries)

    return {"sections": dict(sections)}


def _parse_maltacv(tex: str):
    """Parse a maltacv/AltaCV-class resume."""
    tex = _strip_comments(tex)
    sections = defaultdict(list)

    raw_sections = re.split(r"\\cv(?:sub)?section\{([^}]*)\}", tex)

    for i in range(1, len(raw_sections), 2):
        section_name = clean_latex(raw_sections[i])
        content = raw_sections[i + 1]
        entries = []

        # structured cv entries with positions
        occ = []
        for args, s, e in _find_command_args_pos(content, "\\cvexperience", 5):
            occ.append({"kind": "cvexp", "args": args, "start": s, "end": e})
        for args, s, e in _find_command_args_pos(content, "\\cvuniversity", 4):
            occ.append({"kind": "cvuni", "args": args, "start": s, "end": e})
        occ.sort(key=lambda o: o["start"])

        # plain itemize blocks
        itemizes = [
            (m.start(), m.group(1))
            for m in re.finditer(r"\\begin\{itemize\}(.*?)\\end\{itemize\}", content, re.S)
        ]

        for o in occ:
            nxt_start = min([x["start"] for x in occ if x["start"] > o["start"]], default=len(content))
            inner = None
            for it_start, it_inner in itemizes:
                if o["end"] <= it_start < nxt_start:
                    inner = it_inner
                    break
            raw_bullets = extract_itemize_multiline(inner) if inner is not None else []
            bullets = [{"raw": b.strip(), "clean": clean_latex(b)} for b in raw_bullets]
            a = o["args"]
            if o["kind"] == "cvexp":
                # \cvexperience{role}{org}{date}{location}{tags}
                entry = {
                    "role": clean_latex(a[0]),
                    "company": clean_latex(a[1]),
                    "date": clean_latex(a[2]),
                    "location": clean_latex(a[3]),
                    "title_raw": a[0],
                    "cv": True,
                    "bullets": bullets,
                }
            else:
                # \cvuniversity{degree}{school}{date}{location}
                # title (company field) shows the degree, subtitle (role) shows school
                entry = {
                    "company": clean_latex(a[0]),
                    "role": clean_latex(a[1]),
                    "date": clean_latex(a[2]),
                    "location": clean_latex(a[3]),
                    "title_raw": a[0],
                    "cv": True,
                    "bullets": bullets,
                }
            entries.append(entry)

        # standalone \cvlistitem{name}{desc} -> item entries
        for a in _find_command_args(content, "\\cvlistitem", 2):
            name = clean_latex(a[0])
            desc = clean_latex(a[1])
            item_text = name if not desc else f"{name}: {desc}"
            entries.append({"item": item_text, "raw": a[0], "bullets": []})

        if entries:
            sections[section_name].extend(entries)

    return {"sections": dict(sections)}


def parse_resume(path: str):
    with open(path, "r") as f:
        tex = f.read()

    if "\\cvsection" in tex or "maltacv" in tex or "altacv" in tex:
        return _parse_maltacv(tex)
    return _parse_article(tex)

def save_json(data, path: str):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

if __name__ == "__main__":
    parsed = parse_resume("../data/resume.tex")
    save_json(parsed, "../data/bullet_points.json")
    print("✔ Parsed resume → bullet_points.json")
