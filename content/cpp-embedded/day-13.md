---
title: "Day 13: Ring Buffer Implementation in Modern C++"
date: 2026-06-25
tags: ["til", "cpp-embedded", "ring-buffer", "template"]
---

## What I Explored Today

Ring buffers (circular buffers) are one of those data structures you reach for constantly in embedded systems—UART receive queues, ADC sample streams, inter-task messaging. Today I implemented a fixed-capacity ring buffer using modern C++ templates, with a focus on lock-free single-producer/single-consumer semantics and compile-time size guarantees. The result is a reusable, zero-overhead abstraction that fits neatly into bare-metal and RTOS environments alike.

## The Core Concept

A ring buffer is a fixed-size FIFO that wraps around: when the write pointer reaches the end, it loops back to the beginning. The key insight is that you don't need dynamic memory or linked lists—just a contiguous array, two indices (head and tail), and a modulo operation.

Why not just use `std::queue` or `std::deque`? Those allocate on the heap, which is a non-starter in most embedded contexts. Heap fragmentation, unpredictable latency, and OOM risk make them unsuitable for interrupt handlers or real-time paths. A ring buffer gives you deterministic O(1) push/pop with zero allocations.

The real trick is distinguishing "full" from "empty" when head == tail. The classic solution: waste one slot, or store a separate count. I prefer the count approach—it wastes no space and makes the API intuitive (`size()`, `full()`, `empty()`).

## Key Commands / Configuration / Code

Here's a production-grade ring buffer template I use in my projects. It's `constexpr`-friendly, supports trivially copyable types, and avoids volatile unless you're sharing across cores (that's a separate concern).

```cpp
#include <cstddef>
#include <array>
#include <type_traits>

template<typename T, std::size_t N>
class RingBuffer {
    static_assert(N > 0, "Ring buffer capacity must be positive");
    static_assert(std::is_trivially_copyable_v<T>,
                  "T must be trivially copyable for memcpy safety");

    std::array<T, N> buffer_{};
    std::size_t head_ = 0;  // next write position
    std::size_t tail_ = 0;  // next read position
    std::size_t count_ = 0; // number of elements stored

public:
    constexpr RingBuffer() = default;

    // Push: returns false if full (no overwrite)
    bool push(const T& item) noexcept {
        if (count_ == N) return false;
        buffer_[head_] = item;
        head_ = (head_ + 1) % N;
        ++count_;
        return true;
    }

    // Pop: returns false if empty
    bool pop(T& out) noexcept {
        if (count_ == 0) return false;
        out = buffer_[tail_];
        tail_ = (tail_ + 1) % N;
        --count_;
        return true;
    }

    // Peek at front without removing
    bool front(T& out) const noexcept {
        if (count_ == 0) return false;
        out = buffer_[tail_];
        return true;
    }

    // Bulk push from array (useful for DMA buffers)
    std::size_t push_bulk(const T* src, std::size_t len) noexcept {
        std::size_t pushed = 0;
        while (pushed < len && count_ < N) {
            buffer_[head_] = src[pushed];
            head_ = (head_ + 1) % N;
            ++count_;
            ++pushed;
        }
        return pushed;
    }

    // Bulk pop into array
    std::size_t pop_bulk(T* dst, std::size_t max_len) noexcept {
        std::size_t popped = 0;
        while (popped < max_len && count_ > 0) {
            dst[popped] = buffer_[tail_];
            tail_ = (tail_ + 1) % N;
            --count_;
            ++popped;
        }
        return popped;
    }

    [[nodiscard]] constexpr std::size_t size() const noexcept { return count_; }
    [[nodiscard]] constexpr bool empty() const noexcept { return count_ == 0; }
    [[nodiscard]] constexpr bool full() const noexcept { return count_ == N; }
    [[nodiscard]] constexpr std::size_t capacity() const noexcept { return N; }

    // Clear without deallocating
    constexpr void reset() noexcept {
        head_ = 0;
        tail_ = 0;
        count_ = 0;
    }
};
```

**Usage example** in a UART ISR context:

```cpp
// Global ring buffer for 256 bytes of UART RX
RingBuffer<uint8_t, 256> uart_rx_buffer;

void USART1_IRQHandler() {
    if (USART1->SR & USART_SR_RXNE) {
        uint8_t byte = USART1->DR;
        uart_rx_buffer.push(byte);  // Non-blocking, O(1)
    }
}

// In main loop:
void process_uart_data() {
    uint8_t byte;
    while (uart_rx_buffer.pop(byte)) {
        // Process byte without blocking ISR
    }
}
```

## Common Pitfalls & Gotchas

1. **Modulo is expensive on small MCUs.** On Cortex-M0 or AVR, `% N` compiles to a division. For power-of-two sizes, use `head_ = (head_ + 1) & (N - 1)` instead. I keep the modulo for clarity, but in production I add a `static_assert((N & (N - 1)) == 0, "N must be power of 2")` and use bitwise AND.

2. **Not marking ISR-shared variables volatile.** If your ring buffer is accessed from both an ISR and main context, the compiler may optimize away reads/writes. The fix: use `std::atomic` for head/tail/count, or mark them `volatile`. I prefer `std::atomic` with `memory_order_relaxed` for single-producer/single-consumer—it's portable and avoids the full memory barrier cost.

3. **Forgetting that push/pop are not thread-safe.** This implementation assumes one writer and one reader. If you have multiple producers, you need a mutex or a lock-free design with CAS operations. For most embedded scenarios (ISR → main), single-producer/single-consumer is sufficient and avoids all locking overhead.

## Try It Yourself

1. **Benchmark modulo vs. bitmask.** Implement two versions of the ring buffer—one with `% N` and one with `& (N-1)` for power-of-two sizes. Measure push/pop latency on your target MCU using a GPIO toggle and oscilloscope. You'll likely see 5-10 cycle savings per operation.

2. **Add an overwrite mode.** Modify the `push()` method to overwrite the oldest element when full (useful for real-time data logging). Hint: when `count_ == N`, advance `tail_` as well.

3. **Wrap it in a DMA-friendly interface.** Create a `DmaRingBuffer` subclass that exposes the underlying buffer pointer and a method to commit a variable number of bytes after a DMA transfer completes. This is exactly what you need for SPI or I2C slave receive.

## Next Up

Memory management is the next frontier. Tomorrow I'll dive into **placement new and static memory pools**—how to allocate objects from pre-allocated buffers without heap fragmentation, and why this pattern is essential for hard real-time systems. We'll build a fixed-size pool allocator that's deterministic and interrupt-safe.
