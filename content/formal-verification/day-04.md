---
title: "Day 04: clang-tidy: Linting & Refactoring C/C++ Code"
date: 2026-06-16
tags: ["til", "formal-verification", "clang-tidy", "linting"]
---

## What I Explored Today

Today I integrated `clang-tidy` into my embedded firmware build pipeline. Unlike simple linters that only catch formatting issues, `clang-tidy` performs deep semantic analysis of C/C++ code using the Clang frontend's AST (Abstract Syntax Tree). I focused on configuring it for MISRA-like safety checks, automating refactoring of legacy pointer arithmetic, and integrating it into a CMake-based workflow. The tool caught three real bugs in our sensor driver: an uninitialized struct member, a potential null pointer dereference in an error path, and a signed integer overflow in a timing calculation.

## The Core Concept

Most static analyzers operate on a preprocessed token stream—they see text, not meaning. `clang-tidy` is different: it runs on the same AST that the Clang compiler uses for code generation. This means it understands types, overload resolution, template instantiation, and control flow. When it flags a "potential null pointer dereference," it has actually traced the data flow through your function.

The real power is twofold. First, **semantic linting**: checks like `clang-analyzer-core.NullDereference` or `cppcoreguidelines-pro-type-member-init` require understanding what a pointer points to or whether a constructor initializes all members. Second, **automated refactoring**: `clang-tidy` can apply fixes that modify your source code. For example, replacing `malloc` with `new`, or converting C-style casts to `static_cast`. This is not regex-based—it rewrites the AST and pretty-prints the result, preserving comments and formatting.

For embedded engineers, the `-checks=*` option is dangerous. You must curate your checks to match your coding standard (MISRA C:2012, AUTOSAR C++14, or your own). The tool supports `.clang-tidy` configuration files that can be checked into version control, ensuring every developer runs the same analysis.

## Key Commands / Configuration / Code

### Basic invocation
```bash
# Run all modernize checks on a single file, apply fixes
clang-tidy --checks=modernize-* --fix my_file.cpp -- -I./include -std=c++17

# Run only safety-critical checks, no fixes
clang-tidy --checks="-*,clang-analyzer-*,cppcoreguidelines-pro-type-member-init" \
  --warnings-as-errors="*" \
  firmware/driver/sensor.c -- -I./include -I./hal -std=c11
```

### Project-wide `.clang-tidy` configuration
```yaml
# .clang-tidy at project root
Checks: >
  -*,
  clang-analyzer-*,
  cppcoreguidelines-pro-type-member-init,
  cppcoreguidelines-pro-bounds-pointer-arithmetic,
  misc-definitions-in-headers,
  readability-identifier-naming

CheckOptions:
  readability-identifier-naming.FunctionCase: camelBack
  readability-identifier-naming.VariableCase: lower_case
  readability-identifier-naming.ClassCase: CamelCase
  cppcoreguidelines-pro-bounds-pointer-arithmetic: true

WarningsAsErrors: "*"
HeaderFilterRegex: ".*\\.h$"
AnalyzeTemporaryDtors: false
```

### CMake integration (modern approach)
```cmake
# CMakeLists.txt
find_program(CLANG_TIDY clang-tidy)
if(CLANG_TIDY)
  set(CMAKE_C_CLANG_TIDY "${CLANG_TIDY}" --checks=-*,clang-analyzer-*)
  set(CMAKE_CXX_CLANG_TIDY "${CLANG_TIDY}" --checks=-*,cppcoreguidelines-*)
endif()
```
This makes every `make` invocation run `clang-tidy` on all compiled files. For CI, use `--warnings-as-errors=*` to fail the build on any finding.

### Real refactoring example: fixing pointer arithmetic
```cpp
// Before: legacy embedded code
void process_buffer(uint8_t *buf, size_t len) {
    uint32_t *ptr = (uint32_t *)buf;  // C-style cast, strict aliasing violation
    for (size_t i = 0; i < len / 4; i++) {
        ptr[i] = __REV(ptr[i]);       // pointer arithmetic on void* cast
    }
}

// After clang-tidy --fix with cppcoreguidelines-pro-bounds-pointer-arithmetic
void process_buffer(uint8_t *buf, size_t len) {
    auto *ptr = reinterpret_cast<uint32_t *>(buf);  // explicit cast
    for (size_t i = 0; i < len / sizeof(uint32_t); i++) {
        ptr[i] = __REV(ptr[i]);       // still uses array indexing (acceptable)
    }
}
```

## Common Pitfalls & Gotchas

1. **Header analysis is opt-in by default.** `clang-tidy` only analyzes the main translation unit, not included headers. Use `HeaderFilterRegex` in your `.clang-tidy` or pass `--header-filter=.*` to catch issues in your own headers. Without this, a buggy inline function in a header will never be flagged.

2. **The `--fix` flag can silently change semantics.** `clang-tidy`'s fixes are generally safe, but I've seen it replace `memcpy` with `std::copy` in a way that broke alignment assumptions on ARM Cortex-M. Always review fixes with `git diff` before committing. Use `--fix-errors` with extreme caution—it applies fixes even on files with compilation errors.

3. **False positives from system headers.** The `clang-analyzer-*` checks can produce noise from standard library implementations (e.g., claiming `std::vector::at()` might return null). Use `--system-headers=0` to suppress these, or add `// NOLINTNEXTLINE` comments for known false positives. Better yet, maintain a `.clang-tidy` with explicit suppression patterns.

## Try It Yourself

1. **Set up project-wide linting**: Create a `.clang-tidy` file in an existing C/C++ project with checks for `clang-analyzer-*` and `cppcoreguidelines-pro-type-member-init`. Run `clang-tidy --dump-config` to verify your configuration is parsed correctly.

2. **Automated refactoring of C-style casts**: On a legacy codebase, run `clang-tidy --checks=google-readability-casting --fix` to convert C-style casts to C++ casts. Use `git diff` to review every change—look for cases where the tool chose `reinterpret_cast` when `static_cast` would be safer.

3. **CI integration**: Add a CI step that runs `clang-tidy --warnings-as-errors="*"` on your firmware source. Use `compile_commands.json` (generated by CMake with `-DCMAKE_EXPORT_COMPILE_COMMANDS=ON`) so the tool knows your exact build flags. Fail the pipeline on any warning.

## Next Up

Tomorrow we dive into **Clang Static Analyzer: Path-Sensitive Bug Detection**. While `clang-tidy` checks each line in isolation, the Static Analyzer simulates all possible execution paths through your code. We'll explore how it catches use-after-free bugs, memory leaks, and division-by-zero errors that no linter can find—and how to interpret its path diagrams to fix real firmware bugs.
