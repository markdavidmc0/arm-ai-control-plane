from concurrent import futures
import grpc

# Robust import of generated gRPC stubs
try:
    from proto import telemetry_pb2
    from proto import telemetry_pb2_grpc
except ImportError:
    import telemetry_pb2
    import telemetry_pb2_grpc

class ReasoningV1Servicer(telemetry_pb2_grpc.TelemetryOrchestratorServicer):
    def RouteWorkload(self, request, context):
        # RouteWorkload is not typically handled directly by the reasoning engine, but we implement it as part of the interface
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("RouteWorkload is handled by the router")
        return telemetry_pb2.RouteDecision()

    def AnalyzeHardwareTelemetry(self, request, context):
        print(f"[Reasoning V1] AnalyzeHardwareTelemetry called. Cache Misses={request.cache_misses}, SVE/SME Util={request.sve_sme_utilization:.2f}")
        
        # Simple threshold analyzer: If cache misses > 5000, trigger loop unrolling to optimize instruction fetches
        loop_unroll = request.cache_misses > 5000
        
        # Static Strategy: Vector width is locked at 128 bits (safe baseline)
        vector_width = 128
        
        print(f"[Reasoning V1] Decision: Loop Unroll={loop_unroll}, Vector Register Width={vector_width} bits")
        return telemetry_pb2.OptimizationFeedback(
            loop_unrolling=loop_unroll,
            vector_register_width=vector_width
        )

def serve():
    import os
    port = int(os.environ.get("REASONING_PORT", "50052"))
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=5))
    telemetry_pb2_grpc.add_TelemetryOrchestratorServicer_to_server(
        ReasoningV1Servicer(), server
    )
    server.add_insecure_port(f"[::]:{port}")
    print(f"[Reasoning V1] Starting gRPC server on [::]:{port}...")
    server.start()
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("[Reasoning V1] Stopping server...")
        server.stop(0)

if __name__ == "__main__":
    serve()
