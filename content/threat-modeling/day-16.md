---
title: "Day 16: Static Analysis for Security: Coverity, Klocwork & Cppcheck"
date: 2026-07-16
tags: ["til", "threat-modeling", "static-analysis"]
---

## What I Explored Today

Today I dug into three static analysis tools that every embedded security engineer should have in their pipeline: Coverity (Synopsys), Klocwork (Perforce), and the open-source Cppcheck. While dynamic testing catches runtime bugs, static analysis finds vulnerabilities *before* the code ever hits a target. I focused on how to configure these tools for MISRA compliance, CWE detection, and how to integrate them into a CI/CD pipeline without drowning in false positives.

## The Core Concept

Static analysis for security is about proving the absence of certain classes of bugs, not just finding them. In embedded systems, where a buffer overflow can mean a bricked device or a remote exploit, we need tools that understand control flow, data flow, and taint propagation at the source level.

The key difference between these tools:
- **Coverity** uses a SAT-solver-based engine to explore all feasible paths. It's expensive but has the lowest false-positive rate for deep interprocedural issues.
- **Klocwork** uses a flow-sensitive, path-sensitive analysis with a focus on C/C++ and MISRA. It excels at finding race conditions and resource leaks in RTOS code.
- **Cppcheck** is a lightweight, open-source alternative. It won't find deep logic bugs, but it catches buffer overflows, null pointer dereferences, and uninitialized variables with near-zero setup.

For embedded firmware, the real win is catching violations of the *CWE Top 25* that are specific to constrained environments: integer overflows in sensor data processing, buffer overflows in protocol parsers, and use-after-free in memory pools.

## Key Commands / Configuration / Code

### Cppcheck (Quickest to integrate)
```bash
# Basic run with all checks enabled, MISRA rules, and CWE mapping
cppcheck --enable=all --suppress=missingIncludeSystem \
         --suppress=unmatchedSuppression \
         --inconclusive --xml --xml-version=2 \
         --std=c11 --platform=arm32-wchar4 \
         --addon=misra.py --misra-verbose \
         --suppress=misra-c2012-2.7 \
         src/ 2> cppcheck_report.xml

# Check specific CWE categories
cppcheck --enable=warning,style,performance,portability \
         --suppress=*:*/test/* \
         --check-level=exhaustive \
         --library=posix,gnu \
         -I include/ -I drivers/ \
         --check-config \
         src/main.c
```

### Coverity (Command-line workflow)
```bash
# Step 1: Build capture (intercepts compiler calls)
cov-build --dir cov-int make -j4

# Step 2: Analyze with security checks
cov-analyze --dir cov-int \
    --all \
    --enable-fnptr \
    --security \
    --concurrency \
    --aggressiveness-level high \
    --model-file models/rtos_model.cpp \
    --cwe-map \
    --triage-model default

# Step 3: Generate HTML report
cov-format-errors --dir cov-int \
    --html-output report/ \
    --filesort \
    --cwe-format \
    --strip-path /home/user/project/
```

### Klocwork (CI integration example)
```yaml
# .klocwork/config file snippet
project:
  name: "firmware-v2"
  language: c,cpp
  build-command: "make -j4"
  analysis:
    - checkers: MISRA2012, AUTOSAR, CWE
    - max-path-depth: 100
    - interprocedural: true
    - suppress:
        - "MISRA2012-RULE-2_7"  # Unused parameter (common in HAL stubs)
        - "CWE-476"             # NULL deref in vendor HAL (known false positive)
```

### Real-world suppression example (Cppcheck inline)
```c
// In a UART ISR handler — intentional single-byte buffer
static uint8_t rx_buf[1];
// cppcheck-suppress [misra-c2012-18.4, arrayIndexOutOfBounds]
// Intent: hardware FIFO reads one byte at a time
rx_buf[0] = UART_DR;
```

## Common Pitfalls & Gotchas

1. **False positives from vendor HAL code**  
   Most MCU vendor SDKs (STM32 HAL, NXP SDK) are not MISRA-compliant and will generate thousands of warnings. Always exclude vendor directories with `--suppress=*:*/Drivers/*` or use a baseline suppression file. Otherwise, your team will ignore *all* warnings.

2. **Path explosion in interrupt-heavy code**  
   Coverity and Klocwork can take hours on firmware with many ISRs and state machines. Use `--max-path-depth` (Klocwork) or `--aggressiveness-level medium` (Coverity) to keep analysis time under 30 minutes per commit. Deep analysis can run nightly.

3. **MISRA rule 10.1 (boolean type confusion) in register access**  
   Hardware registers often use bitfields that violate MISRA. You *must* suppress these or use wrapper functions. Example:
   ```c
   // cppcheck-suppress misra-c2012-10.1
   // Reason: Hardware register bitfield, not boolean
   if (GPIOA->IDR & (1 << 5)) { ... }
   ```

4. **Cppcheck doesn't understand inline assembly**  
   Any `__asm__` blocks will cause false positives or missed checks. Wrap them in `// cppcheck-suppress` or move to separate `.S` files.

## Try It Yourself

1. **Run Cppcheck on your current firmware project**  
   `cppcheck --enable=all --inconclusive --xml src/ 2> report.xml`  
   Open the report in `cppcheck-gui` or convert to HTML. Identify the top 3 CWE categories. Are any of them in your threat model?

2. **Create a baseline suppression file**  
   Run Cppcheck with `--suppressions-list=suppressions.txt`. Generate the initial file from the first run, then manually review each suppression. This forces you to understand *why* each warning exists.

3. **Integrate Coverity into your CI pipeline**  
   If you have access, set up a nightly build that runs `cov-analyze` with `--security --cwe-map`. Configure email alerts only for `High` and `Medium` severity issues. Track the false-positive rate over one sprint.

## Next Up

Tomorrow, I’ll dive into **Fuzzing Embedded Firmware: AFL++, libFuzzer & Hardware-in-the-Loop** — how to set up coverage-guided fuzzing for bare-metal code, handle hardware dependencies with QEMU system mode, and catch memory corruption bugs that static analysis misses.
