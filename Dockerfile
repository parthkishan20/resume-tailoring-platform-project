# Dockerfile

# ── Stage 1: Build Next.js static export ────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /build/frontend

# Dependency layer first. Rebuilt only when the manifests change.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --quiet

# Then the build inputs, named individually. Copying `frontend/` wholesale
# would drop the host's darwin `node_modules` on top of the linux tree just
# installed above (PLAN.md D-35). If you add a new top-level build input
# (a `public/` directory, another config file), add it here.
COPY frontend/next.config.js frontend/tsconfig.json frontend/postcss.config.js frontend/tailwind.config.ts ./
COPY frontend/src ./src

RUN npm run build


# ── Stage 2: Python runtime ──────────────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# PATH: the virtualenv `uv sync` builds below, so uvicorn and rendercv are
# invoked directly rather than through `uv run`. Required by `USER app` at the
# end of this file: `uv run` re-syncs the environment on every start, which
# needs write access to a root-owned .venv and to uv's cache.
#
# HOME: set explicitly because Docker does not read the home directory out of
# /etc/passwd for `USER`, and fontconfig — which Typst resolves fonts through —
# is noisy on stderr without a writable one. That stderr ends up in a
# RenderError message.
ENV PATH=/app/backend/.venv/bin:$PATH \
    HOME=/home/app

# tini (D-51): a real init process. `docker stop` sends SIGTERM to PID 1;
# uvicorn installs its own SIGTERM handler and would eventually get there
# directly, but as PID 1 it inherits none of the kernel's default signal
# dispositions and reaps none of its own orphans -- a killed `rendercv`/Typst
# child (D-50's subprocess) becomes a zombie only PID 1 can reap. tini does
# both: forwards signals to the whole process group and reaps zombies. It is
# the one apt package this image installs; everything else stays wheel- or
# digest-pinned copies, but tini has no equivalent static-binary release
# artifact worth trusting over Debian's own package.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tini \
 && rm -rf /var/lib/apt/lists/*

# D-50. LLM-authored YAML is handed to a document renderer: rendering/runner.py
# writes model output to a YAML file and spawns `rendercv render` on it, and
# RenderCV/Typst resolves paths declared inside that document. Typst's own
# sandbox is the only barrier between model-controlled input and this
# filesystem, which has the SQLite volume mounted at /app/db. As root that is
# the highest-value exploit chain in the application; as uid 10001 with
# read-only application code it is a much smaller one.
#
# /app/db and /app/pdfs are created here, owned by the runtime user, rather
# than left to the lifespan: Docker copies a directory's ownership into a fresh
# named volume mounted over it, so creating them root-owned would produce
# volumes the application cannot write to.
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid 10001 --create-home --home-dir /home/app app \
 && install -d -o app -g app -m 0755 /app/db /app/pdfs

# uv, pinned by version and digest. A floating tag here would silently change
# the tool that resolves the entire dependency tree.
COPY --from=ghcr.io/astral-sh/uv:0.11.11@sha256:798712e57f879c5393777cbda2bb309b29fcdeb0532129d4b1c3125c5385975a /uv /usr/local/bin/uv

WORKDIR /app/backend

# Dependency layer: manifests only, so editing backend source does not force a
# re-resolve of the ~80-package tree. `--no-install-project` is what makes
# this cacheable: `resumetailor-backend` is now a real (editable) distribution
# in uv.lock rather than a `virtual` one (D-65), so a plain `uv sync` here
# would need `src/`, which has not been copied in yet, and would fail. This
# installs every dependency and nothing of the project itself; the second
# `uv sync` below, after `src/` lands, installs the project in one cheap step
# on top of an already-populated venv.
# rendercv[full] ships Typst as a pip wheel, so this dependency layer itself
# stays apt-get-free; the one apt package in this image is tini, above.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Application source, named individually so the host's conda/darwin
# `backend/.venv` cannot ride along (PLAN.md D-36).
#
# `migrations/` is not optional: `resumetailor.db.migrate` reads it from
# `BACKEND_ROOT / "migrations"` at every boot, and an empty (missing)
# directory is not an error there — `discover()` just returns no migrations,
# so the lifespan logs "database schema ready" over a database with no
# tables at all and then fails one line later in `seed_defaults`. This was
# missing before task 3.4: no prior task had a Docker daemon to actually run
# the built image and catch it (D-72).
COPY backend/src ./src
COPY backend/migrations ./migrations
COPY backend/rendercv_config ./rendercv_config
RUN uv sync --frozen --no-dev

# Frontend static export, served by FastAPI at / (the static mount at the end of
# `create_app`, which resolves `STATIC_DIR` to /app/backend/static).
COPY --from=frontend-builder /build/frontend/out ./static/

# /app/db and /app/pdfs already exist, owned by `app`, from the RUN above.
# They are volume mount points in docker-compose.yml; the lifespan's mkdir is
# now a no-op rather than the thing that creates them.

# Everything above this line runs as root: installing packages, writing the
# virtualenv, copying application code. Everything below, including every
# `rendercv` child process, runs as uid 10001 with no write access to any of
# it. The only writable paths are the two volumes, /tmp (a tmpfs, see
# docker-compose.yml) and $HOME.
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# tini is PID 1 (D-51); `--` stops it from parsing CMD's own arguments as its
# own. `docker-compose.yml`'s `dev` profile overrides `command:` alone to add
# `--reload`, so it still starts under tini rather than becoming PID 1 itself.
ENTRYPOINT ["tini", "--"]

# `--host 0.0.0.0` is correct and must stay: the Docker bridge cannot reach a
# process bound to the container's loopback. What restricts access is the
# host-side publish in docker-compose.yml, `"127.0.0.1:8000:8000"`. See
# docs/adr/0004-no-auth-loopback-only.md.
CMD ["uvicorn", "resumetailor.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1"]
