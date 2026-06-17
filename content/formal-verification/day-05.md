---
title: "Day 05: Clang Static Analyzer: Path-Sensitive Bug Detection"
date: 2026-06-17
tags: ["til", "formal-verification", "clang-analyzer", "path-sensitive"]
---

## What I Explored Today

Today I dug into the Clang Static Analyzer (CSA), a path-sensitive static analysis tool built directly into the LLVM/Clang compiler infrastructure. Unlike simple linters that check for style violations or pattern matching, CSA performs symbolic execution across every feasible execution path through your C/C++ code. I ran it against a few real-world embedded firmware modules and was genuinely impressed at how it caught subtle use-after-free and null-dereference bugs that had survived code review.

## The Core Concept

Most static analyzers operate on an abstract syntax tree (AST) and look for known patterns — think of them as grep with a PhD in syntax. Path-sensitive analysis is fundamentally different. It tracks *symbolic values* through the program's control flow, maintaining a separate state for each possible execution path. When two paths converge (e.g., after an if-else), the analyzer merges states intelligently, but crucially, it does not discard the constraints that led to each path.

Why does this matter for embedded systems? Because embedded code is full of state machines, interrupt-driven control flow, and hardware-dependent branches. A null-pointer check might pass on one path but fail on another after a specific sequence of events. Path-sensitive analysis catches these conditional bugs. It also tracks tainted data — values from external sources like ADC registers or UART buffers — and flags when they reach sensitive operations without sanitization.

The analyzer works by constructing an *exploded graph*: nodes represent program states (variable values, memory regions, constraints), and edges represent statements or branches. It explores this graph depth-first, pruning infeasible paths when constraints become contradictory (e.g., `x > 5` and `x < 3`). This is what makes it sound — it only reports bugs that are reachable under some set of assumptions.

## Key Commands / Configuration / Code

### Basic invocation on a single file

```bash
# Run the analyzer on a C file, output results as HTML report
clang --analyze -Xclang -analyzer-output=html \
      -o /tmp/analysis_report \
      src/main.c
```

### Analyzing a full build with scan-build

For real projects, you don't invoke clang directly. Use `scan-build`, which wraps your build system:

```bash
# Intercept the build and run CSA on all translation units
scan-build --use-cc=arm-none-eabi-gcc \
           --use-c++=arm-none-eabi-g++ \
           -o /tmp/scan_results \
           make -j4
```

### Enabling specific checkers

```bash
# Enable all core checkers plus security and deadcode
scan-build --use-cc=clang \
           -enable-checker core \
           -enable-checker security.insecureAPI \
           -enable-checker deadcode.DeadStores \
           -enable-checker alpha.security.ArrayBoundV2 \
           make
```

### Example: CSA catches a path-sensitive null dereference

```c
// bug.c — a classic path-sensitive bug
#include <stdlib.h>

void process_data(int *buf, int len) {
    int *tmp = NULL;
    
    if (len > 0) {
        tmp = (int *)malloc(len * sizeof(int));
        // Path A: tmp is non-NULL (assuming malloc succeeds)
        // Path B: tmp is NULL (malloc failure)
    }
    // Paths merge here — analyzer tracks both states
    
    *tmp = 42;  // CSA reports: Dereference of null pointer (on Path B)
    
    if (tmp) {
        free(tmp);
    }
}
```

Running `clang --analyze bug.c` produces:

```
bug.c:12:5: warning: Dereference of null pointer (loaded from variable 'tmp')
    *tmp = 42;
    ^~~~~~~
```

### Suppressing false positives with annotations

```c
// Tell CSA that malloc cannot fail on this platform
int *safe_malloc(size_t sz) {
    int *p = (int *)malloc(sz);
    // CSA understands this assertion
    __attribute__((analyzer_noreturn)) 
    if (!p) abort();  // unreachable in production
    return p;
}
```

## Common Pitfalls & Gotchas

**1. False positives from incomplete modeling of hardware**
CSA doesn't know that your DMA controller always writes to a buffer before the completion interrupt fires. You'll get spurious "uninitialized value" warnings on data read from DMA buffers. The fix is to use `__attribute__((annotate(""))` or add explicit dummy reads to satisfy the analyzer.

**2. Explosion of paths in deeply nested state machines**
Complex switch-case state machines with 20+ states can cause the analyzer to hit its path limit (default 4 paths per function). You'll see "analyzer is giving up on this path" in the output. Mitigate by refactoring into smaller functions or increasing the limit with `-analyzer-max-nodes`.

**3. scan-build does not work with all build systems**
It intercepts compiler calls via `CC` and `CXX` environment variables. If your build system hardcodes compiler paths or uses wrapper scripts, `scan-build` may silently do nothing. Always verify by checking that the output directory contains `.plist` or HTML files.

## Try It Yourself

1. **Find a use-after-free in a linked list**: Write a small C program with a singly-linked list that frees a node but continues to traverse past it. Run `clang --analyze` and observe the path-sensitive report. Note how the analyzer tracks the freed pointer across the loop.

2. **Suppress a false positive on a memory-mapped register**: Create a struct representing a hardware register block, read a field, and use it without initialization. Add a `(void)volatile_read` to suppress the warning, then verify the analyzer stops reporting.

3. **Run scan-build on an existing embedded project**: Grab a small FreeRTOS or Zephyr sample, run `scan-build make`, and inspect the HTML report. Look for bugs in interrupt handlers or callback functions — these are where path-sensitive analysis shines.

## Next Up

Tomorrow, we'll tackle **MISRA C 2012: Rules, Deviations & Compliance Reports** — how to navigate the 143 mandatory rules, write deviation requests that auditors actually accept, and generate compliance reports that don't get you laughed out of the review.
