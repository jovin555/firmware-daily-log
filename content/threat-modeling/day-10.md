---
title: "Day 10: Integer Overflows & Underflows in Firmware Arithmetic"
date: 2026-07-10
tags: ["til", "threat-modeling", "integer-overflow"]
---

## What I Explored Today

Integer overflows and underflows remain one of the most pervasive—and most overlooked—classes of vulnerabilities in embedded firmware. Today I dug into how arithmetic wrapping in C and C++ can silently corrupt sensor readings, bypass authentication checks, and even trigger buffer overflows in memory-constrained systems. I focused on real-world patterns: what happens when a 16-bit ADC value gets multiplied by a calibration constant, or when a timer counter wraps past zero in a safety-critical loop. The key takeaway: the C standard defines unsigned overflow as well-defined wrapping, but signed overflow is undefined behavior—and both can be weaponized.

## The Core Concept

Integer overflow occurs when an arithmetic operation produces a result that exceeds the maximum value representable by the integer type. Underflow is the same phenomenon in the negative direction. In firmware, the consequences are rarely just a wrong number—they cascade.

Consider a typical embedded scenario: you read a 12-bit ADC value (0–4095) into a `uint16_t`. You multiply it by a calibration factor stored in a `uint16_t`. The product, say `4000 * 200 = 800,000`, overflows a `uint16_t` (max 65535). The result wraps to `800,000 % 65536 = 34,240`. Your PID controller now thinks the temperature is 34,240 units instead of 800,000—a completely different control regime. If that value feeds into a memory allocation or a buffer index, you've got a potential write-what-where primitive.

The deeper issue is that C and C++ treat integer overflow differently based on signedness:
- **Unsigned overflow**: well-defined, wraps modulo 2^N (where N is the bit width). This is predictable but often wrong.
- **Signed overflow**: undefined behavior. The compiler can assume it never happens and optimize away entire branches. This has caused real-world failures in safety-critical systems (e.g., the 1996 Ariane 5 explosion traced to a signed integer overflow in a conversion routine).

In threat modeling, integer overflows are a root cause for:
- **Buffer overflows**: a length field wraps, causing `malloc(n)` to allocate a small buffer, then a subsequent `memcpy` writes far more data.
- **Logic bypass**: `if (x + y < LIMIT)` where `x + y` wraps to a small value, passing the check.
- **Denial of service**: infinite loops caused by counter underflow.

## Key Commands / Configuration / Code

### Compiler flags to catch overflows at compile time (GCC/Clang)
```c
// Enable warnings for problematic integer operations
// -Wstrict-overflow=2 warns when compiler assumes signed overflow won't happen
// -Wconversion catches implicit truncation
// -fsanitize=undefined catches signed overflow at runtime
// Compile with: gcc -Wstrict-overflow=2 -Wconversion -fsanitize=undefined -O2 firmware.c
```

### Safe arithmetic with saturation (C example)
```c
#include <stdint.h>
#include <limits.h>

// Saturating addition for uint16_t — clamps to max instead of wrapping
uint16_t sat_add_u16(uint16_t a, uint16_t b) {
    uint16_t sum = a + b;
    // If sum wrapped (sum < a), clamp to UINT16_MAX
    if (sum < a) {
        return UINT16_MAX;
    }
    return sum;
}

// Safe multiplication with overflow detection (returns 1 on overflow)
int safe_mul_u32(uint32_t a, uint32_t b, uint32_t *result) {
    if (a > UINT32_MAX / b) {
        return -1; // overflow would occur
    }
    *result = a * b;
    return 0;
}
```

### Runtime sanitizer for embedded testing (using GCC/Clang)
```c
// In your test harness, compile with:
// gcc -fsanitize=undefined -fsanitize=integer-divide-by-zero -g -O1 firmware_test.c
// Then run: ./a.out
// UBSan will print a stack trace on any signed overflow or illegal shift

// Example that triggers UBSan:
int32_t test_overflow(void) {
    int32_t x = INT32_MAX;
    return x + 1; // UBSan catches this at runtime
}
```

### MISRA-C:2012 rule for integer operations (Rule 10.3, 12.7)
```c
// MISRA requires that the type of the result of an arithmetic operation
// must be able to represent all possible values. Use explicit casts and
// wider intermediate types:
uint16_t adc_raw = 4000;
uint16_t calib = 200;
// Violation: product may overflow uint16_t
// uint16_t result = adc_raw * calib;

// Compliant: use uint32_t intermediate
uint32_t temp = (uint32_t)adc_raw * (uint32_t)calib;
if (temp > UINT16_MAX) {
    // handle saturation or error
}
uint16_t result = (uint16_t)temp;
```

## Common Pitfalls & Gotchas

**1. Assuming `int` is large enough for intermediate results**
In C, integer promotion rules mean that `uint16_t + uint16_t` is performed as `int` (if `int` can represent all `uint16_t` values). On 32-bit platforms, `int` is 32 bits, so this works. On 8-bit or 16-bit MCUs (e.g., PIC, AVR), `int` is 16 bits—and the same promotion can overflow. Always cast to a known-wide type explicitly.

**2. Forgetting that loop counters can underflow**
A `for (uint8_t i = 10; i >= 0; i--)` is an infinite loop because `i` wraps from 0 to 255. This is a classic firmware bug that can hang a watchdog-dependent system. Use `int` for loop counters or check for `i == 0` before decrementing.

**3. Trusting compiler optimizations with signed overflow**
If you write `if (x + 100 > x)` to check for overflow, the compiler may optimize it away because signed overflow is undefined. The compiler assumes `x + 100` is always greater than `x` (since overflow can't happen per the standard). Use `__builtin_add_overflow` (GCC/Clang) or a manual check with `> UINTxx_MAX - increment`.

## Try It Yourself

1. **Find the overflow in a sensor driver**: Take a typical I2C accelerometer driver that reads 16-bit raw values and multiplies by a sensitivity factor stored as `uint16_t`. Insert a test case where the product exceeds 65535. Does your firmware handle it? Add a saturation check.

2. **Enable UBSan on your firmware test suite**: If you use GCC or Clang, add `-fsanitize=undefined` to your test build. Run your unit tests and see how many signed overflows you've been ignoring. Fix the top three.

3. **Write a safe arithmetic wrapper**: Implement `safe_add_i16()`, `safe_sub_u32()`, and `safe_mul_i32()` with overflow detection. Use them in a critical path (e.g., a PID controller update) and measure the performance cost. Is it acceptable for your timing budget?

## Next Up

Tomorrow: **Format String & Injection Vulnerabilities in Embedded C** — how a misplaced `printf(user_input)` can give an attacker arbitrary read/write, and why `snprintf` isn't always the silver bullet you think it is.
