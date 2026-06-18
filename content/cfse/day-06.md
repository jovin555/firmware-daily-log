---
title: "Day 06: HAZOP: Hazard & Operability Study for Embedded Systems"
date: 2026-06-18
tags: ["til", "cfse", "hazop", "hazard"]
---

## What I Explored Today

Today I dug into HAZOP (Hazard and Operability Study) as applied to embedded systems. Unlike FMEA which focuses on component failures, HAZOP is a structured, team-based brainstorming technique that examines process deviations—what happens when a signal, variable, or control flow deviates from its intended design intent. Originally developed for chemical process plants, HAZOP adapts surprisingly well to firmware and control logic, especially when you're dealing with safety-critical functions like brake-by-wire, motor torque limits, or battery management thresholds. I spent the morning running a mini-HAZOP on a simplified battery charge controller and found three latent hazards I'd never considered.

## The Core Concept

HAZOP works by applying a set of **guide words** (e.g., NO, MORE, LESS, REVERSE, PART OF, OTHER THAN) to each **process parameter** (e.g., voltage, current, temperature, state, rate) at every **design intent node** (e.g., a function call, a state machine transition, a sensor read). The goal is not to enumerate every possible failure mode, but to systematically identify deviations that could lead to a hazardous event.

Why HAZOP over other methods? Because it catches *operational* hazards—things that aren't component failures. For example, a sensor reading that's momentarily "MORE" than expected due to a transient ground offset isn't a sensor failure, but it can cause a control loop to saturate. FMEA might miss that. HAZOP forces you to ask: "What if the CAN message arrives *REVERSE* order?" or "What if the watchdog timer fires *PART OF* the expected sequence?" It's about the *behavior* of the system, not just the parts.

The output is a table of deviations, causes, consequences, safeguards, and recommended actions. Each deviation gets a risk ranking (severity × likelihood) and a recommendation—typically a safety mechanism or a design change.

## Key Commands / Configuration / Code

Here's a practical HAZOP worksheet template in Markdown (you'll use this in a spreadsheet or tool, but the structure is what matters). I also include a Python snippet to generate a starter HAZOP table for a simple embedded function.

### HAZOP Worksheet Template (Markdown)

```markdown
# HAZOP Worksheet: Battery Charge Controller
## Node: State Machine - "Fast Charge" State
## Design Intent: Apply constant current (10A) until cell voltage reaches 4.2V

| Guide Word | Parameter      | Deviation                          | Cause                                      | Consequence                                  | Safeguards                     | Risk (S/L) | Recommendation                     |
|------------|----------------|------------------------------------|--------------------------------------------|----------------------------------------------|--------------------------------|------------|------------------------------------|
| NO         | Current        | No charging current                | MOSFET gate driver fault                   | Battery never charges; vehicle stranded      | Watchdog timer on charge cycle | 2/2        | Add current sense feedback         |
| MORE       | Current        | Current > 15A                      | PWM duty cycle stuck high                  | Cell overheat, thermal runaway risk          | Hardware current limit         | 4/3        | Implement software current clamp   |
| LESS       | Voltage        | Cell voltage < 3.0V after 1 hour  | Cell internal short or BMS miswire         | Under-voltage damage, fire risk on recharge  | UVP circuit                   | 4/2        | Add pre-charge check logic         |
| REVERSE    | Current flow   | Current flows from cell to charger | Relay welded closed, reverse polarity       | Battery discharges through charger, fire     | Reverse polarity protection    | 5/1        | Add contactor with polarity check  |
| OTHER THAN | State          | State machine enters "Fault" spuriously | EMI on state variable                    | Charge aborts unnecessarily                  | Debounce filter on state bits  | 2/3        | Add hysteresis to state transitions |
```

### Python Script: Generate HAZOP Table from a YAML Config

```python
# haozp_generator.py
import yaml
import pandas as pd

# Example YAML config for a simple embedded function
config = """
node: "CAN Rx Interrupt Handler"
design_intent: "Decode and validate torque request from steering wheel"
parameters:
  - name: torque_request
    unit: Nm
    normal_range: [0, 300]
  - name: message_counter
    unit: count
    normal_range: [0, 255]
guide_words:
  - NO
  - MORE
  - LESS
  - REVERSE
"""

data = yaml.safe_load(config)
rows = []
for param in data['parameters']:
    for gw in data['guide_words']:
        deviation = f"{gw} {param['name']}"
        # Placeholder causes — you'd fill these in during the study
        cause = f"Unknown cause for {deviation}"
        rows.append({
            "Guide Word": gw,
            "Parameter": param['name'],
            "Deviation": deviation,
            "Cause": cause,
            "Consequence": "TBD",
            "Safeguards": "TBD",
            "Risk": "TBD"
        })

df = pd.DataFrame(rows)
print(df.to_markdown(index=False))
# Outputs a markdown table you can paste into your HAZOP worksheet
```

Run it: `python haozp_generator.py` — then manually fill in causes, consequences, and safeguards during the team session.

## Common Pitfalls & Gotchas

1. **Over-specifying guide words.** Don't apply every guide word to every parameter. "REVERSE" makes no sense for a temperature reading. "PART OF" is meaningless for a boolean flag. You'll waste hours. Instead, pre-filter: for each parameter, list only the guide words that produce a physically plausible deviation.

2. **Confusing HAZOP with FMEA.** HAZOP is about *deviations from design intent*, not component failures. If you find yourself saying "the resistor fails open," you're doing FMEA. HAZOP asks "what if the voltage is MORE than intended?" — the cause might be a resistor failure, but the deviation is the focus. Keep the lens on the process parameter.

3. **Skipping the "design intent" definition.** Without a clear, written design intent for each node, the team will argue about what "normal" means. Before the session, write a one-sentence intent for every function or state. Example: "The brake pedal position sensor shall output a voltage linearly proportional to pedal travel from 0.5V (released) to 4.5V (fully depressed)." Now "MORE" means >4.5V, not "maybe 5V is okay."

## Try It Yourself

1. **Run a mini-HAZOP on a watchdog timer.** Pick a guide word (NO, MORE, LESS, REVERSE) and apply it to the watchdog's timeout period. What happens if the timeout is LESS than expected? What safeguard exists? Write a 3-row HAZOP table.

2. **Generate a starter table for a PWM fan controller.** Use the Python script above, but replace the YAML config with: node = "PWM Fan Speed Control", parameters = ["duty_cycle", "tachometer_frequency"], guide_words = ["NO", "MORE", "LESS"]. Fill in two rows manually with realistic causes (e.g., "MORE duty_cycle" → MOSFET gate stuck on).

3. **Review an existing FMEA and identify one hazard it missed.** Look at a FMEA for a simple system (e.g., a door lock controller). Find a deviation that isn't a component failure—like "the lock command arrives REVERSE order" (unlock before lock). Add that as a HAZOP row. Did your FMEA catch it?

## Next Up

Tomorrow: **ISO 26262: Automotive Functional Safety & ASIL Levels** — we'll break down the ASIL (Automotive Safety Integrity Level) determination process, from hazard classification to risk reduction targets. You'll learn how to map a HAZOP deviation to an ASIL rating and what that means for your software architecture.
