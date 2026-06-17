---
title: "Day 05: std::array, std::span & Fixed-Size Containers"
date: 2026-06-17
tags: ["til", "cpp-embedded", "array", "span", "containers"]
---

## What I Explored Today

Today I dug into two of the most practical fixed-size container tools Modern C++ gives embedded engineers: `std::array` and `std::span`. While `std::vector` gets all the attention in desktop C++, on embedded targets we often can't afford dynamic allocation. `std::array` gives us a compile-time-sized, stack-allocated array with a proper STL interface, and `std::span` provides a lightweight, non-owning view over contiguous memory — perfect for passing around sensor buffers or register maps without copying. I spent the day converting some legacy C-style array code in our motor controller firmware and learned exactly where these containers shine and where they can bite you.

## The Core Concept

The fundamental problem with raw C-style arrays (`int arr[10]`) is that they decay to pointers when passed to functions, losing all size information. You end up passing the size separately, and one wrong `sizeof(arr)` later, you have a buffer overrun. Embedded systems are littered with bugs from manual size tracking.

`std::array<T, N>` solves this by bundling the size into the type. It's a zero-overhead wrapper — the compiler optimizes it down to the same memory layout as a C array, but you get `.size()`, `.begin()`, `.end()`, range-based for loops, and bounds checking in debug builds. No heap allocation, no vtable, no hidden cost.

`std::span<T>` (C++20) is the non-owning counterpart. It's a pointer + length pair that can view any contiguous sequence: `std::array`, C arrays, `std::vector`, or raw memory-mapped I/O regions. It doesn't own the data — it just provides safe, bounds-checked access. For embedded, this is huge: you can write a single function that accepts a `std::span<const uint8_t>` and pass it anything from a flash-stored lookup table to a DMA buffer.

## Key Commands / Configuration / Code

### Using std::array for fixed sensor data

```cpp
#include <array>
#include <cstdint>

// Motor phase current readings - 3 phases, compile-time fixed
std::array<float, 3> phase_currents = {0.0f, 0.0f, 0.0f};

// Access with bounds checking in debug mode
void update_currents(const std::array<float, 3>& currents) {
    // Safe iteration - no manual index management
    for (size_t i = 0; i < currents.size(); ++i) {
        phase_currents[i] = currents[i];  // at() throws on out-of-range
    }
    // Or use range-based for
    for (auto& val : phase_currents) {
        val = clamp(val, -10.0f, 10.0f);
    }
}
```

### std::span as a universal view for peripheral buffers

```cpp
#include <span>
#include <cstdint>

// SPI DMA buffer - could be std::array, C array, or memory-mapped
alignas(4) std::array<uint8_t, 256> spi_rx_buffer;

// Function accepts ANY contiguous buffer
void process_spi_data(std::span<const uint8_t> data) {
    // data.size() is always correct
    // data.data() gives raw pointer if needed for DMA
    for (auto byte : data) {
        // Process each byte safely
    }
}

// Usage - works with std::array, C arrays, or sub-ranges
void on_spi_complete() {
    process_spi_data(spi_rx_buffer);                    // Full buffer
    process_spi_data(spi_rx_buffer.first(64));          // First 64 bytes
    process_spi_data(spi_rx_buffer.subspan(128, 64));   // Bytes 128-191
}
```

### Compile-time size checking with templates

```cpp
template <typename T, size_t N>
void calibrate_sensors(std::array<T, N>& readings) {
    static_assert(N >= 3, "Need at least 3 sensor readings");
    // Compiler error if array is too small - caught at build time
    readings[0] = readings[1] = readings[2] = T{0};
}

// This won't compile:
// std::array<float, 2> bad;  calibrate_sensors(bad);  // ERROR
```

## Common Pitfalls & Gotchas

**1. std::array is an aggregate, not a C array**
You can't brace-initialize `std::array` the same way as C arrays in all contexts. `std::array<int, 3> arr = {1, 2, 3}` works, but `std::array<int, 3> arr = {1}` zero-initializes all elements — no partial initialization warning. Always explicitly initialize: `std::array<int, 3> arr = {1, 0, 0}`.

**2. std::span doesn't extend lifetime**
This is the most dangerous gotcha. `std::span` is a view — if the underlying data goes out of scope, your span dangles. I've seen this with temporary `std::array` objects created in function calls:

```cpp
std::span<const int> get_data() {
    std::array<int, 4> local = {1, 2, 3, 4};
    return local;  // BUG: local destroyed, span dangles
}
```

**3. Alignment surprises with std::array**
`std::array` doesn't guarantee alignment beyond the element type's natural alignment. For DMA buffers requiring 4-byte or 16-byte alignment, use `alignas()`:

```cpp
alignas(16) std::array<uint8_t, 64> dma_buffer;  // Correct
std::array<uint8_t, 64> wrong_buffer;             // May misalign
```

## Try It Yourself

1. **Convert a C-style ring buffer**: Take a legacy circular buffer implementation using `uint8_t buffer[256]` and manual size tracking. Rewrite it using `std::array<uint8_t, 256>` and `std::span` for the read/write interfaces. Verify the assembly output is identical.

2. **Write a generic CRC calculator**: Create a function `uint32_t crc32(std::span<const uint8_t> data)` that works with `std::array`, C arrays, and `std::vector`. Test it with a memory-mapped register region using `std::span(reinterpret_cast<const uint8_t*>(0x4000), 128)`.

3. **Static assertion challenge**: Write a template function that accepts `std::span<T>` and uses `if constexpr` to handle `std::span<const volatile uint8_t>` (memory-mapped registers) differently from regular memory. Use `std::is_const_v` and `std::is_volatile_v` to detect the difference.

## Next Up

Tomorrow we dive into **Templates for Zero-Cost Abstraction in Drivers** — how to write a single SPI driver template that works for any peripheral instance, any data width, and any clock configuration, all resolved at compile time with zero runtime overhead. We'll build a register access layer that makes your hardware abstraction truly cost-free.
