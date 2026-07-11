---
title: "Day 11: Fixed-Point Arithmetic: Implementing Quantized Math by Hand"
date: 2026-07-11
tags: ["til", "edge-ai-tinyml", "fixed-point", "arithmetic"]
---

## What I Explored Today

After spending the last two days on quantization theory and calibration, today I got my hands dirty implementing fixed-point arithmetic from scratch. No floating-point unit, no CMSIS-DSP wrappers—just raw integer math on a Cortex-M4. I built a small library to handle quantized matrix multiplication and convolution, and I finally understood why every TinyML framework obsesses over accumulator types and bit-shift ordering. The key insight: you can't just multiply two int8 values and call it a day; you have to manage overflow, rounding, and the dreaded "double-width accumulator" at every step.

## The Core Concept

Fixed-point arithmetic is the engine that makes quantized inference run on microcontrollers. When you quantize a model, you replace floating-point weights and activations with integers (typically int8) plus a scale factor and zero-point. But the math inside the model—multiply-accumulate operations—must be performed with higher precision to avoid catastrophic loss.

The fundamental operation is: `y = (scale_a * scale_b) * (a_int * b_int)`. Since `a_int * b_int` can overflow an int8 (max 128*128=16384), you must promote to a wider type (int16 or int32) for the accumulation. Then you must rescale the result back to the output quantization range. The order of operations—multiply, accumulate, then rescale—is critical. If you rescale too early, you lose precision; if you rescale too late, you overflow the accumulator.

The standard approach is to use a "double-width accumulator" (e.g., int32 for int8 inputs) and a "multiply-shift" rescale: `result = (accumulator * multiplier) >> shift`, where `multiplier` and `shift` are derived from the product of the input and output scales. This avoids division (expensive on Cortex-M) and keeps everything in integer arithmetic.

## Key Commands / Configuration / Code

Here's a minimal but complete fixed-point convolution kernel for a 3x3 filter, int8 inputs and outputs, with int32 accumulator. This is what you'd actually write for a TinyML inference engine.

```c
#include <stdint.h>
#include <stddef.h>

// Quantized convolution: 3x3 filter, 1 input channel, 1 output channel
// Assumes input and output have same scale (common in depthwise convolutions)
void conv3x3_fixed_point(
    const int8_t *input,    // [H][W]  (H, W are input dimensions)
    const int8_t *weights,  // [3][3]
    int8_t *output,         // [H-2][W-2]
    int32_t input_offset,   // zero-point for input
    int32_t output_offset,  // zero-point for output
    int32_t multiplier,     // Q0.31 fixed-point multiplier (scale product)
    int8_t  shift,          // right-shift amount (positive = right shift)
    size_t H, size_t W
) {
    for (size_t y = 1; y < H - 1; y++) {
        for (size_t x = 1; x < W - 1; x++) {
            int32_t acc = 0;

            // 3x3 kernel with zero-point subtraction
            for (int ky = -1; ky <= 1; ky++) {
                for (int kx = -1; kx <= 1; kx++) {
                    int32_t in_val  = (int32_t)input[(y+ky)*W + (x+kx)] - input_offset;
                    int32_t w_val   = (int32_t)weights[(ky+1)*3 + (kx+1)];
                    acc += in_val * w_val;  // int32 accumulator, safe for 256*128*9 ~ 295k
                }
            }

            // Rescale: multiply by Q0.31 multiplier, then shift
            // Use int64 for intermediate to avoid overflow (multiplier is 32-bit)
            int64_t scaled = (int64_t)acc * multiplier;
            int32_t result = (int32_t)(scaled >> 31);  // Q0.31 -> Q0.0 (integer part)
            if (shift > 0) {
                result = (result + (1 << (shift - 1))) >> shift;  // rounding
            } else if (shift < 0) {
                result = result << (-shift);  // left shift for negative shift
            }

            // Add output offset and clamp to int8 range
            result += output_offset;
            if (result < -128) result = -128;
            if (result > 127)  result = 127;
            output[(y-1)*(W-2) + (x-1)] = (int8_t)result;
        }
    }
}
```

**Key details:**
- The `multiplier` is a Q0.31 fixed-point number (range [0, 2)). It's computed offline as `round(scale_product * 2^31)`.
- The `shift` can be negative to handle cases where `multiplier` > 1 (rare but possible).
- Rounding is done by adding `1 << (shift - 1)` before the right shift—this is the standard "round to nearest, ties to even" for positive values. For production, you'd handle negative rounding too.

**How to compute multiplier and shift offline (Python):**
```python
import math

def compute_multiplier_and_shift(scale_product):
    """Convert a floating-point scale product to multiplier/shift pair."""
    # Find shift such that multiplier fits in Q0.31
    # We want: multiplier * 2^(-shift) ≈ scale_product
    # With multiplier in [2^30, 2^31) for best precision
    shift = 0
    while scale_product < 0.5 and shift < 31:
        scale_product *= 2.0
        shift += 1
    multiplier = round(scale_product * (1 << 31))
    # Clamp multiplier to [0, 2^31-1]
    multiplier = min(max(multiplier, 0), (1 << 31) - 1)
    return multiplier, shift
```

## Common Pitfalls & Gotchas

1. **Accumulator overflow in edge cases.** Even with int32, a 3x3 convolution with 128 int8 values can hit 128*128*9 = 147,456, which fits in int32. But a 5x5 convolution or a fully-connected layer with 256 inputs can overflow. Always compute the worst-case accumulator value and choose your accumulator type accordingly. For int8 weights and activations, int32 is usually safe for kernels up to 5x5; for larger, use int64 or saturate earlier.

2. **Rounding bias with negative values.** The simple `(result + (1 << (shift-1))) >> shift` only rounds correctly for positive numbers. For negative numbers, you need `(result - (1 << (shift-1))) >> shift` to round toward zero. Many production frameworks (TFLite Micro, CMSIS-NN) use a symmetric rounding that handles both signs. If you skip this, your model accuracy can drop by 1-2% on symmetric distributions.

3. **Zero-point subtraction order.** Always subtract the input zero-point *before* the multiply, not after. If you do `acc += in_val * w_val` where `in_val` is already zero-point-corrected, you avoid mixing zero-points into the accumulator. Forgetting this is the #1 bug in hand-written quantized kernels—it introduces a constant bias that grows with kernel size.

## Try It Yourself

1. **Implement a 1D dot product** for two int8 vectors of length 16. Use an int32 accumulator, then rescale with a multiplier/shift pair. Compare the result to a floating-point reference. Vary the multiplier and shift to see how precision changes.

2. **Modify the convolution kernel** to handle asymmetric input/output scales (different multiplier for each output channel). This is what TFLite does for per-channel quantization. Add a `multiplier[]` and `shift[]` array indexed by output channel.

3. **Benchmark your fixed-point kernel** against a naive floating-point version on your dev board (e.g., STM32F4 or nRF52840). Measure cycle count using DWT->CYCCNT. You should see 5-10x speedup. Post your results in the comments.

## Next Up

Tomorrow: **Optimizing Inference Latency: Loop Unrolling & SIMD on Cortex-M**. We'll take this fixed-point kernel and make it scream—unrolling loops, using SMLAD instructions, and aligning memory for 4-byte access.
