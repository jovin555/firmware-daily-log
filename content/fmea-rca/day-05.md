---
title: "Day 05: 5 Whys: Technique, Pitfalls & Avoiding Shallow Answers"
date: 2026-07-14
tags: ["til", "fmea-rca", "5-whys"]
---

## What I Explored Today

After spending yesterday mapping the fault tree for that UART glitch, I turned to the 5 Whys technique. It’s deceptively simple—ask “why” five times to drill from symptom to root cause. But in practice, most engineers stop at the first plausible answer. Today I dissected the method, ran it against a real embedded failure (a watchdog timer reset on a production sensor node), and cataloged the common traps that turn a 5 Whys session into a blame game.

## The Core Concept

The 5 Whys is not a checklist; it’s a directed inquiry. The goal is to move from **symptom** (what broke) through **proximate cause** (the immediate trigger) to **root cause** (the system or process failure that allowed the proximate cause to exist). In embedded systems, the root cause is almost never “the code crashed.” It’s “we didn’t validate the input buffer size against the datasheet’s maximum packet length.”

The technique works because each “why” forces you to cross a layer of abstraction:

- **Why 1:** Physical/observable event (e.g., “the MCU reset”)
- **Why 2:** Direct trigger (e.g., “watchdog timer expired”)
- **Why 3:** Code/state failure (e.g., “main loop blocked on a semaphore”)
- **Why 4:** Design oversight (e.g., “ISR held semaphore longer than WDT period”)
- **Why 5:** Process gap (e.g., “no worst-case ISR latency analysis was performed”)

If you stop before Why 5, you fix the symptom, not the system. The real power is that Why 5 often points to a missing review, test, or specification—something you can change permanently.

## Key Commands / Configuration / Code

Here’s a real 5 Whys session I ran on a sensor node that spontaneously reset every 72 hours. I’ll show the raw log, then the structured output.

**Symptom:** Sensor node resets every ~72 hours.

```
Why 1: Why does the node reset?
Because the watchdog timer (WDT) fires and triggers a hardware reset.

Why 2: Why does the WDT fire?
Because the main loop task does not call `wdt_kick()` within the 2-second timeout window.

Why 3: Why doesn’t the main loop call `wdt_kick()`?
Because the task is blocked indefinitely on `osSemaphoreAcquire(sensor_sem, portMAX_DELAY)`.

Why 4: Why is the semaphore never released?
Because the ISR that gives the semaphore (`sensor_irq_handler`) never executes after the first 72 hours.

Why 5: Why does the ISR stop executing?
Because the sensor’s data-ready pin (GPIO) is configured as a falling-edge interrupt, but after 72 hours the sensor enters a low-power state that drives the pin high permanently—no edge ever occurs.
```

**Root cause:** The GPIO interrupt configuration assumed the sensor would always produce a falling edge on data-ready. The sensor datasheet (Section 7.3.2) states that after 72 hours of continuous operation without a power cycle, the pin transitions to a static high in low-power mode. No edge → no ISR → no semaphore give → WDT reset.

**Fix:** Change the interrupt to trigger on *both* edges, and add a periodic polling fallback in the main loop if the semaphore isn’t given within 1.5 seconds.

Here’s the code diff that fixed it:

```c
// Before: falling-edge only
// GPIO_ConfigInterrupt(SENSOR_DRDY_PIN, GPIO_INT_FALLING_EDGE);

// After: both edges + timeout fallback
GPIO_ConfigInterrupt(SENSOR_DRDY_PIN, GPIO_INT_BOTH_EDGES);

// In main loop task:
while (1) {
    // Wait for semaphore with 1.5s timeout (WDT period is 2s)
    if (osSemaphoreAcquire(sensor_sem, pdMS_TO_TICKS(1500)) == osOK) {
        process_sensor_data();
    } else {
        // Timeout: sensor may be in low-power mode, force a read
        sensor_force_read();  // Toggles sensor power via GPIO
        wdt_kick();           // Ensure WDT is fed
    }
    wdt_kick();               // Always feed after processing
}
```

## Common Pitfalls & Gotchas

**1. Stopping at “Human Error”**
The most seductive shallow answer. “Why did the register get corrupted? Because the programmer forgot to clear the interrupt flag.” That’s a person, not a process. The real Why 5 is: “Why didn’t the code review checklist include verifying interrupt flag clearing?” Never accept “someone made a mistake” as a root cause.

**2. Confirmation Bias in Questioning**
If you already suspect a cause (e.g., “it’s a race condition”), you’ll unconsciously steer the whys to confirm it. I’ve seen teams spend three whys proving a stack overflow when the real issue was a voltage droop. Force yourself to list *alternative* answers at each level before picking one. Use a whiteboard, not your head.

**3. Mixing Causes and Solutions**
A common trap: “Why did the buffer overflow? Because we should have used a bounds-checked function.” That’s a solution, not a cause. The correct answer is: “Because the input length was not validated against the buffer size before the `memcpy`.” Keep the whys descriptive, not prescriptive. Save solutions for the corrective action phase.

## Try It Yourself

1. **Run a 5 Whys on a past failure.** Pick a bug you fixed last month. Write down the symptom, then ask “why” five times. Did you stop at “I forgot to initialize the variable”? If so, push to Why 5: “Why wasn’t initialization required by the coding standard?”

2. **Audit a teammate’s 5 Whys.** Find a postmortem from your team’s bug tracker. For each “why,” ask: “Is this a cause or a solution?” If you see “we should have tested X,” rewrite it as “no test existed for X.” Count how many whys are actually causes.

3. **Add a “Why 0” to your process.** Before the first why, write down the exact symptom in measurable terms (e.g., “UART baud rate error > 2% at 115200 baud”). This prevents scope creep and keeps the chain focused on one failure mode.

## Next Up

Tomorrow: **Fishbone/Ishikawa Diagrams: Categorizing Potential Causes**. We’ll take the output of a 5 Whys session and map it onto a structured cause-and-effect diagram to catch the causes we missed.
