---
title: "Day 25: std::array, std::span & Fixed-Size Containers"
date: 2026-07-07
tags: ["til", "cpp-embedded", "array", "span", "containers"]
---

## What I Explored Today

Today I dug into two of the most underutilized tools in the embedded C++ toolbox: `std::array` and `std::span`. After years of watching teams default to raw C arrays or `std::vector` (with all its heap allocation baggage), I finally committed to understanding when and why fixed-size containers win in embedded contexts. The short answer: almost always, when you know your bounds at compile time. `std::array` gives you a stack-allocated, bounds-checked alternative to `int buf[32]`, and `std::span` lets you pass slices of that data without copying or pointer arithmetic. Together, they eliminate entire classes of memory bugs.

## The Core Concept

The fundamental tension in embedded systems is between safety and performance. Raw arrays are fast but dangerous — no bounds checking, no size information when passed to functions. `std::vector` is safe but brings dynamic allocation, which is a non-starter in interrupt handlers, boot code, or memory-constrained devices.

`std::array` resolves this by being a fixed-size, stack-allocated container that knows its own size at compile time. It's a thin wrapper around a C-style array, but with iterators, `.size()`, `.data()`, and — crucially — `.at()` for bounds-checked access in debug builds. The compiler optimizes it down to the same assembly as a raw array, so there's zero runtime overhead.

`std::span` (C++20) is the missing link: a non-owning view over a contiguous sequence of objects. It doesn't allocate, doesn't copy, and doesn't own the data. It just points to a range with a known size. This is perfect for passing sub-buffers to DMA engines, sensor readout functions, or communication protocol parsers without slicing or pointer/length pairs.

The "why" is simple: in embedded systems, most buffers are fixed-size by design. A CAN message is 8 bytes. An ADC sample buffer is 1024 words. A UART TX ring buffer is 256 bytes. These are compile-time constants. Using `std::array` makes that explicit in the type system, and `std::span` lets you pass views into those buffers safely.

## Key Commands / Configuration / Code

**Basic `std::array` usage on a Cortex-M4:**

```cpp
#include <array>
#include <cstdint>

// Fixed-size ADC buffer - no heap, no VLA
std::array<uint16_t, 1024> adc_samples;

void process_adc_data() {
    // Fill from hardware (simplified)
    for (size_t i = 0; i < adc_samples.size(); ++i) {
        adc_samples[i] = read_adc_channel(i);  // operator[] - no bounds check
    }
    
    // Debug-safe access with bounds checking
    auto first = adc_samples.at(0);   // throws std::out_of_range if 0 >= 1024
    
    // Get raw pointer for DMA transfer
    uint16_t* raw_ptr = adc_samples.data();
    
    // Range-based for loop - works because of begin()/end()
    for (auto& sample : adc_samples) {
        sample = apply_gain(sample);
    }
}
```

**Using `std::span` to pass buffer views:**

```cpp
#include <span>
#include <array>

// Function that processes a view of data - no copy, no ownership
void send_to_uart(std::span<const uint8_t> data) {
    for (auto byte : data) {
        uart_send_byte(byte);  // blocking send for simplicity
    }
}

// Function that fills a span from hardware
void read_sensor_data(std::span<uint8_t> buffer) {
    // buffer.size() tells us exactly how many bytes to read
    for (size_t i = 0; i < buffer.size(); ++i) {
        buffer[i] = spi_transfer(0x00);  // dummy byte to clock in data
    }
}

// Usage in main
std::array<uint8_t, 64> tx_buffer = {0xAA, 0xBB, 0xCC};
std::array<uint8_t, 32> rx_buffer;

// Pass entire array as span
send_to_uart(tx_buffer);  // implicit conversion

// Pass a subrange - no copies, just a view
send_to_uart(std::span(tx_buffer).subspan(1, 2));  // sends 0xBB, 0xCC

// Fill from sensor
read_sensor_data(rx_buffer);  // rx_buffer now has 32 bytes of sensor data
```

**Compile-time size checking with templates:**

```cpp
template <size_t N>
void process_fixed_buffer(std::span<uint8_t, N> buffer) {
    static_assert(N <= 256, "Buffer too large for internal FIFO");
    // N is known at compile time - compiler can unroll loops
    for (size_t i = 0; i < N; ++i) {
        buffer[i] = transform(buffer[i]);
    }
}

// Usage - size is part of the type
std::array<uint8_t, 128> my_buffer;
process_fixed_buffer(my_buffer);  // N = 128, passes static_assert
```

## Common Pitfalls & Gotchas

1. **`std::span` does not extend the lifetime of the data it points to.** If you create a `std::span` from a local `std::array` and return it, you're returning a dangling pointer. The span is a view, not an owner. Always ensure the underlying storage outlives any span that references it.

2. **`std::array` on the stack can overflow.** A `std::array<uint32_t, 4096>` on a system with 8KB of stack will blow your stack. `std::array` lives in automatic storage (stack or static), not heap. For large buffers, consider `std::vector` with a custom allocator or a static pool. Always check your linker map for stack usage.

3. **`std::span` with dynamic extent vs. fixed extent.** `std::span<T>` (dynamic extent) stores a pointer and a size (8 bytes on 32-bit). `std::span<T, N>` (fixed extent) stores only a pointer (4 bytes) because the size is part of the type. If you know the size at compile time, use the fixed extent version — it's smaller and enables better optimization. But be careful: you can't assign a fixed-extent span to a dynamic-extent span implicitly without a conversion.

## Try It Yourself

1. **Refactor a raw array to `std::array`:** Take an existing C-style buffer like `uint8_t uart_rx_buf[64]` and convert it to `std::array<uint8_t, 64>`. Then add bounds-checked access with `.at()` in your debug build. Measure the code size difference (should be zero with optimizations enabled).

2. **Build a span-based protocol parser:** Create a function `bool parse_can_frame(std::span<const uint8_t, 8> frame)` that extracts ID, DLC, and data bytes from a CAN frame. Then test it with both a `std::array<uint8_t, 8>` and a subspan of a larger buffer. Verify that the compiler catches size mismatches.

3. **Stack usage analysis:** Write two versions of a function that processes a 256-byte buffer — one using `std::array` on the stack, one using `std::vector` with a static allocator. Use `-fstack-usage` in GCC to compare stack footprints. Note the difference in interrupt latency guarantees.

## Next Up

Tomorrow we tackle **Templates for Zero-Cost Abstraction in Drivers** — how to use template metaprogramming to create register access structs, hardware abstraction layers, and peripheral drivers that compile down to the same instructions as hand-written C, but with type safety and composability. We'll look at `constexpr` register maps, policy-based design for SPI/I2C/UART, and why `volatile` and templates are a match made in embedded heaven.
