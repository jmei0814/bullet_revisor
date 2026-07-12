# BulletRevisor — Flask + LaTeX + sentence-transformers
# A full container is required: the app shells out to pdflatex and loads an
# ML model, neither of which fit serverless platforms (Vercel/Netlify).
FROM python:3.11-slim

# ---- system deps: a LaTeX toolchain that can compile real resumes ----
# texlive-latex-extra pulls in titlesec, enumitem, etc.; fontawesome5 and
# the recommended fonts cover the common resume templates.
RUN apt-get update && apt-get install -y --no-install-recommends \
      texlive-latex-base \
      texlive-latex-recommended \
      texlive-latex-extra \
      texlive-fonts-recommended \
      texlive-fonts-extra \
      texlive-xetex \
      lmodern \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---- python deps (cached layer) ----
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- pre-download the sentence-transformers model into the image ----
# so the first request isn't a ~80 MB cold-start download.
RUN python -c "from sentence_transformers import SentenceTransformer; \
SentenceTransformer('all-MiniLM-L6-v2')"

# ---- app code ----
COPY . .

# Persist user data outside the app tree (mount a volume here in production).
ENV DATA_DIR=/data
ENV FLASK_DEBUG=0
RUN mkdir -p /data

EXPOSE 8000

# gunicorn serves web/app.py's `app`. One worker keeps the ML model in a
# single process; bump workers only with more RAM (each loads the model).
# Long timeout because pdflatex compiles can take a few seconds.
CMD ["sh", "-c", "gunicorn --chdir web app:app --bind 0.0.0.0:${PORT:-8000} --workers 1 --timeout 120"]
