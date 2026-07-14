from concurrent import futures
import grpc

# Robust import of generated gRPC stubs
try:
    from proto import telemetry_pb2
    from proto import telemetry_pb2_grpc
except ImportError:
    import telemetry_pb2
    import telemetry_pb2_grpc

class ReasoningV2Servicer(telemetry_pb2_grpc.TelemetryOrchestratorServicer):
    def RouteWorkload(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("RouteWorkload is handled by the router")
        return telemetry_pb2.RouteDecision()

    def AnalyzeHardwareTelemetry(self, request, context):
        profile = request.target_profile.lower()
        print(f"[Reasoning V2] AnalyzeHardwareTelemetry called for Profile={profile}. Cache Misses={request.cache_misses}, SVE/SME Util={request.sve_sme_utilization:.2f}")

        # Advanced profile-aware analyzer
        if profile == "cloud_ai":
            # Cloud AI: Maximize Pipeline Throughput
            # If SME utilization < 40%, dynamically scale register width to 512 bits to maximize vector instruction performance
            if request.sve_sme_utilization < 0.40:
                vector_width = 512
            else:
                vector_width = 256
            
            # Aggressive unrolling for high-speed loops (threshold at 2000 misses)
            loop_unroll = request.cache_misses > 2000

        elif profile == "mobile_ai":
            # Mobile AI: Balance Performance and Battery
            # Lock vector width to 256 bits (Cortex-X standard) to avoid excessive dynamic power draw / thermal throttling
            vector_width = 256
            
            # Conservative unrolling (threshold at 5000 misses) to keep instruction footprint manageable
            loop_unroll = request.cache_misses > 5000

        elif profile == "physical_ai":
            # Physical AI: Ultra-Low Footprint & Code Size
            # Keep vector width at 128-bit (compatible with Cortex-M/R or baseline Cortex-A embedded profiles)
            vector_width = 128
            
            # Disable loop unrolling entirely to prevent code bloat, fitting instructions comfortably inside embedded SRAM/TCM
            loop_unroll = False

        else:
            # Fallback safe defaults
            vector_width = 256
            loop_unroll = False

        print(f"[Reasoning V2] Decision: Loop Unroll={loop_unroll}, Vector Width={vector_width} bits")
        return telemetry_pb2.OptimizationFeedback(
            loop_unrolling=loop_unroll,
            vector_register_width=vector_width
        )

def serve():
    import os
    port = int(os.environ.get("REASONING_PORT", "50052"))
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=5))
    telemetry_pb2_grpc.add_TelemetryOrchestratorServicer_to_server(
        ReasoningV2Servicer(), server
    )
    server.add_insecure_port(f"[::]:{port}")
    print(f"[Reasoning V2] Starting gRPC server on [::]:{port}...")
    server.start()
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("[Reasoning V2] Stopping server...")
        server.stop(0)

if __name__ == "__main__":
    serve()
