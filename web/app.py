from flask import Flask, render_template, request, jsonify, send_file
import sys
import uuid
import shutil
from pathlib import Path

# Make parent directory importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from parsers.latex_parser import parse_resume
from parsers.renderer import replace_bullets, compile_pdf
from scripts.scorer import score_all_bullets

app = Flask(__name__)

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if not file.filename.endswith(".tex"):
        return jsonify({"error": "Please upload a .tex LaTeX file"}), 400

    session_id = str(uuid.uuid4())
    session_dir = UPLOAD_DIR / session_id
    session_dir.mkdir()

    tex_path = session_dir / "resume.tex"
    file.save(str(tex_path))

    try:
        data = parse_resume(str(tex_path))
        # Ensure every entry with bullets has a max_bullets default
        for entries in data["sections"].values():
            for entry in entries:
                if "bullets" in entry and "max_bullets" not in entry:
                    entry["max_bullets"] = len(entry["bullets"])
        return jsonify({"session_id": session_id, "data": data})
    except Exception as e:
        shutil.rmtree(session_dir, ignore_errors=True)
        return jsonify({"error": f"Failed to parse resume: {e}"}), 500


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


@app.route("/api/compile", methods=["POST"])
def compile_resume():
    body = request.get_json()
    session_id = body.get("session_id")
    resume_data = body.get("resume_data")

    if not session_id or not resume_data:
        return jsonify({"error": "Missing session_id or resume_data"}), 400

    session_dir = UPLOAD_DIR / session_id
    tex_path = session_dir / "resume.tex"
    output_dir = session_dir / "output"
    output_dir.mkdir(exist_ok=True)

    if not tex_path.exists():
        return jsonify({"error": "Session not found — please re-upload your resume"}), 404

    try:
        tex_content = tex_path.read_text()
        updated_tex = replace_bullets(tex_content, resume_data)

        updated_path = session_dir / "resume_updated.tex"
        updated_path.write_text(updated_tex)

        success = compile_pdf(str(updated_path), str(output_dir))
        if success:
            return jsonify({"success": True})
        return jsonify({"error": "pdflatex compilation failed — is pdflatex installed?"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/preview/<session_id>")
def preview(session_id):
    pdf_path = UPLOAD_DIR / session_id / "output" / "resume_updated.pdf"
    if not pdf_path.exists():
        return jsonify({"error": "PDF not found"}), 404
    return send_file(str(pdf_path), mimetype="application/pdf")


@app.route("/api/download/<session_id>")
def download(session_id):
    pdf_path = UPLOAD_DIR / session_id / "output" / "resume_updated.pdf"
    if not pdf_path.exists():
        return jsonify({"error": "PDF not found"}), 404
    return send_file(str(pdf_path), as_attachment=True, download_name="tailored_resume.pdf")


if __name__ == "__main__":
    app.run(debug=True, port=5050)
