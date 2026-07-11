---
title: "Day 02: The 8D Process: Structure & When to Use It"
date: 2026-07-11
tags: ["til", "fmea-rca", "8d", "process"]
---

## What I Explored Today

Yesterday we laid the groundwork for why systematic root cause analysis matters. Today I dove deep into the 8D (Eight Disciplines) problem-solving methodology itself—its formal structure, the logic behind each discipline, and—critically—when to actually invoke it versus when a simpler approach will do. I reviewed the Ford Motor Company standard (the origin of 8D) and cross-referenced it with the AIAG (Automotive Industry Action Group) guidelines. The key insight: 8D is not a lightweight tool; it’s a heavyweight process designed for systemic, recurring, or high-impact failures. Using it for a loose screw on a prototype board is overkill. Using it for a field-recall-level firmware bug is mandatory.

## The Core Concept

The 8D process is a structured, team-oriented methodology for identifying the root cause of a problem, implementing a permanent corrective action, and preventing recurrence. It’s called “8D” because it has eight formal disciplines (steps), plus a planning phase (D0). The entire process is built on a closed-loop corrective action mindset—not just fixing the symptom, but fixing the system that allowed the symptom to exist.

Why does structure matter here? Because in embedded systems, problems are rarely isolated. A single bit-flip in a memory-mapped register can cascade into a field failure that takes weeks to reproduce. Without a disciplined process, engineers chase symptoms, apply band-aids, and the same root cause resurfaces in the next product revision. 8D forces you to:
- Contain the immediate damage (D1-D3)
- Find the true root cause (D4)
- Choose and verify the best fix (D5-D6)
- Prevent it from happening again (D7)
- Celebrate and standardize (D8)

The disciplines are:

| Discipline | Name | Purpose |
|------------|------|---------|
| D0 | Plan & Prepare | Decide if 8D is needed; define scope |
| D1 | Form the Team | Select cross-functional experts |
| D2 | Describe the Problem | Write a precise, measurable problem statement |
| D3 | Develop Interim Containment | Protect the customer until permanent fix is in |
| D4 | Root Cause Analysis | Use tools (5-Why, Fishbone, Fault Tree) to find the physical, human, and latent root causes |
| D5 | Choose & Verify Permanent Corrective Actions | Select the best fix; test it |
| D6 | Implement & Validate PCA | Deploy the fix; monitor for side effects |
| D7 | Prevent Recurrence | Update FMEAs, control plans, work instructions |
| D8 | Recognize the Team | Close out; document lessons learned |

The critical nuance: **D3 (containment) and D4 (root cause) happen in parallel.** You cannot wait to find the root cause before protecting the customer. In firmware, containment might mean disabling a feature via a patch or adding a watchdog reset. In hardware, it might mean a recall or a software workaround.

## Key Commands / Configuration / Code

While 8D is a process, not a tool, you will use specific engineering artifacts at each step. Here’s a practical example from a recent firmware bug I analyzed (a UART FIFO overflow causing intermittent data corruption):

**D2 – Problem Description (structured as a 5W2H):**

```plaintext
What:   UART data corruption (0x00 bytes inserted randomly)
Where:  On UART2, baud 115200, 8N1, FIFO enabled
When:   After ~1000 consecutive bytes received without delay
Who:    Observed on production units (rev C boards)
Why:    Not yet known (this is the problem statement, not root cause)
How:    Reproduced with a loopback test sending 0x55 pattern
How many: 1 in 500 bytes corrupted, reproducible 100%
```

**D3 – Interim Containment (firmware patch):**

```c
// uart_isr.c — temporary fix to prevent FIFO overflow
// D3 containment: disable FIFO and poll byte-by-byte
// NOTE: This reduces throughput but eliminates corruption
void UART2_IRQHandler(void) {
    // Original code (commented out for containment):
    // while (LL_USART_IsActiveFlag_RXNE(USART2)) {
    //     rx_byte = LL_USART_ReceiveData8(USART2);
    //     fifo_push(rx_byte);
    // }

    // D3 containment: single-byte read, no FIFO
    if (LL_USART_IsActiveFlag_RXNE(USART2)) {
        rx_byte = LL_USART_ReceiveData8(USART2);
        // Direct buffer write, no FIFO
        ring_buffer_write(&rx_ring, rx_byte);
    }
}
```

**D4 – Root Cause Analysis (5-Why snippet):**

```plaintext
Why 1: Data corruption occurs when UART receives >1000 bytes continuously.
Why 2: The FIFO overflows because the ISR cannot drain it fast enough.
Why 3: The ISR calls a blocking function (printf) during high-priority tasks.
Why 4: printf uses semaphore-based mutex that yields to a lower-priority task.
Why 5: The RTOS scheduler preempts the ISR context switch, delaying FIFO drain.
Root cause: Blocking call (printf) inside ISR causes priority inversion and FIFO overflow.
```

**D5 – Permanent Corrective Action (code change):**

```c
// uart_isr.c — permanent fix
// D5 PCA: Remove blocking call from ISR; use deferred processing
void UART2_IRQHandler(void) {
    BaseType_t xHigherPriorityTaskWoken = pdFALSE;
    while (LL_USART_IsActiveFlag_RXNE(USART2)) {
        uint8_t rx_byte = LL_USART_ReceiveData8(USART2);
        // Push to a lock-free ring buffer (ISR-safe)
        ring_buffer_write_from_isr(&rx_ring, rx_byte, &xHigherPriorityTaskWoken);
    }
    // Signal a task to process the data outside ISR
    vTaskNotifyGiveFromISR(xUartProcessingTask, &xHigherPriorityTaskWoken);
    portYIELD_FROM_ISR(xHigherPriorityTaskWoken);
}
```

## Common Pitfalls & Gotchas

1. **Skipping D3 (containment) to "save time."** I’ve seen teams jump straight to D4 because they think containment is unnecessary. This is a critical error. Without containment, the customer continues to experience the failure while you investigate. In embedded systems, containment might be a firmware patch that disables a feature—ugly but necessary. Never skip it.

2. **Confusing "symptom" with "problem description" in D2.** A common mistake: "The UART corrupts data" is a symptom. The problem description must include measurable conditions (baud rate, FIFO state, byte count, error rate). Without precise metrics, you cannot verify root cause or validate the fix. Use the 5W2H template religiously.

3. **Stopping at the physical root cause.** Many engineers find "the FIFO overflowed" and stop. That’s a physical cause. The 8D process requires you to find the *latent* root cause—the system or process flaw that allowed the physical cause to exist. In the example above, the latent cause was "no coding standard forbidding blocking calls in ISRs" and "code review missed the printf." Fixing only the physical cause guarantees recurrence in a different form.

## Try It Yourself

1. **Write a D2 problem statement for a real bug you’ve encountered.** Use the 5W2H format. Be specific: include exact error rates, conditions, and hardware revisions. If you don’t have a real bug, use a known issue like "SPI communication fails after 10 minutes of continuous operation."

2. **Perform a 5-Why analysis on that problem.** Write down each "why" until you reach a system or process flaw. Verify that your final "why" is not a technical detail but a process gap (e.g., "no test coverage for long-duration runs" rather than "the SPI clock polarity was wrong").

3. **Draft a D3 containment plan for the same problem.** What is the fastest, safest way to protect the customer? It doesn’t have to be elegant—it just has to work. Document the performance impact and the plan to remove it after the permanent fix.

## Next Up

Tomorrow we tackle **D1-D2: Forming a Team & Defining the Problem Precisely**. We’ll cover how to select the right cross-functional members, write a problem statement that passes the "stranger test," and avoid the most common D2 traps that waste weeks of engineering time.
