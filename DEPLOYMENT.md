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
3. **It needs a real (if ephemeral) filesystem** for compile sessions.

The app needs a **Docker container host**. Since user persistence lives in the
browser (localStorage) and the server stores resumes only transiently (sessions
are swept after ~1 hour), **no persistent disk is required** — which makes the
free tier of Hugging Face Spaces a perfect fit.

---

## Recommended: Hugging Face Spaces (free)

Free Docker runtime with 2 vCPU / 16 GB RAM — plenty for PyTorch + TeX Live.
Tradeoff: free Spaces sleep after ~48 h without traffic and take ~30–60 s to
wake. (This repo is already Space-ready: the `README.md` front-matter declares
`sdk: docker` / `app_port: 8000`, and the Dockerfile handles HF's non-root
runtime user.)

1. Create a free account at <https://huggingface.co> (Sign Up).
2. Create an access token with **write** scope:
   Settings → Access Tokens → New token.
3. Create the Space: <https://huggingface.co/new-space> →
   - Owner: your username, Space name: `bulletrevisor`
   - License: MIT (or your choice)
   - SDK: **Docker** → Blank template
   - Visibility: **Public**
4. Push this repo to the Space:
   ```bash
   cd /Users/jmei0814/Documents/Resume_Builder
   git remote add hf https://huggingface.co/spaces/<your-hf-username>/bulletrevisor
   git push hf main
   # username: your HF username, password: the access token
   ```
5. Watch the build on the Space page (~10–15 min the first time — it installs
   TeX Live and bakes the ML model into the image).
6. Your public URL: `https://<your-hf-username>-bulletrevisor.hf.space`

Redeploys: just `git push hf main` again. Push to GitHub (`git push origin
main`) as usual — the two remotes are independent.

---

## Paid upgrade path (no code changes)

If the demo needs to be always-warm or on a custom domain:

**Render (~$7/mo)** — this repo includes `render.yaml`:
dashboard.render.com → New + → Blueprint → pick the GitHub repo → Apply.
Supports custom domains + no sleep on paid instances.

**Fly.io (~$3–5/mo)**:
```bash
fly launch --dockerfile Dockerfile
fly deploy
```

**Any $4–6/mo VPS** (Hetzner, DigitalOcean):
```bash
docker build -t bulletrevisor . && docker run -d -p 80:8000 --restart=always bulletrevisor
```
(Add Caddy or nginx for HTTPS.)

---

## Verify a deployment

Run one resume end to end on the public URL: upload → edit → lock a bullet →
paste a job description → match → generate PDF → download. Then reload the
page and confirm the "Pick up where you left off" card restores your edits
(it's reading your browser's localStorage, so it works even right after a
redeploy).

## Local Docker test

```bash
docker build -t bulletrevisor .
docker run -p 8000:8000 bulletrevisor
# open http://localhost:8000
```
