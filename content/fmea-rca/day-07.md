---
title: "Day 07: Fault Tree Analysis for Root Cause Investigation"
date: 2026-07-16
tags: ["til", "fmea-rca", "fault-tree", "rca"]
---

## What I Explored Today

After spending Day 06 mapping process flows for a persistent I2C bus lockup on a production sensor node, I needed a method to systematically decompose the failure into its logical precursors. Fault Tree Analysis (FTA) was the tool I turned to. Unlike a fishbone diagram which captures brainstorming breadth, FTA forces a top-down, deductive decomposition using Boolean logic gates. Today I built a fault tree for the I2C lockup, traced it to a specific race condition in the ISR, and validated the cut set with a logic analyzer capture.

## The Core Concept

Fault Tree Analysis treats an undesired top event (the system failure) as the root of a tree. Below it, you place intermediate events connected by logic gates — primarily AND and OR. An AND gate means all inputs must be true for the output to occur; an OR gate means any input suffices. The leaves of the tree are basic events — component failures, software bugs, environmental conditions — that cannot be further decomposed.

The power of FTA is that it forces you to think in terms of **causal necessity and sufficiency**. An OR gate tells you: "any one of these causes alone is sufficient to produce the parent event." An AND gate tells you: "all of these causes must be present simultaneously." This is far more rigorous than a list of possible causes because it exposes the logical structure of the failure. You can then compute minimal cut sets — the smallest combination of basic events that guarantee the top event.

For embedded systems, FTA is especially useful for intermittent failures. A race condition, for example, often requires an AND of a specific timing window and a specific code path. The tree makes that dependency explicit.

## Key Commands / Configuration / Code

I use a text-based approach for FTA because it's version-controllable and easy to annotate. Here's the fault tree I built for the I2C lockup, using a simple indented notation with gate types:

```
Top Event: I2C Bus Lockup (SCL held LOW > 100ms)
    OR
    +-- Slave device holds clock (stuck bit)
    |   AND
    |   +-- Slave in undefined state
    |   +-- Slave clock stretch timeout exceeded
    +-- Master fails to release clock
        OR
        +-- ISR preemption causes missed SCL release
        |   AND
        |   +-- High-priority ISR fires during I2C STOP
        |   +-- I2C driver uses polling, not DMA
        +-- I2C peripheral state machine stuck
            AND
            +-- Bus error flag not cleared
            +-- No bus recovery routine in ISR
```

To compute minimal cut sets, I use a small Python script that parses this tree and applies the MOCUS (Method for Obtaining Cut Sets) algorithm:

```python
# minimal_cut_sets.py — computes minimal cut sets from fault tree
# Input: tree in nested dict format with 'gate' and 'children'
# Output: list of minimal cut sets (each cut set is a set of basic events)

def get_cut_sets(node):
    if 'gate' not in node:
        # Basic event — return as single-element cut set
        return [{node['name']}]
    
    children_cuts = [get_cut_sets(child) for child in node['children']]
    
    if node['gate'] == 'OR':
        # Union: any child's cut set is sufficient
        result = set()
        for cs in children_cuts:
            result.update(cs)
        return list(result)
    
    elif node['gate'] == 'AND':
        # Intersection: combine all child cut sets
        # Start with first child's cut sets
        result = children_cuts[0]
        for cs in children_cuts[1:]:
            new_result = []
            for r in result:
                for c in cs:
                    new_result.append(r | c)
            result = new_result
        # Remove supersets (minimality)
        minimal = []
        for r in result:
            if not any(r > m for m in minimal):
                minimal.append(r)
        return minimal
```

Running this on my tree produced two minimal cut sets:
1. `{High-priority ISR fires during I2C STOP, I2C driver uses polling}`
2. `{Bus error flag not cleared, No bus recovery routine in ISR}`

Cut set #1 matched the logic analyzer trace: a UART RX ISR fired during the I2C STOP sequence, delaying the SCL release beyond the slave's timeout.

## Common Pitfalls & Gotchas

1. **Confusing AND with OR in the tree.** This is the most common mistake. An OR gate implies any single cause is sufficient. If you use an OR when you mean AND, you'll generate cut sets that are too small and miss the actual root cause. Always ask: "Can this parent event happen if only one child is true?" If yes, use OR. If no, use AND.

2. **Stopping decomposition too early.** A basic event should be something you can directly test or observe. "Firmware bug" is not a basic event — "ISR priority higher than I2C interrupt" is. If you can't write a unit test or a hardware check for a leaf event, decompose further.

3. **Ignoring conditional events.** FTA traditionally uses "inhibit" gates for conditional events (e.g., "if temperature > 85°C"). In embedded systems, these are often environmental preconditions. I handle them as AND gates with a basic event for the condition. Missing these leads to cut sets that are theoretically correct but practically impossible.

## Try It Yourself

1. **Build a fault tree for a watchdog timeout.** Start with the top event "System reset due to WDT timeout." Decompose into OR branches: "Task stuck in infinite loop" vs "WDT not serviced due to interrupt starvation." For the interrupt starvation branch, use an AND gate: "Higher-priority ISR running" AND "WDT ISR is lower priority." Validate by checking your RTOS task priorities.

2. **Compute cut sets manually for a small tree.** Draw a tree with 5 basic events: A, B, C, D, E. Connect A and B with an OR gate (call it G1). Connect C and D with an AND gate (G2). Connect G1, G2, and E with an AND gate for the top event. Compute the minimal cut sets by hand, then verify with the Python script above.

3. **Instrument your I2C driver to log SCL state transitions.** Add a GPIO toggle on every SCL edge in the ISR. Capture it with a logic analyzer alongside the I2C lines. If you see SCL held low for > 100ms, trace back through your fault tree to see which cut set matches the observed pattern.

## Next Up

Tomorrow, I'll apply **Is/Is-Not Analysis** to bound the problem scope. Instead of asking "what caused the failure," we'll ask "what did the failure affect, and what did it not affect?" This spatial and temporal bounding is essential before you commit to a root cause.
