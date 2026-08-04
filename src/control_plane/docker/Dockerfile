FROM python:3.12-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
COPY src/control_plane /app/src/control_plane
RUN uv pip install --system -e /app/src/control_plane
EXPOSE 8000
CMD ["uvicorn", "control_plane.main:app", "--host", "0.0.0.0", "--port", "8000"]
