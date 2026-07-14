---
title: "Day 14: MISRA C++ & AUTOSAR C++14 for Safety-Critical Firmware"
date: 2026-07-14
tags: ["til", "threat-modeling", "misra-cpp", "autosar"]
---

## What I Explored Today

Today I dug into the two dominant C++ coding standards for safety-critical embedded systems: MISRA C++:2008 and the newer AUTOSAR C++14 guidelines. While MISRA C has been the gold standard for C in automotive, medical, and aerospace firmware for decades, the C++ landscape is more fractured. MISRA C++:2008 was based on C++03, which is now ancient, and AUTOSAR C++14 (released in 2017) effectively supersedes it for modern projects. I spent the day mapping their rule sets against real-world firmware attack surfaces—buffer overflows, integer wraparound, and undefined behavior from dynamic dispatch.

## The Core Concept

Why do we need separate C++ standards when MISRA C already exists? Because C++ introduces features that are both powerful and dangerous in safety-critical contexts: virtual functions, exceptions, templates, and the Standard Template Library (STL). A firmware engineer might think "I'll just use `std::vector` for my sensor data buffer," but dynamic memory allocation is banned outright in both standards for systems without an OS (bare-metal). The core philosophy is *determinism*: every allocation, every cast, every function call must have predictable timing and memory behavior. Threat modeling enters because undefined behavior from a dangling pointer or a virtual call through a corrupted vtable is an attacker's entry point. AUTOSAR C++14 explicitly addresses this by forbidding dynamic memory, requiring RAII for resource management, and mandating that all templates be explicitly instantiated to avoid code bloat and ODR violations.

## Key Commands / Configuration / Code

### Rule Mapping: MISRA vs AUTOSAR

MISRA C++:2008 has 228 rules (98 required, 130 advisory). AUTOSAR C++14 has 397 rules, many derived from MISRA but updated for C++14 features like `constexpr` and `auto`. The critical difference: AUTOSAR allows `auto` (rule A2-10-1) but forbids `auto` for fundamental types to avoid ambiguity.

### Static Analysis Configuration (Cppcheck + Clang-Tidy)

```cpp
// cppcheck-suppress misra-cpp2008-5-0-1
// Explicitly disable MISRA rule for this one cast
uint32_t raw = 0xFF00;
uint8_t low = static_cast<uint8_t>(raw & 0xFF); // Compliant: MISRA 5-0-1
```

For Clang-Tidy with AUTOSAR checks:

```bash
# .clang-tidy configuration snippet
Checks: 'autosar-*,cppcoreguidelines-*'
CheckOptions:
  - key: autosar.A5-1-1
    value: 'LiteralSuffix'
  - key: autosar.M0-1-2
    value: 'NoReturnFromNonVoid'
```

### Code Example: Compliant Buffer (No Dynamic Allocation)

```cpp
#include <cstdint>
#include <array>

// AUTOSAR A18-5-1: No dynamic memory allocation
// MISRA C++ 18-4-1: Dynamic heap memory shall not be used

template <typename T, std::size_t N>
class RingBuffer {
public:
    // AUTOSAR A12-1-1: Use = default for trivial constructors
    RingBuffer() = default;

    bool push(T value) noexcept {
        if (full()) {
            return false; // No exceptions allowed (AUTOSAR A15-0-2)
        }
        buffer_[head_] = value;
        head_ = (head_ + 1) % N;
        if (head_ == tail_) {
            full_ = true;
        }
        return true;
    }

    bool pop(T& value) noexcept {
        if (empty()) {
            return false;
        }
        value = buffer_[tail_];
        tail_ = (tail_ + 1) % N;
        full_ = false;
        return true;
    }

private:
    std::array<T, N> buffer_{}; // AUTOSAR A18-1-1: Prefer std::array over C arrays
    std::size_t head_{0};
    std::size_t tail_{0};
    bool full_{false};

    bool empty() const noexcept { return (!full_ && (head_ == tail_)); }
    bool full() const noexcept { return full_; }
};

// Explicit template instantiation (AUTOSAR A14-7-1)
template class RingBuffer<uint8_t, 64>;
```

### Compiler Flags for Safety-Critical Builds

```makefile
# GCC for ARM Cortex-M with AUTOSAR-compliant flags
CXXFLAGS += -std=c++14 -fno-exceptions -fno-rtti -fno-threadsafe-statics
CXXFLAGS += -Werror -Wall -Wextra -Wpedantic
CXXFLAGS += -Wconversion -Wsign-conversion -Wfloat-equal
CXXFLAGS += -fstack-protector-strong --param ssp-buffer-size=4
```

## Common Pitfalls & Gotchas

1. **Assuming MISRA C++:2008 covers modern C++.** It doesn't. It was written for C++03. Using `auto`, `nullptr`, or `constexpr` will trigger false positives in MISRA checkers. AUTOSAR C++14 is the correct standard for any project using C++11 or later. I wasted two hours yesterday silencing MISRA warnings on `auto` before realizing the rule set mismatch.

2. **Forgetting that `std::array` is not a drop-in for C arrays in all contexts.** AUTOSAR A18-1-1 says prefer `std::array`, but rule A18-1-2 forbids using `std::array::data()` to obtain a raw pointer for pointer arithmetic. You must use iterators or range-based for loops. I've seen firmware fail safety reviews because `array.data()[i]` was flagged as a violation of MISRA 5-0-15 (pointer arithmetic).

3. **Ignoring the "no dynamic memory" rule in constructors.** Even if you never call `new`, the STL's `std::vector` default constructor may allocate on some implementations. AUTOSAR A18-5-1 is absolute: no heap allocation at any point. Use `std::array` or static pools. A colleague once had a bootloader crash because a `std::string` local variable triggered a heap allocation during startup.

## Try It Yourself

1. **Audit your current firmware project** for dynamic memory usage. Run `nm --print-size --size-sort firmware.elf | grep malloc` to find any hidden heap allocations. Then refactor one `std::vector` to a `std::array` with a static size.

2. **Configure Clang-Tidy with AUTOSAR C++14 checks** on a small module. Run `clang-tidy --checks='autosar-*' your_file.cpp -- -std=c++14` and fix the first 5 violations. Pay special attention to implicit conversions (AUTOSAR A4-5-1).

3. **Write a unit test** that verifies your ring buffer (from the code above) never throws an exception. Use `noexcept` specifiers and a test harness that catches `std::terminate` calls.

## Next Up

Tomorrow: **CERT C Secure Coding Standard: Key Rules for Embedded** — we'll cover the top 10 CERT C rules that directly prevent firmware vulnerabilities, including STR31-C (buffer overflow), INT30-C (integer overflow), and MSC15-C (information leakage).
