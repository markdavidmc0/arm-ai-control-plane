import os
import sys
import subprocess
import time
import atexit
from concurrent import futures

import grpc

# Robust import of generated gRPC stubs
try:
    from proto import telemetry_pb2
    from proto import telemetry_pb2_grpc
except ImportError:
    import telemetry_pb2
    import telemetry_pb2_grpc

class RouterV2Servicer(telemetry_pb2_grpc.TelemetryOrchestratorServicer):
    def __init__(self, reasoning_process, reasoning_port=50052):
        self.reasoning_process = reasoning_process
        # Establish channel to the reasoning engine on specified port
        self.channel = grpc.insecure_channel(f"localhost:{reasoning_port}")
        self.reasoning_stub = telemetry_pb2_grpc.TelemetryOrchestratorStub(self.channel)

    def RouteWorkload(self, request, context):
        print(f"[Router V2] RouteWorkload called for ID={request.id}, Shape={request.shape}, Precision={request.precision}, Profile={request.target_profile}")
        
        profile = request.target_profile.lower()
        precision = request.precision.upper()
        shape = request.shape

        # Adaptive Strategy matching the 3 frontier tracks of the Arm Developer Challenge
        if profile == "cloud_ai":
            # Cloud AI priorites high throughput - use SME Matrix Coprocessor for large/INT8 matrix workloads
            if precision == "INT8" or "1024" in shape:
                path = "SME_MATRIX"
            else:
                path = "SVE_VECTOR"
        elif profile == "mobile_ai":
            # Mobile AI priorities energy efficiency and battery life. Use SVE vectors for scaling.
            path = "SVE_VECTOR"
        elif profile == "physical_ai":
            # Physical AI prioritizes extremely small footprint and backward-compatible determinism
            path = "NEON_BLAS"
        else:
            # Safe default fallback
            path = "SVE_VECTOR"

        print(f"[Router V2] Adaptive Decision: Mapped workload to -> {path}")
        return telemetry_pb2.RouteDecision(selected_path=path)

    def AnalyzeHardwareTelemetry(self, request, context):
        print(f"[Router V2] AnalyzeHardwareTelemetry received, forwarding to Reasoning V2 on port 50052")
        try:
            # Forward the call to reasoning_v2
            response = self.reasoning_stub.AnalyzeHardwareTelemetry(request)
            return response
        except grpc.RpcError as e:
            print(f"[Router V2] Failed to contact Reasoning V2: {e}")
            context.set_code(grpc.StatusCode.UNAVAILABLE)
            context.set_details("Reasoning service unavailable")
            return telemetry_pb2.OptimizationFeedback()

def start_reasoning_v2(reasoning_port=50052):
    # Locate reasoning_v2 relative to this file
    possible_paths = [
        os.path.join(os.path.dirname(__file__), "../reasoning/reasoning_v2.py"),
        os.path.join(os.path.dirname(__file__), "components/reasoning/reasoning_v2.py"),
        "components/reasoning/reasoning_v2.py"
    ]
    
    reasoning_path = None
    for p in possible_paths:
        if os.path.exists(p):
            reasoning_path = p
            break

    if not reasoning_path:
        print("[Router V2] ERROR: Could not find reasoning_v2.py source file!")
        sys.exit(1)

    print(f"[Router V2] Spawning Reasoning V2 process: {sys.executable} {reasoning_path} on port {reasoning_port}")
    
    # Launch reasoning_v2 using current Python runtime and environment, passing REASONING_PORT
    env = os.environ.copy()
    env["REASONING_PORT"] = str(reasoning_port)
    proc = subprocess.Popen([sys.executable, reasoning_path], env=env)
    
    # Register shutdown hook to clean up the subprocess
    def cleanup():
        print("[Router V2] Terminating Reasoning V2 subprocess...")
        proc.terminate()
        proc.wait()
    atexit.register(cleanup)
    
    # Allow time for reasoning_v2 server to initialize
    time.sleep(1.5)
    return proc

def serve():
    router_port = int(os.environ.get("ROUTER_PORT", "50051"))
    reasoning_port = int(os.environ.get("REASONING_PORT", "50052"))

    # First, spawn reasoning_v2 in the background
    reasoning_process = start_reasoning_v2(reasoning_port)

    # Initialize router_v2 server on port
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    telemetry_pb2_grpc.add_TelemetryOrchestratorServicer_to_server(
        RouterV2Servicer(reasoning_process, reasoning_port), server
    )
    server.add_insecure_port(f"[::]:{router_port}")
    print(f"[Router V2] Starting gRPC server on [::]:{router_port}...")
    server.start()
    
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("[Router V2] Stopping server...")
        server.stop(0)

if __name__ == "__main__":
    serve()
