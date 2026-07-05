---
title: "Day 23: Smart Pointers in Embedded: unique_ptr Without Heap"
date: 2026-07-05
tags: ["til", "cpp-embedded", "unique-ptr", "ownership", "stack"]
---

## What I Explored Today

I spent the day figuring out how to use `std::unique_ptr` in embedded systems without ever touching the heap. The conventional wisdom says smart pointers need dynamic allocation, but that's a misunderstanding of what `unique_ptr` actually does. It's not a memory allocator—it's an ownership model. Today I learned how to make `unique_ptr` work with static memory, placement new, and custom deleters, giving me RAII semantics on bare-metal firmware where `malloc` is banned.

## The Core Concept

The `std::unique_ptr` template has two type parameters: `T` (the pointee) and `Deleter` (defaults to `std::default_delete<T>`). The deleter is what calls `delete` or `delete[]`. If we replace that deleter with a no-op (or a static-resource recycler), `unique_ptr` becomes a pure ownership-transfer tool with zero dynamic allocation.

Why does this matter in embedded? Because ownership semantics are critical when you have:
- Hardware peripherals that must be exclusively owned by one context
- Statically allocated buffer pools shared between ISRs and main loop
- DMA descriptors that need clear lifetime boundaries

The `unique_ptr` gives you move semantics, automatic release on scope exit, and compile-time enforcement of single ownership—all without a single byte of heap. The trick is to separate *ownership management* from *memory management*.

## Key Commands / Configuration / Code

### Custom Deleter for Static Objects

```cpp
#include <memory>
#include <cstdint>

// A deleter that does nothing (for objects in static storage)
struct NoOpDeleter {
    void operator()(void*) const noexcept {
        // Intentionally empty: object lives in static memory
    }
};

// A static buffer for our "heap-free" object
alignas(alignof(uint32_t)) static uint8_t static_buffer[sizeof(uint32_t)];

// Factory function: constructs a uint32_t in static buffer, returns unique_ptr
auto make_static_uint32(uint32_t value) -> std::unique_ptr<uint32_t, NoOpDeleter> {
    auto* ptr = new (static_buffer) uint32_t(value);  // placement new
    return std::unique_ptr<uint32_t, NoOpDeleter>(ptr, NoOpDeleter{});
}

// Usage in a timer ISR
void timer_isr_handler() {
    static auto val = make_static_uint32(0);
    *val = read_hardware_register();
    // No delete needed — NoOpDeleter does nothing
}
```

### Pool-Based unique_ptr with Recycler

```cpp
template<typename T, size_t N>
class StaticPool {
    alignas(alignof(T)) uint8_t storage_[sizeof(T) * N];
    bool used_[N] = {false};
public:
    struct PoolDeleter {
        StaticPool* pool_;
        size_t index_;
        void operator()(T* ptr) const noexcept {
            ptr->~T();                // call destructor
            pool_->used_[index_] = false;  // mark free
        }
    };

    // Allocate from pool (no heap)
    auto acquire() -> std::unique_ptr<T, PoolDeleter> {
        for (size_t i = 0; i < N; ++i) {
            if (!used_[i]) {
                used_[i] = true;
                auto* ptr = new (&storage_[i * sizeof(T)]) T();
                return std::unique_ptr<T, PoolDeleter>(
                    ptr, PoolDeleter{this, i});
            }
        }
        return {nullptr, PoolDeleter{}};  // pool exhausted
    }
};

// Usage
StaticPool<DMA_Descriptor, 4> dma_pool;

void setup_dma() {
    auto desc = dma_pool.acquire();
    if (desc) {
        desc->src_addr = 0x20001000;
        // desc automatically returned to pool when scope exits
    }
}
```

### Transferring Ownership Between Contexts

```cpp
using UniqueTimer = std::unique_ptr<Timer_Regs, NoOpDeleter>;

UniqueTimer claim_timer(Timer_Regs* base_addr) {
    // Timer_Regs is memory-mapped, not dynamically allocated
    return UniqueTimer(base_addr, NoOpDeleter{});
}

void init_system() {
    UniqueTimer timer1 = claim_timer(reinterpret_cast<Timer_Regs*>(0x40000000));
    // Ownership transferred to timer1
    // No heap, no malloc, no free
}
```

## Common Pitfalls & Gotchas

**1. Forgetting to call the destructor in custom deleters**
When you use placement new, the compiler won't automatically call the destructor. Your custom deleter *must* call `ptr->~T()` before releasing the memory back to the pool. The `NoOpDeleter` above is safe only for trivially destructible types (like `uint32_t`). For complex objects, you need a proper destructor call.

**2. Misalignment in static buffers**
Placement new requires properly aligned storage. Use `alignas(alignof(T))` on your static buffer, or risk undefined behavior on ARM Cortex-M (which can silently misbehave with unaligned access). The `std::aligned_storage` template is your friend here.

**3. Assuming `unique_ptr` implies heap allocation**
The standard library's `default_delete` calls `delete`, which on most embedded toolchains maps to `free()`. But the `unique_ptr` template itself has zero knowledge of where memory came from. Replace the deleter, and you decouple ownership from allocation entirely. This is a common source of confusion when reviewing code.

**4. Copying instead of moving**
`unique_ptr` is move-only. If you accidentally copy it (e.g., passing by value to a function that doesn't take rvalue references), the compiler will error. This is a *feature*—it prevents accidental aliasing of hardware resources. Embrace the compiler errors.

## Try It Yourself

1. **Build a static pool for interrupt-safe message passing**: Create a `StaticPool` of 8-byte messages. Use `unique_ptr` with a custom deleter to transfer ownership from an ISR to the main loop. Ensure the deleter disables interrupts during the pool release.

2. **Wrap a memory-mapped peripheral**: Define a `unique_ptr` with `NoOpDeleter` for a UART or GPIO register block. Write a factory function that returns the `unique_ptr` from a fixed address. Verify that moving the pointer transfers exclusive access.

3. **Benchmark the overhead**: On your target MCU (e.g., STM32F4), compare the code size and cycle count of `unique_ptr` with custom deleter vs. raw pointer with manual `new`/`delete`. You'll likely find the `unique_ptr` version is smaller and deterministic.

## Next Up

Tomorrow: **constexpr & consteval: Compile-Time Computation** — We'll push computations to compile time, eliminate runtime overhead, and explore how `consteval` functions can validate hardware configurations before the firmware ever runs.
