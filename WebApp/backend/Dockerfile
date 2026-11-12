# The WebApp backend, run by WebApp/docker-compose.yml (profile "app") on the
# range PC: in Linux, so WeasyPrint's Pango comes with the image rather than
# installed on Windows. It applies the migrations, then serves. Its SQLite
# database file lives on a mounted volume (DATABASE_URL), so it survives a rebuild.
FROM python:3.12-slim

# Pango for WeasyPrint's PDFs, with fonts to draw them in; tzdata so TZ (set
# to the PC's zone) gives log timestamps in local time
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz-subset0 \
    libfontconfig1 \
    libgdk-pixbuf-2.0-0 \
    fonts-dejavu-core \
    tzdata \
  && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --timeout-graceful-shutdown 2"]
