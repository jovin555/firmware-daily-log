---
title: "Day 14: Code Coverage for Embedded: gcov, lcov & Gcovr"
date: 2026-06-26
tags: ["til", "hil-testing", "gcov", "coverage", "lcov"]
---

## What I Explored Today

Today I integrated code coverage measurement into our HIL pipeline for a Cortex-M4 firmware. We're using `gcov` (GCC's built-in coverage tool), `lcov` for HTML report generation, and `Gcovr` for machine-readable XML output. The goal: enforce a quality gate that blocks merges when line coverage drops below 80% for the core control logic. I learned that embedded coverage has unique constraints—flash size, runtime overhead, and cross-compilation quirks—that make it different from desktop coverage workflows.

## The Core Concept

Code coverage tells you *which lines of source code were actually executed during your tests*. In embedded HIL, this is critical because:

- **Untested paths hide bugs.** A 90% pass rate on HIL tests means nothing if the tests never exercise the error handler or the watchdog reset path.
- **Coverage gaps reveal missing test scenarios.** If your PID controller's anti-windup branch never executes, you need a test that saturates the integrator.
- **Quality gates need objective metrics.** "We tested thoroughly" is subjective. "Line coverage is 87% with 100% branch coverage on safety-critical functions" is auditable.

The toolchain works like this: GCC compiles with special flags (`-fprofile-arcs -ftest-coverage`) that instrument every basic block. When the embedded target runs, it writes `.gcda` data files to a RAM filesystem or over a debug probe. Back on the host, `gcov` parses those files with the original source to produce per-file `.gcov` text reports. `lcov` aggregates those into HTML with heat-map coloring. `Gcovr` produces Cobertura XML for CI dashboards.

## Key Commands / Configuration / Code

### 1. Compilation Flags (CMakeLists.txt)

```cmake
# Add coverage flags only for debug/test builds
if(CMAKE_BUILD_TYPE STREQUAL "Coverage")
    add_compile_options(-fprofile-arcs -ftest-coverage -O0 -g)
    add_link_options(-fprofile-arcs -ftest-coverage)
    # Disable optimizations that inline or eliminate branches
    add_compile_options(-fno-inline -fno-default-inline)
endif()
```

**Why `-O0`?** Optimized code (`-O2`) can merge branches, inline functions, and eliminate dead code—making coverage results misleading. You test with `-O0` for coverage, then re-test with production `-O2` for timing.

### 2. Extracting Coverage Data from Target

On our STM32, we dump `.gcda` files over semihosting after each HIL test suite:

```c
// Called after all HIL tests complete, before reset
void dump_coverage_data(void) {
    extern void __gcov_flush(void);  // GCC built-in
    __gcov_flush();                  // Writes all .gcda buffers

    // Transfer via semihosting or UART
    for (int i = 0; i < num_gcda_files; i++) {
        semihosting_write_file(gcda_filenames[i],
                               gcda_buffers[i],
                               gcda_sizes[i]);
    }
}
```

**Alternative:** Use a RAM disk and copy via debugger after test run. For targets without semihosting, you can dump the raw memory region where `gcov` stores counters and reconstruct on host.

### 3. Generating Reports (CI Script)

```bash
#!/bin/bash
# Run on host after collecting .gcda files from target

# Step 1: Generate per-file .gcov text reports
# -b: branch coverage, -c: counts, -l: long filenames
find build -name "*.gcda" -exec gcov -b -c -l {} \;

# Step 2: lcov HTML report (human-readable)
lcov --capture --directory build \
     --output-file coverage.info \
     --rc lcov_branch_coverage=1 \
     --exclude "*/test/*" \
     --exclude "*/mocks/*"

genhtml coverage.info --output-directory coverage_html \
    --branch-coverage \
    --title "Firmware HIL Coverage"

# Step 3: Gcovr XML report (CI-friendly)
gcovr --root . --xml-pretty \
      --exclude "test/" \
      --exclude "third_party/" \
      --output coverage.xml

# Step 4: Quality gate (fail if < 80% line coverage)
gcovr --root . --fail-under-line 80 \
      --exclude "test/" \
      --exclude "third_party/"
```

### 4. CI Quality Gate (GitLab CI Example)

```yaml
coverage_job:
  stage: quality
  script:
    - ./collect_coverage.sh
    - gcovr --root . --fail-under-line 80 \
            --fail-under-branch 70 \
            --exclude "test/" --exclude "third_party/"
  artifacts:
    reports:
      coverage_report: coverage.xml
    paths:
      - coverage_html/
```

## Common Pitfalls & Gotchas

1. **Flash/RAM exhaustion.** Instrumented code is 2-3x larger and slower. On a 64KB flash MCU, coverage instrumentation can blow your binary. Solution: only instrument the module under test, or use a larger test-target variant with more flash.

2. **`__gcov_flush()` must be called before reset.** If the target resets (watchdog, power cycle) without flushing, all `.gcda` data is lost. We added a 5-second delay after tests complete to ensure flush completes over semihosting.

3. **Optimization skews coverage.** `-O2` can make branches disappear. A `while(1)` loop might get optimized to a single branch instruction, making loop-body coverage meaningless. Always use `-O0` for coverage builds, and accept that coverage numbers won't match production performance.

## Try It Yourself

1. **Add coverage flags to your existing embedded project.** Compile one module with `-fprofile-arcs -ftest-coverage -O0` and run your HIL tests. Extract the `.gcda` files and run `gcov -b -c` on a single source file. Look at the branch coverage—find one branch that's never taken.

2. **Set up a CI quality gate.** Use `gcovr --fail-under-line 80` in your pipeline. Intentionally add a test that misses a branch (e.g., don't test the error path of an ADC read). Watch the pipeline fail.

3. **Compare `-O0` vs `-O2` coverage.** Compile the same source with both optimization levels, run identical tests, and diff the `.gcov` outputs. Note which functions or branches disappear under optimization. Document this in your team's coverage policy.

## Next Up

Tomorrow: **Static Analysis in CI: cppcheck, clang-tidy, MISRA** — we'll enforce coding standards automatically, catch null-pointer dereferences before they reach HIL, and integrate MISRA C:2012 checks into our merge request pipeline.
