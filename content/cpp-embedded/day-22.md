---
title: "Day 22: RAII: Resource Acquisition Is Initialization for Hardware"
date: 2026-07-04
tags: ["til", "cpp-embedded", "raii", "resources", "ownership"]
---

## What I Explored Today

Today I dug into RAII (Resource Acquisition Is Initialization) as it applies to embedded hardware resources. While most C++ developers associate RAII with heap memory management, in embedded systems it’s the go-to pattern for managing hardware peripherals, GPIO pins, interrupt handlers, DMA channels, and other finite resources. I explored how to wrap hardware resources in C++ objects so that acquisition happens in the constructor and release in the destructor—guaranteeing cleanup even through early returns or exceptions. This is not just good practice; it’s essential for deterministic, leak-free firmware.

## The Core Concept

RAII is often misunderstood as “using destructors to free memory.” The real insight is far more fundamental: **the lifetime of a resource is tied to the lifetime of an object**. When the object is constructed, the resource is acquired. When the object goes out of scope, the resource is automatically released. In embedded systems, this means:

- A `GPIO` object acquires a pin in its constructor and releases it in its destructor.
- A `SPI_Transaction` object claims the SPI bus in its constructor and releases it in its destructor.
- A `TimerChannel` object configures a hardware timer and disables it when destroyed.

The key benefit is **exception safety and scope-bound cleanup**. If a function returns early or throws, all local RAII objects are destroyed in reverse order of construction, releasing resources. Without RAII, you’d need manual cleanup at every return point—error-prone and verbose.

For hardware, RAII also solves the problem of **resource ownership tracking**. In bare-metal or RTOS environments, multiple tasks might try to use the same peripheral. RAII wrappers can enforce exclusive access at compile time (via move semantics) or runtime (via mutex acquisition in the constructor).

## Key Commands / Configuration / Code

Here’s a practical RAII wrapper for a UART peripheral on a Cortex-M MCU. The wrapper acquires the hardware in the constructor and releases it in the destructor.

```cpp
#include <cstdint>
#include <utility>  // for std::exchange

// Hardware register map (simplified)
struct UART_Regs {
    volatile uint32_t DR;      // Data register
    volatile uint32_t SR;      // Status register
    volatile uint32_t CR1;     // Control register 1
};

// RAII wrapper for a UART peripheral
class UART_Handle {
public:
    // Acquire the hardware resource
    explicit UART_Handle(uintptr_t base_addr) 
        : regs_(reinterpret_cast<UART_Regs*>(base_addr)) 
    {
        // Enable UART clock (platform-specific)
        RCC->APB2ENR |= RCC_APB2ENR_USART1EN;
        
        // Configure GPIO pins for UART (omitted for brevity)
        
        // Enable UART peripheral
        regs_->CR1 = 0x200C;  // UE=1, TE=1, RE=1
    }

    // Non-copyable: each UART is a unique resource
    UART_Handle(const UART_Handle&) = delete;
    UART_Handle& operator=(const UART_Handle&) = delete;

    // Movable: transfer ownership
    UART_Handle(UART_Handle&& other) noexcept
        : regs_(std::exchange(other.regs_, nullptr)) {}

    UART_Handle& operator=(UART_Handle&& other) noexcept {
        if (this != &other) {
            release();  // Release current resource
            regs_ = std::exchange(other.regs_, nullptr);
        }
        return *this;
    }

    // Release the hardware resource
    ~UART_Handle() {
        release();
    }

    // Send a byte (example operation)
    void send(uint8_t data) {
        while (!(regs_->SR & (1 << 7)));  // Wait for TXE flag
        regs_->DR = data;
    }

private:
    void release() {
        if (regs_) {
            // Disable UART
            regs_->CR1 = 0;
            // Disable clock (platform-specific)
            RCC->APB2ENR &= ~RCC_APB2ENR_USART1EN;
            regs_ = nullptr;
        }
    }

    UART_Regs* regs_;
};

// Usage example
void send_message() {
    UART_Handle uart(0x40013800);  // USART1 base address
    uart.send('H');
    uart.send('i');
    // uart is automatically released when function returns
}  // Destructor runs here, disabling UART and clock
```

For a more advanced pattern, here’s an RAII wrapper for a **critical section** (disable interrupts):

```cpp
class CriticalSection {
public:
    CriticalSection() 
        : primask_(__get_PRIMASK())  // Save interrupt state
    {
        __disable_irq();  // Acquire: disable all interrupts
    }

    ~CriticalSection() {
        __set_PRIMASK(primask_);  // Release: restore previous state
    }

    // Non-copyable, non-movable
    CriticalSection(const CriticalSection&) = delete;
    CriticalSection& operator=(const CriticalSection&) = delete;

private:
    uint32_t primask_;
};

// Usage: automatically restores interrupt state
void atomic_operation() {
    CriticalSection cs;
    // This code runs with interrupts disabled
    // Interrupts are re-enabled when cs goes out of scope
}
```

## Common Pitfalls & Gotchas

1. **Forgetting to disable copy semantics**: Hardware resources are unique. If you allow copying an RAII wrapper, two objects might try to release the same peripheral, causing double-free or undefined behavior. Always delete copy constructor/assignment, or implement move semantics with `std::exchange`.

2. **Destructor that throws**: Never throw from a destructor. If your resource release can fail (e.g., waiting for a bus to idle), handle the error silently or log it. A throwing destructor during stack unwinding will call `std::terminate()`.

3. **Order of destruction in complex objects**: If a class contains multiple RAII wrappers, they are destroyed in reverse order of declaration. Ensure that dependencies are respected. For example, if a DMA channel depends on a timer, declare the timer first so it’s destroyed last.

## Try It Yourself

1. **Wrap a GPIO pin**: Create an RAII class `GPIO_Pin` that configures a pin as output in the constructor and sets it to high-impedance input (safe state) in the destructor. Use it to blink an LED without manual cleanup.

2. **Implement a mutex guard**: Write a `MutexGuard` class that acquires a FreeRTOS mutex in its constructor and releases it in the destructor. Ensure it’s non-copyable and non-movable. Test with a shared resource between two tasks.

3. **Extend the UART example**: Add a `send_string(const char* str)` method that sends each character. Then, intentionally cause an early return in the middle of sending. Verify the UART is still properly released by checking the hardware state after the function exits.

## Next Up

Tomorrow: **Smart Pointers in Embedded: unique_ptr Without Heap**. We’ll explore how to use `std::unique_ptr` with custom deleters to manage hardware resources, all without dynamic memory allocation. You’ll see how to combine RAII with static storage and placement new for deterministic, zero-overhead resource management.
