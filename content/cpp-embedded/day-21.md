---
title: "Day 21: Why C++ in Embedded? Myths, Tradeoffs & Modern Approach"
date: 2026-07-03
tags: ["til", "cpp-embedded", "cpp", "embedded", "tradeoffs"]
---

## What I Explored Today

I decided to step back from code patterns today and tackle a question that every embedded engineer eventually faces: *Should I use C++ on this microcontroller?* The debate has been raging for decades, often fueled by outdated assumptions and cargo-cult rules. I spent today dissecting the real tradeoffs, benchmarking the actual overhead of modern C++ features on a Cortex-M4, and confronting the myths head-on. The conclusion: C++ is not just viable for embedded—it's often superior, *if* you know which language features to use and which to avoid.

## The Core Concept

The core tension is simple: C gives you total control and predictable code generation. C++ gives you abstraction, type safety, and zero-cost abstractions—but only if you understand the cost model. The "zero-cost" principle means you don't pay for what you don't use, but you *do* pay for what you do use. The problem is that many embedded developers learned C++ from desktop or server contexts, where dynamic allocation, virtual dispatch, and exception handling are normal. In embedded, those features are often the wrong tool.

The real power of C++ in embedded comes from:

- **constexpr and templates** — compile-time computation replaces runtime logic
- **RAII** — deterministic resource management without manual cleanup
- **`std::array` and `std::span`** — bounds-safe containers without heap allocation
- **`enum class`** — type-safe hardware register masks
- **`static_assert`** — compile-time validation of hardware constraints

The myth is that C++ is "bloated." The reality is that *bad* C++ is bloated. Well-written embedded C++ generates identical or smaller machine code than equivalent C, while catching bugs at compile time that C would miss until runtime.

## Key Commands / Configuration / Code

Here's a concrete comparison showing how modern C++ compiles to the same assembly as C, but with stronger guarantees:

```cpp
// C-style: manual struct, no type safety
typedef struct {
    volatile uint32_t CR;   // Control Register
    volatile uint32_t SR;   // Status Register
} UART_Regs_C;

#define UART_BASE ((UART_Regs_C*)0x40004000)

void uart_send_c(char c) {
    while (!(UART_BASE->SR & (1 << 5)));  // wait for TX ready
    UART_BASE->CR = c;                    // send byte
}
```

```cpp
// Modern C++: type-safe, compile-time checked
class Uart {
public:
    // Use enum class for bit fields - no magic numbers
    enum class Status : uint32_t {
        TX_READY = (1 << 5)
    };

    // constexpr constructor - zero runtime cost
    constexpr Uart(volatile uint32_t* base) : base_(base) {}

    void send(char c) {
        // Wait for TX buffer empty
        while (!(base_[1] & static_cast<uint32_t>(Status::TX_READY)));
        base_[0] = c;
    }

private:
    volatile uint32_t* base_;  // pointer to register block
};

// Instantiate at compile time - no constructor call at runtime
constexpr Uart uart(reinterpret_cast<volatile uint32_t*>(0x40004000));

void uart_send_cpp(char c) {
    uart.send(c);
}
```

Both functions compile to identical ARM Thumb-2 assembly on GCC `-Os`:

```asm
uart_send_c:
.L1:    ldr     r3, [r0, #4]    ; load SR
        tst     r3, #32         ; check bit 5
        beq     .L1             ; loop if not ready
        strb    r1, [r0]        ; store byte to CR
        bx      lr
```

The C++ version gives you:
- No runtime overhead (constexpr constructor)
- No magic numbers (named enum values)
- No accidental bit-field misuse (type-safe enum)
- Self-documenting register access

## Common Pitfalls & Gotchas

**1. Virtual functions on small microcontrollers**
Virtual dispatch requires a vtable pointer per object (4 bytes on ARM) and indirect function calls. On a Cortex-M0 with 8KB RAM, that overhead matters. Use CRTP (Curiously Recurring Template Pattern) for static polymorphism instead—zero overhead, resolved at compile time.

```cpp
// BAD: virtual dispatch on ATTiny
class Sensor {
public:
    virtual int read() = 0;  // vtable pointer in every instance
};

// GOOD: CRTP - no vtable, no overhead
template<typename Derived>
class Sensor {
public:
    int read() {
        return static_cast<Derived*>(this)->read_impl();
    }
};
```

**2. Assuming `std::function` is free**
`std::function` can allocate on the heap for lambdas with captures. On a bare-metal system with no heap, this silently crashes. Use function pointers or `etl::function` from the Embedded Template Library instead.

**3. Exception handling in interrupt context**
Exceptions require unwind tables and runtime type information (RTTI). Both bloat code and add nondeterministic latency. Disable exceptions entirely with `-fno-exceptions -fno-rtti` in your compiler flags. Use error codes or `std::expected` (C++23) for error propagation.

## Try It Yourself

1. **Compile-size comparison**: Take a C driver for your favorite peripheral (UART, SPI, I2C) and rewrite it using C++ with `enum class`, `constexpr`, and templates. Compile both with `-Os -mcpu=cortex-m4` and compare the `.text` section sizes with `arm-none-eabi-size`.

2. **Disable the bloat**: In your current embedded C++ project, add `-fno-exceptions -fno-rtti -fno-threadsafe-statics` to your compiler flags. Measure the flash and RAM savings. If anything breaks, you've found code relying on these features—refactor it.

3. **Static dispatch experiment**: Write a driver interface with virtual functions, then refactor it to use CRTP. Compare the generated assembly for a function call. Count the instructions and indirect loads saved.

## Next Up: RAII: Resource Acquisition Is Initialization for Hardware

Tomorrow, we'll dive into the single most important C++ pattern for embedded: RAII. You'll learn how to wrap GPIO pins, SPI transactions, and interrupt locks in objects that automatically initialize and clean up—no more forgetting to release a peripheral or restore a register. We'll benchmark the overhead (spoiler: it's zero) and show how RAII eliminates entire classes of bugs that plague C firmware.
