---
title: "Day 15: AddressSanitizer & UBSan: Runtime Bug Detection"
date: 2026-06-27
tags: ["til", "formal-verification", "asan", "ubsan", "sanitizers"]
---

## What I Explored Today

Today I integrated AddressSanitizer (ASan) and UndefinedBehaviorSanitizer (UBSan) into a production embedded Linux build. These compiler-based runtime tools catch memory errors and undefined behavior that static analysis alone can miss—especially the heap-use-after-free and signed integer overflow bugs that plague C/C++ firmware. I learned that with modern GCC/Clang, enabling both sanitizers is a single compiler flag change, and the runtime overhead (~2x slowdown, ~2x memory) is acceptable for pre-release testing.

## The Core Concept

Static analysis (like our previous days on Frama-C and CBMC) proves properties about all possible executions. But it has blind spots: dynamic memory allocation, pointer arithmetic through unions, and interactions with volatile registers. Sanitizers fill this gap by instrumenting the binary at compile time to check every memory access and arithmetic operation at runtime.

**ASan** works by replacing `malloc`/`free` with instrumented versions that maintain shadow memory—a bitmap tracking which bytes are valid to access. Every load/store is preceded by a check against this shadow map. A use-after-free is detected because the freed region is marked "poisoned" in shadow memory, and the check fails with a detailed stack trace.

**UBSan** checks for C/C++ undefined behavior that the compiler assumes never happens: signed integer overflow, shift past bit-width, null pointer dereference through `this`, misaligned access, and type-punning violations. It inserts conditional traps before each operation; if the condition triggers, it prints a diagnostic and aborts (or continues, depending on config).

The key insight: these are not static analyzers. They require running the code with test inputs. But they catch bugs that static analysis cannot prove (because the proof would require solving the halting problem for heap allocation patterns). In practice, combining static analysis with sanitizer runs during CI catches ~90% of memory safety bugs before they reach QA.

## Key Commands / Configuration / Code

### Enabling ASan + UBSan in GCC/Clang

```bash
# Compile with both sanitizers (debug build)
gcc -fsanitize=address,undefined -g -O1 -fno-omit-frame-pointer \
    -o test_program main.c

# For CMake projects, add to CMAKE_C_FLAGS_DEBUG:
# set(CMAKE_C_FLAGS_DEBUG "${CMAKE_C_FLAGS_DEBUG} -fsanitize=address,undefined -fno-omit-frame-pointer")
```

### Detecting a Use-After-Free

```c
// buggy.c — classic use-after-free
#include <stdlib.h>
#include <string.h>

int main() {
    char *buf = malloc(64);
    strcpy(buf, "hello");
    free(buf);
    // BUG: reading freed memory
    char c = buf[0];  // ASan catches this
    return c;
}
```

Compile and run:
```bash
gcc -fsanitize=address -g -O1 -o buggy buggy.c
./buggy
# Output includes:
# ==12345==ERROR: AddressSanitizer: heap-use-after-free on address 0x602000000010
# READ of size 1 at 0x602000000010 thread T0
#     #0 0x401234 in main buggy.c:9
# 0x602000000010 is located 0 bytes inside of 64-byte region [0x602000000010,0x602000000050)
# freed by thread T0 here:
#     #0 0x7f1234567890 in free (libasan.so)
#     #1 0x401234 in main buggy.c:8
```

### Detecting Signed Integer Overflow with UBSan

```c
// overflow.c
#include <stdio.h>
#include <stdint.h>

int main() {
    int32_t a = 2147483647;  // INT32_MAX
    int32_t b = a + 1;       // UB: signed overflow
    printf("%d\n", b);
    return 0;
}
```

```bash
gcc -fsanitize=undefined -g -O1 -o overflow overflow.c
./overflow
# Output:
# overflow.c:7:19: runtime error: signed integer overflow: 2147483647 + 1 cannot be represented in type 'int'
```

### Suppressing Known Issues (for legacy code)

```bash
# Create a suppression file
echo "use-after-poison:my_legacy_file.c" > asan_suppress.txt
export ASAN_OPTIONS="suppressions=asan_suppress.txt"
./test_program
```

## Common Pitfalls & Gotchas

1. **ASan doubles memory usage.** The shadow memory requires 1/8 of the program's virtual address space. On memory-constrained embedded Linux (e.g., 64MB RAM), this can cause OOM kills. Mitigation: use `-fsanitize=address` only on test builds, or use `-fsanitize=address:quarantine_size_mb=32` to reduce the free-list quarantine.

2. **UBSan false positives with compiler optimization.** At `-O2` or higher, the compiler may optimize away the check because it assumes UB never happens. Always use `-O1` for sanitized builds. Example: `-fsanitize=undefined` with `-O2` may not catch signed overflow because the compiler already transformed the code assuming no overflow.

3. **Interrupt handlers and signal contexts.** ASan's shadow memory checks are not reentrant. If you call `malloc` inside a signal handler or ISR, ASan will crash with a nested error. Workaround: disable ASan for interrupt context with `__attribute__((no_sanitize("address")))` on the handler function, or use a dedicated interrupt-safe allocator.

4. **Linking order matters.** When using ASan with shared libraries, you must link ASan first (before `-lfoo`). Otherwise, the dynamic linker may resolve `malloc` to glibc's version instead of ASan's instrumented one. Use `-lasan` before all other libraries.

## Try It Yourself

1. **Find a use-after-free in a linked list.** Write a singly-linked list with an `insert_after` function that frees a node but continues to use its `next` pointer. Compile with ASan and verify it catches the bug. Then fix it by setting `next = NULL` after free.

2. **Trigger every UBSan check.** Write a small program that exercises: signed overflow (`INT_MAX + 1`), shift overflow (`1 << 33` on 32-bit int), null pointer through `this` (call a member function on a null pointer), and misaligned access (cast `char*` to `int*` at odd address). Compile with `-fsanitize=undefined -fno-sanitize-recover=all` to abort on first error.

3. **Integrate into an existing CMake project.** Add `-fsanitize=address,undefined` to your debug build flags. Run your unit tests. Count how many new bugs you find. Suppress any false positives from third-party libraries using the suppression file mechanism.

## Next Up

Tomorrow: **Integrating Static Analysis in CI: Fail on Warnings**. We'll wire up Frama-C and CBMC into a GitHub Actions pipeline, configure exit codes to fail the build on any alarm, and handle false positives with a baseline suppression file.
