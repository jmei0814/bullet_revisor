#!/usr/bin/env python
"""
Tests for parsers.latex_parser and parsers.renderer.

Run with:  my_env/bin/python tests/test_parser.py

Plain-assert style (no pytest required). Exercises three resume templates:
  1. jakes_resume.tex            -- canonical article-class Jake template
  2. data/jakes_resume.tex       -- article-class variant (subheadingS, orphan
                                     lists, enumerate publications, empty args)
  3. data/alternative.tex        -- maltacv class (cvsection/cvexperience/...)
"""
import os
import re
import sys

# Make the repo root importable regardless of CWD.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from parsers.latex_parser import parse_resume
from parsers.renderer import replace_bullets, compile_pdf

import tempfile
SCRATCH = os.path.join(tempfile.gettempdir(), "bulletrevisor_tests")

JAKE = os.path.join(REPO_ROOT, "tests", "fixtures", "jake_original.tex")
GLORIA = os.path.join(REPO_ROOT, "data", "jakes_resume.tex")
ALT = os.path.join(REPO_ROOT, "data", "alternative.tex")
TORTURE = os.path.join(REPO_ROOT, "tests", "fixtures", "torture.tex")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def bullet_counts(data):
    """{section_name: [bullet-count per entry]}"""
    return {sec: [len(e.get("bullets", [])) for e in ents]
            for sec, ents in data["sections"].items()}


def find_section(data, needle):
    for sec, ents in data["sections"].items():
        if needle in sec:
            return sec, ents
    raise AssertionError(f"section containing {needle!r} not found in {list(data['sections'])}")


def preamble_of(tex):
    i = tex.find(r"\begin{document}")
    return tex if i == -1 else tex[:i]


def has_empty_itemize(tex):
    """True if any empty item-list block exists (would break pdflatex)."""
    if re.search(r"\\resumeItemListStart\s*\\resumeItemListEnd", tex):
        return True
    if re.search(r"\\begin\{itemize\}(\[[^\]]*\])?\s*\\end\{itemize\}", tex):
        return True
    return False


def assert_structurally_valid(tex, label):
    # balanced literal environments
    nb, ne = tex.count(r"\begin{"), tex.count(r"\end{")
    assert nb == ne, f"{label}: unbalanced begin/end ({nb} vs {ne})"
    # balanced resume macro list environments
    assert tex.count(r"\resumeItemListStart") == tex.count(r"\resumeItemListEnd"), \
        f"{label}: unbalanced resumeItemList macros"
    assert tex.count(r"\resumeSubHeadingListStart") == tex.count(r"\resumeSubHeadingListEnd"), \
        f"{label}: unbalanced resumeSubHeadingList macros"
    # per-environment balance for itemize/tabular*/enumerate
    for env in ("itemize", "enumerate", "tabular*", "center", "multicols"):
        b = len(re.findall(r"\\begin\{" + re.escape(env) + r"\}", tex))
        e = len(re.findall(r"\\end\{" + re.escape(env) + r"\}", tex))
        assert b == e, f"{label}: unbalanced {env} ({b} vs {e})"
    # no empty item lists
    assert not has_empty_itemize(tex), f"{label}: empty itemize block present"


def modify_first_bullet(data, marker="ZZUNIQUEMARKER1234"):
    """Replace the first bullet of the first entry that has bullets.
    Returns (old_raw, new_raw)."""
    for sec, ents in data["sections"].items():
        for e in ents:
            if e.get("bullets"):
                old_raw = e["bullets"][0]["raw"]
                new_raw = marker + " rewritten bullet content"
                e["bullets"][0] = {"raw": new_raw, "clean": new_raw}
                return old_raw, new_raw
    raise AssertionError("no bullets found to modify")


# --------------------------------------------------------------------------- #
# 1. parse counts
# --------------------------------------------------------------------------- #
def test_parse_counts_jake():
    data = parse_resume(JAKE)
    c = bullet_counts(data)
    assert set(c) == {"Education", "Experience", "Projects", "Technical Skills"}, c
    assert c["Education"] == [0, 0], c
    assert c["Experience"] == [3, 3, 6], c
    assert c["Projects"] == [4, 4], c
    assert c["Technical Skills"] == [0, 0, 0, 0], c  # 4 skill items
    print("  [ok] jakes_resume.tex parse counts")


def test_field_placement():
    """Fields must land in the right slots regardless of the argument order
    the resume author used. Education and Experience in the Jake template
    use OPPOSITE {org/loc/role/date} vs {role/date/org/loc} orderings."""
    data = parse_resume(JAKE)

    # Experience: {Role}{Date}{Company}{Location}
    _, exp = find_section(data, "Experience")
    e0 = exp[0]
    assert e0["company"] == "Undergraduate Research Assistant", e0   # bold heading = title
    assert "2020" in e0["date"] and "Present" in e0["date"], e0      # date detected
    assert "TX" in e0["location"], e0                                # not swapped into date
    assert re.search(r"\d{4}", e0["location"]) is None, e0           # location has no year

    # Education: {School}{Location}{Degree}{Date} — opposite order
    _, edu = find_section(data, "Education")
    d0 = edu[0]
    assert d0["company"] == "Southwestern University", d0            # bold heading = title
    assert "2018" in d0["date"], d0                                  # date still found
    assert "TX" in d0["location"], d0                                # location still correct
    assert re.search(r"\d{4}", d0["location"]) is None, d0
    print("  [ok] field placement (date/location/title by heuristic)")



def _missing(path, label):
    """data/ resumes are local-only (real PII, never committed). Skip
    their tests gracefully when the files aren't present (e.g. fresh clone)."""
    if os.path.exists(path):
        return False
    print(f"  [skip] {label} not present (local-only fixture)")
    return True

def test_parse_counts_gloria():
    if _missing(GLORIA, 'data/jakes_resume.tex'): return
    data = parse_resume(GLORIA)
    c = bullet_counts(data)
    assert len(data["sections"]) == 9, list(data["sections"])
    assert c["Education"] == [1], c
    assert c["Publications"] == [0, 0, 0, 0], c
    assert c["Research Experience"] == [3, 2], c
    assert c["Industry Experience"] == [3, 3, 4], c            # subheadingS
    _, lead = find_section(data, "Leadership")
    assert [len(e["bullets"]) for e in lead] == [4, 3]
    assert c["Honors and Awards"] == [6], c                    # orphan
    _, hon = find_section(data, "Honors")
    assert hon[0].get("orphan") is True, hon[0]
    assert c["Teaching Experience"] == [2], c
    assert c["Service"] == [1], c                              # subheadingS w/ extra {}
    assert c["Technical Skills"] == [0, 0, 0, 0], c
    # subheadingS mapped title -> company
    _, ind = find_section(data, "Industry")
    assert ind[0]["company"].startswith("Amazon Robotics"), ind[0]
    print("  [ok] data/jakes_resume.tex parse counts")


def test_parse_counts_alternative():
    if _missing(ALT, 'data/alternative.tex'): return
    data = parse_resume(ALT)
    c = bullet_counts(data)
    assert len(data["sections"]) == 6, list(data["sections"])
    assert c["Skills"] == [0] * 9, c
    assert c["Education"] == [2, 3], c
    assert c["Experience"] == [2, 3], c
    _, other = find_section(data, "Other Activities")
    assert len(other) == 6
    assert c["Awards"] == [0, 0, 0], c
    assert c["Languages"] == [0, 0, 0], c
    # cvuniversity: title (company) shows degree, subtitle (role) shows school
    edu = data["sections"]["Education"]
    assert edu[0]["company"].startswith("M.Sc."), edu[0]
    assert "University of Nowhere" in edu[0]["role"], edu[0]
    assert edu[0].get("cv") is True
    # cvexperience keeps org as company
    exp = data["sections"]["Experience"]
    assert exp[0].get("cv") is True
    print("  [ok] data/alternative.tex parse counts")


# --------------------------------------------------------------------------- #
# 2. round-trip: parse -> modify -> render
# --------------------------------------------------------------------------- #
def _roundtrip_check(path, label):
    tex = open(path).read()
    data = parse_resume(path)
    old_raw, new_raw = modify_first_bullet(data)
    out = replace_bullets(tex, data)

    assert new_raw in out, f"{label}: new bullet text not present"
    assert old_raw not in out, f"{label}: old bullet text still present"
    assert preamble_of(out) == preamble_of(tex), f"{label}: preamble changed"
    assert not has_empty_itemize(out), f"{label}: empty itemize created"
    assert_structurally_valid(out, label)
    print(f"  [ok] round-trip {label}")
    return out


def test_roundtrip_all():
    _roundtrip_check(JAKE, "jakes_resume.tex")
    if not _missing(GLORIA, "data/jakes_resume.tex"):
        _roundtrip_check(GLORIA, "data/jakes_resume.tex")
    if not _missing(ALT, "data/alternative.tex"):
        _roundtrip_check(ALT, "data/alternative.tex")


# --------------------------------------------------------------------------- #
# 3. compilation / structural validity
# --------------------------------------------------------------------------- #
def _render_to_file(path, out_name, mutate=True):
    tex = open(path).read()
    data = parse_resume(path)
    if mutate:
        modify_first_bullet(data)
    out = replace_bullets(tex, data)
    out_path = os.path.join(SCRATCH, out_name)
    with open(out_path, "w") as f:
        f.write(out)
    return out, out_path


def test_compile_jake():
    """Canonical article resume must compile to a real PDF."""
    out, out_path = _render_to_file(JAKE, "test_jake_out.tex")
    assert_structurally_valid(out, "jakes_resume.tex")
    ok = compile_pdf(out_path, SCRATCH)
    pdf = out_path.replace(".tex", ".pdf")
    assert ok and os.path.exists(pdf), "jakes_resume.tex failed to compile"
    print("  [ok] compile jakes_resume.tex -> PDF")


def test_compile_gloria():
    if _missing(GLORIA, 'data/jakes_resume.tex'): return
    """
    Gloria variant: the SOURCE itself does not compile with pdflatex because the
    'Honors and Awards' section nests an item list directly inside a subheading
    list with no outer \\item (a pre-existing source issue, identical with or
    without our rewrite). So we only require structural validity of the rewrite.
    """
    out, out_path = _render_to_file(GLORIA, "test_gloria_out.tex")
    assert_structurally_valid(out, "data/jakes_resume.tex")

    # Sanity: the failure is in the source, not introduced by us -- the original
    # unmodified file fails at the same place.
    orig_path = os.path.join(SCRATCH, "test_gloria_orig.tex")
    with open(orig_path, "w") as f:
        f.write(open(GLORIA).read())
    src_ok = compile_pdf(orig_path, SCRATCH)
    rew_ok = compile_pdf(out_path, SCRATCH)
    if src_ok:
        # environment can handle it -> our rewrite must also compile
        assert rew_ok and os.path.exists(out_path.replace(".tex", ".pdf")), \
            "data/jakes_resume.tex rewrite failed though source compiled"
        print("  [ok] compile data/jakes_resume.tex -> PDF")
    else:
        assert rew_ok == src_ok, \
            "our rewrite changed compilability of an already-broken source"
        print("  [ok] data/jakes_resume.tex structurally valid "
              "(source does not compile in this environment; not introduced by us)")


def test_alternative_structural():
    if _missing(ALT, 'data/alternative.tex'): return
    """maltacv.cls is not installed locally -> assert structural validity only."""
    out, _ = _render_to_file(ALT, "test_alt_out.tex")
    assert_structurally_valid(out, "data/alternative.tex")
    print("  [ok] data/alternative.tex structurally valid (maltacv.cls not installed)")


# --------------------------------------------------------------------------- #
# 4. frontend-payload shape: empty skill entries + newly added bullet
#    Reproduces the reported "add bullet then pdflatex fails" bug.
# --------------------------------------------------------------------------- #
def test_frontend_payload_compiles():
    import json
    tex = open(JAKE).read()
    # Simulate JSON round-trip through the frontend.
    data = json.loads(json.dumps(parse_resume(JAKE)))

    # sanity: payload actually contains empty-bullet skill entries and {raw,clean}
    skills = data["sections"]["Technical Skills"]
    assert skills and all(s["bullets"] == [] for s in skills), "expected empty skill entries"
    exp = data["sections"]["Experience"]
    assert all(isinstance(b, dict) and "raw" in b and "clean" in b
               for b in exp[0]["bullets"]), "bullets must be {raw,clean} dicts"

    # user adds a brand-new bullet to the first experience entry
    exp[0]["bullets"].append({"raw": "New bullet", "clean": "New bullet"})

    out = replace_bullets(tex, data)
    assert "New bullet" in out
    assert not has_empty_itemize(out), "empty itemize created from skill entries"
    assert_structurally_valid(out, "frontend-payload")

    out_path = os.path.join(SCRATCH, "test_frontend_out.tex")
    with open(out_path, "w") as f:
        f.write(out)
    ok = compile_pdf(out_path, SCRATCH)
    assert ok and os.path.exists(out_path.replace(".tex", ".pdf")), \
        "frontend payload (empty skills + added bullet) failed to compile"
    print("  [ok] frontend payload compiles (add-bullet bug fixed)")


def test_torture_parse_and_roundtrip():
    """torture.tex: every supported construct plus deliberate nastiness."""
    data = parse_resume(TORTURE)
    import json as _json
    blob = _json.dumps(data)

    # Commented-out ghost section must not leak
    assert "Ghost Corp" not in blob and "never appear" not in blob, \
        "commented-out section leaked into parse"

    # Section and entry expectations
    sec, es = find_section(data, "R&D Experience")
    assert len(es) == 3, f"expected 3 R&D entries, got {len(es)}"
    # Org appears as the bold heading (company) or the italic line (role)
    # depending on the author's argument order — either is visually correct.
    assert all("Ampersand & Sons" in (e.get("company", "") + e.get("role", "")) for e in es)
    assert [len(e["bullets"]) for e in es] == [3, 2, 1]

    _, proj = find_section(data, "Projects")
    assert proj[0]["title"].startswith("Deep{Brace} Project"), \
        f"nested-brace title mangled: {proj[0]['title']!r}"

    _, honors = find_section(data, "Honors")
    assert honors[0].get("orphan") and len(honors[0]["bullets"]) == 2

    _, comm = find_section(data, "Community Involvement")
    assert len(comm) == 2 and comm[0]["role"].startswith("Founding Member")

    _, skills = find_section(data, "Technical Skills")
    assert skills[0]["item"].startswith("Languages:"), \
        f"skill item has stray braces: {skills[0]['item']!r}"

    # Round-trip: unique marker per entry, each must land exactly once,
    # in document order, with duplicate companies resolved correctly.
    tex = open(TORTURE).read()
    markers = []
    i = 0
    for _s, ents in data["sections"].items():
        for e in ents:
            if e.get("bullets"):
                m = f"TORTMARK-{i:02d}"
                e["bullets"][0] = {"raw": f"{m} replaced", "clean": f"{m} replaced"}
                markers.append(m)
                i += 1
    out = replace_bullets(tex, data)
    for m in markers:
        assert out.count(m) == 1, f"{m} appears {out.count(m)}x"
    pos = [out.find(m) for m in markers]
    assert pos == sorted(pos), "marker order does not match document order"
    assert preamble_of(out) == preamble_of(tex), "preamble modified"

    out_path = os.path.join(SCRATCH, "test_torture_out.tex")
    open(out_path, "w").write(out)
    ok = compile_pdf(out_path, SCRATCH)
    assert ok, "torture round-trip failed to compile"
    print("  [ok] torture.tex parse + round-trip + compile")


def test_hostile_user_edits_compile():
    """Bullets edited with unescaped LaTeX specials must still compile."""
    hostile = [
        "Grew revenue by 45% year over year",
        "Led R&D team of 12 engineers",
        "Saved $50,000 in annual costs",
        "Managed budget of $1M { with unbalanced brace",
        "Wrote C# and F# tooling with snake_case_names",
        "kept intentional math $O(n^2)$ and \\textbf{bold} intact",
    ]
    tex = open(TORTURE).read()
    for h in hostile:
        data = parse_resume(TORTURE)
        first = next(e for ents in data["sections"].values() for e in ents if e.get("bullets"))
        first["bullets"][0] = {"raw": h, "clean": h}
        out = replace_bullets(tex, data)
        out_path = os.path.join(SCRATCH, "test_hostile.tex")
        open(out_path, "w").write(out)
        assert compile_pdf(out_path, SCRATCH), f"hostile edit failed to compile: {h!r}"
    # intentional LaTeX must survive escaping
    assert "$O(n^2)$" in out and "\\textbf{bold}" in out, "intentional LaTeX was escaped"
    print("  [ok] hostile user edits compile (specials auto-escaped)")


# --------------------------------------------------------------------------- #
def main():
    os.makedirs(SCRATCH, exist_ok=True)
    tests = [
        test_parse_counts_jake,
        test_field_placement,
        test_parse_counts_gloria,
        test_parse_counts_alternative,
        test_roundtrip_all,
        test_compile_jake,
        test_compile_gloria,
        test_alternative_structural,
        test_frontend_payload_compiles,
        test_torture_parse_and_roundtrip,
        test_hostile_user_edits_compile,
    ]
    failures = 0
    for t in tests:
        try:
            t()
        except AssertionError as ex:
            failures += 1
            print(f"  [FAIL] {t.__name__}: {ex}")
        except Exception as ex:  # noqa
            failures += 1
            print(f"  [ERROR] {t.__name__}: {ex!r}")
    print()
    if failures:
        print(f"FAILED: {failures} test(s) failed")
        sys.exit(1)
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
