---
title: "Day 04: constexpr & consteval: Compile-Time Computation"
date: 2026-06-16
tags: ["til", "cpp-embedded", "constexpr", "compile-time"]
---

## What I Explored Today

Today I dug into C++ compile-time evaluation — specifically `constexpr` and `consteval` — and how they let us shift computation from runtime to compile time. For embedded systems, this is a game-changer: we can compute lookup tables, CRC checksums, and configuration parameters before the firmware ever hits the target, saving both flash and cycles. I experimented with `constexpr` functions, `consteval` for mandatory compile-time execution, and the subtle differences that matter when your compiler is GCC for ARM Cortex-M.

## The Core Concept

In embedded C, we often use macros or precomputed tables to avoid runtime overhead. But macros are error-prone and lack type safety. `constexpr` (C++11, expanded in C++14/17/20) lets you write real functions that the compiler *may* evaluate at compile time if all inputs are constant expressions. `consteval` (C++20) goes further: it *forces* compile-time evaluation — the function can never be called at runtime.

Why does this matter for embedded? Consider a sensor calibration routine that computes a polynomial correction. With `constexpr`, you can compute the correction coefficients at compile time from constants, then store only the result in flash. No runtime math, no floating-point overhead on a Cortex-M0 that lacks an FPU. The compiler literally replaces the function call with the computed value.

The key insight: `constexpr` gives you the *option* of compile-time evaluation; `consteval` gives you a *guarantee*. For embedded, `consteval` is often safer because it prevents accidental runtime calls that might bloat your binary or introduce timing jitter.

## Key Commands / Configuration / Code

### Basic `constexpr` for a Lookup Table

```cpp
// Compute sine values at compile time for a 256-entry lookup table
#include <array>
#include <cmath>  // std::sin is NOT constexpr, so we roll our own

constexpr double pi = 3.14159265358979323846;

// constexpr approximation of sin(x) using Taylor series (3 terms)
constexpr double sin_approx(double x) {
    double x2 = x * x;
    double x3 = x2 * x;
    double x5 = x3 * x2;
    double x7 = x5 * x2;
    return x - x3 / 6.0 + x5 / 120.0 - x7 / 5040.0;
}

// Generate a 256-entry sine table at compile time
constexpr std::array<double, 256> sine_table = []() {
    std::array<double, 256> table{};
    for (size_t i = 0; i < 256; ++i) {
        table[i] = sin_approx(2.0 * pi * i / 256.0);
    }
    return table;
}();

// Usage in interrupt handler — no runtime computation
double get_sine(uint8_t index) {
    return sine_table[index];  // Just a flash lookup
}
```

### `consteval` for Mandatory Compile-Time CRC

```cpp
#include <cstdint>
#include <array>

// CRC-8-ATM (polynomial 0x07) — must be computed at compile time
consteval uint8_t crc8_atm(const std::array<uint8_t, 8>& data) {
    uint8_t crc = 0xFF;
    for (auto byte : data) {
        crc ^= byte;
        for (int i = 0; i < 8; ++i) {
            if (crc & 0x80) {
                crc = (crc << 1) ^ 0x07;
            } else {
                crc <<= 1;
            }
        }
    }
    return crc ^ 0xFF;
}

// Firmware version info — CRC computed at compile time
constexpr std::array<uint8_t, 8> fw_version = {0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08};
constexpr uint8_t fw_crc = crc8_atm(fw_version);  // Computed at compile time

// This would fail to compile:
// uint8_t runtime_crc = crc8_atm(some_runtime_array);  // ERROR: not a constant expression
```

### Compiler Flags (GCC for ARM)

```bash
# Ensure constexpr evaluation is forced (no -fno-builtin-constexpr)
arm-none-eabi-g++ -std=c++20 -O2 -mcpu=cortex-m4 -mfloat-abi=hard \
    -ffunction-sections -fdata-sections -Wno-expansion-to-defined \
    -fconstexpr-loop-limit=1000000  # Increase loop limit for large tables
```

The `-fconstexpr-loop-limit` flag is critical — default is 262144 iterations, but if your table generation loops exceed that, the compiler will refuse to evaluate at compile time.

## Common Pitfalls & Gotchas

### 1. `constexpr` Does Not Guarantee Compile-Time Evaluation

```cpp
constexpr int square(int x) { return x * x; }

int main() {
    int runtime_val = 5;
    int result = square(runtime_val);  // This compiles! But runs at runtime.
    // The function is still valid, but the compiler generates runtime code.
}
```

**Fix:** Use `consteval` if you *must* have compile-time evaluation. Or force it by assigning to a `constexpr` variable: `constexpr int result = square(5);`

### 2. Floating-Point in `constexpr` Is Tricky on Embedded Targets

`constexpr` functions can use `double` and `float`, but the compiler's math library must support it. On ARM Cortex-M without hardware FPU, the compiler may silently fall back to runtime software floating-point, defeating the purpose. Always check the generated assembly.

**Fix:** Use fixed-point arithmetic or integer approximations in `constexpr` functions for embedded targets without FPU.

### 3. `consteval` Functions Cannot Be Called with Runtime Values

This seems obvious, but it bites when you refactor. If you change a `consteval` function's parameter from a constant to a runtime variable, the code won't compile. This can be frustrating during debugging when you want to test with dynamic values.

**Fix:** Create a `constexpr` wrapper that calls the `consteval` function, and use the wrapper for testing. Or use `if consteval` (C++23) to branch on context.

## Try It Yourself

1. **Compute a CRC-16 at compile time:** Write a `consteval` function that computes CRC-16-IBM (polynomial 0x8005) for a 32-byte configuration block. Verify the result matches a known-good implementation.

2. **Generate a gamma correction table:** For an LED driver with 8-bit PWM, create a `constexpr` array that maps linear brightness values (0–255) to gamma-corrected values (gamma=2.2). Use integer math only — no floating point.

3. **Force a compile-time error:** Write a `consteval` function that takes an integer and returns its square. Then try to call it with a runtime variable in a separate function. Observe the compiler error message and understand why it fails.

## Next Up

Tomorrow we'll explore `std::array` and `std::span` — fixed-size containers that give us bounds-safe, cache-friendly data structures without the overhead of `std::vector`. Perfect for embedded systems where dynamic allocation is forbidden. We'll see how they pair with `constexpr` to build compile-time initialized buffers that are both safe and efficient.
