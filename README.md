# BulletRevisor

Tailor your LaTeX resume to any job posting in about a minute.

Upload a `.tex` resume, edit and lock bullet points, paste a job description,
and BulletRevisor ranks every bullet by semantic relevance (sentence-transformer
embeddings), then recompiles a tailored PDF with pdflatex.

**Privacy:** your resume is never stored on the server. Persistence ("pick up
where you left off") lives entirely in your browser's localStorage; server-side
compile sessions are wiped within the hour.

## Supported resume templates

- The classic [Jake's Resume](https://github.com/jakegut/resume) template
  (`\resumeItem` / `\resumeSubheading`), including common variants
  (`\resumeSubheadingS`, orphan item lists)
- maltacv / AltaCV-style (`\cvsection`, `\cvexperience`, `\cvuniversity`)
- Plain-LaTeX resumes (`\section*` + `\textbf` headings + `itemize` bullets)

## Run locally

```bash
python3 -m venv my_env
source my_env/bin/activate
pip install -r requirements.txt
python web/app.py            # http://localhost:5050
```

Requires a LaTeX installation (MacTeX/BasicTeX/TeX Live) with common packages.

## Run with Docker

```bash
docker build -t bulletrevisor .
docker run -p 8000:8000 bulletrevisor
```

## Tests

```bash
my_env/bin/python tests/test_parser.py
```

## Deploy

See [DEPLOYMENT.md](DEPLOYMENT.md) — free on Render (blueprint included), or
Cloud Run/Fly/VPS via the same Dockerfile.
