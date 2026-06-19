---
title: "Day 07: Type Traits & SFINAE for Hardware-Specific Code"
date: 2026-06-19
tags: ["til", "cpp-embedded", "type-traits", "sfinae"]
---

## What I Explored Today

Today I dove into compile-time type introspection with type traits and SFINAE (Substitution Failure Is Not An Error) to write hardware-specific code that adapts to different peripherals and architectures without runtime overhead. On embedded systems, where every cycle and byte matters, the ability to select the right implementation at compile time—based on the exact type of a hardware register, peripheral driver, or memory region—is a game-changer. I explored how `std::is_same`, `std::enable_if`, and custom type traits let me write generic template code that compiles to zero-overhead, target-specific machine code.

## The Core Concept

Embedded firmware often needs to handle multiple hardware variants: different GPIO pin configurations, register widths (8-bit vs 32-bit), or memory-mapped I/O with volatile semantics. Using `if` statements at runtime to check these differences wastes cycles and bloats code. Type traits and SFINAE move these decisions to compile time.

The key insight: **SFINAE allows a template to "fail gracefully"**—if a substitution produces invalid code, the compiler simply removes that overload from consideration rather than emitting an error. Combined with type traits (compile-time boolean queries about types), we can write multiple template specializations, and the compiler picks the one that matches the hardware type exactly. The result: the generated code contains only the instructions needed for that specific target, with zero runtime branching.

## Key Commands / Configuration / Code

Here's a practical example: a register accessor that adapts to different register widths and memory attributes.

```cpp
#include <type_traits>
#include <cstdint>

// Hardware register descriptor: wraps a volatile pointer with type info
template<typename T>
struct Register {
    volatile T* addr;
    static constexpr bool is_byte = sizeof(T) == 1;
    static constexpr bool is_word = sizeof(T) == 4;
};

// SFINAE: enable this overload only for 8-bit registers
template<typename T>
auto read_register(Register<T>& reg)
    -> typename std::enable_if<reg.is_byte, uint8_t>::type
{
    // Single LDRB instruction on ARM Cortex-M
    return *reg.addr;
}

// SFINAE: enable this overload only for 32-bit registers
template<typename T>
auto read_register(Register<T>& reg)
    -> typename std::enable_if<reg.is_word, uint32_t>::type
{
    // Single LDR instruction on ARM Cortex-M
    return *reg.addr;
}

// Custom type trait: detect if a type is a GPIO port
template<typename T>
struct is_gpio_port : std::false_type {};

// Specialize for our specific GPIO types
struct GPIOC;  // forward declaration
template<>
struct is_gpio_port<GPIOC> : std::true_type {};

// SFINAE: only enable for GPIO ports
template<typename T>
void configure_pin(T& port, uint8_t pin)
{
    static_assert(is_gpio_port<T>::value, "T must be a GPIO port type");
    // Hardware-specific configuration
    port.MODER &= ~(0x3 << (pin * 2));
    port.MODER |= (0x1 << (pin * 2));  // Output mode
}

// Usage example
struct GPIOC {
    volatile uint32_t MODER;
    volatile uint32_t OTYPER;
    // ... other registers
};

int main() {
    GPIOC port;
    Register<uint32_t> reg32{&port.MODER};
    Register<uint8_t>  reg8{reinterpret_cast<volatile uint8_t*>(0x40020000)};
    
    auto val32 = read_register(reg32);  // calls 32-bit version
    auto val8  = read_register(reg8);   // calls 8-bit version
    
    configure_pin(port, 5);  // compiles fine
    // configure_pin(reg32, 5);  // static_assert fails at compile time
}
```

**Key details:**
- `std::enable_if` with a boolean condition controls overload visibility
- `typename std::enable_if<...>::type` is the return type (or can be a dummy template parameter)
- Custom traits via template specialization let you tag your own hardware types
- `static_assert` provides clear error messages when wrong types are used

## Common Pitfalls & Gotchas

1. **Ambiguous overloads with multiple SFINAE conditions**  
   If two SFINAE-enabled overloads both match (e.g., `is_byte` and `is_word` for a 2-byte type), the compiler errors. Always ensure your conditions are mutually exclusive, or use `std::enable_if` with complementary conditions like `sizeof(T) == 1` vs `sizeof(T) != 1`.

2. **Forgetting `typename` before dependent types**  
   Inside template definitions, `std::enable_if<...>::type` is a dependent name. You *must* write `typename std::enable_if<...>::type` (or use C++14's `std::enable_if_t` alias). Missing `typename` causes a hard error, not SFINAE.

3. **SFINAE only works on immediate context of template declaration**  
   If the substitution failure occurs inside the function body (e.g., calling a non-existent member function), it's a hard error, not SFINAE. Only failures in the function signature (return type, parameter types, template parameter defaults) trigger SFINAE.

## Try It Yourself

1. **Write a type trait `is_volatile_register`** that detects whether a type has a `volatile` qualifier. Then create a SFINAE-enabled `write_register` that only compiles for volatile types.

2. **Implement a compile-time endianness adapter** using type traits: create a `to_little_endian<T>` function that swaps bytes only if `std::endian::native == std::endian::big`. Use `std::enable_if` to select the correct implementation.

3. **Build a generic bit-field accessor** for a 32-bit register: write a template `bit_field<T, uint8_t Offset, uint8_t Width>` that uses SFINAE to enforce `Offset + Width <= 32` at compile time, with a `static_assert` for clear error messages.

## Next Up

Tomorrow, we'll explore `std::variant` and `std::optional` for robust error handling in embedded C++. These types replace error codes and sentinel values with type-safe, zero-overhead alternatives that make your firmware's failure paths explicit and testable.
