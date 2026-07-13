# Deploying BulletRevisor

## Why not Vercel / Netlify / HF Spaces

BulletRevisor is **not** a static site or a lightweight serverless function:

1. **It runs `pdflatex`** — a full TeX Live install (hundreds of MB of system
   binaries). Serverless platforms can't run arbitrary system binaries.
2. **It loads a machine-learning model** — `sentence-transformers` pulls in
   PyTorch (~340 MB on disk). Vercel's function bundle limit is 250 MB.
3. **It needs a real (if ephemeral) filesystem** for compile sessions.

So it needs a **Docker container host**. Hugging Face Spaces would work
technically, but Docker Spaces now require a PRO subscription ($9/mo).

Good news: user persistence lives in the **browser** (localStorage) and the
server stores resumes only transiently (sessions swept after ~1 hour), so
**no persistent disk is required** — and the app's measured memory footprint
is only **~220 MB** with the model warm. That fits Render's free tier.

---

## Recommended: Render free tier ($0, no credit card)

Tradeoff: free services sleep after ~15 min without traffic and take ~30–60 s
to wake. Fine for personal use; for a live demo, open the URL a minute early
(or upgrade to Starter, $7/mo, to stay always-warm — one line in render.yaml).

This repo already contains the blueprint (`render.yaml`, `plan: free`).

1. Push the repo to GitHub (already done: `jmei0814/bullet_revisor`).
2. Go to <https://dashboard.render.com> → sign in **with GitHub**.
3. Click **New +** → **Blueprint**.
4. Select the `bullet_revisor` repo. Render reads `render.yaml`.
5. Click **Apply**. First build takes ~10–15 min (TeX Live + model bake).
6. Your public URL: `https://bulletrevisor.onrender.com` (or similar).

Redeploys are automatic on every `git push origin main`.

---

## Alternatives

**Google Cloud Run** — genuinely serverless *containers*, generous free tier
(2M requests/mo), scale-to-zero. Needs a Google Cloud account with a credit
card on file (stays $0 at personal usage levels):
```bash
gcloud run deploy bulletrevisor --source . --region us-central1 \
  --memory 1Gi --allow-unauthenticated
```

**Oracle Cloud Always Free** — a free-forever ARM VM (up to 4 cores / 24 GB
RAM). Most powerful $0 option, most setup: create the VM, install Docker,
`docker run`, add Caddy for HTTPS, open port 443 in the security list.

**Fly.io / Railway** — ~$3–5/mo, both deploy the Dockerfile directly.

**Any $4–6/mo VPS** (Hetzner, DigitalOcean):
```bash
docker build -t bulletrevisor . && docker run -d -p 80:8000 --restart=always bulletrevisor
```

---

## Verify a deployment

Run one resume end to end on the public URL: upload → edit → lock a bullet →
paste a job description → match → generate PDF → download. Then reload the
page and confirm the "Pick up where you left off" card restores your edits
(it reads your browser's localStorage, so it survives redeploys).

## Local Docker test

```bash
docker build -t bulletrevisor .
docker run -p 8000:8000 bulletrevisor
# open http://localhost:8000
```
