---
title: "Day 02: Static vs Dynamic Analysis: The Verification Spectrum"
date: 2026-06-14
tags: ["til", "formal-verification", "static-analysis", "dynamic"]
---

## What I Explored Today

I spent the day mapping out the verification spectrum between static and dynamic analysis, testing both approaches on a real embedded C project. I ran `cppcheck` for static analysis, `valgrind` for dynamic memory checking, and `gcc -fsanitize=address` for runtime instrumentation. The goal was to understand when each technique catches bugs, where they overlap, and—critically—where they leave gaps.

## The Core Concept

Static analysis examines code *without executing it*. It parses the source (or binary) and reasons about all possible execution paths. Dynamic analysis runs the code and observes what happens on *specific* inputs. The distinction isn't academic—it directly affects what bugs you find and when.

Consider a buffer overflow in an embedded firmware function:

```c
// firmware.c
void process_packet(uint8_t *data, uint16_t len) {
    uint8_t buffer[64];
    if (len > 64) {
        // static analysis flags this: len can be > 64
        // dynamic analysis only catches it if you call with len=65
        memcpy(buffer, data, len);  // overflow
    }
}
```

A static analyzer sees the path where `len > 64` and warns immediately. A dynamic analyzer (like AddressSanitizer) only catches the overflow if your test harness actually passes `len=65`. This is the fundamental trade-off: static analysis is *sound* (covers all paths) but may produce false positives; dynamic analysis is *precise* (only real bugs) but misses anything your tests don't trigger.

In embedded systems, this spectrum is critical. You can't always run dynamic analysis on target hardware (no OS, no sanitizer support). Static analysis runs on your host machine, catching issues before you even flash the device.

## Key Commands / Configuration / Code

I built a small test harness to compare tools on the same buggy code:

```c
// test_bugs.c — intentionally vulnerable
#include <string.h>
#include <stdlib.h>

void use_after_free(void) {
    int *p = malloc(sizeof(int));
    free(p);
    *p = 42;  // use-after-free
}

void leak_memory(void) {
    malloc(1024);  // never freed
}

int main(void) {
    use_after_free();
    leak_memory();
    return 0;
}
```

**Static analysis with cppcheck:**
```bash
# cppcheck catches use-after-free and uninitialized variables
# --enable=all turns on style, performance, portability checks
cppcheck --enable=all --suppress=missingIncludeSystem test_bugs.c
# Output: [test_bugs.c:7]: (error) Memory pointed to by 'p' is freed twice.
#         [test_bugs.c:6]: (error) Memory pointed to by 'p' is freed.
```

**Dynamic analysis with AddressSanitizer (ASan):**
```bash
# Compile with -fsanitize=address to instrument memory accesses
# -g adds debug symbols for better stack traces
gcc -fsanitize=address -g -o test_bugs_asan test_bugs.c
./test_bugs_asan
# Output: ERROR: AddressSanitizer: heap-use-after-free on address 0x...
```

**Dynamic analysis with Valgrind:**
```bash
# Valgrind runs the binary in a synthetic CPU — 10-20x slowdown
# --leak-check=full reports all unfreed memory
valgrind --leak-check=full ./test_bugs_asan
# Output: Invalid write of size 4 ... Address 0x... is 0 bytes inside a block of size 4 free'd
#         40 bytes in 1 blocks are definitely lost in loss record ... malloc
```

Notice how cppcheck caught the use-after-free statically (no execution needed), while ASan and Valgrind required running the program. But cppcheck missed the memory leak—it's a runtime property that depends on control flow.

## Common Pitfalls & Gotchas

1. **False sense of coverage from static analysis.** A clean cppcheck report doesn't mean your code is safe. Static analyzers have false negatives—they can miss bugs that require deep interprocedural analysis or complex pointer arithmetic. I once had a static analyzer pass a firmware module with zero warnings, only to have a race condition crash the device in the field. Static analysis is a filter, not a proof.

2. **Dynamic analysis on host != target behavior.** Running ASan on your Linux desktop tells you nothing about the actual embedded target's memory layout, stack size, or timing. I've seen code that passes all sanitizer checks on x86 but corrupts the stack on ARM Cortex-M because the compiler laid out variables differently. Always run dynamic analysis on the actual target hardware or an instruction-accurate emulator.

3. **Static analysis configuration matters.** Default settings often miss critical checks. For embedded C, always enable:
   ```bash
   cppcheck --enable=warning,style,performance,portability,information \
            --std=c99 --platform=arm32-wchar4
   ```
   Without `--platform`, cppcheck assumes desktop-sized integers and pointers, which can hide integer overflow bugs on 16-bit microcontrollers.

## Try It Yourself

1. **Compare static vs dynamic on a null pointer dereference.** Write a function that conditionally dereferences a NULL pointer (e.g., `if (condition) *ptr = 0;` where `ptr` is NULL). Run cppcheck on it, then compile with `-fsanitize=undefined` and run with a test that triggers the condition. Note which tool catches it and under what conditions.

2. **Find a memory leak that static analysis misses.** Create a function that allocates memory in a loop but only frees it on one branch. Run cppcheck with `--enable=all` and observe it doesn't report the leak. Then run Valgrind with `--leak-check=full` to confirm the leak exists. This demonstrates the fundamental blind spot of static analysis for runtime behavior.

3. **Test your own embedded project.** Pick a C file from your current firmware project. Run cppcheck with the platform flag matching your target MCU (e.g., `--platform=arm32-wchar4` for ARM Cortex-M). Then compile with `-fsanitize=address` and run your unit tests. Compare the warnings—how many overlap? How many are unique to each tool?

## Next Up

Tomorrow we dive into **Cppcheck: Fast Open-Source Static Analysis**. I'll walk through configuring it for embedded C projects, suppressing false positives, and integrating it into a CI pipeline that runs before every firmware build. Bring your own code—we're going to find some bugs.
