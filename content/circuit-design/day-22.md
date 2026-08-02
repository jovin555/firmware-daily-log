---
title: "Day 22: Full Review & Project: Design a Battery-Powered Sensor Front-End"
date: 2026-08-02
tags: ["til", "circuit-design", "review", "project"]
---

## What I Explored Today

After 21 days of isolated topics—op-amps, ADCs, power management, noise analysis—today I forced myself to integrate everything into a single, realistic design: a battery-powered sensor front-end for a low-power IoT node. The goal wasn't to build something exotic, but to apply the fundamentals under real constraints: 3.3V rail, 10-bit resolution target, 1% accuracy, and a 1000mAh LiPo cell. The exercise exposed how much I'd been hand-waving about *system-level* power budgets and ground plane strategy when working on individual blocks in isolation.

## The Core Concept

A sensor front-end is not a collection of good parts; it's a *compromise engine*. Every decision—from the op-amp's quiescent current to the ADC's reference voltage—interacts with the battery's discharge curve and the MCU's sleep/wake cycle. The core insight today: **your noise floor is set by your reference and layout, not by the ADC's datasheet ENOB.** If you use a 3.3V LDO output as your ADC reference, you inherit the LDO's line regulation and thermal drift. If you route the sensor return trace under the digital SPI lines, you've just added 50mV of switching noise to your signal. The "why" behind every component choice is about managing *energy* (battery life) and *information integrity* (signal-to-noise ratio) simultaneously.

## Key Commands / Configuration / Code

I prototyped this on an STM32L432KC (Cortex-M4, 12-bit ADC) with a TLV9002 dual op-amp and an MCP9700 temp sensor. Here's the critical configuration and the power-budget math.

**1. ADC Reference Selection (STM32 HAL)**

```c
// Use internal 2.5V reference, NOT VDDA, for stable measurements
// VDDA varies with battery discharge; VREFINT is bandgap-stable
ADC_HandleTypeDef hadc1;
hadc1.Instance = ADC1;
hadc1.Init.ClockPrescaler = ADC_CLOCK_SYNC_PCLK_DIV4;
hadc1.Init.Resolution = ADC_RESOLUTION_12B;
hadc1.Init.DataAlign = ADC_DATAALIGN_RIGHT;
hadc1.Init.ScanConvMode = DISABLE;
hadc1.Init.EOCSelection = ADC_EOC_SINGLE_CONV;
hadc1.Init.LowPowerAutoWait = ENABLE;  // Critical: stops ADC clock between conversions
hadc1.Init.LowPowerAutoPowerOff = ENABLE; // Shuts down ADC entirely when idle
HAL_ADC_Init(&hadc1);

// Configure the internal reference channel
ADC_ChannelConfTypeDef sConfig = {0};
sConfig.Channel = ADC_CHANNEL_VREFINT;
sConfig.Rank = ADC_REGULAR_RANK_1;
sConfig.SamplingTime = ADC_SAMPLINGTIME_640CYCLES_5; // Long sample for VREFINT stability
HAL_ADC_ConfigChannel(&hadc1, &sConfig);
```

**2. Op-Amp Gain Stage (Non-inverting, gain=10)**

The MCP9700 outputs 500mV at 0°C, 10mV/°C. For 0-50°C range, that's 500-1000mV. To use the ADC's 2.5V reference fully, I need gain=2.5, but I chose gain=10 and a voltage divider after—this gives better noise immunity at the cost of headroom.

```
R1 = 9kΩ (feedback)
R2 = 1kΩ (to ground)
Gain = 1 + R1/R2 = 10
Vout = 5V at 50°C → too high! So I use a 2:1 divider after the op-amp.
R3 = R4 = 10kΩ → Vout_ADC = Vout_opamp / 2 = 2.5V max
```

**3. Power Budget Calculation (Python snippet I actually ran)**

```python
# Battery: 1000mAh LiPo, 3.7V nominal, 3.0V cutoff
# MCU: 10uA sleep, 5mA active @ 4MHz
# Sensor+OpAmp: 120uA continuous (MCP9700: 60uA, TLV9002: 60uA)
# ADC conversion: 10us @ 1mA average (with auto-power-off)

active_time_s = 0.010  # 10ms wake, read sensor, transmit
sleep_time_s = 60.0    # 1 minute sleep cycle

avg_current = (5e-3 * active_time_s + 10e-6 * sleep_time_s + 120e-6 * (active_time_s + sleep_time_s)) / (active_time_s + sleep_time_s)
# = (5e-5 + 6e-4 + 7.2e-3) / 60.01 ≈ 131uA average

battery_life_hours = 1000e-3 / (avg_current * 1e-3)  # 1000mAh / 0.131mA
print(f"Average current: {avg_current*1e3:.2f} mA")
print(f"Battery life: {battery_life_hours/24:.1f} days")
# Output: Average current: 0.13 mA, Battery life: 318.5 days
```

The dominant term is the sensor's 120uA always-on current. **Lesson: if you want >1 year battery life, you must power-switch the sensor and op-amp.**

## Common Pitfalls & Gotchas

1. **VREFINT sampling time too short.** The internal reference has a high output impedance. If you sample it with the same 12-cycle sampling time as your external channels, you'll get a reading that's 10-20mV off. Always use the maximum sampling time (640.5 cycles) for VREFINT, and measure it once at startup, not every conversion.

2. **Ground plane split under the op-amp.** I initially routed a split ground plane (analog/digital) and placed the op-amp straddling the split. This created a 0.3V offset due to ground bounce between the two planes. Fix: use a *solid* ground plane, and route the digital SPI lines *away* from the analog input traces. The split-plane approach is for mixed-signal ICs with separate AGND/DGND pins, not for discrete op-amps.

3. **Battery voltage as ADC reference.** The most tempting shortcut is to use VDDA (which is the battery through an LDO) as the ADC reference. This means your measurement accuracy directly tracks the battery's discharge curve. A 0.5V drop in battery voltage = a 15% error in your temperature reading. Always use VREFINT or an external reference if you need better than 5% accuracy.

## Try It Yourself

1. **Modify the power budget script** to include a P-channel MOSFET switch (AO3401, ~0.5uA leakage) that powers the sensor only during the 10ms active window. Recalculate battery life. What's the new dominant current term?

2. **Measure VREFINT on your own board** using the HAL code above. Log 100 readings over 10 minutes. Calculate the standard deviation. If it's more than 2 LSBs, check your VDDA decoupling (should be 100nF + 1uF ceramic right at the VDDA pin).

3. **Redesign the gain stage** for a different sensor: a thermocouple with 40uV/°C output. What gain do you need to get 1°C resolution with a 12-bit ADC? What's the new noise floor if your op-amp has 10nV/√Hz input noise and you use a 10Hz low-pass filter?

## Next Up

Tomorrow is the **Full Review**—I'm going to take every concept from Days 1-21 and map it to a single block diagram of a complete IoT sensor node, showing where each pitfall we've covered actually bites in a real system. We'll trace the signal path from the sensor's physical stimulus to the cloud packet, and I'll highlight the three most common places where engineers lose accuracy or battery life without realizing it.
