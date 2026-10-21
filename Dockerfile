FROM python:3.12-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY data/seasonal ./data/seasonal
COPY data/outcomes ./data/outcomes
COPY data/confidence ./data/confidence
COPY data/scoring ./data/scoring
COPY data/spot_grid ./data/spot_grid
COPY data/crop_calendar ./data/crop_calendar
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH" HERBTWIN_PHOTOS_DIR=/data/photos
EXPOSE 8000
CMD ["uvicorn", "herbtwin.web.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
