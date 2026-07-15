---
title: "Day 15: CERT C Secure Coding Standard: Key Rules for Embedded"
date: 2026-07-15
tags: ["til", "threat-modeling", "cert-c"]
---

## What I Explored Today

Today I dug into the CERT C Secure Coding Standard (2016 edition), specifically the rules that matter most for embedded systems. While the full standard has hundreds of rules, embedded engineers face unique constraints—limited stack, no dynamic allocation in safety-critical paths, direct hardware access, and ISR interactions. I focused on the rules that prevent the bugs that actually brick devices or cause safety violations: rule 04 (integers), rule 05 (bit fields), rule 06 (pointers), rule 07 (arrays), and rule 09 (memory management). These aren't academic; every one of these rules maps to a real CVSS 7+ vulnerability I've seen in production firmware.

## The Core Concept

The CERT C standard isn't about writing "beautiful" code—it's about writing code that doesn't have exploitable undefined behavior. In embedded systems, undefined behavior doesn't just crash a user-space process; it can corrupt control registers, jump to arbitrary addresses, or bypass safety interlocks. The key insight is that most embedded vulnerabilities come from violating one of five fundamental rules: integer overflow (INT30-C), bit-field misalignment (INT12-C), pointer arithmetic out of bounds (ARR30-C), null pointer dereference (EXP34-C), and failure to validate memory operations (MEM30-C). These rules exist because the C standard leaves behavior undefined in these cases, and compilers aggressively optimize based on the assumption that undefined behavior never occurs. Your `if (ptr)` check might be removed by the optimizer if a prior operation on `ptr` was undefined.

## Key Commands / Configuration / Code

### Rule INT30-C: Ensure operations on unsigned integers do not wrap
```c
// BAD: Undefined behavior on overflow for signed, wraps for unsigned
uint16_t sensor_raw = 0xFFFF;
uint16_t offset = 0x0002;
uint16_t corrected = sensor_raw + offset;  // wraps to 0x0001 silently

// GOOD: Check before operation
uint16_t sensor_raw = 0xFFFF;
uint16_t offset = 0x0002;
uint16_t corrected;

if (UINT16_MAX - sensor_raw < offset) {
    // Handle overflow: clamp, saturate, or log error
    corrected = UINT16_MAX;
    error_handler(ERR_SENSOR_OVERFLOW);
} else {
    corrected = sensor_raw + offset;
}
```

### Rule INT12-C: Do not assume bit-field layout
```c
// BAD: Layout is implementation-defined
struct status_reg {
    unsigned int ready : 1;
    unsigned int error : 1;
    unsigned int mode  : 2;
};

// GOOD: Use explicit masks and shifts for hardware registers
#define STATUS_READY_MASK  (1U << 0)
#define STATUS_ERROR_MASK  (1U << 1)
#define STATUS_MODE_MASK   (3U << 2)
#define STATUS_MODE_SHIFT  2

uint32_t status = READ_REG(STATUS_ADDR);
uint8_t mode = (status & STATUS_MODE_MASK) >> STATUS_MODE_SHIFT;
```

### Rule ARR30-C: Do not form or use out-of-bounds pointers
```c
// BAD: Pointer arithmetic past end of array
uint8_t buffer[64];
uint8_t *ptr = buffer + 64;  // OK: one past the end
uint8_t val = *ptr;          // UB: dereference one past end

// GOOD: Only form one-past-the-end, never dereference
uint8_t buffer[64];
uint8_t *end = buffer + 64;
uint8_t *ptr = buffer;

while (ptr < end) {
    process_byte(*ptr);
    ptr++;
}
```

### Rule MEM30-C: Do not access freed memory
```c
// BAD: Use-after-free in ISR context
static uint8_t *shared_buffer;

void init(void) {
    shared_buffer = (uint8_t *)malloc(256);
}

void ISR_handler(void) {
    // ISR might fire after free() but before pointer is NULL'd
    shared_buffer[0] = 0xAA;  // Use-after-free
}

void cleanup(void) {
    free(shared_buffer);
    // Missing: shared_buffer = NULL;
}

// GOOD: Set to NULL and use volatile for ISR-shared pointers
static volatile uint8_t *shared_buffer;

void cleanup(void) {
    free((void *)shared_buffer);
    shared_buffer = NULL;  // ISR can check this
}
```

## Common Pitfalls & Gotchas

### 1. The "But It Works on My Compiler" Trap
Just because GCC on your host doesn't optimize away your null check doesn't mean the ARM GCC 10.3 used for production won't. I've seen `if (ptr) { *ptr = val; }` get reduced to just `*ptr = val;` because the compiler proved `ptr` was non-null from a prior (undefined) operation. Always compile with `-Wall -Wextra -Wpedantic` and enable `-Wnull-dereference` at minimum.

### 2. Bit Fields Are Not Portable Across Compilers
The order of bits in a bit-field (MSB vs LSB first) is implementation-defined. If you write a register definition using bit-fields on GCC for ARM, then port to IAR for RISC-V, your `mode` field might end up in the wrong bits. Always use explicit masks and shifts for hardware register access—bit-fields are only safe for purely software structures that never cross compilation boundaries.

### 3. Integer Promotion Bites in Embedded
When you do `uint8_t a = 0xFF; uint8_t b = 0x01; uint8_t c = a + b;`, the addition happens in `int` (promoted), then truncates back to `uint8_t`. The compiler may warn, but many embedded projects treat warnings as errors only for specific categories. Always cast explicitly or use the `UINT8_C()` macro to avoid surprises.

## Try It Yourself

1. **Audit your ISR code for MEM30-C violations**: Find every `free()` call in your codebase. For each one, verify the pointer is set to `NULL` immediately after, and that any ISR that might access that pointer checks for `NULL` first. Use `volatile` on the pointer declaration.

2. **Replace all bit-field register definitions with mask/shift macros**: Pick one peripheral driver (e.g., UART control register). Rewrite the register access using `#define` masks and inline functions. Verify the generated assembly is identical or better.

3. **Enable integer overflow detection**: Add `-fsanitize=undefined -fsanitize=integer` to your debug build. Run your test suite and fix every unsigned integer wrap that isn't intentional (and document the intentional ones with a comment and a static assert).

## Next Up

Tomorrow I'll dive into static analysis tools for embedded C: how to configure Coverity for MISRA and CERT C rules, what Klocwork catches that GCC doesn't, and why Cppcheck's `--std=c11 --enable=all` is your first line of defense before even running a dynamic test. We'll look at real false positive suppression strategies and how to integrate these into a CI pipeline without drowning in noise.
