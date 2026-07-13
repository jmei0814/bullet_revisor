from flask import Flask, render_template, request, jsonify, send_file
import json
import os
import sys
import threading
import uuid
import shutil
import re
from datetime import datetime, timezone
from pathlib import Path

# Make parent directory importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from parsers.latex_parser import parse_resume
from parsers.renderer import replace_bullets, compile_pdf
from scripts.scorer import score_all_bullets

app = Flask(__name__)
# Resume .tex files are tiny; cap uploads to reject oversized/DoS payloads.
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # 2 MB

# Working data lives under DATA_DIR (default: web/). Sessions are transient
# by design: resumes are persisted in the USER'S BROWSER (localStorage), not
# on the server, so DATA_DIR needs no durable volume — /tmp works fine.
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent))
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# How long a compile session (uploaded tex + generated PDF) may live on disk.
SESSION_TTL_SECONDS = 60 * 60  # 1 hour

_SESSION_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                         r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _valid_session(sid):
    """A session id must be a well-formed uuid4 string (guards path traversal)."""
    return bool(sid) and bool(_SESSION_RE.match(sid))


def _sweep_stale_sessions():
    """Delete session dirs older than SESSION_TTL_SECONDS. Called
    opportunistically on upload so no resume outlives an editing session."""
    cutoff = datetime.now(timezone.utc).timestamp() - SESSION_TTL_SECONDS
    try:
        for d in os.scandir(UPLOAD_DIR):
            if d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d.path, ignore_errors=True)
    except OSError:
        pass  # sweeping is best-effort


@app.errorhandler(413)
def _too_large(e):
    return jsonify({"error": "That file is too large. Resume .tex files should be under 2 MB."}), 413


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if not file.filename or not file.filename.endswith(".tex"):
        return jsonify({"error": "Please upload a .tex LaTeX file"}), 400

    _sweep_stale_sessions()

    session_id = str(uuid.uuid4())
    session_dir = UPLOAD_DIR / session_id
    session_dir.mkdir()

    tex_path = session_dir / "resume.tex"
    file.save(str(tex_path))

    # Reject non-text uploads (binary renamed .tex) before parsing.
    try:
        tex_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, ValueError):
        shutil.rmtree(session_dir, ignore_errors=True)
        return jsonify({"error": "That file isn't readable as text. Please upload a LaTeX .tex source file."}), 400

    try:
        data = parse_resume(str(tex_path))

        # A resume with no editable bullets means we couldn't recognise its
        # structure — tell the user instead of showing a blank editor.
        total_bullets = sum(
            len(e.get("bullets", []))
            for entries in data["sections"].values()
            for e in entries
        )
        if total_bullets == 0:
            shutil.rmtree(session_dir, ignore_errors=True)
            return jsonify({"error": (
                "Couldn't find any bullet points in this resume. BulletRevisor "
                "supports standard LaTeX resume templates (e.g. the Jake "
                "resumeItem template). Check that your file uses \\resumeItem "
                "or itemize bullets."
            )}), 422

        # Ensure every entry with bullets has a max_bullets default
        for entries in data["sections"].values():
            for entry in entries:
                if "bullets" in entry and "max_bullets" not in entry:
                    entry["max_bullets"] = len(entry["bullets"])

        return jsonify({"session_id": session_id, "data": data})
    except Exception as e:
        app.logger.exception("parse_resume failed")
        shutil.rmtree(session_dir, ignore_errors=True)
        return jsonify({"error": "We couldn't parse that resume. Please check it's a valid LaTeX .tex file."}), 500


@app.route("/api/score", methods=["POST"])
def score():
    body = request.get_json()
    job_description = (body.get("job_description") or "").strip()
    resume_data = body.get("resume_data")

    if not job_description:
        return jsonify({"error": "Job description is required"}), 400
    if not resume_data:
        return jsonify({"error": "Resume data is required"}), 400

    try:
        result = score_all_bullets(resume_data, job_description)
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": f"Scoring failed: {e}"}), 500


# ---- async compile -------------------------------------------------------
# pdflatex can take 30-60s on fractional-CPU hosts. Blocking the HTTP request
# that long trips proxy timeouts (empty responses / HTML 502 pages) and, with
# a single worker, wedges every other request behind it. So /api/compile
# kicks off a background thread and returns immediately; the client polls
# /api/compile/status/<sid>. Status lives in a file in the session dir.

def _status_path(session_dir):
    return session_dir / "compile_status.json"


def _write_status(session_dir, status, error=None):
    payload = {"status": status}
    if error:
        payload["error"] = error
    _status_path(session_dir).write_text(json.dumps(payload))


def _run_compile(session_dir, resume_data):
    try:
        tex_content = (session_dir / "resume.tex").read_text()
        updated_tex = replace_bullets(tex_content, resume_data)

        updated_path = session_dir / "resume_updated.tex"
        updated_path.write_text(updated_tex)

        output_dir = session_dir / "output"
        output_dir.mkdir(exist_ok=True)

        if compile_pdf(str(updated_path), str(output_dir)):
            _write_status(session_dir, "done")
        else:
            _write_status(session_dir, "error",
                          "PDF compilation failed. Your resume's LaTeX may use "
                          "packages the server doesn't have.")
    except Exception as e:
        app.logger.exception("compile failed")
        _write_status(session_dir, "error", f"Compilation crashed: {e}")


@app.route("/api/compile", methods=["POST"])
def compile_resume():
    body = request.get_json()
    session_id = body.get("session_id")
    resume_data = body.get("resume_data")

    if not session_id or not resume_data:
        return jsonify({"error": "Missing session_id or resume_data"}), 400
    if not _valid_session(session_id):
        return jsonify({"error": "Invalid session id"}), 400

    session_dir = UPLOAD_DIR / session_id
    tex_path = session_dir / "resume.tex"

    if not tex_path.exists():
        return jsonify({"error": "Session not found — please re-upload your resume"}), 404

    # Don't stack a second compile on a session that's already compiling.
    sp = _status_path(session_dir)
    if sp.exists():
        try:
            if json.loads(sp.read_text()).get("status") == "running":
                return jsonify({"started": True})
        except Exception:
            pass

    _write_status(session_dir, "running")
    threading.Thread(target=_run_compile, args=(session_dir, resume_data), daemon=True).start()
    return jsonify({"started": True})


@app.route("/api/compile/status/<session_id>")
def compile_status(session_id):
    if not _valid_session(session_id):
        return jsonify({"error": "Invalid session id"}), 400
    sp = _status_path(UPLOAD_DIR / session_id)
    if not sp.exists():
        return jsonify({"status": "none"})
    try:
        return jsonify(json.loads(sp.read_text()))
    except Exception:
        return jsonify({"status": "none"})


@app.route("/api/preview/<session_id>")
def preview(session_id):
    if not _valid_session(session_id):
        return jsonify({"error": "Invalid session id"}), 400
    pdf_path = UPLOAD_DIR / session_id / "output" / "resume_updated.pdf"
    if not pdf_path.exists():
        return jsonify({"error": "PDF not found"}), 404
    return send_file(str(pdf_path), mimetype="application/pdf")


@app.route("/api/download/<session_id>")
def download(session_id):
    if not _valid_session(session_id):
        return jsonify({"error": "Invalid session id"}), 400
    pdf_path = UPLOAD_DIR / session_id / "output" / "resume_updated.pdf"
    if not pdf_path.exists():
        return jsonify({"error": "PDF not found"}), 404

    # Optional custom filename from the client; sanitize to a safe basename.
    name = (request.args.get("name") or "").strip()
    name = Path(name).name  # strip any directory components
    name = re.sub(r'[^\w .()\[\]-]', "", name).strip(". ")
    if not name:
        name = "tailored_resume.pdf"
    if not name.lower().endswith(".pdf"):
        name += ".pdf"

    return send_file(str(pdf_path), as_attachment=True, download_name=name)


if __name__ == "__main__":
    # In production (Docker/Render) a WSGI server runs `app`; PORT is injected
    # by the platform. Locally this falls back to 5050 with debug on.
    port = int(os.environ.get("PORT", 5050))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
