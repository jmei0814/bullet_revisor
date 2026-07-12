# Deploying BulletRevisor

## Why not Vercel / Netlify

BulletRevisor is **not** a static site or a lightweight serverless function, so
Vercel and Netlify cannot host it. Three hard blockers:

1. **It runs `pdflatex`.** Compiling a resume shells out to a full TeX Live
   installation (hundreds of MB of system binaries). Serverless platforms don't
   let you install or run arbitrary system binaries.
2. **It loads a machine-learning model.** `sentence-transformers` pulls in
   PyTorch (~340 MB). Vercel's serverless function bundle limit is 250 MB
   unzipped — PyTorch alone exceeds it.
3. **It writes to disk.** Uploaded resumes, per-user sessions, and compiled PDFs
   are written to the filesystem. Serverless filesystems are read-only except a
   small ephemeral `/tmp` that vanishes between requests.

The app needs a **container with a real filesystem** — i.e. a platform that runs
Docker. The instructions below use **Render** (free-ish tier, easiest), with
**Railway** and **Fly.io** as alternatives. All three deploy the same
`Dockerfile` in this repo.

---

## Step 1 — Push to GitHub

If the repo isn't on GitHub yet:

```bash
cd /Users/jmei0814/Documents/Resume_Builder

# create the repo on GitHub first (github.com/new), then:
git remote add origin https://github.com/<your-username>/bullet_revisor.git
git add .
git commit -m "BulletRevisor: parsing, scoring, persistence, deploy config"
git branch -M main
git push -u origin main
```

If `origin` already exists, just `git add . && git commit && git push`.

> The repo's `.gitignore` already excludes `my_env/`, `web/uploads/`,
> `web/user_data/`, and build artifacts, so none of that gets pushed.

---

## Step 2 — Deploy on Render (recommended)

Render reads the included `render.yaml` blueprint (Docker service + 1 GB
persistent disk mounted at `/data`).

1. Go to <https://dashboard.render.com> and sign in with GitHub.
2. Click **New +** → **Blueprint**.
3. Select your `bullet_revisor` repo. Render detects `render.yaml`.
4. Click **Apply**. The first build takes ~10–15 min (it installs TeX Live and
   pre-downloads the ML model into the image).
5. When it goes live you'll get a URL like `https://bulletrevisor.onrender.com`.

**Notes**
- The `starter` plan (512 MB RAM) is required — the free 256 MB plan is too
  small for PyTorch + LaTeX. Change the `plan:` line in `render.yaml` if needed.
- Cold starts: on the free/hobby tiers Render spins the service down when idle;
  the first request after a sleep takes ~30 s to boot. Keep it on a paid
  instance for the demo, or ping it right before showing it off.

### Manual setup (without the blueprint)

New + → **Web Service** → connect repo → **Runtime: Docker** → add a **Disk**
(mount path `/data`, 1 GB) → add env vars `DATA_DIR=/data`, `FLASK_DEBUG=0` →
Create.

---

## Alternative platforms (same Dockerfile)

**Railway** — <https://railway.app> → New Project → Deploy from GitHub repo. It
auto-detects the Dockerfile. Add a Volume mounted at `/data` and set
`DATA_DIR=/data` in Variables.

**Fly.io** — with the CLI:

```bash
fly launch --dockerfile Dockerfile   # answer prompts, don't deploy yet
fly volumes create data --size 1
# add to fly.toml:  [mounts]  source="data"  destination="/data"
fly secrets set DATA_DIR=/data FLASK_DEBUG=0
fly deploy
```

---

## Step 3 — Verify

Open the deployed URL and run one resume end to end: upload → edit → paste a job
description → match → generate PDF → download. If the PDF step fails, check the
platform's build logs to confirm `texlive-latex-extra` installed.

---

## Local Docker test (optional, before deploying)

```bash
docker build -t bulletrevisor .
docker run -p 8000:8000 -e PORT=8000 bulletrevisor
# open http://localhost:8000
```

## Running locally without Docker

```bash
python3 -m venv my_env
source my_env/bin/activate
pip install -r requirements.txt
python web/app.py            # http://localhost:5050
```

This needs a local LaTeX install (e.g. MacTeX/BasicTeX on macOS) with the
`fontawesome5` package available for templates that use it.
