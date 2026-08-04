FROM python:3.12-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
COPY src/data_plane /app/src/data_plane
RUN uv pip install --system -e /app/src/data_plane
EXPOSE 8001
CMD ["python", "-m", "data_plane.worker"]
