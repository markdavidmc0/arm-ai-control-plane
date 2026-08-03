"""E2E Session Fixtures & Port-Forwarding Configuration."""

import logging
import os
import socket
import subprocess
import time

import pytest

logger = logging.getLogger("mvcp.e2e.conftest")

E2E_TARGET = os.getenv("E2E_TARGET", "inmemory").lower()
GATEWAY_BASE_URL = os.getenv("MVCP_GATEWAY_URL", "http://localhost:8000")


def is_port_open(host: str, port: int) -> bool:
    """Checks if a TCP port is open and listening."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        return sock.connect_ex((host, port)) == 0


@pytest.fixture(scope="session", autouse=True)
def auto_port_forward_if_cluster_target():
    """Session fixture managing background kubectl port-forwarding when targeting live clusters."""
    port_forward_process = None

    if E2E_TARGET in ["kind", "live_gke", "cluster"]:
        if not is_port_open("localhost", 8000):
            logger.info(
                f"Target is '{E2E_TARGET}'. Port 8000 inactive. Launching kubectl port-forward..."
            )
            try:
                port_forward_process = subprocess.Popen(
                    [
                        "kubectl",
                        "port-forward",
                        "svc/mvcp-gateway-service",
                        "8000:8000",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                for _ in range(10):
                    if is_port_open("localhost", 8000):
                        break
                    time.sleep(0.5)
            except Exception as e:
                logger.warning(f"Could not start kubectl port-forward: {e}")

    yield GATEWAY_BASE_URL

    if port_forward_process:
        logger.info("Terminating background kubectl port-forward process...")
        port_forward_process.terminate()
        port_forward_process.wait()
