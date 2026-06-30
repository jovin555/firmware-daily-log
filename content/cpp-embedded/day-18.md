---
title: "Day 18: Undefined Behavior: UBSan & Catching UB in Firmware"
date: 2026-06-30
tags: ["til", "cpp-embedded", "ubsan", "undefined-behavior"]
---

## What I Explored Today

Today I integrated Undefined Behavior Sanitizer (UBSan) into a bare-metal firmware build for an ARM Cortex-M4 target. I've known for years that UB is the silent killer of embedded systems — it doesn't crash immediately, it just corrupts state and waits. What I didn't fully appreciate until today is how practical UBSan actually is on constrained targets. With the right configuration, you can catch signed integer overflow, misaligned pointer dereferences, and shift-out-of-bounds at runtime with surprisingly low overhead. I walked away with a working UBSan-instrumented firmware binary that logs UB events over a UART debug channel.

## The Core Concept

Undefined Behavior in C++ means the standard imposes no requirements on what happens. The compiler is free to assume UB never occurs, which enables aggressive optimizations — but also means your firmware can silently produce wrong results, corrupt memory, or jump to random addresses. In embedded systems, UB often manifests as: a timer fires at the wrong rate (signed overflow in a period calculation), a DMA transfer corrupts a buffer (pointer arithmetic that wraps around), or a watchdog resets for no apparent reason (infinite loop optimized away because the compiler proved the loop condition is always true).

UBSan works by inserting runtime checks before every operation that could invoke UB. When a check fails, it calls a handler function. On hosted platforms, this prints a stack trace and aborts. On embedded targets, we redirect the handler to our own function — typically logging the source file, line number, and kind of UB over a debug interface, then optionally halting or continuing.

The key insight: UBSan does not prevent UB. It detects it when it happens. This is invaluable during development and CI testing because it catches bugs that static analysis misses and that unit tests might not trigger. The overhead is per-operation (a few instructions and a conditional branch), which is acceptable for debug builds but not for release.

## Key Commands / Configuration / Code

### Enabling UBSan in GCC/Clang for ARM

```bash
# Add these flags to your debug build
-fsanitize=undefined -fsanitize-undefined-trap-on-error

# For more granular control, enable specific checks:
-fsanitize=signed-integer-overflow,shift,alignment,null,pointer-overflow

# Disable recovery (halt on first UB):
-fno-sanitize-recover=all
```

### Custom UBSan Handler for Bare-Metal

```c
// ubsan_handler.c — link this into your firmware
#include <stdint.h>

// UBSan runtime calls these with __ubsan_ prefix
struct UBSanSourceLocation {
    const char *filename;
    uint32_t line;
    uint32_t column;
};

// Minimal handler — logs via your debug UART
void __ubsan_handle_type_mismatch_v1(void *data, uintptr_t ptr) {
    struct UBSanSourceLocation *loc = (struct UBSanSourceLocation *)data;
    debug_printf("UB: type mismatch at %s:%lu (ptr=0x%08lx)\r\n",
                 loc->filename, loc->line, ptr);
    // Optionally: __asm__("bkpt #0"); // halt debugger
}

void __ubsan_handle_add_overflow(void *data, void *lhs, void *rhs) {
    struct UBSanSourceLocation *loc = (struct UBSanSourceLocation *)data;
    debug_printf("UB: signed add overflow at %s:%lu\r\n",
                 loc->filename, loc->line);
}
```

### CMake Integration for Embedded UBSan

```cmake
# In your toolchain file or CMakeLists.txt
set(CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG} \
    -fsanitize=undefined \
    -fsanitize-undefined-trap-on-error \
    -fno-sanitize-recover=all")

# Link the handler object
target_sources(firmware PRIVATE ubsan_handler.c)
```

## Common Pitfalls & Gotchas

**1. UBSan increases code size significantly.** On Cortex-M4, I saw a 30-50% increase in .text section for a moderate-sized firmware. This can overflow your flash if you're near capacity. Always check the map file after enabling UBSan. Mitigation: enable only specific checks (`-fsanitize=signed-integer-overflow,shift`) rather than the blanket `-fsanitize=undefined`.

**2. The default handler calls `abort()` — which doesn't exist on bare-metal.** Without a custom handler, UBSan will try to call `abort()`, which is not implemented in most embedded runtimes. This causes a hard fault or linker error. You must provide all the `__ubsan_handle_*` functions that your code might trigger. Start with the most common ones: `add_overflow`, `sub_overflow`, `mul_overflow`, `shift_out_of_bounds`, `type_mismatch`, `alignment_assumption`.

**3. UBSan checks are not free in interrupt context.** If you enable UBSan in interrupt service routines (ISRs), the additional checks can increase latency and, worse, the handler itself might call functions that are not ISR-safe (like `printf`). Solution: either disable UBSan for ISRs using `__attribute__((no_sanitize("undefined")))` on the ISR function, or ensure your handler is reentrant and lock-free.

## Try It Yourself

1. **Enable UBSan on your debug build.** Add `-fsanitize=undefined -fsanitize-undefined-trap-on-error` to your compiler flags. Write a minimal handler that blinks an LED at a specific pattern when UB is detected. Run your firmware and see if any latent UB surfaces.

2. **Instrument a known UB.** Write a function that performs signed integer overflow (e.g., `int32_t x = INT32_MAX; x += 1;`). Verify that UBSan catches it and your handler fires. Then fix the code to use unsigned arithmetic or saturation.

3. **Profile the overhead.** Build your firmware twice — once with UBSan, once without. Compare the .text size and measure the execution time of a critical loop (e.g., a PID controller) with a logic analyzer or cycle counter. Document the trade-off for your team.

## Next Up

Tomorrow: **Compiler Optimizations: What -O2 Does to Your Driver** — we'll disassemble a simple GPIO driver compiled at -O0, -O1, -O2, and -Os, and see exactly which optimizations the compiler applies, including loop unrolling, inlining, and dead code elimination. Bring your objdump.
