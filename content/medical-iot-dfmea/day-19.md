---
title: "Day 19: Risk Control Hierarchy: Inherent Safety, Protective Measures & Information for Safety"
date: 2026-10-29
tags: ["til", "medical-iot-dfmea", "risk-control", "mitigation"]
---

# Day 19: Risk Control Hierarchy: Inherent Safety, Protective Measures & Information for Safety

## What I Explored Today

Today I dug into the risk control hierarchy defined in ISO 14971 and how it maps onto the firmware and hardware of a wearable SpO₂ monitor I'm working on. The hierarchy is deceptively simple on paper — inherent safety first, then protective measures, then information for safety — but applying it forces you to confront uncomfortable questions about your architecture. Every mitigation I wrote into the DFMEA had to be tagged with which level of the hierarchy it belonged to, and I found that half of my "controls" were really just labels and warnings. That's a red flag, because information for safety is the weakest control and regulators know it. The exercise reshaped how I think about where risk control actually lives in a medical IoT device: in the design, not the manual.

## The Core Concept

The hierarchy exists because not all risk controls are equal. ISO 14971:2019 §7.1 requires you to apply controls in a specific order of priority, and you must document why you didn't use a higher-priority control if you drop down a level.

**Inherent safety by design** means the hazard is eliminated or the risk is reduced by the fundamental design of the device — no reliance on the user doing anything correctly. For a pulse oximeter, that means choosing a sensor wavelength pair that doesn't overheat skin, or designing the LED driver so it physically cannot exceed a current that would burn tissue. The hazard is gone, not guarded against.

**Protective measures** are added safeguards that sit between the hazard and the harm. These come in two flavors: guards built into the device (a watchdog timer that resets a hung MCU, a hardware overcurrent cutoff, a plausibility check that rejects a SpO₂ reading of 40% when the perfusion index is 0.1) and guards in the manufacturing or use process. A protective measure doesn't remove the hazard — it reduces the probability of the hazardous situation or the severity of harm.

**Information for safety** is the last resort: labels, alarms, IFUs, training. It only works if a human perceives, understands, and acts correctly under stress. In a hospital at 3 a.m. with an alarm fatigue problem, that's a fragile assumption. It's still legitimate — you can't eliminate every hazard — but it should be the residual, not the primary control.

The reason this matters for DFMEA is that your detection and prevention actions in the FMEA should map cleanly onto these levels. If your only mitigation for "MCU fails to detect sensor disconnect" is a line in the manual saying "verify sensor connection," you have a weak control and your RPN should reflect that. Regulators reviewing your 510(k) or technical file will ask why you didn't design the disconnect detection into firmware.

## Key Commands / Configuration / Code

Here's how I encoded the hierarchy in the DFMEA spreadsheet's risk control column and in firmware. First, a structured tag in the FMEA so the hierarchy level is machine-checkable:

```yaml
# dfmea_risk_controls.yaml — one entry per failure mode
- failure_mode: "LED drive current exceeds safe tissue limit"
  effects: "Thermal burn at sensor site"
  severity: 8
  controls:
    - type: inherent_safety        # priority 1
      description: "Series resistor + LED forward-voltage budget caps current at 18 mA by design"
      verification: "Bench measurement across Vf bin, -20..60C"
    - type: protective_measure     # priority 2
      description: "MCU ADC samples LED current sense every 10 ms; firmware cuts drive on >25 mA"
      verification: "Fault injection: short sense resistor, confirm cutoff <20 ms"
    - type: information_for_safety # priority 3
      description: "IFU warns against third-party sensor cables"
      verification: "Usability review"
```

The firmware side of the protective measure — a plausibility and cutoff check that runs in the main loop:

```c
// led_safety.c — protective measure layer
#define LED_CURRENT_MAX_MA   25.0f   // hard cutoff, above inherent design limit of 18 mA
#define LED_CURRENT_TRIP_MS  20      // must trip within 20 ms per DFMEA

static uint32_t overcurrent_since_ms = 0;

void led_safety_task(uint32_t now_ms) {
    float i_ma = adc_read_led_current_ma();

    if (i_ma > LED_CURRENT_MAX_MA) {
        if (overcurrent_since_ms == 0) {
            overcurrent_since_ms = now_ms;
        } else if ((now_ms - overcurrent_since_ms) >= LED_CURRENT_TRIP_MS) {
            led_driver_disable();          // hardware gate off
            set_fault_flag(FAULT_LED_OVERCURRENT);
            // Do NOT auto-recover — require power cycle (protective measure)
        }
    } else {
        overcurrent_since_ms = 0;
    }
}
```

Note the deliberate choice not to auto-recover: an auto-resetting cutoff is a weaker protective measure because it can mask a persistent fault. Requiring a power cycle forces the hazardous situation to be visible.

## Common Pitfalls & Gotchas

**1. Calling a firmware check "inherent safety."** A watchdog or plausibility check is a protective measure, not inherent safety — the hazard (e.g., a hung MCU) still exists, you're just guarding against it. Mislabeling inflates your apparent design strength and regulators will catch it. Inherent safety means the hazardous situation cannot occur given the design.

**2. Relying on alarms as the primary control.** An alarm is information for safety. If your only mitigation for "SpO₂ reading drifts low" is an alarm, you've built a device that depends on a clinician noticing and acting. Add a protective measure (e.g., signal-quality gating that suppresses readings when perfusion is inadequate) so the alarm is a backstop, not the control.

**3. Forgetting verification traceability.** Each control needs a verification method tied to it. A protective measure with no test — "firmware checks current" — is an assertion, not evidence. In the DFMEA, every control row needs a verification column that a test engineer can execute, and that verification feeds directly into design verification planning (tomorrow's topic).

## Try It Yourself

1. **Audit your last DFMEA.** Open it and tag every risk control as `inherent_safety`, `protective_measure`, or `information_for_safety`. Count how many are information-only. If more than ~20% of your high-severity failure modes rely solely on information for safety, you have redesign work.

2. **Write a fault-injection test.** For one protective measure in your firmware (watchdog, overcurrent cutoff, plausibility check), write a test that forces the hazardous condition and measures the time-to-mitigation. Confirm it meets the response time you claimed in the DFMEA.

3. **Challenge one "inherent" claim.** Pick a control you labeled inherent safety and ask: if the user does everything wrong and a component fails, can the hazard still occur? If yes, it's a protective measure — relabel it and add the missing verification.

## Next up

Tomorrow: **Design Verification Planning Driven by the DFMEA** — how each risk control's verification method becomes a test case, how to build a traceability matrix from failure mode → control → verification → test result, and why your DV plan should be a direct projection of the DFMEA rather than a separate document written by someone else.
