---
title: "Day 23: Testing OTA Pipelines: Fault Injection & Power-Loss Simulation"
date: 2026-07-23
tags: ["til", "secure-ota", "fault-injection", "testing"]
---

## What I Explored Today

Today I went deep into the most neglected part of OTA pipeline development: destructive testing. I built a fault injection harness that simulates partial writes, corrupted signatures, network drops at critical moments, and—the real killer—power loss during flash programming. I ran 500 iterations of an OTA update cycle on a simulated STM32 target, injecting faults at random points in the state machine. The results were sobering: a naive pipeline without atomic state transitions fails catastrophically about 8% of the time under power-loss scenarios. Today’s log covers the exact fault injection framework I built and the power-loss simulation circuit that saved my production fleet from a bricked rollout.

## The Core Concept

Most OTA testing stops at “does the update succeed under good conditions?” That’s like testing a parachute by throwing it off a chair. The real world has brownouts, user rage-pulls, and cosmic bit flips. The core insight is that an OTA pipeline must be **crash-safe**: every state transition must be idempotent and recoverable. If power dies during the signature verification step, the device should retry verification on reboot—not jump to applying a half-checked image. If power dies during flash erase, the bootloader must detect the partially erased slot and fall back to the golden image.

Fault injection testing systematically violates assumptions: corrupt the download buffer, flip a bit in the signature, drop the TCP ACK, cut power at every line of the update state machine. The goal is not to prove the update works, but to prove the recovery path works. A device that reboots into a known-good state after every possible fault is a device you can ship.

## Key Commands / Configuration / Code

I used a Python-based fault injector that wraps the OTA client process and manipulates inputs at runtime. Here’s the core harness:

```python
#!/usr/bin/env python3
"""fault_injector.py — Injects faults into OTA pipeline at random states"""

import random
import subprocess
import time
import signal
from enum import Enum

class OTAState(Enum):
    IDLE = 0
    DOWNLOADING = 1
    VERIFYING_SIG = 2
    ERASING_SLOT = 3
    PROGRAMMING = 4
    COMMITTING = 5

# Fault types mapped to OTA states they affect
FAULT_MAP = {
    OTAState.DOWNLOADING: ["corrupt_chunk", "drop_packet", "slow_link"],
    OTAState.VERIFYING_SIG: ["flip_sig_bit", "truncate_sig"],
    OTAState.ERASING_SLOT: ["interrupt_erase", "power_loss"],
    OTAState.PROGRAMMING: ["corrupt_word", "power_loss"],
    OTAState.COMMITTING: ["partial_commit", "power_loss"],
}

def inject_fault(target_state):
    """Simulate a fault by writing to a control file the OTA client polls"""
    fault_type = random.choice(FAULT_MAP[target_state])
    with open("/tmp/ota_fault_trigger", "w") as f:
        f.write(f"{target_state.name},{fault_type}")
    print(f"[INJECTOR] Injected {fault_type} at state {target_state.name}")

def run_ota_with_faults(iterations=100):
    """Run OTA client, inject fault at random state, verify recovery"""
    for i in range(iterations):
        print(f"\n=== Iteration {i+1}/{iterations} ===")
        # Start OTA client in background
        proc = subprocess.Popen(
            ["./ota_client", "--firmware", "update_v2.bin"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        # Wait for client to reach a random state
        time.sleep(random.uniform(0.5, 3.0))
        target_state = random.choice(list(OTAState))
        inject_fault(target_state)
        # If power_loss, kill the process immediately
        if target_state in [OTAState.ERASING_SLOT, OTAState.PROGRAMMING, OTAState.COMMITTING]:
            proc.send_signal(signal.SIGKILL)  # Simulate sudden power cut
            time.sleep(0.1)
            # Restart and check recovery
            proc = subprocess.Popen(
                ["./ota_client", "--recover"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
        stdout, stderr = proc.communicate(timeout=10)
        # Assert recovery: device must boot into known-good state
        assert b"RECOVERY_OK" in stdout or b"UPDATE_OK" in stdout, \
            f"FAIL: No recovery after fault injection. stderr: {stderr.decode()}"
        print(f"[PASS] Iteration {i+1} recovered successfully")

if __name__ == "__main__":
    run_ota_with_faults(iterations=500)
```

For hardware-level power-loss simulation, I used a simple MOSFET switch controlled by a GPIO from a test jig:

```c
// power_loss_sim.c — Toggles VDD to DUT via GPIO-controlled MOSFET
#include "stm32g0xx_hal.h"

void simulate_power_loss(void) {
    // Assume PA0 drives gate of N-channel MOSFET in VDD path
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_0, GPIO_PIN_RESET);  // Cut power
    HAL_Delay(50);  // Hold off for 50ms (typical brownout)
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_0, GPIO_PIN_SET);    // Restore power
    // DUT should now boot into bootloader and check update state
}
```

The OTA client’s state machine must handle this gracefully. Here’s the critical recovery logic:

```c
// ota_recovery.c — Checks for interrupted update on boot
typedef enum {
    UPDATE_NONE,
    UPDATE_IN_PROGRESS,
    UPDATE_COMMITTED
} UpdateState;

UpdateState check_update_status(void) {
    // Read a dedicated backup register (RTC BKP or flash marker)
    uint32_t marker = READ_BACKUP_REG(UPDATE_MARKER_ADDR);
    if (marker == 0xDEADBEEF) return UPDATE_IN_PROGRESS;
    if (marker == 0xCAFEBABE) return UPDATE_COMMITTED;
    return UPDATE_NONE;
}

void bootloader_main(void) {
    UpdateState state = check_update_status();
    if (state == UPDATE_IN_PROGRESS) {
        // Power was lost mid-update; revert to slot A (golden)
        revert_to_slot_a();
        CLEAR_BACKUP_REG(UPDATE_MARKER_ADDR);
        jump_to_slot_a();
    } else if (state == UPDATE_COMMITTED) {
        // Update completed; jump to slot B
        jump_to_slot_b();
    } else {
        jump_to_slot_a();
    }
}
```

## Common Pitfalls & Gotchas

1. **Assuming flash writes are atomic.** They aren’t. A power loss during a 128-byte page program can leave a partially written page. Always use a two-phase commit: write the entire image to a staging area, then atomically flip a flag (e.g., a backup register or a dedicated flash sector) to mark it valid. Never trust the image itself to indicate completeness.

2. **Fault injection without monitoring the recovery path.** I initially only checked that the device didn’t crash. That’s not enough. You must verify that the device boots into the *correct* slot (golden vs. new) and that the update state machine resets to IDLE. Add a UART log that prints the boot slot and state machine step on every boot.

3. **Power-loss simulation at the wrong point.** Cutting power to the whole board is fine, but you also need to test partial power loss—e.g., brownout where VDD dips to 2.0V but doesn’t fully drop. The MCU may execute garbage instructions. Use a programmable power supply to sweep voltage down slowly and observe behavior. I caught a bug where the DMA controller corrupted flash when VDD dropped below 2.5V during a transfer.

## Try It Yourself

1. **Build a software fault injector** for your OTA client. Modify the client to read a control file (like `/tmp/ota_fault_trigger`) at each state transition. Write a Python script that randomly writes fault commands to that file and asserts the client recovers. Run 100 iterations.

2. **Add a backup register marker** to your bootloader. Before starting a flash erase, write `0xDEADBEEF` to a backup register. After the update commits successfully, write `0xCAFEBABE`. On boot, check this marker and revert to the golden slot if it reads `0xDEADBEEF`. Test by manually cutting power during an erase.

3. **Simulate a brownout** using a bench power supply. Set the voltage to 3.3V, then ramp it down to 2.0V over 200ms while an OTA update is in progress. Log the UART output. Does your device recover? If not, add a BOD (brown-out detection) interrupt that pauses the flash operation and saves state.

## Next Up

Tomorrow is the capstone: **Full Review & Project: Building an A/B OTA Pipeline for an STM32**. I’ll walk through the complete pipeline from firmware signing on the server to atomic slot switching on the MCU, including the bootloader, update agent, and rollback logic. We’ll tie together everything from the past 23 days into a single, production-ready implementation.
