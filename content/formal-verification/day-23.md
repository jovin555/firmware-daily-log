---
title: "Day 23: Clang Static Analyzer: Path-Sensitive Bug Detection"
date: 2026-07-05
tags: ["til", "formal-verification", "clang-analyzer", "path-sensitive"]
---

## What I Explored Today

Today I dug into the Clang Static Analyzer (CSA) and its path-sensitive analysis engine. Unlike simpler linters that check each line in isolation, CSA tracks what values variables can actually hold at every program point, following every possible execution path through your code. I ran it against a real embedded firmware module and watched it catch a use-after-free that had survived three code reviews. The analyzer doesn't just say "this pointer might be null" — it shows you the exact sequence of assignments, branches, and function calls that lead to the bug.

## The Core Concept

Most static analyzers work "intraprocedurally" — they analyze one function at a time, often without tracking how values flow through loops or conditional branches. They'll flag a potential null dereference if they see a pointer used without a null check, but they can't tell you *which* path leads there.

Path-sensitive analysis is different. CSA builds an abstract representation of every feasible execution path through your code. For each path, it maintains a symbolic state: what each variable could be, what memory is allocated, what locks are held. As it walks the code, it forks the state at every branch, then explores both sides. When it finds a bug — say, a double-free — it can reconstruct the exact sequence of conditions that trigger it. This is why CSA produces those beautiful bug reports with the "arrow" diagram showing the execution trace.

For embedded engineers, this is a game-changer. We deal with resource-constrained systems where memory leaks, use-after-free, and null pointer dereferences are not just bugs — they're safety hazards. A watchdog reset on a medical pump or an automotive ECU is not a "crash and restart" situation. Path-sensitive analysis catches the kind of subtle, interleaved bugs that unit tests miss because they depend on a specific sequence of events.

## Key Commands / Configuration / Code

The simplest way to run CSA is through `scan-build`, which wraps your normal build process:

```bash
# Analyze a single file
clang --analyze -Xanalyzer -analyzer-output=text \
  -I./include main.c

# Full project analysis with scan-build
scan-build --use-cc=arm-none-eabi-gcc \
  --use-c++=arm-none-eabi-g++ \
  -o ./analysis-reports \
  make -j4

# Generate HTML reports (much easier to read)
scan-build -o ./reports \
  -enable-checker alpha.unix.cstring.OutOfBounds \
  -enable-checker optin.portability.UnixAPI \
  make
```

Enable specific checkers for embedded work:

```bash
# Checkers I enable for every firmware project
scan-build \
  -enable-checker core.CallAndMessage \
  -enable-checker core.DivideZero \
  -enable-checker core.NullDereference \
  -enable-checker core.StackAddressEscape \
  -enable-checker cplusplus.NewDeleteLeaks \
  -enable-checker deadcode.DeadStores \
  -enable-checker security.insecureAPI.strcpy \
  -enable-checker unix.Malloc \
  -enable-checker unix.MismatchedDeallocator \
  make
```

Here's a concrete example of what CSA catches that a simpler tool would miss:

```c
// buggy.c — CSA finds the use-after-free
#include <stdlib.h>

typedef struct {
    int *buffer;
    size_t len;
} RingBuf;

RingBuf* init_buffer(size_t n) {
    RingBuf *rb = malloc(sizeof(RingBuf));
    if (!rb) return NULL;
    rb->buffer = malloc(n * sizeof(int));
    if (!rb->buffer) {
        free(rb);          // CSA: rb freed here
        return NULL;
    }
    rb->len = n;
    return rb;
}

int process_item(RingBuf *rb, int idx) {
    if (idx < 0 || idx >= rb->len) return -1;
    return rb->buffer[idx];  // safe — bounds checked
}

void cleanup(RingBuf *rb) {
    if (rb) {
        free(rb->buffer);
        free(rb);
    }
}

int main(void) {
    RingBuf *rb = init_buffer(100);
    if (!rb) return 1;
    
    int val = process_item(rb, 50);
    cleanup(rb);
    
    // CSA flags this: use-after-free
    val = process_item(rb, 10);  // rb already freed!
    
    return val;
}
```

Run it:

```bash
clang --analyze -Xanalyzer -analyzer-output=text buggy.c
```

CSA outputs a trace showing: `cleanup(rb)` frees the memory, then `process_item(rb, 10)` dereferences the dangling pointer. It even shows the call stack and the exact line numbers.

## Common Pitfalls & Gotchas

**1. False positives from function pointers and callbacks.** CSA doesn't know what function a function pointer actually points to at runtime. If you have a dispatch table in your RTOS scheduler, you'll get spurious "uninitialized value" warnings. Suppress them with `__attribute__((annotate("reinitialized")))` on the variable, or use a suppression file.

**2. Loop unrolling limits.** By default, CSA unrolls loops only 4 times. If your bug requires 5 iterations to manifest, CSA won't find it. Increase with `-analyzer-max-loop 8` but be warned — analysis time grows exponentially with loop depth. For embedded code with tight loops, I usually set it to 6 and accept the trade-off.

**3. System header noise.** CSA analyzes headers it includes, including libc and CMSIS headers. You'll get flooded with false positives from standard library implementations. Always use `-analyzer-config stable-report-filename=true` and filter with `grep -v` on known system paths, or better, use a `.clang-analyzer-suppress` file to exclude entire directories.

## Try It Yourself

1. **Find a use-after-free in a linked list.** Write a simple singly-linked list with `insert_head()` and `remove_head()`. Intentionally call `remove_head()` twice without checking if the list is empty. Run CSA and observe the path trace showing the double-free.

2. **Analyze a real embedded project.** Grab a small FreeRTOS demo from GitHub. Run `scan-build` with the `unix.Malloc` and `core.StackAddressEscape` checkers enabled. Fix at least one real bug — I guarantee you'll find at least one stack variable that escapes into a task handle.

3. **Compare CSA with a non-path-sensitive tool.** Run `cppcheck` (which is path-insensitive) on the same buggy code from this post. Note how cppcheck flags the potential null dereference but cannot trace the use-after-free path. Then run CSA and see the difference in diagnostic quality.

## Next Up

Tomorrow we tackle **MISRA C 2012: Rules, Deviations & Compliance Reports** — how to navigate the 143 mandatory rules, write deviation requests that auditors actually accept, and generate compliance reports that don't get rejected on first submission.
