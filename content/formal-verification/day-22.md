---
title: "Day 22: clang-tidy: Linting & Refactoring C/C++ Code"
date: 2026-07-04
tags: ["til", "formal-verification", "clang-tidy", "linting"]
---

## What I Explored Today

Today I dove into `clang-tidy`, the LLVM-based static analysis tool that goes far beyond simple style checking. While most engineers reach for `cppcheck` or `gcc -Wall -Wextra`, `clang-tidy` offers something unique: it's a modular, extensible linter that can also perform automated refactoring. I spent the day wiring it into a real embedded project, configuring checks for MISRA-like safety rules, and discovering how its fix-it hints can automatically correct violations. The tool's ability to understand your build system via `compile_commands.json` makes it practical for real-world codebases, not just toy examples.

## The Core Concept

Why use `clang-tidy` instead of a simpler linter? The answer lies in its architecture. `clang-tidy` operates on Clang's AST (Abstract Syntax Tree), meaning it understands your code at the semantic level, not just as text. This allows it to catch issues that regex-based or token-based linters miss: uninitialized variables in complex control flow, misuse of standard library containers, or potential buffer overflows in C-style arrays.

The "why" is about catching bugs before they become runtime failures. In embedded systems, a null pointer dereference or an integer overflow can mean a crashed ECU or a bricked device. `clang-tidy` can detect these statically, at compile time, without needing to run the code. Moreover, its refactoring capabilities mean you can apply fixes consistently across thousands of files — critical when migrating a legacy C codebase to modern C++ or enforcing a new coding standard.

## Key Commands / Configuration / Code

### Generating the Compilation Database
`clang-tidy` needs to know your compiler flags. For CMake projects:

```bash
# Generate compile_commands.json
cmake -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON .
# Or for existing build directories:
cmake -DCMAKE_EXPORT_COMPILE_COMMANDS=ON .
```

For non-CMake projects, use `bear` or `compiledb`:
```bash
bear -- make          # intercepts compiler calls
compiledb make        # alternative tool
```

### Running clang-tidy on a Single File
```bash
# Basic usage with a specific check
clang-tidy --checks="bugprone-*,performance-*" \
  --fix-errors \
  src/main.c -- -Iinclude -DPLATFORM_ARM
# --fix-errors applies fixes even if other warnings exist
# Everything after "--" is passed to the compiler
```

### Using a .clang-tidy Configuration File
Create `.clang-tidy` in your project root:

```yaml
# .clang-tidy
Checks: >
  clang-analyzer-*,
  bugprone-*,
  performance-*,
  readability-*,
  -readability-identifier-length,  # too noisy for embedded
  -readability-magic-numbers       # we use named constants

CheckOptions:
  # Enforce C-style casts only in C files
  readability-uppercase-literal-suffix: 
    NewSuffix: U
  # Warn on any implicit widening conversions
  bugprone-narrowing-conversions:
    WarnOnIntegerNarrowing: true
    WarnOnFloatingPointNarrowing: true

# Run as: clang-tidy --config='' src/file.c
# Empty --config forces reading from .clang-tidy
```

### Automated Refactoring Example
Fix all `NULL` to `nullptr` in a C++ codebase:

```bash
# Dry run first
clang-tidy --checks="modernize-use-nullptr" \
  src/*.cpp -- -std=c++17

# Apply fixes
clang-tidy --checks="modernize-use-nullptr" \
  --fix --fix-errors \
  src/*.cpp -- -std=c++17
```

### Running on an Entire Project (Parallel)
```bash
# Use run-clang-tidy.py (ships with LLVM)
run-clang-tidy.py -j4 -p build/ \
  -checks="bugprone-*,clang-analyzer-*" \
  -fix -format

# -j4: 4 parallel jobs
# -p: path to compile_commands.json directory
# -format: run clang-format after fixes
```

## Common Pitfalls & Gotchas

1. **Missing Compilation Database**  
   `clang-tidy` needs `compile_commands.json`. Without it, it assumes default compiler flags, which often miss include paths or defines. Result: false positives or missed checks. Always verify the file exists and contains your actual compiler invocations.

2. **Header File Analysis**  
   By default, `clang-tidy` only analyzes `.c`/`.cpp` files. To check headers, you must explicitly list them or use `--header-filter`:
   ```bash
   clang-tidy --header-filter=".*" src/*.cpp
   ```
   Without this, bugs in inline functions or macros in headers go undetected.

3. **Fix Conflicts with Complex Macros**  
   When `--fix` encounters a macro expansion, it may produce incorrect fixes (e.g., splitting a macro argument). Always review fixes in macro-heavy code. Use `--fix-notes` to see what was changed, and run a build after applying fixes to catch breakage.

## Try It Yourself

1. **Set up a project with compile_commands.json**  
   Take any C/C++ project you have (or create a simple one with a few files). Generate `compile_commands.json` using CMake or `bear`. Run `clang-tidy --checks="bugprone-*,performance-*"` on a single file. Observe the warnings and try applying `--fix` to one of them.

2. **Create a custom .clang-tidy config**  
   Write a `.clang-tidy` file that enables `clang-analyzer-*` and `bugprone-*` but disables `readability-identifier-length`. Add a check option to enforce `U` suffix on unsigned literals. Run `clang-tidy --config=''` on your project and see how the output changes.

3. **Automate a refactoring**  
   In a C++ file, deliberately use `NULL` instead of `nullptr`. Run `clang-tidy --checks="modernize-use-nullptr" --fix` and verify the file is updated. Then try the same with `for` loops that could be range-based (`modernize-loop-convert`).

## Next Up

Tomorrow we move from linting to deeper analysis with **Clang Static Analyzer: Path-Sensitive Bug Detection**. We'll explore how the analyzer simulates execution paths to find null pointer dereferences, memory leaks, and use-after-free bugs that `clang-tidy` can't catch.
