---
title: "Day 21: Cppcheck: Fast Open-Source Static Analysis"
date: 2026-07-03
tags: ["til", "formal-verification", "cppcheck", "static", "bugs"]
---

## What I Explored Today

Today I integrated Cppcheck into a production embedded C++ codebase for an ARM Cortex-M4 firmware module. The goal was to catch undefined behavior, buffer overflows, and style violations before they reached hardware-in-the-loop testing. Cppcheck is unique in the static analysis landscape because it performs *path-sensitive* analysis without compiling your code — it works directly on the AST (Abstract Syntax Tree) parsed from source files. This makes it fast enough to run on every commit, yet powerful enough to detect real bugs like null pointer dereferences and out-of-bounds array access.

## The Core Concept

Most developers think static analysis is just "linting" — checking for formatting or naming conventions. Cppcheck operates at a deeper level. It performs *value flow analysis*: it tracks the possible values of variables through branches, loops, and function calls to identify provably incorrect states. For example, it can detect that a buffer of size 64 is accessed at index 72 after a specific loop iteration, even if the loop condition is non-trivial.

Why does this matter for embedded systems? Because the cost of a bug found in production is orders of magnitude higher than one caught at compile time. Cppcheck fills the gap between the compiler's basic warnings (which miss many logical errors) and heavy-duty formal verification tools (which require significant setup and runtime). It's the "sweet spot" for daily CI pipelines.

Cppcheck uses *abstract interpretation* under the hood. It simulates all possible execution paths through a function, but with abstract values (e.g., "this integer is in range [0, 15]") rather than concrete ones. This allows it to prove properties like "this pointer is never null here" or "this array index is always within bounds" without actually running the code.

## Key Commands / Configuration / Code

### Basic Scan
```bash
# Scan a single file with all checks enabled
cppcheck --enable=all --suppress=missingIncludeSystem main.cpp

# Scan a project directory, outputting results to XML for CI tools
cppcheck --enable=warning,performance,portability --xml \
  --xml-version=2 src/ 2> cppcheck-report.xml
```

### Embedded-Specific Configuration
```bash
# For ARM Cortex-M targets, specify the platform to get correct sizes
cppcheck --platform=arm32-wchar4 --std=c++17 \
  --enable=all --suppress=unmatchedSuppression \
  --suppress=missingIncludeSystem \
  -I include/ -I CMSIS/Core/Include/ src/
```

### Example Bug Cppcheck Catches
```cpp
// buggy_example.cpp
#include <cstdint>
#include <cstring>

void process_packet(const uint8_t* data, uint16_t len) {
    uint8_t buffer[64];
    
    // Cppcheck warns: possible buffer overflow if len > 64
    memcpy(buffer, data, len);  // <-- error: (error) Buffer access out-of-bounds
    
    // Cppcheck warns: null pointer dereference if data is NULL
    if (data[0] == 0xAA) {      // <-- error: (error) Possible null pointer dereference
        // ...
    }
    
    // Cppcheck warns: shift by negative or too-large value
    uint32_t value = 1 << len;  // <-- error: (portability) Shifting 32-bit value by 32 bits is undefined behaviour
}
```

### Suppressing False Positives
```cpp
// Inline suppression for known false positives
void dma_transfer(uint32_t* buf, size_t sz) {
    // cppcheck-suppress [arrayIndexOutOfBounds] - DMA hardware handles bounds
    for (size_t i = 0; i < sz; ++i) {
        buf[i] = 0;
    }
}
```

### CI Integration (GitHub Actions)
```yaml
- name: Run Cppcheck
  run: |
    cppcheck --enable=warning,style,performance \
      --suppress=missingIncludeSystem \
      --error-exitcode=1 \
      --inline-suppr \
      src/
```

## Common Pitfalls & Gotchas

**1. False Positives from Incomplete Configurations**
The most common issue is not providing the correct include paths or platform definitions. Cppcheck needs to resolve all headers to build a complete AST. If you omit `-I` flags for your HAL or CMSIS headers, it will report hundreds of `missingInclude` warnings and may miss real bugs because it can't analyze function bodies from those headers. Always run with `--check-config` first to verify includes are found.

**2. Suppression Blindness**
Engineers often suppress warnings without understanding why. The `--inline-suppr` flag is powerful, but it's easy to suppress a real bug by accident. Always add a comment explaining *why* the suppression is safe. Better yet, use `--suppress=warningId:fileName` at the project level for known false positives, and reserve inline suppressions for exceptional cases.

**3. Performance vs. Depth Tradeoff**
Cppcheck's `--enable=all` includes `style` and `information` checks that can be noisy. In a CI pipeline, use `--enable=warning,performance,portability` for speed. Reserve the full analysis for nightly runs. Also, the `--max-configs` flag defaults to 12, which may miss bugs hidden behind preprocessor branches. Increase it to 25 or 50 for complex projects.

## Try It Yourself

1. **Scan your current project**: Run `cppcheck --enable=warning,performance --error-exitcode=1 src/` on an existing embedded project. Fix at least one buffer overflow or null pointer dereference warning. Verify the fix by re-running the analysis.

2. **Write a buggy test file**: Create a small C++ file with an off-by-one array access, a use-after-free, and a shift-by-type-width error. Run Cppcheck with `--enable=all` and confirm it catches all three. Then add inline suppressions for one of them and verify the suppression works.

3. **Integrate into CI**: Add a Cppcheck step to your project's CI pipeline (GitHub Actions, GitLab CI, or Jenkins). Configure it to fail the build on `error` and `warning` levels, but allow `style` and `information` to pass. Run it on a merge request and observe the feedback loop.

## Next Up

Tomorrow we dive into **clang-tidy: Linting & Refactoring C/C++ Code**. While Cppcheck focuses on bug detection through abstract interpretation, clang-tidy leverages the full Clang compiler infrastructure to provide modern C++ linting, automatic fixes, and refactoring suggestions. We'll compare the two tools and show how they complement each other in a robust static analysis pipeline.
