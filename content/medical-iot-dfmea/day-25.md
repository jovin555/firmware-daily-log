---
title: "Day 25: Full Review & Project: DFMEA for a BLE Wearable Patient Monitor"
date: 2026-11-04
tags: ["til", "medical-iot-dfmea", "review", "project"]
---

# Day 25: Full Review & Project: DFMEA for a BLE Wearable Patient Monitor

## What I Explored Today

Today I closed the loop on the DFMEA series by running a complete, end-to-end DFMEA on a realistic BLE wearable patient monitor — a chest-worn ECG + SpO₂ + temperature patch that streams to a bedside gateway. Rather than inventing a toy example, I pulled the structure from a design I've worked on: nRF52840 SoC, MAX30101 PPG sensor, AD8232 ECG front end, and a 250 mAh LiPo. The goal was to prove that the templates, severity/occurrence/detection scales, and RPN math from the previous 24 days actually hold together when you apply them to a full system with firmware, hardware, and BLE radio all interacting. I built the worksheet as a structured CSV so it can be version-controlled and diffed, then generated the risk-priority summary with a short Python script.

## The Core Concept

A DFMEA is only as good as its **boundary definition and interface analysis**. On a wearable patient monitor, most high-severity failure modes live at *interfaces*: sensor-to-firmware (I²C bus lockup), firmware-to-radio (BLE disconnect during an alarm), radio-to-gateway (packet loss), and battery-to-system (brownout during a critical SpO₂ reading). If you scope the DFMEA to "the firmware" or "the PCB" in isolation, you miss the cross-domain failure modes that actually harm patients.

The second principle is that **RPN alone is a poor prioritization tool**. Two failure modes can share RPN = 120, but one with Severity 9 / Occurrence 4 / Detection 3 (a missed desaturation alarm) is far more urgent than Severity 4 / Occurrence 6 / Detection 5 (a cosmetic display glitch). ISO 14971 and IEC 62304 both push you toward severity-first triage, and the DFMEA should reflect that. I used an **Action Priority (AP)** table — High/Medium/Low — layered on top of RPN, which is what AIAG-VDA moved to in 2019 for exactly this reason.

## Key Commands / Configuration / Code

I kept the DFMEA as a CSV so it lives in Git alongside the firmware. Here's the schema and a Python snippet that computes RPN, flags severity-critical rows, and assigns Action Priority.

```python
# dfmea_review.py — RPN + Action Priority rollup for a BLE wearable DFMEA
import csv
from collections import Counter

# AIAG-VDA style AP table (simplified): (S, O, D) -> priority
def action_priority(s, o, d):
    rpn = s * o * d
    if s >= 9 and o >= 4:          # high severity + plausible occurrence
        return "HIGH"
    if s >= 9 or rpn >= 200:       # severity-dominant or very high RPN
        return "HIGH"
    if rpn >= 100:
        return "MEDIUM"
    return "LOW"

rows = []
with open("dfmea_ble_monitor.csv") as f:
    for r in csv.DictReader(f):
        s, o, d = int(r["sev"]), int(r["occ"]), int(r["det"])
        r["rpn"] = s * o * d
        r["ap"]  = action_priority(s, o, d)
        rows.append(r)

# Sort severity-first, then RPN — matches ISO 14971 risk-first triage
rows.sort(key=lambda r: (-int(r["sev"]), -r["rpn"]))

for r in rows:
    print(f'{r["id"]:>4}  S{r["sev"]} O{r["occ"]} D{r["det"]}  '
          f'RPN={r["rpn"]:>3}  {r["ap"]:<6}  {r["failure_mode"][:50]}')

print("\nAP distribution:", Counter(r["ap"] for r in rows))
```

A representative slice of the CSV — note the interface-level failure modes:

```csv
id,item,function,failure_mode,effect,sev,occ,det,current_control,recommended_action
F-01,ECG front end,Detect R-wave,Electrode off / high impedance,Missed arrhythmia,9,4,3,Lead-off detect + LED,Add impedance-driven alarm escalation
F-02,BLE radio,Stream vitals to gateway,Disconnect during alarm,Packet loss at bedside,8,5,4,Connection supervision timeout,Add local buzzer fallback + retry backoff
F-03,PPG sensor,Measure SpO2,I2C bus lockup (SDA held low),No SpO2 reading,8,3,5,Watchdog reset,Add I2C bus recovery (9 clock pulses)
F-04,PMIC,Brownout protection,LiPo sag during TX burst,MCU reset mid-measurement,7,4,3,BOR at 2.1V,Add bulk cap + TX current shaping
F-05,Firmware,Timestamp samples,RTC drift over 24h,Skewed trend data,5,5,2,NTP sync at gateway,Add periodic RTC calibration
```

The I²C recovery control is worth calling out — it's a real, correct fix for a stuck bus:

```c
/* I2C bus recovery: clock SCL 9x while SDA floats, then STOP */
static void i2c_bus_recover(void) {
    gpio_set_dir(PIN_SDA, GPIO_IN);      /* release SDA */
    for (int i = 0; i < 9; i++) {
        gpio_put(PIN_SCL, 0); busy_wait_us(5);
        gpio_put(PIN_SCL, 1); busy_wait_us(5);
    }
    /* manual STOP: SDA low->high while SCL high */
    gpio_set_dir(PIN_SDA, GPIO_OUT);
    gpio_put(PIN_SDA, 0); busy_wait_us(5);
    gpio_put(PIN_SCL, 1); busy_wait_us(5);
    gpio_put(PIN_SDA, 1); busy_wait_us(5);
}
```

## Common Pitfalls & Gotchas

1. **Scoping the DFMEA to one discipline.** If hardware and firmware teams each run their own DFMEA, the interface failure modes (bus lockup, brownout during TX, disconnect during alarm) fall through the cracks — and those are exactly the ones with Severity 8–9 on a patient monitor. Run one cross-functional DFMEA with a shared boundary diagram.

2. **Treating Detection as a firmware property only.** Detection credit is often claimed for "watchdog resets the MCU," but a watchdog doesn't detect a *wrong* SpO₂ value — it only catches a hang. Be honest about what each control actually detects; over-crediting detection inflates RPN confidence and hides real risk.

3. **Forgetting the radio as a failure source.** BLE disconnect, packet loss, and connection-supervision timeouts are frequently omitted because "the radio works." On a wearable, the radio is the highest-occurrence failure path to the gateway, and it needs its own line items with local-fallback controls (buzzer, on-device storage).

## Try It Yourself

1. **Build the boundary diagram first.** Sketch the wearable's functional blocks (sensors → MCU → radio → gateway → cloud) and label every interface. Then write one DFMEA row per interface, not per component. Compare the count to a component-scoped list — the interface rows should surface at least two Severity ≥ 8 items you'd otherwise miss.

2. **Run the script against your own CSV.** Adapt `dfmea_review.py` to your worksheet, then sort severity-first and check whether your top-5 by RPN matches your top-5 by severity. If they diverge, you've found rows where detection credit is masking a high-severity risk.

3. **Audit your detection controls.** For each row with Detection ≤ 3, write one sentence describing *exactly* what the control detects and what it does *not*. Any control that only catches a hang (not a wrong value) should have its Detection score raised.

## Next Up

Tomorrow is the **Full Review** — I'll step back from the individual techniques and assess the whole DFMEA workflow: what held up across 25 days, where the AIAG-VDA vs. ISO 14971 tension actually bites, and a checklist you can hand to a design team starting their first medical-device DFMEA.
