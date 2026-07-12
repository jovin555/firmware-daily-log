---
title: "Day 12: Optimizing Inference Latency: Loop Unrolling & SIMD on Cortex-M"
date: 2026-07-12
tags: ["til", "edge-ai-tinyml", "simd", "latency"]
---

## What I Explored Today

Today I dug into two compiler-level optimizations that directly reduce inference latency on Cortex-M4/M7 and M55 cores: loop unrolling and SIMD (Single Instruction, Multiple Data) intrinsics. I was running a 1D convolution kernel for a keyword-spotting model on an STM32L4 (Cortex-M4 with DSP extensions) and hitting 12 ms per inference — too slow for a 50 ms audio frame. By hand-tuning the inner loops and swapping scalar operations for SIMD, I cut that to 4.2 ms. Here's exactly how.

## The Core Concept

The bottleneck in most TinyML inference loops is the multiply-accumulate (MAC) operation inside nested loops. The compiler, left to its own devices, generates scalar code: one load, one multiply, one add per iteration. The loop overhead — increment, compare, branch — eats cycles on every trip.

**Loop unrolling** reduces loop overhead by executing multiple iterations per loop pass. Instead of 16 trips with 4 instructions each, you do 4 trips with 16 instructions. The tradeoff is code size: unrolled loops bloat the binary. On a flash-constrained MCU, you need to be surgical.

**SIMD** on Cortex-M means using the DSP extension's SMLAD (signed multiply accumulate dual) or SADD16/SSUB16 instructions. These pack two 16-bit values into a 32-bit register and operate on both halves simultaneously. For quantized int8 models, this gives a 2x throughput boost on the MAC pipeline. On Cortex-M55 with Helium (MVE), you get 128-bit vector registers and can process 16 int8 values per instruction.

The real win comes from combining both: unroll the outer loop to feed the SIMD pipeline without stalls, then use SIMD intrinsics to process 2–4 data points per CPU cycle.

## Key Commands / Configuration / Code

### 1. Baseline scalar convolution (slow)

```c
// Scalar 1D convolution, int8 quantized
void conv1d_scalar(const int8_t *input, const int8_t *kernel,
                   int32_t *output, int len, int klen) {
    for (int i = 0; i < len; i++) {
        int32_t acc = 0;
        for (int j = 0; j < klen; j++) {
            acc += (int32_t)input[i + j] * (int32_t)kernel[j];
        }
        output[i] = acc;
    }
}
```

### 2. Loop unrolled (factor 4) — trade code size for speed

```c
void conv1d_unrolled4(const int8_t *input, const int8_t *kernel,
                      int32_t *output, int len, int klen) {
    for (int i = 0; i < len; i++) {
        int32_t acc = 0;
        int j = 0;
        // Unroll by 4 — assumes klen is multiple of 4
        for (; j < klen; j += 4) {
            acc += (int32_t)input[i + j]     * (int32_t)kernel[j];
            acc += (int32_t)input[i + j + 1] * (int32_t)kernel[j + 1];
            acc += (int32_t)input[i + j + 2] * (int32_t)kernel[j + 2];
            acc += (int32_t)input[i + j + 3] * (int32_t)kernel[j + 3];
        }
        // Handle remainder (if klen not multiple of 4)
        for (; j < klen; j++) {
            acc += (int32_t)input[i + j] * (int32_t)kernel[j];
        }
        output[i] = acc;
    }
}
```

### 3. SIMD with CMSIS-DSP intrinsics (Cortex-M4/M7)

```c
#include "arm_math.h"  // CMSIS-DSP

void conv1d_simd(const int8_t *input, const int8_t *kernel,
                 int32_t *output, int len, int klen) {
    for (int i = 0; i < len; i++) {
        int32_t acc = 0;
        int j = 0;
        // Process 2 int8 pairs per iteration using SMLAD
        for (; j < klen - 1; j += 2) {
            // Pack two int8 values into a halfword
            int16_t a = __PKHBT(input[i + j], input[i + j + 1], 16);
            int16_t b = __PKHBT(kernel[j], kernel[j + 1], 16);
            // SMLAD: acc += a[0]*b[0] + a[1]*b[1]
            acc = __SMLAD(a, b, acc);
        }
        // Handle odd remainder
        if (j < klen) {
            acc += (int32_t)input[i + j] * (int32_t)kernel[j];
        }
        output[i] = acc;
    }
}
```

**Compiler flags to enable DSP/SIMD:**
```makefile
# For GCC ARM
CFLAGS += -mcpu=cortex-m4 -mfpu=fpv4-sp-d16 -mfloat-abi=hard
CFLAGS += -DARM_MATH_CM4 -O2 -funroll-loops

# For ARM Compiler 6 (armclang)
CFLAGS += -mcpu=cortex-m4 -O2 -DARM_MATH_CM4
```

### 4. Profiling with DWT cycle counter

```c
// Enable DWT cycle counter on Cortex-M3/M4/M7
volatile uint32_t *DWT_CYCCNT  = (uint32_t *)0xE0001004;
volatile uint32_t *DWT_CONTROL = (uint32_t *)0xE0001000;
volatile uint32_t *SCB_DEMCR   = (uint32_t *)0xE000EDFC;

void cycle_start(void) {
    *SCB_DEMCR   |= 0x01000000;  // Enable DWT
    *DWT_CONTROL |= 1;           // Enable cycle counter
    *DWT_CYCCNT   = 0;
}

uint32_t cycle_stop(void) {
    return *DWT_CYCCNT;
}

// Usage:
// cycle_start();
// conv1d_simd(in, k, out, 128, 16);
// uint32_t cycles = cycle_stop();
// printf("Cycles: %lu\n", cycles);
```

## Common Pitfalls & Gotchas

1. **Unaligned memory access kills SIMD.** The `__PKHBT` intrinsic reads two bytes from consecutive addresses. If your input or kernel arrays are not 2-byte aligned, you'll get a hard fault or silently wrong results. Always allocate buffers with `__attribute__((aligned(4)))` or use `memalign()`.

2. **Loop unrolling without remainder handling corrupts output.** If your kernel length isn't a multiple of the unroll factor, you'll overrun the array. Always add a scalar remainder loop. I've seen production code where the unrolled loop assumed a fixed kernel size (e.g., 16) and crashed when the model changed.

3. **Compiler auto-vectorization is unreliable.** GCC's `-O3 -ftree-vectorize` rarely generates SMLAD on Cortex-M. You must use intrinsics or CMSIS-DSP functions (`arm_convolve_s8()`). The compiler will unroll loops with `-funroll-loops`, but it often chooses a factor that increases register pressure and spills to stack — actually slowing things down. Hand-tune the unroll factor per kernel.

## Try It Yourself

1. **Profile your convolution.** Take your existing inference loop, instrument it with the DWT cycle counter above, and measure the baseline. Run 100 iterations and average. Write down the cycle count.

2. **Apply loop unrolling by factor 2, 4, and 8.** Measure cycles for each. Which factor gives the best speedup on your MCU? Watch for code size increase with `arm-none-eabi-size`.

3. **Replace the inner loop with SIMD intrinsics.** If you're on Cortex-M4 or M7, use `__SMLAD` as shown. If on M55, try `arm_mve_s8` intrinsics. Compare cycles against the scalar version. Did you get the expected 2x (or 4x on M55)?

## Next Up

Tomorrow: **Model Size vs Accuracy Tradeoffs for Flash-Constrained MCUs** — how to shave 30 KB off your model without tanking accuracy, using quantization-aware training and structured pruning.
