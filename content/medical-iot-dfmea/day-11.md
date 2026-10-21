---
title: "Day 11: DFMEA: Sensor & Analog Front-End Failure Modes (ECG, SpO2, Temperature)"
date: 2026-10-21
tags: ["til", "medical-iot-dfmea", "sensors", "afe"]
---

## What I Explored Today

Today I moved the DFMEA from the digital core (MCU, memory, comms) into the analog domain — the place where medical devices actually earn their regulatory keep. I worked through the failure modes of the ECG front-end (electrodes, instrumentation amp, driven right leg), the SpO2 path (LED drive, photodiode TIA, ambient light rejection), and the temperature channel (NTC/thermistor divider or digital sensor). The goal was to build a structured worksheet that captures failure mode → effect → severity/occurrence/detection → RPN, and then map each high-RPN line to a concrete mitigation I can actually implement in firmware or schematic. The analog front-end (AFE) is where "silent" failures live: a saturated TIA or a dried-out electrode doesn't throw an error code, it just produces plausible-looking garbage that a clinician might trust.

## The Core Concept

DFMEA on a digital bus is forgiving — a dropped I²C transaction is detectable. The AFE is different for three reasons:

1. **Failure modes are continuous, not binary.** An ECG electrode doesn't "fail"; its half-cell offset drifts, its contact impedance rises, and the differential signal slowly disappears under a DC baseline. Your severity rating must reflect *misdiagnosis risk*, not just "no reading."
2. **Detection is the hard part.** For each failure mode you must ask: *what observable in firmware or hardware proves this happened?* If the answer is "nothing," your detection rank is 10 and the RPN explodes. The engineering response is to design the detection in — lead-off current injection, LED current monitoring, open-thermistor detection.
3. **Severity is anchored to harm, not function.** Per ISO 14971, an SpO2 sensor reading 100% when the true value is 85% is a *hazardous* failure (occult hypoxemia), severity 9–10. A temperature channel reading 0.5 °C high is severity 3. Same "sensor failed" category, wildly different RPN.

The practical takeaway: for every AFE line item, write the detection method as a *testable firmware assertion or hardware monitor*, not a vague "self-test."

## Key Commands / Configuration / Code

A representative DFMEA row plus the firmware that implements its detection. This is the pattern I use: each high-RPN failure mode gets a monitor function with a defined threshold and a fault code.

```c
/* ECG lead-off detection via AC lead-off current injection.
 * Inject a small ~30 kHz square wave through the lead-off resistors;
 * a connected electrode loads the node, an open lead does not.
 * Measure the resulting amplitude at the AFE output. */

#define LEADOFF_FREQ_HZ      30000u
#define LEADOFF_AMP_THRESH   0.15f   /* normalized; open lead >> this */

typedef enum {
    ECG_LEAD_RA = 0,
    ECG_LEAD_LA,
    ECG_LEAD_LL,
    ECG_LEAD_COUNT
} ecg_lead_t;

/* Returns true if lead is OFF (open). Called at 1 Hz from the
 * main supervisory task, NOT from the sampling ISR. */
bool ecg_leadoff_check(ecg_lead_t lead)
{
    afe_inject_leadoff(lead, LEADOFF_FREQ_HZ);
    float amp = afe_measure_band_amplitude(LEADOFF_FREQ_HZ);
    afe_disable_leadoff(lead);

    /* DFMEA detection: open lead -> high injected amplitude.
     * Log fault with timestamp for the audit trail. */
    if (amp > LEADOFF_AMP_THRESH) {
        fault_log(Fault_ECG_LeadOff, lead, amp);
        return true;
    }
    return false;
}
```

```c
/* SpO2 LED drive monitor: a failed (open) LED or dead driver
 * produces zero photodiode response. Compare the AC/DC ratio
 * of the red and IR channels; a ratio outside the physiological
 * window (or a flat DC with no pulsatile component) is a fault. */

#define SPO2_DC_MIN_COUNTS   2000u   /* ADC counts; below = no light */
#define SPO2_PI_MIN          0.001f  /* perfusion index floor */

typedef struct {
    uint32_t dc_red, dc_ir;
    float    pi_red, pi_ir;   /* perfusion index = AC/DC */
} spo2_sample_t;

bool spo2_channel_valid(const spo2_sample_t *s)
{
    if (s->dc_red < SPO2_DC_MIN_COUNTS || s->dc_ir < SPO2_DC_MIN_COUNTS)
        return false;                 /* LED open / driver dead / no finger */
    if (s->pi_red < SPO2_PI_MIN || s->pi_ir < SPO2_PI_MIN)
        return false;                 /* no pulsatile signal -> unreliable SpO2 */
    return true;
}
```

```c
/* Temperature: NTC in a divider. Open thermistor -> ADC rails high;
 * short -> rails low. Detect both, plus a plausibility window. */

#define NTC_ADC_OPEN_MAX   4090u   /* 12-bit ADC, near full scale */
#define NTC_ADC_SHORT_MIN  5u
#define TEMP_MIN_C        -10.0f
#define TEMP_MAX_C         50.0f

bool ntc_read_checked(float *temp_c)
{
    uint16_t raw = adc_read_channel(ADC_CH_NTC);
    if (raw >= NTC_ADC_OPEN_MAX || raw <= NTC_ADC_SHORT_MIN) {
        fault_log(Fault_NTC_OpenShort, raw, 0);
        return false;
    }
    *temp_c = ntc_raw_to_celsius(raw);
    if (*temp_c < TEMP_MIN_C || *temp_c > TEMP_MAX_C) {
        fault_log(Fault_NTC_Implausible, raw, *temp_c);
        return false;
    }
    return true;
}
```

## Common Pitfalls & Gotchas

- **Rating detection as "firmware self-test" without specifying the test.** "Self-test" is not a detection control. If you can't name the injected signal, the measured threshold, and the fault code, the detection rank is a guess. Reviewers (and auditors) will catch this.
- **Forgetting the DC baseline drift failure mode on ECG.** Electrode polarization causes a slowly rising DC offset that saturates the instrumentation amp *before* the signal disappears. Your DFMEA needs a line for "baseline drift → amp saturation," with a high-pass filter cutoff and a saturation flag as the detection control.
- **Treating SpO2 ambient light as a nuisance instead of a failure mode.** Strong ambient (surgical lamp, sunlight) can drive the TIA into saturation and produce a falsely low or high reading. Add "ambient light saturation" as a failure mode with a DC-level monitor and an LED-off dark measurement as detection.

## Try It Yourself

1. **Build the worksheet.** Create a DFMEA table with columns: Item, Failure Mode, Effect, S (1–10), O (1–10), D (1–10), RPN, Detection Control, Mitigation. Fill in at least 6 rows across ECG, SpO2, and temperature. Flag every row where D ≥ 7 and rewrite the detection control until D drops.
2. **Implement one monitor.** Take the `ntc_read_checked()` pattern and port it to your actual ADC HAL. Verify the open/short thresholds by physically disconnecting the thermistor and logging the raw ADC value — confirm your constants bracket reality.
3. **Run a fault-injection test.** Short the SpO2 photodiode input to ground (simulating a dead TIA) and confirm `spo2_channel_valid()` returns false and a fault is logged with a timestamp. Document the result as evidence for your DFMEA detection rating.

## Next Up

Tomorrow: **DFMEA: Power & Battery Failure Modes (Li-ion Safety, IEC 62133, Brownout)** — thermal runaway severity ratings, the difference between a protection-circuit failure and a cell failure, and how to design brownout detection that doesn't corrupt your fault log.
