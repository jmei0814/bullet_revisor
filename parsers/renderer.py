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

def _sanitize_raw(raw: str) -> str:
    """
    Minimal sanitization:
      - Leave LaTeX commands alone.
      - If braces are unbalanced, attempt to close open braces at the end.
      - Warn if a fix was needed.
    """
    # Normalize Windows newlines
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")

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

def replace_bullets(tex: str, data: Dict) -> str:
    """
    Replace bullet blocks in the provided LaTeX `tex` string using the structured JSON `data`.
    - `data` is expected to follow {"sections": { "SectionName": [ entries... ] } }
    - Each entry with bullets should have `entry["bullets"]` which may be a list of dicts or strings.
    - Only content inside each matched \resumeItemListStart ... \resumeItemListEnd block is replaced.
    - Replacements are restricted to the document body (after \begin{document}) to avoid
      corrupting preamble command definitions that also contain \resumeItemListStart/End.
    """
    # Split preamble from body so we never touch \newcommand definitions
    BODY_MARKER = r'\begin{document}'
    split_idx = tex.find(BODY_MARKER)
    if split_idx != -1:
        preamble = tex[:split_idx]
        updated_tex = tex[split_idx:]
    else:
        preamble = ''
        updated_tex = tex

    # Keep track of how many resumeItemList blocks we've consumed (fallback matching)
    consumed_itemlists = 0

    # Precompile a general itemlist pattern for fallback replacement
    itemlist_pattern = re.compile(r"(\\resumeItemListStart)(.*?)(\\resumeItemListEnd)", re.S)

    for section_name, entries in data.get("sections", {}).items():
        for entry in entries:
            if not entry or "bullets" not in entry:
                continue

            bullets_raw = [_sanitize_raw(_get_raw_bullet(b)) for b in entry["bullets"]]

            # Choose the best identifier available to anchor the replacement
            identifier = (
                entry.get("company")
                or entry.get("title_raw")  # raw LaTeX title (projects); needed to match tex source
                or entry.get("title")
                or entry.get("school")
                or entry.get("role")
                or entry.get("item")
            )

            if identifier:
                # Build anchor-aware pattern (anchor on the identifier occurring before the itemlist)
                # We allow some text between identifier and the item list. Use DOTALL so newlines match.
                try_pattern = rf"({re.escape(identifier)}.*?\\resumeItemListStart)(.*?)(\\resumeItemListEnd)"
                match = re.search(try_pattern, updated_tex, re.S)
            else:
                match = None

            if match:
                # Replace this specific anchored item-list block
                prefix = match.group(1)
                suffix = match.group(3)

                new_block = "\n"
                for raw_b in bullets_raw:
                    new_block += f"\\resumeItem{{{raw_b}}}\n"

                replacement = prefix + new_block + suffix
                # replace only the first occurrence of this exact match (so we don't clobber duplicates)
                updated_tex = updated_tex[: match.start()] + replacement + updated_tex[match.end() :]
                logger.info("Replaced bullets for identifier '%s' in section '%s'.", identifier, section_name)
            else:
                # Fallback: find the next unmatched resumeItemListStart ... resumeItemListEnd
                # We'll replace the next one we haven't consumed.
                def fallback_replacer(m):
                    nonlocal consumed_itemlists
                    if consumed_itemlists == 0:
                        # replace this one
                        new_block = "\n"
                        for raw_b in bullets_raw:
                            new_block += f"\\resumeItem{{{raw_b}}}\n"
                        consumed_itemlists += 1
                        return m.group(1) + new_block + m.group(3)
                    else:
                        # leave unchanged and decrement counter for next calls
                        consumed_itemlists -= 1
                        return m.group(0)

                # Use subn to replace the first available block
                updated_tex, nsub = itemlist_pattern.subn(lambda m: fallback_replacer(m), updated_tex, count=1)
                if nsub > 0:
                    logger.info("Fallback replaced the next item-list block for an entry in section '%s'.", section_name)
                else:
                    logger.warning("Could not find an item-list block to replace for entry (identifier=%s).", identifier)

    return preamble + updated_tex


def compile_pdf(tex_file: str, output_dir: str = "./output") -> bool:
    """
    Compile the provided .tex file with pdflatex into output_dir.
    Returns True on success, False on failure. Prints compiler stdout/stderr on error.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    cmd = ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "-output-directory", output_dir, tex_file]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info("pdflatex completed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        logger.error("pdflatex failed. stdout:\n%s\n\nstderr:\n%s", e.stdout, e.stderr)
        return False
