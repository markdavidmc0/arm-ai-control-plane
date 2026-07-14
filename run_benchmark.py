import subprocess
import os
import sys
import time

def run_benchmark():
    print("========================================================================")
    print("         ARM 2026 CO-DESIGN loop MULTI-COMPONENT BENCHMARK RUNNER       ")
    print("========================================================================")
    
    # 1. Start Router V1 + Reasoning V1 on 50051 / 50052
    print("\n[Runner] Launching V1 Baseline SDK (Ports: Router=50051, Reasoning=50052)...")
    env_v1 = os.environ.copy()
    env_v1["ROUTER_PORT"] = "50051"
    env_v1["REASONING_PORT"] = "50052"
    
    proc_v1 = subprocess.Popen(
        [sys.executable, "components/router/router_v1.py"],
        env=env_v1,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    # 2. Start Router V2 + Reasoning V2 on 50053 / 50054
    print("[Runner] Launching V2 Adaptive SDK (Ports: Router=50053, Reasoning=50054)...")
    env_v2 = os.environ.copy()
    env_v2["ROUTER_PORT"] = "50053"
    env_v2["REASONING_PORT"] = "50054"
    
    proc_v2 = subprocess.Popen(
        [sys.executable, "components/router/router_v2.py"],
        env=env_v2,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    # Allow servers time to spin up and bind ports
    print("[Runner] Waiting 2.5 seconds for all gRPC systems to initialize...")
    time.sleep(2.5)
    
    client_proc = None
    try:
        # 3. Execute the C++ Benchmark Harness
        print("[Runner] Launching C++ FVP simulation benchmark client...\n")
        client_proc = subprocess.run(
            ["./bazel-bin/components/runtime/fvp_runtime"],
            stdout=sys.stdout,
            stderr=sys.stderr
        )
    except KeyboardInterrupt:
        print("\n[Runner] KeyboardInterrupt detected. Cleaning up...")
    finally:
        # 4. Safely terminate and clean up background server subprocesses
        print("[Runner] Tearing down background servers...")
        for label, proc in [("V1 Baseline SDK", proc_v1), ("V2 Adaptive SDK", proc_v2)]:
            try:
                print(f" - Terminating {label}...")
                proc.terminate()
                proc.wait(timeout=3)
            except Exception as e:
                print(f" - Error cleaning up {label}: {e}")
                
        print("\n[Runner] Benchmark execution complete. Ports freed.")

if __name__ == "__main__":
    run_benchmark()
