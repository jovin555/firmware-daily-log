---
title: "Day 11: Interrupt Handlers in C++: Class Methods as Callbacks"
date: 2026-06-23
tags: ["til", "cpp-embedded", "interrupts", "callbacks", "isr"]
---

## What I Explored Today

Today I tackled one of the most persistent pain points in embedded C++: wiring class member functions as interrupt service routines (ISRs). The fundamental problem is that ISRs require a plain C function pointer—a static address with no hidden `this` pointer—while class methods carry an implicit `this` that the hardware vector table cannot resolve. I explored three production-grade solutions: static member function trampolines, template-based dispatch with IRQ numbers, and the `std::function` + global instance pattern. Each has tradeoffs in code size, latency, and maintainability.

## The Core Concept

The core tension is between C++ object orientation and the bare-metal interrupt model. The CPU's vector table expects a fixed function address—typically a `void (*)(void)`—that it can call directly with no context. A non-static member function, however, has a hidden first parameter (`this`), making its calling convention incompatible. Worse, even if you cast the pointer, the ABI won't set up `this` correctly, leading to a crash or corruption.

The solution is to decouple the ISR entry point from the object instance. You provide a static function (which has no `this`) as the real ISR, and that static function forwards to the appropriate instance method. The forwarding mechanism is where the engineering decisions live: you can use a singleton, a lookup table keyed by interrupt number, or template metaprogramming to generate unique trampolines at compile time.

## Key Commands / Configuration / Code

### Pattern 1: Static Member Function Trampoline (Simplest)

This pattern uses a static member function as the ISR, which then calls a virtual or non-virtual method on a global instance. It's the go-to for single-instance drivers.

```cpp
class UartDriver {
public:
    void init() {
        // Register the static ISR
        NVIC_SetVector(UART0_IRQn, reinterpret_cast<uint32_t>(&UartDriver::isr_trampoline));
        NVIC_EnableIRQ(UART0_IRQn);
    }

    void handle_rx() {
        char c = UART0->DR;  // Read data register
        rx_buffer_.push(c);
    }

private:
    static void isr_trampoline() {
        // Forward to the singleton instance
        instance_.handle_rx();
    }

    static UartDriver instance_;  // One global instance
    RingBuffer<char, 64> rx_buffer_;
};

UartDriver UartDriver::instance_;
```

**Tradeoff:** Simple, but only works for one instance. If you need two UARTs, you need two separate classes or a different pattern.

### Pattern 2: Template-Based Dispatch (Zero Overhead)

Use a template parameter (the IRQ number) to generate unique static functions at compile time. This eliminates runtime lookup tables.

```cpp
template <int IRQn>
class GpioInterrupt {
public:
    void init() {
        NVIC_SetVector(static_cast<IRQn_Type>(IRQn),
                       reinterpret_cast<uint32_t>(&GpioInterrupt::isr));
        NVIC_EnableIRQ(static_cast<IRQn_Type>(IRQn));
    }

    void handle_interrupt() {
        uint32_t mask = GPIO->MIS;  // Masked interrupt status
        // Process pins...
        GPIO->ICR = mask;           // Clear interrupts
    }

private:
    static void isr() {
        // Each instantiation gets its own unique static function
        instance_.handle_interrupt();
    }

    static GpioInterrupt instance_;
};

// Instantiate for two different GPIO ports
template <> GpioInterrupt<GPIOA_IRQn> GpioInterrupt<GPIOA_IRQn>::instance_;
template <> GpioInterrupt<GPIOB_IRQn> GpioInterrupt<GPIOB_IRQn>::instance_;
```

**Tradeoff:** Each template instantiation creates a separate static function and global instance. No runtime overhead, but code size grows linearly with instances.

### Pattern 3: `std::function` with Global Instance (Flexible but Heavy)

For dynamic binding (e.g., runtime-configurable ISR handlers), use `std::function` to store a callable. This is common in RTOS task wrappers.

```cpp
class InterruptManager {
public:
    using Handler = std::function<void()>;

    void register_isr(IRQn_Type irq, Handler handler) {
        handlers_[irq] = std::move(handler);
        NVIC_SetVector(irq, reinterpret_cast<uint32_t>(&InterruptManager::dispatcher));
        NVIC_EnableIRQ(irq);
    }

private:
    static void dispatcher() {
        // Read the active IRQ number from the interrupt controller
        uint32_t active_irq = __get_IPSR() & 0x1F;
        if (instance_.handlers_[active_irq]) {
            instance_.handlers_[active_irq]();
        }
    }

    static InterruptManager instance_;
    std::array<Handler, 256> handlers_{};
};
```

**Tradeoff:** `std::function` may allocate on the heap (depending on implementation) and adds call overhead. Use only when runtime flexibility justifies the cost.

## Common Pitfalls & Gotchas

1. **Forgetting the `static` keyword on the trampoline.** Without `static`, the member function still expects `this`, and the compiler will generate a thunk that corrupts the stack. The linker won't warn you—the crash happens at runtime.

2. **Using `std::function` with a lambda that captures `this`.** A lambda capture stores a pointer to the object, but the lambda itself is a temporary. If the lambda goes out of scope, the `std::function` holds a dangling pointer. Always ensure the lambda (or its captures) lives as long as the ISR is registered.

3. **Assuming the vector table is writable.** On some Cortex-M MCUs, the vector table is in flash and requires remapping to RAM (via `SCB->VTOR`) before you can modify entries. Check your linker script—many default setups keep the table in flash, and writing to it silently fails.

## Try It Yourself

1. **Refactor a C-style ISR:** Take a legacy C project that uses a global variable and a plain function ISR. Convert it to a C++ class with a static member trampoline. Measure the change in code size (check the `.text` section in the map file).

2. **Implement a two-instance driver:** Use the template pattern to create two instances of a `TimerDriver` class, each handling a different timer peripheral (e.g., TIM2 and TIM3). Verify both ISRs fire independently by toggling separate GPIO pins.

3. **Profile `std::function` overhead:** Write a benchmark that toggles a pin in the ISR using (a) a direct static function, (b) a static trampoline, and (c) a `std::function`. Measure the latency with a logic analyzer or oscilloscope. Note the difference in worst-case interrupt latency.

## Next Up

Tomorrow, I'm diving into **State Machines in C++: `enum class` & `std::variant` FSMs**. We'll move beyond switch-case spaghetti and explore modern C++17 techniques for building type-safe, zero-overhead state machines that are testable and maintainable—perfect for protocol decoders, button debouncers, and task schedulers.
