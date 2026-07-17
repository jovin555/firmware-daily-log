---
title: "Day 17: Fuzzing Embedded Firmware: AFL++, libFuzzer & Hardware-in-the-Loop"
date: 2026-07-17
tags: ["til", "threat-modeling", "fuzzing", "afl"]
---

## What I Explored Today

Today I dove into fuzzing embedded firmware—specifically how to apply AFL++ and libFuzzer to microcontroller code, and why hardware-in-the-loop (HIL) fuzzing is necessary when you can't fully simulate peripherals. I built a harness for a real-time control loop, ran AFL++ on the parser logic in user-space, then cross-compiled the same harness for an ARM Cortex-M4 target and ran it on actual silicon via OpenOCD+GDB. The gap between simulated and real-world behavior was stark: timing-dependent bugs and memory-mapped register side-effects only appeared on hardware.

## The Core Concept

Fuzzing embedded firmware is harder than fuzzing a Linux binary because the code is tightly coupled to hardware. You can't just `afl-fuzz -i input -o output -- ./firmware.elf`—the firmware expects specific register addresses, interrupt vectors, and peripheral states. The standard approach is to extract the "logic" (parsers, protocol handlers, state machines) into a user-space harness, then fuzz that with AFL++ or libFuzzer. But this misses hardware-specific bugs: race conditions with DMA, memory-mapped I/O timing, and watchdog resets. That's where HIL fuzzing comes in—you run the real firmware on a dev board, feed it mutated inputs via a debugger or serial, and monitor for crashes or hangs. The tradeoff is speed: user-space fuzzing does 10k+ execs/sec; HIL fuzzing does 10-100 execs/sec.

## Key Commands / Configuration / Code

### 1. User-Space Harness for AFL++ (extracting a CAN parser)

```c
// harness.c — compile with afl-clang-fast, link against firmware logic
#include "can_parser.h"  // from firmware source
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

// AFL++ requires __AFL_FUZZ_INIT() for persistent mode
__AFL_FUZZ_INIT();

int main(int argc, char **argv) {
    unsigned char *buf = __AFL_FUZZ_TESTCASE_BUF;
    while (__AFL_LOOP(10000)) {  // persistent mode: 10k iterations per fork
        int len = __AFL_FUZZ_TESTCASE_LEN;
        if (len < 8) continue;  // minimum CAN frame size
        
        CanFrame frame;
        memset(&frame, 0, sizeof(frame));
        memcpy(&frame.id, buf, 4);
        memcpy(&frame.dlc, buf + 4, 1);
        memcpy(&frame.data, buf + 5, len - 5);
        
        // Call the actual firmware parser
        parse_can_frame(&frame);
    }
    return 0;
}
```

Compile and run:
```bash
# Instrument with AFL++
afl-clang-fast -O2 -g -o harness harness.c can_parser.c -lm

# Start fuzzing (use a small seed corpus)
afl-fuzz -i seeds/ -o findings/ -t 1000 -- ./harness
```

### 2. libFuzzer Harness for a JSON config parser (with sanitizers)

```c
// fuzz_json_parser.c
#include <stdint.h>
#include <stddef.h>
#include "json_config.h"

int LLVMFuzzerTestOneInput(const uint8_t *Data, size_t Size) {
    // libFuzzer handles the loop; just parse one input
    ConfigResult result;
    if (parse_json_config((const char *)Data, Size, &result) == 0) {
        // Free any allocated memory to avoid leaks
        free_config_result(&result);
    }
    return 0;  // 0 = no crash detected
}
```

Compile and run with AddressSanitizer:
```bash
clang -fsanitize=fuzzer,address -O2 -g -o fuzz_json fuzz_json_parser.c json_config.c
./fuzz_json -max_len=512 -runs=1000000 seeds/
```

### 3. Hardware-in-the-Loop Fuzzing with OpenOCD+GDB

```python
# hil_fuzzer.py — simplified HIL fuzzer for STM32F4
import subprocess
import struct
import random

TARGET_ADDR = 0x20001000  # SRAM buffer for input
CRASH_ADDR  = 0x08000000  # HardFault handler

def flash_and_run(firmware_elf, input_bytes):
    # Write input to SRAM via OpenOCD
    cmd = f"echo 'mww {hex(TARGET_ADDR)} {len(input_bytes)}; " \
          f"load_image {firmware_elf}; resume; sleep 100; halt; " \
          f"reg r15' | openocd -f board/stm32f4discovery.cfg -c 'gdb_port 3333'"
    result = subprocess.run(cmd, shell=True, capture_output=True, timeout=5)
    
    # Check if PC is at crash handler
    if f"0x{CRASH_ADDR:08x}" in result.stdout.decode():
        return "CRASH"
    return "OK"

# Fuzz loop
for i in range(1000):
    length = random.randint(4, 128)
    payload = bytes([random.randint(0, 255) for _ in range(length)])
    status = flash_and_run("firmware.elf", payload)
    if status == "CRASH":
        with open(f"crash_{i}.bin", "wb") as f:
            f.write(payload)
```

## Common Pitfalls & Gotchas

1. **Ignoring memory-mapped register side-effects in user-space harnesses**  
   When you extract a parser, you often stub out hardware access with dummy functions. But if the real code writes to a register that triggers a DMA transfer, your stub won't catch the race condition. Always verify that the harness behavior matches hardware by running the same test case on the target.

2. **AFL++ persistent mode without proper state reset**  
   In the `__AFL_LOOP(10000)` example above, if your parser allocates heap memory or modifies global state, you'll get false positives on the second iteration. Always reset globals or use `__AFL_INIT()` with `mmap()` for clean state per iteration.

3. **HIL fuzzing speed kills coverage**  
   At 10 execs/sec, you can't brute-force. Use coverage-guided mutation (e.g., collect branch coverage via ETM trace or hardware breakpoints) to focus on new paths. Without coverage feedback, you're just random testing.

## Try It Yourself

1. **Extract a UART command parser from your firmware** into a standalone C file, write an AFL++ harness, and fuzz it. Find at least one crash (buffer overflow or null dereference) in the first 100k iterations.

2. **Cross-compile the same harness for your target MCU** (e.g., ARM Cortex-M4) and run it on a dev board via OpenOCD. Compare the crash rate and bug types between user-space and HIL fuzzing.

3. **Add coverage feedback to the HIL fuzzer** using hardware breakpoints on basic blocks. Use GDB's `rwatch` or STM32's DWT unit to count unique paths. Report the coverage difference vs. blind random input.

## Next Up

Tomorrow: **Command Injection & Insecure Deserialization in IoT Protocols** — how MQTT, CoAP, and custom binary protocols get pwned when firmware blindly trusts serialized data, and how to validate inputs before they hit the parser.
