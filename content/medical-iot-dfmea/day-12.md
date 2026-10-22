---
title: "Day 12: DFMEA: Power & Battery Failure Modes (Li-ion Safety, IEC 62133, Brownout)"
date: 2026-10-22
tags: ["til", "medical-iot-dfmea", "battery", "iec62133"]
---

# Day 12: DFMEA: Power & Battery Failure Modes (Li-ion Safety, IEC 62133, Brownout)

## What I Explored Today

Today I ran the power subsystem through the DFMEA wringer: the Li-ion cell, the protection IC, the charger, and the brownout behavior of the MCU when the rail sags. For a medical wearable, the battery is the single highest-severity item on the BOM — a thermal event isn't a field return, it's a recall and potentially a patient injury. I mapped failure modes against Severity/Occurrence/Detection, cross-referenced the protection chain against IEC 62133-2 test clauses, and then went down to the bench to actually characterize brownout behavior on an nRF52840 with a programmable supply. The gap between "the datasheet says BOR at 1.7 V" and "here's what my firmware actually does at 1.7 V" was, as usual, educational.

## The Core Concept

DFMEA for power isn't about predicting that a battery dies — that's a certainty, not a failure mode. It's about enumerating *how* the energy path fails and what the downstream effect is on the patient-facing function. The energy path is a chain: cell → protection IC (overcharge/overdischarge/overcurrent/short) → charger → regulator → MCU. Each link has failure modes with different severities.

The reason IEC 62133-2 matters in the DFMEA is that it's the *detection control* for the worst-case cell failures. If your design relies on a single protection IC and that IC's FET fails shorted, you have no independent barrier against overcharge. IEC 62133-2 clause 7.3.8 (overcharge) and 7.3.9 (forced discharge) are the tests that prove your protection chain actually works — and DFMEA should cite them as verification evidence, not just "we used a protected cell."

Brownout is the subtler one. A Li-ion at 3.0 V under a 200 mA BLE TX burst can sag below the MCU's BOR threshold for microseconds. If your firmware doesn't handle that gracefully, you get a reset loop, corrupted flash writes, or — worst case — a partially written calibration record that makes the device report wrong values. The DFMEA failure mode is "loss of supply during non-volatile write → corrupted calibration → incorrect measurement." Severity: high. Detection: depends entirely on whether you have a brownout detector with a threshold *above* the flash write minimum, plus a write-completion flag.

## Key Commands / Configuration / Code

**1. Characterize brownout with a programmable supply (bench):**

```bash
# Using a Rigol DP832 via pyvisa to sweep the rail down slowly
# and log when the nRF52840 resets (detected via UART boot banner)
python3 - <<'EOF'
import pyvisa, time, serial
rm = pyvisa.ResourceManager()
psu = rm.open_resource("USB0::0x1AB1::0x0E11::DP8B::INSTR")
ser = serial.Serial("/dev/ttyACM0", 115200, timeout=0.5)

psu.write(":OUTP CH1,ON")
psu.write(":VOLT 3.3")
time.sleep(1)
for mv in range(3300, 1600, -10):          # 10 mV steps down to 1.6 V
    psu.write(f":VOLT {mv/1000:.3f}")
    time.sleep(0.05)
    ser.reset_input_buffer()
    time.sleep(0.2)
    line = ser.readline().decode(errors="ignore")
    if "BOOT" in line:                      # firmware prints BOOT on reset
        print(f"RESET at {mv} mV")
        break
EOF
```

**2. Configure the nRF52840 brownout detector above flash-write minimum:**

```c
// nrf52840: POWER->POFCON sets the power-fail comparator.
// Flash write requires VDD >= 1.7 V (datasheet); set POFCON to 2.1 V
// so we get an interrupt with margin before the rail collapses.
#include "nrf.h"

void brownout_init(void) {
    // POFCON: POF=1 enable, THRESHOLD=4 -> 2.1 V (see nRF52840 PS, Table 24)
    NRF_POWER->POFCON = (POWER_POFCON_POF_Enabled << POWER_POFCON_POF_Pos)
                      | (POWER_POFCON_THRESHOLD_V21 << POWER_POFCON_THRESHOLD_Pos);
    NRF_POWER->INTENSET = POWER_INTENSET_POF_Msk;
    NVIC_EnableIRQ(POWER_CLOCK_IRQn);
}

void POWER_CLOCK_IRQHandler(void) {
    if (NRF_POWER->EVENTS_POF) {
        NRF_POWER->EVENTS_POF = 0;
        // Abort any in-flight flash write, set a "dirty" flag in RAM,
        // and let the supervisor decide: finish write or roll back.
        flash_abort_and_flag();
    }
}
```

**3. DFMEA worksheet row (the actual artifact):**

```csv
Item,Failure Mode,Effect,Sev,Cause,Occ,Current Control,Det,AP
Li-ion cell,Thermal runaway,Patient burn / fire,10,Internal short / overcharge,2,IEC 62133-2 7.3.8 overcharge test; 2nd protection IC,3,Medium
Protection IC,FET fails shorted,No overcurrent barrier,9,Single-point failure,3,Redundant PTC + charger timeout,4,Medium
MCU supply,Brownout during flash write,Corrupted calibration -> wrong dose,8,Rail sag on BLE TX,4,POFCON @2.1V + write-completion flag,3,Low
Charger,Overcharge to 4.35V,Cell degradation / venting,9,Charger IC failure,2,IEC 62133-2 7.3.8 + cell-level OVP,2,Low
```

## Common Pitfalls & Gotchas

**1. Setting the brownout threshold below the flash-write minimum.** The nRF52840 flash needs VDD ≥ 1.7 V to write reliably, but the default BOR is often left at a lower value or disabled entirely in the softdevice config. If POFCON fires at 1.7 V, you have zero margin — the rail is already collapsing. Set it at least 300–400 mV above the write minimum and verify with the sweep above.

**2. Treating "protected cell" as a complete mitigation.** A protected 18650 has one protection IC. IEC 62133-2 assumes the *cell* is tested, but your *pack* needs its own independent barrier if the DFMEA severity is 9+. Cite the test clause as detection evidence, but don't let it close the failure mode — the protection IC itself is a single point of failure.

**3. Forgetting the write-completion flag.** Brownout detection is useless if firmware can't tell whether the last flash write finished. Without an atomic "write in progress" flag in a separate flash page (or a CRC over the record), a reset mid-write leaves you with a record that passes a length check but fails a CRC — and if you don't check the CRC on boot, you ship corrupted calibration.

## Try It Yourself

1. **Run the sweep.** Take any Cortex-M board with a Li-ion rail and a programmable supply. Sweep VDD down in 10 mV steps and log the reset voltage. Compare it to your BOR/POFCON setting. If the gap is under 200 mV, you have a DFMEA action item.

2. **Write the DFMEA row.** For your own power path, fill in the CSV above with your actual components. Force yourself to assign a Severity of 9 or 10 to at least one row — if you can't, you haven't found the real failure mode yet.

3. **Add a write-completion flag.** Implement a two-page flash scheme: page A holds the record + CRC, page B holds a single "commit" byte written *after* the CRC passes. On boot, only accept a record whose commit byte is set. Test it by pulling power mid-write with a MOSFET on the rail.

## Next Up

Tomorrow: **DFMEA: Wireless Link Failure Modes (BLE Dropouts, Data Loss, Latency)** — connection interval vs. supervision timeout, the difference between a dropped packet and a dropped connection, and how to characterize BLE latency on the bench without a $20k protocol analyzer.
