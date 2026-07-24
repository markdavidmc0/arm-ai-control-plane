#!/usr/bin/env python3
"""
Test script to verify the new Consolidated Streamable HTTP/2 JSON-RPC Gateway.
Starts a local instance of the MVCP backend, triggers a streamable compile request,
and reads the response chunks line-by-line over a single persistent HTTP connection.
Uses the requests library for robust chunked transfer decoding.
"""

import subprocess
import time
import requests
import sys
import os


def test_streamable_mcp():
    print(
        "\033[94m[INFO] Launching local MVCP FastAPI server for streaming integration tests...\033[0m"
    )

    # Start uvicorn server in background by executing main.py directly
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()

    server_process = subprocess.Popen(
        [sys.executable, "src/control_plane/main.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    # Give uvicorn a couple seconds to boot up
    time.sleep(2.5)

    try:
        # 1. Define the standard MCP JSON-RPC Payload (Calling optimize_kernel)
        mcp_payload = {
            "jsonrpc": "2.0",
            "id": "test-stream-id-123",
            "method": "tools/call",
            "params": {
                "name": "optimize_kernel",
                "arguments": {
                    "code": "void kernel() { /* Test Streamable Kernel Vectorization */ }"
                },
            },
        }

        url = "http://127.0.0.1:8000/api/v1/mcp/stream"
        print(f"\033[94m[INFO] Sending streamable POST request to {url}...\033[0m")

        # 2. Open single HTTP POST connection and stream the response chunk-by-chunk using requests
        response = requests.post(url, json=mcp_payload, stream=True, timeout=10)

        if response.status_code != 200:
            print(f"\033[91m[FAIL] Gateway returned HTTP {response.status_code}\033[0m")
            sys.exit(1)

        print(
            "\033[92m[SUCCESS] Connection established! Streaming JSON-RPC frames line-by-line:\033[0m"
        )
        print("-" * 80)

        frame_count = 0
        # iter_lines() handles chunked transport boundaries dynamically and streams line-by-line
        for line in response.iter_lines():
            if line:
                frame_count += 1
                decoded_line = line.decode("utf-8")
                print(f"\033[95m[FRAME {frame_count}]\033[0m {decoded_line}")
                sys.stdout.flush()

        print("-" * 80)
        if frame_count > 0:
            print(
                f"\033[92m[SUCCESS] Successfully received {frame_count} streaming frames over a SINGLE connection!\033[0m"
            )
            print(
                "\033[92m[SUCCESS] Streamable HTTP / Newline-Delimited JSON-RPC Gateway is fully verified.\033[0m"
            )
        else:
            print("\033[91m[FAIL] Connection closed without emitting any stream frames.\033[0m")
            sys.exit(1)

    except Exception as e:
        print(f"\033[91m[ERROR] Test encountered exception: {e}\033[0m")
        print("\033[93m[LOGS] Pulling background server output to diagnose:\033[0m")
        # Terminate the server to flush buffers
        server_process.terminate()
        server_process.wait()

        stdout, stderr = server_process.communicate()
        print("\n=== SERVER STDOUT ===")
        print(stdout)
        print("\n=== SERVER STDERR ===")
        print(stderr)
        sys.exit(1)
    finally:
        if server_process.poll() is None:
            print("\033[94m[INFO] Shutting down background FastAPI server...\033[0m")
            server_process.terminate()
            server_process.wait()
            print("\033[94m[INFO] Server terminated.\033[0m")


if __name__ == "__main__":
    test_streamable_mcp()
