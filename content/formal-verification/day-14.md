---
title: "Day 14: AFL++: Coverage-Guided Fuzzing for Firmware"
date: 2026-06-26
tags: ["til", "formal-verification", "afl", "fuzzing", "coverage"]
---

## What I Explored Today

Today I set up AFL++ to fuzz a firmware image extracted from a Cortex-M4 target. While AFL++ is typically associated with user-space binaries, the same coverage-guided engine can be pointed at firmware code if we provide a proper harness and a hardware-in-the-loop or emulated execution environment. I walked through instrumenting a stripped-down firmware parser, running AFL++ in persistent mode, and interpreting the crash corpus it generated. The key takeaway: AFL++ doesn't care whether the target is a Linux ELF or a bare-metal firmware blob—it only cares about code coverage feedback and input mutation.

## The Core Concept

Coverage-guided fuzzing works by feeding mutated inputs into a target program and observing which code paths are exercised. AFL++ instruments the binary at compile time (or uses QEMU user-mode emulation for black-box binaries) to insert lightweight counters at every basic block. When an input triggers a new edge—a transition from one basic block to another that hasn't been seen before—the fuzzer saves that input as a "seed" for further mutation. Over time, the fuzzer builds a map of all reachable edges, prioritizing inputs that explore new territory.

For firmware, the challenge is that the code doesn't run on a host OS. We solve this by writing a harness that mimics the firmware's entry point, loads the firmware blob into a memory buffer, and calls the target function (e.g., a protocol parser) in a loop. The harness runs under AFL++'s instrumented environment, and the fuzzer treats the harness as the "firmware." This is the same technique used by projects like FuzzOS and Unicorn-based fuzzers, but with AFL++ we get the full power of its genetic mutation engine and crash deduplication.

## Key Commands / Configuration / Code

### 1. Instrumenting the Firmware Harness

We compile the harness with AFL++'s compiler wrapper. The firmware parser is a simple function that processes a byte buffer:

```c
// firmware_harness.c
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "afl-fuzz.h"  // provides __AFL_FUZZ_INIT()

// The firmware's parser function (simplified)
int parse_firmware_packet(const uint8_t *data, size_t len);

// AFL++ persistent mode harness
__AFL_FUZZ_INIT();

int main(int argc, char **argv) {
    // Initialize AFL++ persistent loop
    #ifdef __AFL_HAVE_MANUAL_CONTROL
        __AFL_INIT();
    #endif

    uint8_t *buf = __AFL_FUZZ_TESTCASE_BUF;
    while (__AFL_LOOP(10000)) {  // 10k iterations before restart
        size_t len = __AFL_FUZZ_TESTCASE_LEN;
        // Call the firmware parser
        parse_firmware_packet(buf, len);
    }
    return 0;
}
```

Compile with AFL++'s LLVM mode for best instrumentation:

```bash
# Use afl-clang-fast for LLVM-based instrumentation
afl-clang-fast -O2 -g -o firmware_harness firmware_harness.c \
    firmware_parser.c -I./include

# Verify instrumentation
afl-showmap -o /dev/null -- ./firmware_harness < seed.bin
```

### 2. Running AFL++ in Persistent Mode

Persistent mode avoids the overhead of forking for every input. The harness reuses the same process for up to 10,000 iterations, which is critical for firmware fuzzing where setup costs (e.g., MMU initialization) are high.

```bash
# Create input and output directories
mkdir -p seeds findings

# Place a valid firmware packet as seed
echo -n -e '\x01\x02\x03\x04' > seeds/valid.bin

# Run AFL++ with 4 cores
afl-fuzz -i seeds -o findings -M fuzzer1 \
    -t 5000 -m 512 \
    ./firmware_harness

# On other terminals, add secondary fuzzers
afl-fuzz -i seeds -o findings -S fuzzer2 \
    -t 5000 -m 512 \
    ./firmware_harness
```

Key flags:
- `-t 5000`: timeout per input (5 seconds—generous for firmware)
- `-m 512`: memory limit (512 MB)
- `-M`/`-S`: master/slave mode for parallel fuzzing

### 3. Analyzing Crashes

When AFL++ finds a crash, it saves the input to `findings/default/crashes/`. Use a debugger to replay:

```bash
# Replay a crash with GDB
gdb --args ./firmware_harness < findings/default/crashes/id:000000,sig:06,src:000001

# Or use AFL++'s crash exploration mode
afl-fuzz -C -i findings/default/crashes -o crash_explore \
    -t 5000 -m 512 \
    ./firmware_harness
```

## Common Pitfalls & Gotchas

1. **Missing persistent mode setup**: Without `__AFL_LOOP()`, AFL++ forks for every input. For firmware harnesses with heavy initialization (e.g., loading firmware into emulated memory), this kills throughput. Always use persistent mode and set the iteration count high (10,000–100,000).

2. **False positives from timeout**: Firmware often has infinite loops or watchdog timers. AFL++'s default timeout (1 second) may kill valid inputs. Increase `-t` to 5000 ms or more, and consider using `AFL_EXIT_WHEN_DONE` to avoid premature termination.

3. **Instrumentation of non-firmware code**: If your harness links against libc or OS libraries, AFL++ instruments those too, diluting coverage feedback. Use `AFL_INST_RATIO=10` to instrument only 10% of non-target code, or compile with `-fsanitize-coverage=trace-pc` for precise control.

## Try It Yourself

1. **Harness a real firmware parser**: Extract a simple protocol parser from an open-source firmware (e.g., the CAN bus handler from FreeRTOS+TCP). Write a harness that feeds raw bytes into the parser and run AFL++ for 1 hour. Compare the number of edges covered vs. random fuzzing.

2. **Tune persistent mode**: Modify the `__AFL_LOOP()` count from 100 to 100,000. Measure the execs/sec reported by AFL++ for each setting. Plot the throughput vs. iteration count—find the sweet spot where fork overhead is negligible.

3. **Crash triage with ASan**: Recompile the harness with AddressSanitizer (`-fsanitize=address`) and re-fuzz the same target. Compare the number of unique crashes found. ASan often catches buffer overflows that AFL++'s signal-based detection misses.

## Next Up

Tomorrow we dive into runtime sanitizers: AddressSanitizer (ASan) and UndefinedBehaviorSanitizer (UBSan). These tools instrument the binary at compile time to detect memory errors and undefined behavior during execution—critical for validating the crashes that AFL++ finds. We'll build a firmware harness with both sanitizers and see how they catch bugs that static analysis alone cannot.
