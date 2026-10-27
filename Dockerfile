# The demo in a container: the offline close on the committed sample, the
# rule-based triage, no API key. Build and run:
#
#   docker build -t intercompany-close-agent .
#   docker run --rm intercompany-close-agent
#
# The reviewer dashboard from the same image, on http://localhost:8501:
#
#   docker run --rm -p 8501:8501 intercompany-close-agent \
#     streamlit run app/streamlit_app.py --server.address=0.0.0.0 --server.headless=true
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.3 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Runtime dependencies only, in their own layer, so a code change doesn't
# reinstall them: the versions in uv.lock, the ones CI tests, and the build
# fails if the lock doesn't match pyproject.
COPY pyproject.toml README.md uv.lock ./
RUN uv sync --locked --no-install-project

COPY src ./src
COPY app ./app
COPY data ./data
RUN uv sync --locked

# Not root, and a named user, so the close can say who prepared it.
RUN useradd --create-home demo && chown -R demo /app
USER demo

CMD ["python", "-m", "intercompany_close_agent.cli", "demo"]
