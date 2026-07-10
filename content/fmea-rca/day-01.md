---
title: "Day 01: Why Root Cause Analysis? From Symptom to Systemic Fix"
date: 2026-07-10
tags: ["til", "fmea-rca", "rca", "root-cause"]
---

## What I Explored Today

I’ve spent the last decade chasing bugs in embedded systems—from UART glitches on prototype boards to watchdog resets in production fleets. Every time, the temptation was to patch the symptom: add a delay, retry the transaction, or swap the component. Today, I formally stepped back to study *why* Root Cause Analysis (RCA) exists as a discipline, not just a buzzword. I dissected the difference between a symptom, a proximate cause, and a root cause, and mapped how systemic fixes prevent recurrence. This isn’t theory—it’s the difference between a hotfix that holds for a week and a design change that survives a field upgrade.

## The Core Concept

Most engineers are trained to fix what breaks. You see a CAN bus error, you increase the timeout. You see a memory corruption, you add a `volatile` qualifier. That’s treating the symptom. The root cause is the *mechanism* that made the symptom possible in the first place.

Consider a real embedded scenario: a sensor reading occasionally returns `0xFFFFFFFF` instead of a valid ADC value. The symptom is the bad reading. The proximate cause might be a race condition in the ISR that reads the ADC register while the conversion is still in progress. The root cause? The system design didn’t enforce atomic access to the shared ADC data register between the ISR and the main loop. The systemic fix isn’t a `while(!ADC_READY);` spin—it’s a proper mutex or a double-buffer pattern that eliminates the race by design.

RCA forces you to ask “why” five times (the 5 Whys technique) until you hit a process, design, or requirement failure. If your fix doesn’t change a specification, a schematic, or a code review checklist, you haven’t found the root cause.

## Key Commands / Configuration / Code

Let’s ground this with a concrete embedded C example. Here’s a classic symptom: an I²C write to an EEPROM occasionally fails with a NACK.

```c
// Symptom: i2c_write() returns -1 (NACK) ~1% of the time
int i2c_write(uint8_t dev_addr, uint8_t reg, uint8_t data) {
    // Wait for bus idle (proximate fix: add delay)
    // delay_ms(10);  // <-- This masks the symptom
    
    i2c_start();
    if (i2c_send_byte(dev_addr << 1 | 0) != 0) { // Write address
        i2c_stop();
        return -1; // NACK on address
    }
    // ... send reg, data, stop
    return 0;
}
```

The proximate fix (commented out) adds a 10 ms delay before every write. It “works” because the EEPROM’s internal write cycle finishes. But it’s fragile—change the EEPROM part, increase the bus speed, or add another master, and the failure returns.

The root cause analysis using a 5-Whys trace:

1. **Why does the write NACK?** The EEPROM is busy with an internal write cycle.
2. **Why is it busy?** The previous write hasn’t completed (tWR = 5 ms typical).
3. **Why don’t we wait for completion?** The driver doesn’t check the ACK polling sequence after a write.
4. **Why doesn’t the driver check?** The I²C state machine was designed for a different EEPROM that had a shorter tWR.
5. **Why was the design assumption wrong?** The hardware spec wasn’t updated when the EEPROM was swapped in a BOM change.

The systemic fix is to implement proper ACK polling, not a delay:

```c
// Systemic fix: Poll for ACK after write (per EEPROM datasheet)
int i2c_write_with_ack_poll(uint8_t dev_addr, uint8_t reg, uint8_t data) {
    int ret = i2c_write(dev_addr, reg, data);
    if (ret != 0) return ret;

    // Poll: send the device address and check for ACK
    uint32_t timeout = 1000; // 1 second max
    while (timeout--) {
        i2c_start();
        if (i2c_send_byte(dev_addr << 1 | 0) == 0) { // ACK received
            i2c_stop();
            return 0; // EEPROM ready
        }
        i2c_stop();
        delay_ms(1); // Small delay between polls
    }
    return -2; // Timeout error
}
```

This fix addresses the root cause: the driver now respects the EEPROM’s timing specification. It’s portable, deterministic, and survives part changes.

## Common Pitfalls & Gotchas

1. **Confusing correlation with causation.** Just because a bug disappears when you add a `volatile` qualifier doesn’t mean the missing `volatile` was the root cause. It might have just changed the compiler’s register allocation, masking a deeper race condition. Always verify the mechanism, not just the outcome.

2. **Stopping at the proximate cause.** In the I²C example, “the EEPROM is busy” is a proximate cause. If you fix by adding a delay, you’ve stopped too early. The real root cause is a process failure: the BOM change wasn’t reviewed against the driver spec. Always ask “why” until you hit a process, documentation, or design standard that can be changed.

3. **Ignoring systemic factors in firmware-only fixes.** A firmware patch that adds a retry loop might work, but if the hardware has a marginal pull-up resistor on the I²C line, the root cause is a design margin issue. The firmware fix is a bandage. The systemic fix is updating the schematic and the hardware verification checklist.

## Try It Yourself

1. **5-Whys on a past bug.** Pick a bug you fixed in the last month. Write down the symptom, then ask “why” five times. Did you stop at the proximate cause? If so, what’s the systemic fix you missed?

2. **Audit a driver for “magic delays.”** Find a driver in your codebase that uses `delay_ms()` or `usleep()` to work around a timing issue. Remove the delay and see if the failure returns. If it does, implement a proper polling or interrupt-based solution per the datasheet.

3. **Create a “symptom vs. root cause” log.** For the next week, every time you fix a bug, write two lines: “Symptom fixed by:” and “Root cause addressed by:”. At the end of the week, count how many fixes addressed a root cause vs. a symptom.

## Next Up

Tomorrow, we’ll dive into the **8D Problem Solving Process**—the structured framework that turns RCA from a mental exercise into a repeatable, auditable methodology. We’ll cover when to use 8D (and when not to), the eight disciplines, and how to avoid the “jump to solution” trap that kills effective root cause analysis.
