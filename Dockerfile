# Use a lightweight, official Python image
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies needed for compiling gRPC stubs if necessary
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python gRPC dependencies
RUN pip install --no-cache-dir grpcio grpcio-tools

# Copy the proto definitions and component source code
COPY proto/ /app/proto/
COPY components/ /app/components/

# Generate Python gRPC stubs inside the container
RUN python -m grpc_tools.protoc \
    -I. \
    --python_out=. \
    --grpc_python_out=. \
    proto/telemetry.proto

# Default ports to expose
EXPOSE 50051
EXPOSE 50052
EXPOSE 50053
EXPOSE 50054

# Default command expects ROUTER_PORT and REASONING_PORT environment variables
# Run router_v2 by default, but allow overriding via Compose
CMD ["python", "components/router/router_v2.py"]
