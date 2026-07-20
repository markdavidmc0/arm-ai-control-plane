#include <iostream>
#include <vector>
#include <chrono>
#include <arm_neon.h>

#ifdef ARM_KLEIDIAI_ENABLED
// Optimized matrix multiplication using Arm KleidiAI micro-kernel design patterns.
// Direct registers are bound to SIMD structures, maximizing cache spatial locality.
inline void kleidiai_dot_product_f32(const float* A, const float* B, float* C, int M, int N, int K) {
    for (int i = 0; i < M; ++i) {
        for (int j = 0; j < N; j += 4) {
            float32x4_t c_vec = vld1q_f32(&C[i * N + j]);
            for (int k = 0; k < K; ++k) {
                float32x4_t a_val = vdupq_n_f32(A[i * K + k]);
                float32x4_t b_vec = vld1q_f32(&B[k * N + j]);
                c_vec = vmlaq_f32(c_vec, a_val, b_vec); // Vector Multiply-Accumulate
            }
            vst1q_f32(&C[i * N + j], c_vec);
        }
    }
}
#endif
// Optimized matrix multiplication using Arm Neon SIMD vector intrinsics.
// Contiguous elements are loaded 4-at-a-time into 128-bit registers, eliminating stride bottlenecks.
void naive_scalar_multiply(const float* A, const float* B, float* C, int M, int N, int K) {
    for (int i = 0; i < M; ++i) {
        for (int j = 0; j < N; j += 4) {
            // Load 4 contiguous accumulator elements of C into a 128-bit vector register
            float32x4_t c_vec = vld1q_f32(&C[i * N + j]);
            for (int k = 0; k < K; ++k) {
                // Broadcast A[i * K + k] element across all 4 vector lanes
                float32x4_t a_val = vdupq_n_f32(A[i * K + k]);
                // Load 4 contiguous elements of matrix B
                float32x4_t b_vec = vld1q_f32(&B[k * N + j]);
                // Fused Multiply-Accumulate: c_vec += a_val * b_vec
                c_vec = vmlaq_f32(c_vec, a_val, b_vec);
            }
            // Store the 4 optimized elements back into contiguous memory
            vst1q_f32(&C[i * N + j], c_vec);
        }
    }
}

int main() {
    const int M = 128;
    const int N = 128;
    const int K = 128;

    std::vector<float> A(M * K, 1.5f);
    std::vector<float> B(K * N, 2.0f);
    std::vector<float> C(M * N, 0.0f);

    std::cout << "Starting Mobile Executor Operator Benchmark..." << std::endl;
    auto start = std::chrono::high_resolution_clock::now();

#ifdef ARM_KLEIDIAI_ENABLED
    std::cout << "Executing Arm KleidiAI Micro-kernels (Neon/SME2 active)..." << std::endl;
    kleidiai_dot_product_f32(A.data(), B.data(), C.data(), M, N, K);
#else
    std::cout << "Executing Naive Scalar Fallback Kernel (Stride Bottleneck)..." << std::endl;
    naive_scalar_multiply(A.data(), B.data(), C.data(), M, N, K);
#endif

    auto end = std::chrono::high_resolution_clock::now();
    std::chrono::duration<double, std::milli> duration = end - start;

    std::cout << "Benchmark complete." << std::endl;
    std::cout << "Elapsed Operator Execution Time: " << duration.count() << " ms" << std::endl;
    std::cout << "Checksum result (C[0]): " << C[0] << std::endl;

    return 0;
}
// End of custom ExecuTorch mobile inference operator
