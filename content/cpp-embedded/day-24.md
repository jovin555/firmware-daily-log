---
title: "Day 24: constexpr & consteval: Compile-Time Computation"
date: 2026-07-06
tags: ["til", "cpp-embedded", "constexpr", "compile-time"]
---

## What I Explored Today

Today I dug deep into `constexpr` and `consteval` — two C++ features that shift computation from runtime to compile time. For embedded systems, where every cycle and byte of RAM matters, this isn't just a nicety; it's a game-changer. I explored how to write functions that evaluate at compile time, how `consteval` enforces strict compile-time evaluation, and where these tools actually save resources in real firmware.

## The Core Concept

The fundamental problem in embedded C++ is that runtime computation costs you in two ways: CPU cycles (power, latency) and RAM (stack frames, temporary variables). `constexpr` lets you tell the compiler: "This function *can* run at compile time if the inputs are known." `consteval` goes further: "This function *must* run at compile time, period."

Why does this matter? Consider a lookup table for a sine wave. Without compile-time computation, you either:
- Precompute it manually (brittle, hard to maintain)
- Compute it at startup (wastes cycles and stack space)
- Hardcode a giant array (wastes flash)

With `constexpr`, you can write a function that generates the table at compile time. The resulting binary contains only the final values — no computation code, no runtime overhead. For a 256-entry sine table, that's 256 `float` values in flash, zero runtime cost.

The key insight: `constexpr` isn't about "making things faster" in the traditional sense. It's about moving the cost of computation to the build step, where it happens once, rather than every time the device boots or runs.

## Key Commands / Configuration / Code

### Basic `constexpr` Function

```cpp
// Compile-time power-of-two calculation
constexpr uint32_t power2(uint8_t exp) {
    return 1u << exp;  // Simple enough for any compiler
}

// Usage: value computed at compile time
constexpr uint32_t mask = power2(5);  // mask = 32 at runtime

// In embedded: bitmask for GPIO pins
constexpr uint32_t PIN_MASK = power2(3) | power2(5);  // Pins 3 and 5
```

### Complex `constexpr` — Sine Lookup Table

```cpp
#include <cmath>  // For std::sin (constexpr in C++23, but let's be portable)

// Manual constexpr sine approximation (Taylor series)
constexpr float sin_approx(float x) {
    // Only works for small x, but demonstrates the point
    return x - (x * x * x) / 6.0f + (x * x * x * x * x) / 120.0f;
}

// Generate lookup table at compile time
template<size_t N>
struct SineTable {
    float values[N];
    
    constexpr SineTable() : values{} {
        for (size_t i = 0; i < N; ++i) {
            float angle = (2.0f * 3.14159265f * i) / N;
            values[i] = sin_approx(angle);
        }
    }
};

// Usage: table is fully computed at compile time
constexpr SineTable<256> sine_table;

// Access in ISR or tight loop — no computation, just a lookup
float sample = sine_table.values[index & 0xFF];
```

### `consteval` — Enforcing Compile-Time

```cpp
// Must be evaluated at compile time
consteval uint32_t crc8_lookup(uint8_t polynomial) {
    uint32_t table[256] = {0};
    for (uint16_t i = 0; i < 256; ++i) {
        uint8_t crc = i;
        for (uint8_t j = 0; j < 8; ++j) {
            crc = (crc & 0x80) ? (crc << 1) ^ polynomial : (crc << 1);
        }
        table[i] = crc;
    }
    // Return something derived from the table
    return table[0xFF];  // Example: last entry
}

// This works: argument is a constant expression
constexpr auto crc_val = crc8_lookup(0x07);

// This fails to compile: x is not a constant expression
// uint8_t x = 0x07;
// auto bad = crc8_lookup(x);  // Error!
```

### Compile-Time CRC for Flash Integrity

```cpp
// Compute CRC over a fixed data set at compile time
consteval uint32_t compute_flash_crc() {
    // In real code, this would iterate over flash sections
    // For demo, we compute a simple checksum
    constexpr uint8_t firmware_data[] = {0x01, 0x02, 0x03, 0x04};
    uint32_t crc = 0xFFFFFFFF;
    for (auto byte : firmware_data) {
        crc ^= byte;
        for (int i = 0; i < 8; ++i) {
            crc = (crc >> 1) ^ (0xEDB88320 & -(crc & 1));
        }
    }
    return ~crc;
}

// Stored in flash, computed once at build time
constexpr uint32_t EXPECTED_CRC = compute_flash_crc();
```

## Common Pitfalls & Gotchas

### 1. `constexpr` Doesn't Guarantee Compile-Time

A `constexpr` function *can* run at runtime if called with non-constant arguments. This is subtle and dangerous in embedded:

```cpp
constexpr int add(int a, int b) { return a + b; }

int main() {
    int x = get_sensor_value();  // Runtime value
    int y = add(x, 5);           // Runs at runtime, not compile time!
}
```

**Fix:** Use `consteval` when you absolutely need compile-time evaluation, or always call `constexpr` functions with constant expressions.

### 2. Debugging Nightmares

Compile-time computation means no breakpoints, no stepping through. If your `constexpr` function has a bug, you get a cryptic compiler error or a wrong value in the binary.

**Fix:** Write a runtime version first, test it thoroughly, then add `constexpr`. Use `static_assert` to verify results:

```cpp
constexpr int square(int x) { return x * x; }
static_assert(square(3) == 9, "square(3) should be 9");
```

### 3. Flash Bloat from Template Instantiations

Every unique set of `constexpr` template arguments generates a separate instance. For large tables, this can explode flash usage.

**Fix:** Use `constexpr` arrays with runtime indexing (like the sine table example) rather than template metaprogramming for data generation.

## Try It Yourself

1. **CRC-8 Lookup Table:** Write a `consteval` function that generates a 256-entry CRC-8 lookup table for polynomial 0x07. Use `static_assert` to verify that `table[0] == 0` and `table[0x80] == 0x07` (for MSB-first).

2. **Compile-Time Bit Reversal:** Create a `constexpr` function that reverses the bits of a `uint8_t`. Then generate a 256-entry lookup table for fast bit reversal. Measure the flash savings compared to a runtime implementation.

3. **PWM Period Calculator:** Write a `consteval` function that takes a desired frequency (Hz) and timer clock speed (Hz), and returns the timer period value (ARR) and prescaler needed. Use it to compute PWM parameters for 1 kHz, 10 kHz, and 100 kHz with a 16 MHz clock.

## Next Up

Tomorrow we tackle `std::array` and `std::span` — fixed-size containers that bring safety and zero-overhead abstractions to embedded buffers. Say goodbye to raw C arrays and pointer/length pairs.
