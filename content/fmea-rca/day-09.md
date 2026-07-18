---
title: "Day 09: D4: Root Cause Identification & Verification"
date: 2026-07-18
tags: ["til", "fmea-rca", "d4", "root-cause"]
---

## What I Explored Today

Today I worked through D4 of the 8D process — Root Cause Identification and Verification. This is the make-or-break step where we move from describing *what* happened to proving *why* it happened. I focused on three practical techniques: the 5-Whys with evidence gates, Ishikawa (fishbone) diagrams for systematic cause mapping, and statistical verification using real embedded system data. The goal isn't just to list causes — it's to isolate the *root* cause that, when removed, prevents recurrence.

## The Core Concept

Most engineers skip verification. They brainstorm causes, pick the most plausible one, and jump to fixing it. That’s how we get recurring bugs and field returns. D4 demands that we **verify** the root cause with data, not opinion.

The key insight: a root cause must satisfy two criteria:
1. **Causal necessity** — if you remove it, the failure stops.
2. **Causal sufficiency** — if you reintroduce it (under controlled conditions), the failure reproduces.

In embedded systems, this often means instrumenting the system with debug logs, oscilloscope captures, or fault injection to prove the causal chain. Without verification, you’re guessing. With verification, you have a defensible root cause that survives peer review and management scrutiny.

## Key Commands / Configuration / Code

### 1. Systematic 5-Whys with Evidence Gates

Instead of a free-form 5-Whys, I use a structured table that forces evidence at each level. Here’s a real example from a UART buffer overflow issue:

```bash
# Problem: System watchdog reset after 72 hours of continuous UART traffic
# 5-Whys with evidence gates

Level | Why Question                        | Answer                          | Evidence
------|-------------------------------------|---------------------------------|-----------------------------------------
1     | Why did the watchdog reset?         | Task watchdog timeout           | Log: "WDT reset at T+259200s"
2     | Why did the task timeout?           | UART ISR blocked for >500ms     | Oscilloscope: ISR pin high for 620ms
3     | Why was the ISR blocked so long?    | RX buffer full, ISR in loop     | Code review: while loop without timeout
4     | Why was the RX buffer full?         | DMA not draining fast enough    | DMA descriptor count = 0 (stalled)
5     | Why did DMA stall?                  | DMA channel priority lower than SPI | Datasheet: DMA priority table
```

**Verification step:** I changed DMA priority to match SPI, ran the same 72-hour test — no reset. Then I reverted the priority, and the reset returned. Causal sufficiency confirmed.

### 2. Ishikawa Diagram with Fault Injection

For complex failures, I build a fishbone in a text file, then inject faults to test each branch:

```bash
# fishbone.txt — UART watchdog reset
# Categories: Methods, Machine, Material, Measurement, Environment, People

Methods:
  └─ ISR without timeout
  └─ No DMA flow control

Machine:
  └─ DMA priority < SPI priority
  └─ UART FIFO depth = 16 bytes

Material:
  └─ RS-232 cable > 15m (noise)
  └─ Ground loop on test bench

Measurement:
  └─ No DMA descriptor watermark interrupt
  └─ Watchdog timeout too short (500ms)

Environment:
  └─ Temperature > 60°C (clock drift)
  └─ EMI from adjacent motor driver

People:
  └─ No code review of ISR
  └─ DMA config copied from different MCU
```

**Fault injection test (pseudocode):**
```c
// Test branch: "No DMA flow control"
// Inject: Disable DMA flow control, enable UART at 115200 baud
// Expected: Watchdog reset within 10 minutes
// Actual: Reset at 8m23s — branch confirmed

void test_dma_flow_control(void) {
    // Temporarily disable flow control
    DMA_Channel->CFG &= ~DMA_CFG_FLOW_CTRL;
    // Run stress test
    uart_send_burst(1024 * 100, 115200);
    // Log result
    if (watchdog_reset_occurred) {
        printf("FAIL: DMA flow control required\n");
    } else {
        printf("PASS: DMA flow control not root cause\n");
    }
}
```

### 3. Statistical Verification with Log Analysis

For intermittent failures, I use log timestamp analysis to correlate causes:

```bash
# Extract all watchdog reset timestamps from syslog
grep "WDT reset" /var/log/embedded.log | awk '{print $1}' > reset_times.txt

# Extract all UART overflow events
grep "UART RX overflow" /var/log/embedded.log | awk '{print $1}' > overflow_times.txt

# Check correlation: are overflows always within 1 second before resets?
while read reset; do
  grep -q "$(date -d "$reset -1 second" +%H:%M:%S)" overflow_times.txt && echo "Correlated: $reset"
done < reset_times.txt
```

If every reset has a preceding overflow within 1 second, you have strong statistical evidence.

## Common Pitfalls & Gotchas

1. **Confusing symptoms with root causes.** "The watchdog reset" is a symptom. "The ISR had no timeout" is closer, but "The DMA priority was lower than SPI" is the root cause. Keep asking "why" until you reach a physical or design-level cause that you can change.

2. **Verifying only one direction.** Engineers often verify that removing the cause stops the failure, but they skip re-introducing it to prove it causes the failure. Both directions are required for causal sufficiency. I’ve seen teams "fix" a bug by changing DMA priority, then later discover the real cause was a ground loop — the priority change just masked it.

3. **Over-relying on code review for verification.** Code review finds potential causes, but it doesn’t prove them. Always run a controlled experiment. For embedded systems, this means a test harness that can inject the suspected cause and measure the failure. If you can’t reproduce it on demand, you haven’t found the root cause.

## Try It Yourself

1. **Pick a recent embedded system failure** (watchdog reset, crash, data corruption). Write a 5-Whys table with an evidence column. For each "why," list the specific log, oscilloscope trace, or code inspection that proves that answer. If you can’t provide evidence, that level is a guess — go deeper.

2. **Build a fishbone diagram** for the same failure. For each branch, write a one-line fault injection test that would confirm or eliminate that branch. Example: "To test the 'ground loop' branch, disconnect the ground wire and measure noise on the UART RX pin with an oscilloscope."

3. **Run a correlation analysis** on your system logs. Extract timestamps for the failure symptom and for each suspected cause. Write a script (bash, Python, or even Excel) to check if the cause always precedes the symptom within a time window. If the correlation is weak, you’re looking at the wrong cause.

## Next Up

Tomorrow I’ll cover **D5-D6: Permanent Corrective Actions & Validation**. We’ll move from identifying the root cause to designing a fix that doesn’t just patch the symptom — and then prove the fix works under all conditions, not just the test bench. We’ll look at regression test suites, stress testing, and how to write a validation plan that survives a customer audit.
