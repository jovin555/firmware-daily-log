---
title: "Day 10: Operator Overloading for Register Bitfields"
date: 2026-06-22
tags: ["til", "cpp-embedded", "operator-overloading", "bitfields", "registers"]
---

## What I Explored Today

Today I tackled one of the most practical uses of operator overloading in embedded C++: making register bitfield access both safe and readable. After years of writing `REG->bits.field = 3` or worse, raw bit manipulation with `|=` and `&=~`, I finally sat down to build a proper bitfield proxy that uses `operator=` and `operator int()` to make register access look like natural struct member assignment. The result is code that reads like hardware documentation while still compiling to the same single `STR` instruction.

## The Core Concept

Hardware registers are not memory—they're volatile side-effect interfaces. Every read or write has consequences. The fundamental problem is that C++ bitfields (`struct { int a:3; int b:5; }`) don't guarantee bit layout, and they certainly don't guarantee single-instruction read-modify-write. The compiler is free to insert whatever padding it wants.

Operator overloading solves this by creating a proxy object that sits between your code and the actual register. When you write `reg.field = value`, the proxy's `operator=` performs an atomic read-modify-write using the exact mask and shift you specify. When you read `if (reg.field)`, the proxy's `operator int()` reads the register and extracts the bits. The key insight: the proxy is stateless—it only stores the register address, the mask, and the shift. All state lives in the hardware.

## Key Commands / Configuration / Code

Here's the pattern I settled on after several iterations. First, the register definition:

```cpp
#include <cstdint>
#include <type_traits>

// Bitfield proxy: stateless, zero-cost abstraction
template<typename RegType, RegType Mask, uint8_t Shift>
class Bitfield {
    static_assert(std::is_unsigned_v<RegType>, "Register type must be unsigned");
    static_assert(Mask != 0, "Mask cannot be zero");
    static_assert(Shift < sizeof(RegType) * 8, "Shift exceeds register width");
    
    volatile RegType* const reg;
    
public:
    // Constructor takes register address, stored as pointer
    explicit Bitfield(volatile RegType* r) : reg(r) {}
    
    // Read: extract bits, shift down, return as RegType
    operator RegType() const volatile {
        return (*reg & Mask) >> Shift;
    }
    
    // Write: clear field bits, then set new value
    Bitfield& operator=(RegType value) volatile {
        static_assert((value & ~(Mask >> Shift)) == 0, "Value exceeds field width");
        *reg = (*reg & ~Mask) | ((value << Shift) & Mask);
        return *this;
    }
    
    // Compound assignment for convenience
    Bitfield& operator|=(RegType value) volatile {
        *reg |= ((value << Shift) & Mask);
        return *this;
    }
    
    Bitfield& operator&=(RegType value) volatile {
        *reg &= ((value << Shift) & Mask) | ~Mask;
        return *this;
    }
};

// Register template: holds a pointer to the hardware address
template<typename RegType, RegType Addr>
class Register {
    static_assert(Addr != 0, "Null address not allowed");
    
    volatile RegType* const reg = reinterpret_cast<volatile RegType*>(Addr);
    
public:
    // Read/write the whole register
    operator RegType() const volatile { return *reg; }
    Register& operator=(RegType value) volatile { *reg = value; return *this; }
    
    // Create bitfield accessor for a specific field
    template<RegType Mask, uint8_t Shift>
    Bitfield<RegType, Mask, Shift> field() volatile {
        return Bitfield<RegType, Mask, Shift>(reg);
    }
};

// Example: STM32 USART Status Register (simplified)
// Address 0x40004400 + 0x00 = USART1 base, offset 0x00 for SR
using USART_SR = Register<uint32_t, 0x40004400>;

// Field definitions: mask and shift for each bitfield
constexpr uint32_t TXE_MASK  = (1 << 7);   // Bit 7: Transmit empty
constexpr uint32_t TXE_SHIFT = 7;
constexpr uint32_t RXNE_MASK = (1 << 5);   // Bit 5: Receive not empty
constexpr uint32_t RXNE_SHIFT = 5;
constexpr uint32_t TC_MASK   = (1 << 6);   // Bit 6: Transmission complete
constexpr uint32_t TC_SHIFT  = 6;

// Usage in application code
void send_byte(volatile USART_SR& sr, uint8_t data) {
    // Wait for TX buffer empty - reads like documentation
    while (!sr.field<TXE_MASK, TXE_SHIFT>()) {
        // Spin
    }
    // Write data to DR register (not shown for brevity)
}

bool data_available(volatile USART_SR& sr) {
    return sr.field<RXNE_MASK, RXNE_SHIFT>() != 0;
}
```

The beauty is that `sr.field<TXE_MASK, TXE_SHIFT>()` returns a temporary `Bitfield` object. The compiler elides the temporary entirely, inlines the read/write, and produces the exact same assembly as hand-coded bit manipulation—but with type safety and readability.

## Common Pitfalls & Gotchas

**1. Forgetting `volatile` on the proxy methods**
If you omit `volatile` from `operator int() const volatile` and `operator=`, the compiler will not generate proper memory barriers or prevent optimization of repeated reads. The hardware register can change between accesses, and without `volatile`, the compiler may cache the value in a register. Always mark both the stored pointer and the accessor methods as `volatile`.

**2. Mask/shift mismatch in compound assignments**
The `&=` operator is particularly tricky. You must preserve bits outside the field while clearing the field bits. The expression `((value << Shift) & Mask) | ~Mask` correctly clears the field and sets the new value, but only if `Mask` covers exactly the field bits. If your mask includes extra bits, you'll corrupt adjacent fields. Always verify masks with static assertions.

**3. Value range checking at compile time**
The `static_assert` in `operator=` catches value overflow at compile time, but only if the value is a constant expression. If you pass a runtime variable that exceeds the field width, you'll silently truncate. Consider adding a runtime assertion in debug builds: `assert((value & ~(Mask >> Shift)) == 0);`

## Try It Yourself

1. **Extend the pattern for multi-bit fields**: Modify the `Bitfield` class to support fields wider than the register type (e.g., a 12-bit field in a 32-bit register). Add a `value_mask` template parameter that represents `Mask >> Shift` for compile-time range checking.

2. **Add a `read_modify_write` method**: Implement a method that takes a lambda: `reg.field<M,S>().modify([](auto& v) { v |= 0x3; })`. This ensures atomic read-modify-write for complex operations.

3. **Benchmark against raw bit manipulation**: Write a test that toggles a GPIO pin 1 million times using your proxy and using direct `REG |= BIT` style. Compare the generated assembly with `-Os` and `-O2`. Verify zero-cost abstraction.

## Next Up: Interrupt Handlers in C++: Class Methods as Callbacks

Tomorrow, we'll tackle the problem that has plagued embedded C++ developers for decades: how to use a class member function as an interrupt handler. We'll explore static thunks, CRTP-based dispatch, and the `this` pointer trick that makes it work without virtual function overhead.
