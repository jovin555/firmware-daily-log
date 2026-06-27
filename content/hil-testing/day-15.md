---
title: "Day 15: Static Analysis in CI: cppcheck, clang-tidy, MISRA"
date: 2026-06-27
tags: ["til", "hil-testing", "cppcheck", "clang-tidy"]
---

## What I Explored Today

Today I wired static analysis tools into our CI pipeline as a quality gate before HIL testing even starts. The goal: catch undefined behavior, MISRA violations, and style issues at commit time rather than during hardware-in-the-loop runs. I integrated `cppcheck` for general defect detection, `clang-tidy` for modern C++ linting and safety checks, and a MISRA C:2012 checker to enforce automotive/medical coding standards. The pipeline now rejects any PR that introduces new violations, saving hours of HIL debug time.

## The Core Concept

Static analysis in embedded CI isn't about "nice-to-have" code quality — it's about preventing undefined behavior from reaching hardware. A buffer overflow that passes unit tests might corrupt memory only under specific timing conditions on the target. Static analysis catches these at the source level, before compilation.

The three tools serve complementary roles:
- **cppcheck**: Detects memory leaks, null pointer dereferences, uninitialized variables, and STL misuse. It's fast and doesn't need a build system.
- **clang-tidy**: Modern C++ linting with checks for `const` correctness, move semantics, and lifetime safety. It integrates with CMake for translation-unit-aware analysis.
- **MISRA checker**: Enforces the MISRA C/C++ guidelines (e.g., no dynamic memory, no recursion, strict type enforcement). Essential for safety-critical firmware.

The key insight: run these as a **pre-HIL gate**. If static analysis fails, don't even bother flashing the target. This reduces HIL slot contention and prevents flaky test results caused by code that's technically "wrong" but happens to work on this particular hardware revision.

## Key Commands / Configuration / Code

### CI Pipeline Stage (GitHub Actions)

```yaml
# .github/workflows/static-analysis.yml
name: Static Analysis Gate
on: [pull_request]

jobs:
  static-analysis:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: cppcheck (defect detection)
        run: |
          cppcheck --enable=all --suppress=missingIncludeSystem \
            --suppress=unmatchedSuppression \
            --error-exitcode=1 \
            --inline-suppr \
            --std=c11 \
            --xml-version=2 \
            firmware/src/ 2> cppcheck-report.xml
        # --error-exitcode=1 makes CI fail on any finding

      - name: clang-tidy (with CMake integration)
        run: |
          cmake -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
          run-clang-tidy -p build -checks='-*,clang-analyzer-*,modernize-*,readability-*' \
            -warnings-as-errors='*' \
            firmware/src/
        # -warnings-as-errors='*' promotes all warnings to errors

      - name: MISRA C:2012 check
        run: |
          # Using cppcheck with MISRA add-on
          cppcheck --addon=misra.json --suppress=misra-c2012-20.7 \
            --error-exitcode=1 firmware/src/
```

### MISRA Configuration (misra.json)

```json
{
  "script": "misra.py",
  "args": [
    "--rule-texts=misra_c2012_rules.txt",
    "--mandatory-only"
  ]
}
```

### Local Developer Workflow

```bash
# Run all three locally before pushing
#!/bin/bash
set -e

echo "=== cppcheck ==="
cppcheck --enable=all --error-exitcode=1 firmware/src/

echo "=== clang-tidy ==="
cmake -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
run-clang-tidy -p build -checks='clang-analyzer-*' firmware/src/

echo "=== MISRA ==="
cppcheck --addon=misra.json --error-exitcode=1 firmware/src/

echo "All static analysis passed."
```

### Example Violation and Fix

```c
// BAD: MISRA 17.2 violation (function called before declaration)
// clang-tidy: readability-identifier-naming violation
void process_sensor(void) {
    int32_t result = read_adc();  // implicit declaration - undefined behavior!
}

// GOOD: Proper declaration and naming
static int32_t read_adc(void);  // forward declaration per MISRA 8.4

static int32_t read_adc(void) {
    return (int32_t)ADC1->DR;
}

void ProcessSensor(void) {  // PascalCase per project convention
    int32_t result = read_adc();
}
```

## Common Pitfalls & Gotchas

### 1. False Positives from Third-Party Code
MISRA checkers will flag vendor HAL libraries and CMSIS headers. **Always exclude third-party directories** using `--suppress` or `-i` flags. We maintain a `suppressions.txt` file that's version-controlled and reviewed quarterly.

```bash
cppcheck --suppressions-list=suppressions.txt firmware/src/
```

### 2. clang-tidy Needs Compilation Database
Without `compile_commands.json`, clang-tidy can't resolve includes or macros. Developers often forget to run CMake first. **Fix**: Add a CI step that verifies the compilation database exists before running clang-tidy.

```bash
if [ ! -f build/compile_commands.json ]; then
    echo "ERROR: Run cmake -B build first"
    exit 1
fi
```

### 3. MISRA Rule 20.7 (Expressions from macro expansion)
This rule fires on every `assert()` and `offsetof()` call. **Suppress it globally** unless you're writing safety-critical code that forbids all macros. We suppress 20.7 and document the rationale in our coding standard.

## Try It Yourself

1. **Add cppcheck to your existing CMake project**: Create a `cmake/StaticAnalysis.cmake` module that runs cppcheck on every source file. Use `add_custom_target(static-analysis)` so developers can run `make static-analysis`.

2. **Write a clang-tidy check for your project's naming convention**: Create a `.clang-tidy` file with `CheckOptions: readability-identifier-naming` to enforce `CamelCase` for functions and `snake_case` for variables. Run it on a legacy file and count how many violations you find.

3. **Set up a MISRA baseline**: Run your MISRA checker on your entire codebase, save the output as `misra-baseline.txt`, then configure your CI to only fail on *new* violations. This lets you adopt MISRA incrementally without a massive refactor.

## Next Up

Tomorrow: **IEC 62304-Compliant Test Documentation from CI** — how to auto-generate traceability matrices linking requirements to HIL test cases, and produce audit-ready documentation that satisfies FDA and Notified Body reviewers. We'll use Python scripts to parse test reports and generate the required artifacts.
