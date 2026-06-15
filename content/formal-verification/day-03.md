---
title: "Day 03: Cppcheck: Fast Open-Source Static Analysis"
date: 2026-06-15
tags: ["til", "formal-verification", "cppcheck", "static", "bugs"]
---

## What I Explored Today

Today I integrated Cppcheck into our CI pipeline for a mixed C/C++ firmware project targeting ARM Cortex-M. The immediate win: it caught a buffer underflow in a ring buffer implementation that had passed three code reviews and all functional tests. Cppcheck found it in 2.3 seconds. This tool is not a replacement for deeper formal methods, but it is the fastest path to eliminating entire classes of memory and logic bugs before they reach testing.

## The Core Concept

Cppcheck is a static analysis tool that detects bugs the compiler does not catch. Unlike the compiler, which checks syntax and type rules, Cppcheck performs path-sensitive analysis to find:

- **Buffer overflows and underflows** (including off-by-one in arrays)
- **Null pointer dereferences** across function calls
- **Memory leaks** (malloc without free, missing delete)
- **Uninitialized variables** (including struct padding issues)
- **STL and container misuse** (e.g., iterator invalidation)
- **Division by zero** and other arithmetic errors

The key insight: Cppcheck does not require building your project. It parses the source directly, which means you can run it on incomplete code, header-only libraries, or code that does not compile yet. This makes it ideal for catching bugs early in the development cycle, before you even attempt a build.

Cppcheck uses abstract interpretation to simulate execution paths. It tracks variable values as ranges (e.g., `x ∈ [0, 10]`) and flags operations that produce undefined behavior. The analysis is sound for the checks it implements—if it reports no errors, those specific bug classes do not exist in the analyzed paths.

## Key Commands / Configuration / Code

### Basic Usage

```bash
# Check a single file with all checks enabled
cppcheck --enable=all --suppress=missingIncludeSystem main.c

# Check a project with MISRA compliance (automotive/medical)
cppcheck --enable=all --std=c11 --suppress=missingIncludeSystem \
  --suppress=unmatchedSuppression \
  --suppress=preprocessorErrorDirective \
  --suppress=*:*/third_party/* \
  --suppress=*:*/build/* \
  --suppress=*:*/test/* \
  --xml --xml-version=2 2> cppcheck_report.xml \
  src/ include/
```

### Project-Wide Analysis with `compile_commands.json`

For CMake-based projects, generate the compilation database and let Cppcheck use it:

```bash
# Generate compile_commands.json
cmake -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON

# Run Cppcheck with project settings
cppcheck --project=build/compile_commands.json \
  --enable=warning,performance,portability,style \
  --suppress=*:*/build/* \
  --suppress=*:*/test/* \
  --suppress=unmatchedSuppression \
  --suppress=missingIncludeSystem \
  --suppress=preprocessorErrorDirective \
  --error-exitcode=1 \
  --inline-suppr \
  --check-level=exhaustive
```

### Suppressing False Positives Inline

```c
// Example: intentional buffer access that Cppcheck flags
void process_buffer(uint8_t *buf, size_t len) {
    // cppcheck-suppress[arrayIndexOutOfBounds]
    // Reason: buf is guaranteed to have len+1 bytes by caller contract
    buf[len] = 0;  // null-terminate
}
```

### Custom Rules (Python-based)

Cppcheck supports user-defined rules via Python scripts. Example rule to detect magic numbers:

```python
# custom_rules.py
import cppcheckdata

def check_magic_numbers(cfg):
    for token in cfg.tokenlist:
        if token.isNumber and token.str not in ("0", "1", "2"):
            # Report magic number
            cppcheckdata.reportError(token, "style", "magicNumber",
                "Avoid magic numbers; use named constants")
```

Run with: `cppcheck --rule=custom_rules.py main.c`

## Common Pitfalls & Gotchas

1. **False positives from conditional compilation**  
   Cppcheck processes all preprocessor branches by default. If your code uses `#ifdef DEBUG` with debug-only assertions, Cppcheck may report null pointer dereferences that cannot happen in release builds.  
   *Fix:* Use `--suppress=*:*/debug/*` or add `// cppcheck-suppress[nullPointerRedundantCheck]` on debug-only paths.

2. **Missing includes cause incomplete analysis**  
   Without `--suppress=missingIncludeSystem`, Cppcheck floods output with system header errors. But suppressing them also means it cannot analyze system header interactions (e.g., `memcpy` buffer sizes).  
   *Fix:* Provide include paths explicitly: `-I /usr/arm-none-eabi/include -I ./include`

3. **Performance on large codebases**  
   With `--check-level=exhaustive`, Cppcheck can take hours on a million-line codebase. The default `normal` level is fast but misses some interprocedural bugs.  
   *Fix:* Use `--check-level=exhaustive` only on changed files in CI, or run it nightly on the full codebase.

4. **C++ specific checks require `--language=c++`**  
   Cppcheck defaults to C for `.c` files. If you have C++ code in `.c` files (common in embedded projects), you must specify `--language=c++` or rename files.

## Try It Yourself

1. **Find a buffer overflow in a string utility**  
   Write a simple `strcpy` wrapper that copies `n` bytes but forgets to null-terminate. Run `cppcheck --enable=all --suppress=missingIncludeSystem` and observe the `bufferAccessOutOfBounds` warning. Fix it and verify the warning disappears.

2. **Integrate Cppcheck into your CMake project**  
   Add a custom target:  
   ```cmake
   add_custom_target(cppcheck
     COMMAND cppcheck --project=${CMAKE_BINARY_DIR}/compile_commands.json
       --enable=warning,performance --error-exitcode=1
     WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
     COMMENT "Running Cppcheck static analysis")
   ```
   Run `cmake --build build --target cppcheck` and fix any issues.

3. **Suppress a false positive with inline comments**  
   Create a function that intentionally accesses `array[size]` (for a sentinel value). Cppcheck will flag it. Add `// cppcheck-suppress[arrayIndexOutOfBounds]` with a comment explaining why it is safe. Verify the warning is suppressed.

## Next Up

Tomorrow we dive into **clang-tidy: Linting & Refactoring C/C++ Code**. While Cppcheck focuses on bug detection, clang-tidy provides modern C++ linting, automatic fixes, and refactoring tools. We will compare their strengths and show how to run both in parallel for maximum coverage.
