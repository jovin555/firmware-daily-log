---
title: "Day 01: Why Embedded Teams Need CI/CD: From Desk-Testing to Pipelines"
date: 2026-07-01
tags: ["til", "embedded-cicd", "cicd", "embedded"]
---

## What I Explored Today

I spent the day mapping out the gap between how most embedded teams test firmware today — flashing a dev board on a desk, running a few manual tests, then shipping — and what a proper CI/CD pipeline could look like for constrained targets. The core insight is that embedded systems suffer from a "hardware bottleneck" that makes traditional CI seem impossible, but modern tooling (QEMU, Renode, hardware-in-the-loop runners) has quietly solved most of the friction. Today I documented the concrete steps to move from "it works on my desk" to "it passes in a pipeline."

## The Core Concept

The fundamental problem with embedded development is that your code is inseparable from the hardware it runs on. A web developer can run `npm test` and get feedback in seconds. An embedded engineer must cross-compile, flash, reset, observe LEDs or UART output, and interpret scope traces. This feedback loop is slow, manual, and non-reproducible — the "works on my desk" problem is amplified by hardware variance, floating pins, and timing dependencies.

CI/CD for embedded systems isn't about replacing hardware testing. It's about **shifting left** the things you *can* test without hardware: compilation, static analysis, unit tests on the host, and integration tests in emulation. Then, when you do run hardware tests, they're triggered automatically and the results are captured as artifacts — not scribbled on a sticky note.

The pipeline I'm building this week follows a three-stage model:

1. **Build & Static Analysis** — Compile for the target, run `cppcheck`, `clang-tidy`, and check binary size.
2. **Emulated Integration** — Run firmware in QEMU or Renode with synthetic peripheral stimuli, capture logs and pass/fail assertions.
3. **Hardware-in-the-Loop (HIL)** — Flash a physical board in a test jig, run a suite of end-to-end tests, and publish results.

Most teams skip stage 2 entirely. That's the biggest missed opportunity.

## Key Commands / Configuration / Code

Here's a minimal GitHub Actions workflow that demonstrates the first two stages for a STM32 project using the ARM GCC toolchain and QEMU:

```yaml
# .github/workflows/firmware-ci.yml
name: Firmware CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

env:
  # Pin the toolchain version for reproducibility (more on this tomorrow)
  ARM_TOOLCHAIN_VERSION: 12.3.rel1
  ARM_TOOLCHAIN_URL: "https://developer.arm.com/-/media/Files/downloads/gnu/12.3.rel1/binrel/arm-gnu-toolchain-12.3.rel1-x86_64-arm-none-eabi.tar.xz"

jobs:
  build-and-test:
    runs-on: ubuntu-22.04
    steps:
      - uses: actions/checkout@v4

      - name: Install ARM Toolchain
        run: |
          wget -q ${{ env.ARM_TOOLCHAIN_URL }}
          tar -xf arm-gnu-toolchain-*.tar.xz
          echo "$PWD/arm-gnu-toolchain-*/bin" >> $GITHUB_PATH

      - name: Build Firmware
        run: |
          # Assuming a CMake-based project with a custom toolchain file
          cmake -B build -DCMAKE_TOOLCHAIN_FILE=toolchain-arm-none-eabi.cmake
          cmake --build build --target firmware.elf
          # Check binary size doesn't exceed flash limit (512KB)
          SIZE=$(arm-none-eabi-size build/firmware.elf | tail -1 | awk '{print $1+$2}')
          if [ "$SIZE" -gt 524288 ]; then
            echo "ERROR: Binary size $SIZE exceeds 512KB limit"
            exit 1
          fi

      - name: Run Unit Tests (Host)
        run: |
          # Unit tests compiled for x86_64 using a test harness
          cmake -B build_test -DCMAKE_BUILD_TYPE=Test -DBUILD_UNIT_TESTS=ON
          cmake --build build_test
          ctest --test-dir build_test --output-on-failure

      - name: Run QEMU Integration Test
        run: |
          # Flash the ELF into QEMU's STM32 microcontroller model
          qemu-system-arm -M stm32-p103 \
            -kernel build/firmware.elf \
            -nographic \
            -semihosting \
            -serial mon:stdio \
            -d guest_errors \
            -D qemu_trace.log \
            -m 64M \
            -timeout 30 \
            || echo "QEMU exited (expected for test)"
          # Check for test pass/fail markers in UART output
          if grep -q "TEST_PASS" qemu_trace.log; then
            echo "Integration test passed"
          else
            echo "Integration test failed"
            exit 1
          fi

      - name: Archive Build Artifacts
        uses: actions/upload-artifact@v4
        with:
          name: firmware-binaries
          path: |
            build/firmware.elf
            build/firmware.hex
            build/firmware.bin
```

Key points in this workflow:

- **Toolchain pinning**: The URL includes a specific version (`12.3.rel1`). Tomorrow we'll make this even more rigorous.
- **Binary size gate**: A simple shell check prevents flash overflow before hardware testing.
- **QEMU integration**: The `-semihosting` and `-serial mon:stdio` flags let the firmware output test results to the host. The `-timeout` prevents hung tests from blocking the pipeline.
- **Artifact archiving**: Every build produces a downloadable binary, making it easy to flash a specific commit.

## Common Pitfalls & Gotchas

1. **QEMU models are not cycle-accurate.** Your firmware might pass in QEMU but fail on real hardware due to timing differences (e.g., a UART baud rate that's slightly off, or an interrupt that fires one cycle too late). Always treat emulation as a *sanity check*, not a replacement for HIL.

2. **Toolchain version drift between developer machines.** I've seen teams waste days debugging a linker error that only happened because one engineer had GCC 10.3 and another had 12.2. Pin your toolchain in the CI config *and* in your Docker image. More on this tomorrow.

3. **Flaky hardware tests in CI.** A physical test jig might fail because a USB cable wiggled loose or a power supply sagged. Build retry logic into your HIL stage (e.g., "run up to 3 times, pass if any succeeds") and log environmental data (temperature, voltage) alongside test results.

## Try It Yourself

1. **Add a binary size gate to your existing build.** If you don't have one, add a post-build step that runs `arm-none-eabi-size` and fails if the `.text` + `.data` sections exceed 80% of your MCU's flash. This prevents silent overflow when adding features.

2. **Run your firmware in QEMU.** Pick a supported board (STM32, Raspberry Pi, or ARM versatile). Add a `printf` that prints "TEST_PASS" after initialization. Run it in QEMU with `-nographic` and verify the string appears. This is your first emulated integration test.

3. **Set up a GitHub Actions workflow** that compiles your firmware and runs a single unit test (even a trivial one like "assert 1 == 1"). The goal is to see the pipeline turn green. From there, you can add more tests.

## Next Up

Tomorrow: **Reproducible Builds: Pinning Compiler, SDK & Dependency Versions** — we'll lock down every version in your toolchain, from the ARM GCC compiler to the CMSIS headers to your RTOS source, so that a build from six months ago produces byte-identical output.
