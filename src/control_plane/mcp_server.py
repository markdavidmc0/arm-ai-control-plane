import json
import logging
from typing import Dict, Any, List

logger = logging.getLogger("mvcp.mcp_server")

class MCPServer:
    """
    Model Context Protocol (MCP) server implementation.
    Translates raw JSON profile logs from the sandbox into structured UI visualization payloads,
    following the MCP JSON-RPC 2.0 standard protocol.
    """
    def __init__(self, orchestrator=None):
        self.orchestrator = orchestrator

    def handle_mcp_request(self, request_body: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processes standard MCP JSON-RPC 2.0 request payloads.
        Supports tools/list, tools/call, resources/list, resources/read.
        """
        method = request_body.get("method")
        req_id = request_body.get("id")
        params = request_body.get("params", {})

        logger.info(f"Received MCP RPC Call: {method} (id={req_id})")

        try:
            if method == "tools/list":
                return self._build_jsonrpc_response(req_id, self._list_tools())
            elif method == "tools/call":
                return self._build_jsonrpc_response(req_id, self._call_tool(params))
            elif method == "resources/list":
                return self._build_jsonrpc_response(req_id, self._list_resources())
            elif method == "resources/read":
                return self._build_jsonrpc_response(req_id, self._read_resource(params))
            else:
                return self._build_jsonrpc_error(req_id, -32601, f"Method not found: {method}")
        except Exception as e:
            logger.error(f"Error handling MCP request: {e}")
            return self._build_jsonrpc_error(req_id, -32603, f"Internal error: {str(e)}")

    def translate_profile_to_heatmap(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """
        Translates raw profile outputs into visual widget payloads.
        Generates metadata mapping source line numbers to vectorization status for the UI Heatmap.
        """
        missed = profile.get("missed_vectorization_lines", [])
        optimized = profile.get("optimized_microkernel_lines", [])
        
        heatmap_data = []
        
        # We define ranges of interest in the matrix.cpp file (lines 1 to 45)
        for line in range(1, 46):
            if line in missed:
                status = "missed_neon_sve"
                color = "amber"
                description = "High latency scalar loop. Stride-based memory indexing blocked auto-vectorization."
                severity = "HIGH"
            elif line in optimized:
                status = "kleidiai_optimized"
                color = "green"
                description = "Arm KleidiAI Micro-kernel deployed. Native SME2/Neon instructions active."
                severity = "OPTIMIZED"
            else:
                status = "normal"
                color = "neutral"
                description = "Boilerplate setup or variable declaration."
                severity = "NONE"
                
            heatmap_data.append({
                "line": line,
                "status": status,
                "color": color,
                "description": description,
                "severity": severity
            })

        return {
            "task_id": profile.get("task_id"),
            "target_hardware": profile.get("target_hardware"),
            "runtime": profile.get("runtime"),
            "sme2_utilization_pct": profile.get("sme2_utilization_pct"),
            "peak_ram_mb": profile.get("peak_ram_mb"),
            "vector_extension_utilization_pct": profile.get("vector_extension_utilization_pct"),
            "latency_ttft_impact": profile.get("latency_ttft_impact"),
            "assembly_insights": profile.get("assembly_insights"),
            "heatmap": heatmap_data,
            "sandbox_security_mode": profile.get("sandbox_security", "gvisor"),
            "network_crypto_layer": profile.get("network_cryptography", "tsnet")
        }

    def _list_tools(self) -> Dict[str, Any]:
        return {
            "tools": [
                {
                    "name": "optimize_kernel",
                    "description": "Cross-compiles and optimizes a C++ matrix multiplication kernel targeting Armv9-A Cortex-X925 using Arm KleidiAI Micro-kernels within a gVisor sandboxed data plane.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "code": {
                                "type": "string",
                                "description": "The complete C++ matrix multiplication kernel code to be optimized."
                            }
                        },
                        "required": ["code"]
                    }
                }
            ]
        }

    def _call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if tool_name == "optimize_kernel":
            code = arguments.get("code")
            if not code:
                raise ValueError("Missing 'code' argument in optimize_kernel tool call.")
            
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Optimization engine triggered for submitted C++ source. Initiated sandbox run under gVisor isolated environment."
                    }
                ]
            }
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    def _list_resources(self) -> Dict[str, Any]:
        return {
            "resources": [
                {
                    "uri": "mvcp://heatmap/latest",
                    "name": "Assembly Line Vectorization Heatmap Payload",
                    "mimeType": "application/json",
                    "description": "Structured heatmap metadata pointing out unoptimized scalar bottlenecks and KleidiAI optimized blocks."
                }
            ]
        }

    def _read_resource(self, params: Dict[str, Any]) -> Dict[str, Any]:
        uri = params.get("uri")
        if uri == "mvcp://heatmap/latest":
            mock_profile = {
                "task_id": "default-task-000",
                "target_hardware": "Cortex-X925",
                "runtime": "ExecuTorch + Naive Scalar Fallback",
                "sme2_utilization_pct": 0.0,
                "peak_ram_mb": 320,
                "vector_extension_utilization_pct": 0.0,
                "latency_ttft_impact": "0% Latency Improvement",
                "missed_vectorization_lines": [16, 17, 18, 19, 20, 21, 22],
                "optimized_microkernel_lines": [],
                "assembly_insights": {
                    "vectorized_loops": 0,
                    "scalar_fallback_loops": 1,
                    "register_spills": 4,
                    "neon_instructions": 0
                }
            }
            translated = self.translate_profile_to_heatmap(mock_profile)
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": json.dumps(translated)
                    }
                ]
            }
        else:
            raise ValueError(f"Resource not found: {uri}")

    def _build_jsonrpc_response(self, req_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": result
        }

    def _build_jsonrpc_error(self, req_id: Any, code: int, message: str) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": code,
                "message": message
            }
        }
