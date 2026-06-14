---
title: "Day 02: RAII: Resource Acquisition Is Initialization for Hardware"
date: 2026-06-14
tags: ["til", "cpp-embedded", "raii", "resources", "ownership"]
---

## What I Explored Today

Today I dug into RAII (Resource Acquisition Is Initialization) applied to embedded hardware—specifically how to manage GPIO pins, SPI peripherals, and DMA channels without leaking resources or leaving hardware in undefined states. While RAII is often taught as a C++ memory management trick (smart pointers), its real power in embedded systems is guaranteeing that hardware resources are acquired, used, and released in a deterministic, exception-safe manner. I implemented a simple `GpioPin` wrapper and a `SpiTransaction` guard to see how constructor/destructor pairs eliminate manual init/deinit calls.

## The Core Concept

In bare-metal or RTOS-based embedded C++, you frequently deal with finite hardware resources: timer channels, ADC slots, interrupt vectors, or peripheral clocks. The classic C approach is to call `HAL_GPIO_Init()` at the start of a function and `HAL_GPIO_DeInit()` at the end, hoping every code path remembers to clean up. RAII flips this: the resource acquisition happens in the constructor, and the release happens automatically in the destructor. When the object goes out of scope—whether by normal return, early `break`, or an exception—the destructor runs. This is not just about convenience; it’s about correctness on resource-constrained systems where forgetting to release a DMA channel can lock up an entire data stream.

The key insight: RAII binds the lifetime of a hardware resource to the lifetime of a C++ object. This is especially valuable in embedded because hardware registers are global state. Without RAII, you rely on discipline. With RAII, the compiler enforces cleanup.

## Key Commands / Configuration / Code

Below is a practical RAII wrapper for a GPIO output pin on a typical ARM Cortex-M MCU (e.g., STM32). The wrapper acquires the pin in the constructor and releases it in the destructor.

```cpp
#include <cstdint>
#include <stm32f4xx_hal.h>  // vendor HAL

class GpioOutputPin {
public:
    // Acquire resource: configure the pin
    GpioOutputPin(GPIO_TypeDef* port, uint16_t pin)
        : port_(port), pin_(pin) {
        GPIO_InitTypeDef init = {
            .Pin       = pin_,
            .Mode      = GPIO_MODE_OUTPUT_PP,
            .Pull      = GPIO_NOPULL,
            .Speed     = GPIO_SPEED_FREQ_LOW
        };
        HAL_GPIO_Init(port_, &init);
        // Ensure known state: output low
        HAL_GPIO_WritePin(port_, pin_, GPIO_PIN_RESET);
    }

    // Release resource: deinitialize the pin
    ~GpioOutputPin() {
        HAL_GPIO_DeInit(port_, pin_);
    }

    // Non-copyable (hardware pins cannot be duplicated)
    GpioOutputPin(const GpioOutputPin&) = delete;
    GpioOutputPin& operator=(const GpioOutputPin&) = delete;

    // Movable: transfer ownership of the pin
    GpioOutputPin(GpioOutputPin&& other) noexcept
        : port_(other.port_), pin_(other.pin_) {
        other.port_ = nullptr;  // mark source as empty
        other.pin_ = 0;
    }

    GpioOutputPin& operator=(GpioOutputPin&& other) noexcept {
        if (this != &other) {
            // Release current resource first
            if (port_ != nullptr) {
                HAL_GPIO_DeInit(port_, pin_);
            }
            port_ = other.port_;
            pin_ = other.pin_;
            other.port_ = nullptr;
            other.pin_ = 0;
        }
        return *this;
    }

    void set(bool value) {
        HAL_GPIO_WritePin(port_, pin_,
            value ? GPIO_PIN_SET : GPIO_PIN_RESET);
    }

private:
    GPIO_TypeDef* port_;
    uint16_t pin_;
};

// Usage: RAII guarantees cleanup even on early return
void blink_led() {
    GpioOutputPin led(GPIOB, GPIO_PIN_0);
    led.set(true);
    // ... some work that might return early ...
    if (some_error) return;  // destructor runs here
    led.set(false);
}  // destructor runs here too
```

For a more advanced pattern, here’s a RAII guard for an SPI transaction that locks a bus and configures chip select:

```cpp
class SpiTransaction {
public:
    SpiTransaction(SPI_HandleTypeDef* hspi, GPIO_TypeDef* cs_port, uint16_t cs_pin)
        : hspi_(hspi), cs_port_(cs_port), cs_pin_(cs_pin) {
        // Acquire: assert chip select (active low)
        HAL_GPIO_WritePin(cs_port_, cs_pin_, GPIO_PIN_RESET);
    }

    ~SpiTransaction() {
        // Release: deassert chip select
        HAL_GPIO_WritePin(cs_port_, cs_pin_, GPIO_PIN_SET);
    }

    // Non-copyable, non-movable (transaction is a scope guard)
    SpiTransaction(const SpiTransaction&) = delete;
    SpiTransaction& operator=(const SpiTransaction&) = delete;

    uint8_t transfer(uint8_t data) {
        uint8_t rx;
        HAL_SPI_TransmitReceive(hspi_, &data, &rx, 1, HAL_MAX_DELAY);
        return rx;
    }

private:
    SPI_HandleTypeDef* hspi_;
    GPIO_TypeDef* cs_port_;
    uint16_t cs_pin_;
};

// Usage
void read_sensor() {
    SpiTransaction tx(&hspi2, GPIOB, GPIO_PIN_12);
    uint8_t cmd = 0x10;
    tx.transfer(cmd);
    uint8_t result = tx.transfer(0x00);
    // CS released automatically when tx goes out of scope
}
```

## Common Pitfalls & Gotchas

1. **Destructor order in complex objects** — If your class contains multiple RAII wrappers (e.g., a `UartPeripheral` that owns a `GpioOutputPin` for RTS), the destructors run in reverse construction order. This is usually correct, but if the UART deinit depends on the pin still being configured, you have a problem. Always design your resource dependencies so that the most dependent resource is constructed last.

2. **Move semantics with hardware** — Moving a RAII wrapper is tempting for transferring ownership (e.g., from a factory function), but you must leave the source object in a “null” state where its destructor is a no-op. Forgetting to set the source’s port pointer to `nullptr` will cause a double deinit when the source goes out of scope. Always test move operations with a debugger.

3. **Interrupt contexts** — Destructors that release hardware resources (like disabling a timer) may not be safe to call from an ISR. If your RAII object’s lifetime ends inside an interrupt handler, ensure the destructor does not call blocking HAL functions or functions that are not ISR-safe. Consider an explicit `release()` method for interrupt contexts, or use a scope guard that checks `__get_IPSR()`.

## Try It Yourself

1. **Wrap a UART handle** — Write an RAII class `UartChannel` that calls `HAL_UART_Init()` in the constructor and `HAL_UART_DeInit()` in the destructor. Add a `send(const uint8_t* data, size_t len)` method. Test that the destructor runs even when an exception is thrown mid-transmission.

2. **Implement a DMA channel guard** — Create a `DmaGuard` that reserves a DMA stream in the constructor and releases it in the destructor. Use the STM32 HAL’s `HAL_DMA_Init()` and `HAL_DMA_DeInit()`. Make the class non-copyable but movable. Verify that moving a `DmaGuard` correctly transfers ownership without double-free.

3. **Build a nested transaction logger** — Combine `SpiTransaction` with a `GpioOutputPin` for a debug LED. In a function, create an `SpiTransaction` and a `GpioOutputPin` (for a status LED). Confirm that the LED turns off only after the SPI transaction ends (destructor order: LED destructor runs first if constructed second).

## Next Up

Tomorrow: **Smart Pointers in Embedded: unique_ptr Without Heap** — We’ll explore how to use `std::unique_ptr` with a custom deleter to manage memory-mapped peripherals and static buffers, avoiding dynamic allocation entirely while still getting automatic cleanup.
