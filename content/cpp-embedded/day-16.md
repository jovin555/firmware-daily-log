---
title: "Day 16: MISRA C++ 2023: Key Rules & Enforcement with clang-tidy"
date: 2026-06-28
tags: ["til", "cpp-embedded", "misra-cpp", "clang-tidy", "safety"]
---

## What I Explored Today

I spent the day diving into the MISRA C++ 2023 standard — the latest update to the Motor Industry Software Reliability Association's guidelines for C++ in safety-critical systems. While MISRA C++ 2008 was based on C++03, the 2023 revision finally aligns with C++17, adding 40 new rules and retiring many outdated ones. I focused on the most impactful rules for embedded firmware and, more importantly, how to enforce them automatically using `clang-tidy` with the `misra-cpp2023` check group. No more manual code reviews for trivial violations.

## The Core Concept

MISRA C++ isn't just a coding style guide — it's a set of *enforceable* rules designed to eliminate undefined behavior, reduce complexity, and prevent common embedded pitfalls. The 2023 revision introduces three categories:

- **Required** (must be followed, deviation required for waiver)
- **Advisory** (should be followed, no deviation required)
- **Directive** (requires manual verification, not automatically checkable)

The key shift in 2023: they removed many rules that were redundant with modern C++ features (e.g., banning `auto` is gone; instead, they require explicit type annotations in certain contexts). The new rules focus on:
- **Rule 5-0-1**: The value of an expression shall not be implicitly converted to a different underlying type (catches silent truncation)
- **Rule 8-5-2**: Braced initialisation shall be used for object initialization (no more `int x = 0;` — use `int x{0};`)
- **Rule 15-5-1**: All user-defined destructors, copy/move constructors, and copy/move assignment operators shall be defined as `= default;` or `= delete;` (Rule of Five enforcement)

The real power comes from automation. `clang-tidy` with the `misra-cpp2023` module can catch these at compile time, integrated into your CI pipeline.

## Key Commands / Configuration / Code

### Installing the MISRA C++ 2023 checks

`clang-tidy` 18+ includes the `misra-cpp2023` module. Verify your version:

```bash
clang-tidy --version
# Should show: LLVM version 18.1.0 or newer
```

### Basic invocation

```bash
# Run MISRA checks on a single file
clang-tidy --checks='-*,misra-cpp2023-*' \
           --warnings-as-errors='misra-cpp2023-*' \
           main.cpp -- -std=c++17 -I./include
```

### Project-wide `.clang-tidy` configuration

Create a `.clang-tidy` file in your project root:

```yaml
# .clang-tidy
Checks: '-*,misra-cpp2023-*'
WarningsAsErrors: 'misra-cpp2023-*'
HeaderFilterRegex: '.*'
CheckOptions:
  # Rule A0-1-1: Require 'noexcept' on move operations
  misra-cpp2023-noexcept-move-operations: true
  # Rule A12-1-1: Require explicit constructor for single-argument constructors
  misra-cpp2023-explicit-single-argument-constructor: true
```

### Example: Catching Rule 5-0-1 violation

```cpp
// bad_example.cpp
#include <cstdint>

int32_t multiply(int16_t a, int16_t b) {
    return a * b;  // MISRA violation: implicit conversion of int16_t to int32_t
}
```

Run clang-tidy:

```bash
clang-tidy --checks='-*,misra-cpp2023-rule-5-0-1' bad_example.cpp
# Output:
# warning: implicit conversion from 'int16_t' (aka 'short') to 'int32_t' (aka 'int') may lose value [misra-cpp2023-rule-5-0-1]
```

Fix:

```cpp
// good_example.cpp
#include <cstdint>

int32_t multiply(int16_t a, int16_t b) {
    return static_cast<int32_t>(a) * static_cast<int32_t>(b);  // Explicit cast
}
```

### Integrating into CMake

```cmake
# CMakeLists.txt
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Enable clang-tidy for all targets
set(CMAKE_CXX_CLANG_TIDY
    "clang-tidy;--checks=-*,misra-cpp2023-*;--warnings-as-errors=misra-cpp2023-*")
```

## Common Pitfalls & Gotchas

1. **False positives with standard library headers**: MISRA 2023 checks often flag STL internals (e.g., `std::vector`'s implicit conversions). Use `HeaderFilterRegex` to exclude third-party headers: `HeaderFilterRegex: '^(?!.*std).*$'` or better, only check your own source files by passing them explicitly.

2. **Rule 8-5-2 (braced initialization) breaks `std::initializer_list`**: If you have a `std::vector<int> v{5}`, this creates a vector with one element (5), not five elements. MISRA 2023 allows an exception: use parentheses for container constructors that take a size. The rule says "braced initialization shall be used *unless* the constructor is explicit or an initializer_list overload exists."

3. **`clang-tidy` doesn't catch all directives**: MISRA 2023 has ~30 directives that require manual review (e.g., "All code shall be traceable to requirements"). Don't assume a clean clang-tidy run means full compliance. You still need a static analysis tool like PC-lint or QAC for complete coverage.

## Try It Yourself

1. **Set up a `.clang-tidy` file** in an existing embedded C++ project. Run `clang-tidy --checks='-*,misra-cpp2023-*'` on your most complex module. How many violations do you get? Categorize them by rule number.

2. **Fix Rule 5-0-1 violations**: Find all implicit integer conversions in your codebase. Replace them with `static_cast`. Re-run clang-tidy to confirm the warnings disappear.

3. **Write a CMakeLists.txt** that enables MISRA C++ 2023 checks as errors for a single target. Build with `-DCMAKE_CXX_CLANG_TIDY="clang-tidy;--checks=-*,misra-cpp2023-*;--warnings-as-errors=misra-cpp2023-*"`. Verify that a deliberate violation (e.g., implicit conversion) fails the build.

## Next Up

Tomorrow, we'll tackle **AUTOSAR C++14: Subset for Safety-Critical Systems** — the automotive industry's stricter cousin of MISRA. We'll compare the rule sets, see where AUTOSAR goes beyond MISRA (especially for dynamic memory and exception handling), and set up clang-tidy for AUTOSAR compliance. If you thought MISRA was strict, wait until you see the rules on `new` and `delete`.
