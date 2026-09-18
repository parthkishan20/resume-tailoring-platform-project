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

# PYTHONPATH: src-layout. `resumetailor-backend` is a virtual project in
# uv.lock, so uv installs the dependency tree but not this package, and `src/`
# has to be on the path for `resumetailor.main` to import. Mirrors `pythonpath`
# in [tool.pytest.ini_options].
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/backend/src

# uv, pinned by version and digest. A floating tag here would silently change
# the tool that resolves the entire dependency tree.
COPY --from=ghcr.io/astral-sh/uv:0.11.11@sha256:798712e57f879c5393777cbda2bb309b29fcdeb0532129d4b1c3125c5385975a /uv /usr/local/bin/uv

WORKDIR /app/backend

# Dependency layer: manifests only, so editing backend source does not force a
# re-resolve of the ~80-package tree. `resumetailor-backend` is a virtual
# project in uv.lock (`source = { virtual = "." }`), so uv sync needs no source.
# rendercv[full] ships Typst as a pip wheel — no apt-get layer, no TeX Live.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

# Application source, named individually so the host's conda/darwin
# `backend/.venv` cannot ride along (PLAN.md D-36).
COPY backend/src ./src
COPY backend/db ./db
COPY backend/rendercv_config ./rendercv_config

# Frontend static export, served by FastAPI at / (the static mount at the end of
# `create_app`, which resolves `STATIC_DIR` to /app/backend/static).
COPY --from=frontend-builder /build/frontend/out ./static/

# /app/db and /app/pdfs are created by the lifespan on startup and are volume
# mount points in docker-compose.yml.

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["uv", "run", "--project", "/app/backend", "uvicorn", "resumetailor.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1"]
