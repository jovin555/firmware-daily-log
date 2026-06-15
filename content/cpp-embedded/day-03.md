---
title: "Day 03: Smart Pointers in Embedded: unique_ptr Without Heap"
date: 2026-06-15
tags: ["til", "cpp-embedded", "unique-ptr", "ownership", "stack"]
---

## What I Explored Today

Today I dug into a pattern that feels almost heretical at first: using `std::unique_ptr` in embedded systems *without* dynamic memory allocation. The conventional wisdom says smart pointers are for heap-managed objects, but the C++ standard actually gives us a powerful tool for expressing ownership semantics on the stack and in static memory. I explored how custom deleters and `std::unique_ptr<T, Deleter>` let us use RAII for hardware resources, memory-mapped peripherals, and statically-allocated buffers — all without a single `new` or `malloc`.

## The Core Concept

The fundamental insight is that `std::unique_ptr` is not a "heap pointer" — it's an *ownership wrapper*. The default deleter calls `delete`, but that's just the default. The type signature `std::unique_ptr<T, Deleter>` accepts any callable object that satisfies `void(pointer)`. When you provide a custom deleter, the unique_ptr becomes a general-purpose RAII guard for any resource that has a "create" and "destroy" lifecycle.

In embedded systems, we constantly deal with resources that aren't heap-allocated:
- Memory-mapped peripheral registers (need to enable/disable clocks)
- DMA buffer pools (fixed-size, statically allocated)
- Mutex or spinlock handles (acquire/release)
- GPIO pin configurations (set/reset)

The pattern works because `std::unique_ptr` with a custom deleter stores the deleter as part of its type (unless the deleter is stateless, in which case EBO kicks in). The size overhead is exactly `sizeof(pointer)` for stateless deleters — zero runtime overhead over a raw pointer. This is critical for embedded where every byte matters.

## Key Commands / Configuration / Code

Here's the canonical pattern for a statically-allocated buffer with ownership semantics:

```cpp
#include <memory>
#include <cstdint>
#include <array>

// A custom deleter for a statically-allocated buffer pool
struct BufferPoolDeleter {
    void operator()(uint8_t* ptr) const noexcept {
        // In real code: return buffer to pool, clear ownership flag
        // For this example, we just mark it invalid
        *reinterpret_cast<volatile uint32_t*>(0xDEADBEEF) = 0;
    }
};

// Statically allocated buffer pool (no heap!)
alignas(64) std::array<uint8_t, 1024> buffer_pool;

// Factory function returns a unique_ptr with custom deleter
auto acquire_buffer() -> std::unique_ptr<uint8_t, BufferPoolDeleter> {
    // In real code: find a free buffer from pool
    // Here we just return a pointer into our static array
    return std::unique_ptr<uint8_t, BufferPoolDeleter>{
        buffer_pool.data(),
        BufferPoolDeleter{}
    };
}

// Usage in an ISR-safe context
void process_sensor_data() {
    auto buf = acquire_buffer();
    // buf behaves like a unique_ptr, but no heap involved
    // When buf goes out of scope, BufferPoolDeleter runs
    // No delete, no free — just our custom cleanup
}
```

For memory-mapped peripherals, the pattern is even cleaner:

```cpp
#include <memory>

// Memory-mapped UART registers (example)
struct UartRegs {
    volatile uint32_t DR;   // Data register
    volatile uint32_t SR;   // Status register
    volatile uint32_t CR;   // Control register
};

// Deleter that disables the peripheral clock
struct UartDeleter {
    void operator()(UartRegs* uart) const noexcept {
        // Disable UART clock in RCC register
        *reinterpret_cast<volatile uint32_t*>(0x40023800) &= ~(1U << 4);
        // Optional: gate the peripheral
    }
};

// Factory for a UART at fixed address 0x40011000
auto create_uart() -> std::unique_ptr<UartRegs, UartDeleter> {
    auto* uart = reinterpret_cast<UartRegs*>(0x40011000);
    // Enable clock
    *reinterpret_cast<volatile uint32_t*>(0x40023800) |= (1U << 4);
    // Configure UART...
    uart->CR = 0x2021;  // Enable, 8N1, 115200
    return std::unique_ptr<UartRegs, UartDeleter>{uart, UartDeleter{}};
}

void send_message() {
    auto uart = create_uart();
    uart->DR = 'H';
    // When uart goes out of scope, clock is disabled automatically
}
```

The key compiler flags to ensure no heap is used:

```bash
# For GCC ARM embedded
arm-none-eabi-g++ -std=c++17 -fno-exceptions -fno-rtti \
    -fno-threadsafe-statics -Os \
    -Wl,--gc-sections \
    -ffunction-sections -fdata-sections \
    -nostdlib -nodefaultlibs \
    main.cpp -o firmware.elf

# Verify no heap symbols
arm-none-eabi-nm firmware.elf | grep -E 'malloc|free|new|delete'
# Should return nothing
```

## Common Pitfalls & Gotchas

**1. Deleter must be stateless for zero overhead**
If your deleter has member variables, `sizeof(unique_ptr)` grows. Always prefer stateless functors or function pointers (though function pointers add `sizeof(void*)`). The `BufferPoolDeleter` above is empty — it costs nothing. If you need state, consider `std::unique_ptr<T, void(*)(T*)>` but measure the size impact.

**2. The "null deleter" trap**
Never pass `nullptr` as a deleter. The standard says calling `operator()` on a null deleter is undefined behavior. Always provide a valid callable. If you truly want a no-op deleter, create an empty struct:

```cpp
struct NoOpDeleter {
    void operator()(auto*) const noexcept {}
};
```

**3. Array types need `T[]` specialization**
For buffers, use `std::unique_ptr<uint8_t[], BufferPoolDeleter>`. The default `unique_ptr<T>` calls `delete` not `delete[]`, which is undefined for arrays. The array specialization calls `delete[]` — but with a custom deleter, you control the cleanup anyway. Still, match the type for clarity.

**4. Watch for implicit conversions in deleters**
If your deleter takes a base class pointer but you're managing a derived type, slicing can occur. Always match the exact pointer type in the deleter signature.

## Try It Yourself

1. **Implement a GPIO pin RAII wrapper**: Create a `std::unique_ptr<GpioPin, GpioDeleter>` where the deleter sets the pin to input mode (high-impedance) on destruction. Use a fixed memory address for the GPIO registers. Verify no heap allocation with `-nostdlib`.

2. **Build a statically-allocated ring buffer pool**: Design a pool of 4 ring buffers (each 256 bytes). Write a factory function that returns `std::unique_ptr<RingBuffer, PoolDeleter>` where the deleter returns the buffer to the pool. Ensure the deleter is stateless.

3. **Profile the size overhead**: On your target MCU, compare `sizeof(raw_pointer)` vs `sizeof(unique_ptr_with_stateless_deleter)` vs `sizeof(unique_ptr_with_function_pointer_deleter)`. Document the byte cost.

## Next Up

Tomorrow we dive into `constexpr` and `consteval` — compile-time computation that eliminates runtime overhead entirely. We'll explore how to compute CRC tables, lookup tables, and configuration constants at compile time, turning runtime work into zero-cost abstractions.
