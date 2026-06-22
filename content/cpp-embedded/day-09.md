---
title: "Day 09: Lambda Expressions & Callbacks in Firmware"
date: 2026-06-22
tags: ["til", "cpp-embedded", "lambda", "callbacks"]
---

## What I Explored Today

Today I dove into lambda expressions in C++ and how they can replace traditional function pointers and callback mechanisms in embedded firmware. I’ve been burned before by callback spaghetti—global function pointers, opaque `void*` contexts, and hard-to-trace control flow. Lambdas, especially when combined with `std::function` or template parameters, offer a type-safe, inline, and often more efficient way to handle interrupts, timers, and peripheral events. I tested this on an STM32L4 target with GCC 12.2 and `-Os` to see the real codegen impact.

## The Core Concept

In embedded C, callbacks are typically implemented as function pointers:

```c
typedef void (*button_callback_t)(uint8_t pin);
void register_button_callback(button_callback_t cb);
```

This works, but it’s clunky. You need a separate function, often with a `void*` context parameter to carry state. That context pointer is error-prone—cast it wrong and you get undefined behavior.

Lambdas solve this by letting you define the callback inline, capturing local variables by value or reference. The compiler can often inline the lambda entirely, eliminating function call overhead. For firmware, this means:

- **Zero-cost abstraction** when used with templates (no vtable, no heap allocation)
- **Type safety** — no more `void*` casts
- **Locality** — callback logic lives next to where it’s registered

The key insight: a lambda is syntactic sugar for a functor (a class with `operator()`). The capture list becomes member variables. The compiler generates a unique type for each lambda, which is why `auto` or templates are needed to store them.

## Key Commands / Configuration / Code

### Basic Lambda as Callback

Here’s a timer callback using a lambda, stored as a `std::function` (heap-free if the lambda is small enough for small-buffer optimization):

```cpp
#include <functional>

class Timer {
public:
    // Store callback as std::function
    void setCallback(std::function<void()> cb) {
        callback_ = cb;
    }

    void trigger() {
        if (callback_) callback_();
    }

private:
    std::function<void()> callback_;
};

// Usage
Timer t;
int toggle_count = 0;
t.setCallback([&toggle_count]() {
    toggle_count++;
    GPIO_TogglePin(LED_PIN);
});
```

**Warning:** `std::function` may allocate on the heap for large lambdas. On constrained targets, prefer templates.

### Template-Based Lambda (Zero Overhead)

```cpp
template<typename Callback>
class Button {
public:
    void attach(Callback&& cb) {
        callback_ = std::forward<Callback>(cb);
    }

    void handleInterrupt() {
        if (callback_) callback_(pin_);
    }

private:
    Callback callback_;
    uint8_t pin_ = 0;
};

// Usage — no heap, no vtable
Button<decltype([](uint8_t p){ /* handle */ })> btn;
btn.attach([](uint8_t p) {
    if (p == 0) startMotor();
});
```

The `decltype` trick lets you specify the lambda’s unique type. For production, use `auto` and CTAD (C++17):

```cpp
auto btn = Button([](uint8_t p){ /* ... */ });
```

### Capturing Hardware Registers

Lambdas can capture references to hardware registers safely:

```cpp
auto& usart = USART1->DR;
auto tx_byte = [&usart](uint8_t data) {
    while (!(USART1->SR & USART_SR_TXE));
    usart = data;
};
```

### Using with Interrupt Handlers (IRQ)

On Cortex-M, you can’t pass a lambda directly to the vector table (it expects a plain function pointer). But you can use a lambda to initialize a static function pointer:

```cpp
// In some init function
static void (*irq_handler)();

void init_timer_irq() {
    int overflow_count = 0;
    static auto handler = [&overflow_count]() {
        overflow_count++;
        // clear interrupt flag
        TIM1->SR &= ~TIM_SR_UIF;
    };
    irq_handler = +handler;  // + forces decay to function pointer
    // Set vector table entry to irq_handler
}
```

The unary `+` operator forces the non-capturing lambda to decay to a function pointer. If the lambda captures, this won’t compile—a good safety check.

## Common Pitfalls & Gotchas

1. **Capturing by reference in deferred callbacks** — If the lambda outlives the captured variable, you get a dangling reference. In firmware, this happens when you queue a lambda for a timer but the local variable goes out of scope. Always capture by value (`[=]`) or use `std::shared_ptr` for heap-allocated state.

2. **`std::function` heap allocation** — On MCUs with <64KB RAM, `std::function` can silently allocate on the heap. If your lambda is larger than the small-buffer optimization (typically 16-32 bytes), you get a `bad_alloc` at runtime. Prefer template parameters or `etl::function` from the Embedded Template Library.

3. **Lambda size explosion** — Each lambda has a unique type. If you define 100 lambdas in a header, you get 100 different types. This can bloat binary size. Use `auto` parameters or type-erased wrappers if you have many similar callbacks.

4. **Recursive lambdas** — You can’t capture a lambda by reference before it’s defined. Use `std::function` and capture by reference after construction, or use a Y-combinator (overkill for most firmware).

## Try It Yourself

1. **Convert a legacy C callback** — Take an existing interrupt-driven UART driver that uses `void (*rx_callback)(uint8_t byte, void* ctx)`. Rewrite it to accept a lambda. Measure the code size difference with `-Os`.

2. **Build a debounced button class** — Create a `DebouncedButton` template that takes a lambda for the press handler. Use a timer to sample the pin at 10ms intervals. The lambda should capture a `bool&` to indicate press state.

3. **Profile lambda vs function pointer** — On your dev board, set up a GPIO toggle in a loop: once with a direct function call, once with a function pointer, once with a lambda. Use a logic analyzer to measure the overhead. Note: with `-Os`, the lambda should be identical to the direct call.

## Next Up

Tomorrow: **Operator Overloading for Register Bitfields** — We’ll build a type-safe, zero-overhead bitfield abstraction using `operator|`, `operator&`, and `operator~`. No more magic hex constants or `#define` macros.
