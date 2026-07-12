import re
import subprocess
from pathlib import Path
import logging
from typing import Any, Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _get_raw_bullet(bullet: Any) -> str:
    """
    Return the raw LaTeX string for a bullet.
    Accepts either:
      - a dict with 'raw' and 'clean' keys (preferred)
      - a plain string (assumed raw LaTeX)
    """
    if isinstance(bullet, dict):
        raw = bullet.get("raw") or bullet.get("clean") or ""
    else:
        raw = str(bullet)
    return raw

def _escape_specials(raw: str) -> str:
    """
    Escape LaTeX special characters a user is likely to type as plain text,
    while leaving intentional LaTeX (commands, escaped chars, balanced math)
    alone:
      - bare % & # are never valid in bullet text -> always escape
      - $: an odd number of unescaped $ cannot be math -> escape them all;
        an even count is assumed to be intentional $...$ math and left alone
      - _: escaped only outside $...$ math spans
    """
    raw = re.sub(r"(?<!\\)%", r"\\%", raw)
    raw = re.sub(r"(?<!\\)&", r"\\&", raw)
    raw = re.sub(r"(?<!\\)#", r"\\#", raw)

    if len(re.findall(r"(?<!\\)\$", raw)) % 2 == 1:
        raw = re.sub(r"(?<!\\)\$", r"\\$", raw)

    out, in_math, i = [], False, 0
    while i < len(raw):
        c = raw[i]
        if c == "\\" and i + 1 < len(raw):
            out.append(raw[i:i + 2])
            i += 2
            continue
        if c == "$":
            in_math = not in_math
        if c == "_" and not in_math:
            out.append(r"\_")
        else:
            out.append(c)
        i += 1
    return "".join(out)


# Macros that can read/write files or redefine control sequences at compile
# time. Stripped from user bullet text so a crafted bullet cannot exfiltrate
# server files (e.g. \input{/etc/passwd}) or corrupt the document.
_DANGEROUS_MACROS = re.compile(
    r"\\(?:input|include|write|openin|openout|read|immediate|catcode|def|edef|"
    r"gdef|xdef|let|csname|expandafter|loop|repeat|newcommand|renewcommand|"
    r"usepackage|documentclass|makeatletter|special)\b"
)


def _sanitize_raw(raw: str) -> str:
    """
    Make a user-edited bullet safe to embed in LaTeX:
      - normalize newlines
      - strip file-reading / redefinition macros (LaTeX injection guard)
      - escape likely-unintentional special characters (see _escape_specials)
      - balance braces so a stray { or } cannot cause a runaway argument
    """
    # Normalize Windows newlines
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")

    stripped = _DANGEROUS_MACROS.sub("", raw)
    if stripped != raw:
        logger.warning("Stripped disallowed macro(s) from bullet: %s", raw[:120])
    raw = stripped

    raw = _escape_specials(raw)

    # Count braces
    open_braces = raw.count("{")
    close_braces = raw.count("}")
    if open_braces != close_braces:
        diff = open_braces - close_braces
        if diff > 0:
            logger.warning("Unbalanced braces detected. Appending %d closing brace(s). Bullet: %s", diff, raw[:120])
            raw = raw + ("}" * diff)
        elif diff < 0:
            logger.warning("More closing braces than opening braces. Prepending %d opening brace(s). Bullet: %s", -diff, raw[:120])
            raw = ("{" * (-diff)) + raw
    return raw


# Boundaries that separate one entry's item list from the next entry's.
_ARTICLE_BOUNDARY = re.compile(r"\\resumeSubheading|\\resumeProjectHeading|\\section\b")
_CV_BOUNDARY = re.compile(r"\\cvexperience|\\cvuniversity|\\cvsection|\\cvsubsection")
# Plain-LaTeX resumes: entries are \textbf headings, so a new heading or section ends the entry.
_PLAIN_BOUNDARY = re.compile(r"\\textbf\{|\\section\b")

_ARTICLE_LIST = re.compile(r"\\resumeItemListStart(.*?)\\resumeItemListEnd", re.S)
# Group 1 captures itemize options (e.g. [noitemsep]) so replacement preserves them.
_CV_LIST = re.compile(r"\\begin\{itemize\}(\[[^\]]*\])?(.*?)\\end\{itemize\}", re.S)


def _find_block(body, start_pos, anchor_str, list_re, boundary_re):
    """
    Find the item-list block that belongs to the entry anchored by ``anchor_str``.

    Tries each occurrence of ``anchor_str`` at or after ``start_pos``; for each, the
    item list is the first one that follows without crossing an entry/section
    boundary. Returns the regex match for that list, or ``None``.
    """
    if not anchor_str:
        return None
    p = start_pos
    while True:
        idx = body.find(anchor_str, p)
        if idx == -1:
            return None
        anchor_end = idx + len(anchor_str)
        m = None
        for cand in list_re.finditer(body, anchor_end):
            m = cand
            break
        if m is not None and not boundary_re.search(body[anchor_end:m.start()]):
            return m
        p = idx + 1


def _entry_should_skip(entry: Dict, bullets_raw) -> bool:
    """
    Skip entries that must not trigger an item-list replacement:
      - no bullets at all (would produce an empty itemize -> pdflatex error),
      - pure skill / item entries (they carry no editable bullet block).
    """
    if not bullets_raw:
        return True
    if entry.get("item") is not None:
        return True
    return False


def replace_bullets(tex: str, data: Dict) -> str:
    """
    Replace bullet blocks in the provided LaTeX `tex` string using the structured JSON `data`.

    - `data` follows {"sections": { "SectionName": [ entries... ] } }.
    - Only content inside each matched item-list block is replaced.
    - Replacements are restricted to the document body (after \\begin{document}) to avoid
      corrupting preamble command definitions that also contain \\resumeItemListStart/End.
    - Entries are processed in document order using an advancing cursor, so duplicate
      identifiers (e.g. two "Southwestern University" entries) map to the correct block and
      no replacement crosses into a neighbouring entry's item list.
    - Entries with empty bullets, and pure skill/item entries, are skipped (they would
      otherwise create empty itemize blocks and break compilation).
    - maltacv entries (``entry["cv"]``) replace a plain ``\\begin{itemize}`` block with
      ``\\item`` lines; article entries replace ``\\resumeItemListStart`` blocks with
      ``\\resumeItem{...}`` lines.
    - Orphan entries (``entry["orphan"]``) are anchored by their section heading.
    """
    # Split preamble from body so we never touch \newcommand definitions.
    BODY_MARKER = r'\begin{document}'
    split_idx = tex.find(BODY_MARKER)
    if split_idx != -1:
        preamble = tex[:split_idx]
        body = tex[split_idx:]
    else:
        preamble = ''
        body = tex

    search_pos = 0  # advancing cursor into `body`

    for section_name, entries in data.get("sections", {}).items():
        for entry in entries:
            if not entry or "bullets" not in entry:
                continue

            bullets_raw = [_sanitize_raw(_get_raw_bullet(b)) for b in entry.get("bullets", [])]
            if _entry_should_skip(entry, bullets_raw):
                continue

            is_cv = bool(entry.get("cv"))
            is_plain = bool(entry.get("plain"))
            is_orphan = bool(entry.get("orphan"))

            if is_cv:
                list_re, boundary_re = _CV_LIST, _CV_BOUNDARY
            elif is_plain:
                list_re, boundary_re = _CV_LIST, _PLAIN_BOUNDARY
            else:
                list_re, boundary_re = _ARTICLE_LIST, _ARTICLE_BOUNDARY

            # ---- choose an anchor string ----
            # Prefer raw (un-cleaned) anchors: cleaned text (e.g. "A&M") may not
            # appear verbatim in the tex source (which has "A\&M").
            if is_orphan:
                # \section and \section* both occur in the wild; find whichever exists
                marker = "\\section{" + (entry.get("section_raw") or section_name) + "}"
                if marker not in body:
                    marker = "\\section*{" + (entry.get("section_raw") or section_name) + "}"
                anchor_str = marker
            else:
                anchor_str = (
                    entry.get("title_raw")
                    or entry.get("company")
                    or entry.get("title")
                    or entry.get("school")
                    or entry.get("role")
                    or entry.get("item")
                )

            if not anchor_str:
                logger.warning("Could not anchor entry in section '%s' (identifier missing).", section_name)
                continue

            # ---- find the item list belonging to this entry ----
            # Try occurrences from the advancing cursor first, then fall back to a
            # global search (needed when an entry appears before the cursor).
            m = _find_block(body, search_pos, anchor_str, list_re, boundary_re)
            if m is None:
                m = _find_block(body, 0, anchor_str, list_re, boundary_re)

            if m is None:
                logger.warning("No item list found for entry in section '%s' (anchor=%r).", section_name, anchor_str[:40])
                continue

            # ---- build replacement ----
            if is_cv or is_plain:
                opts = m.group(1) or ""  # preserve [options] on the itemize
                new_inner = "\n"
                for raw_b in bullets_raw:
                    new_inner += f"  \\item {raw_b}\n"
                replacement = "\\begin{itemize}" + opts + new_inner + "\\end{itemize}"
            else:
                new_inner = "\n"
                for raw_b in bullets_raw:
                    new_inner += f"\\resumeItem{{{raw_b}}}\n"
                replacement = "\\resumeItemListStart" + new_inner + "\\resumeItemListEnd"

            body = body[:m.start()] + replacement + body[m.end():]
            search_pos = m.start() + len(replacement)
            logger.info("Replaced bullets for an entry in section '%s'.", section_name)

    return preamble + body


def compile_pdf(tex_file: str, output_dir: str = "./output") -> bool:
    """
    Compile the provided .tex file with pdflatex into output_dir.

    Runs in nonstopmode WITHOUT -halt-on-error so recoverable errors
    (e.g. a "missing \\item" LaTeX can insert itself) still yield a PDF,
    matching Overleaf-like tolerance. Success = the PDF file exists,
    not the exit code (pdflatex exits nonzero on any logged error).
    Returns True on success, False on failure.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    cmd = ["pdflatex", "-interaction=nonstopmode", "-output-directory", output_dir, tex_file]
    pdf_path = Path(output_dir) / (Path(tex_file).stem + ".pdf")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        logger.error("pdflatex timed out after 60s for %s", tex_file)
        return False

    if pdf_path.exists() and pdf_path.stat().st_size > 0:
        if proc.returncode != 0:
            logger.warning("pdflatex recovered from errors but produced a PDF (%s).", pdf_path.name)
        else:
            logger.info("pdflatex completed successfully.")
        return True

    logger.error("pdflatex failed (no PDF produced). stdout tail:\n%s", proc.stdout[-3000:] if proc.stdout else "")
    return False
