---
title: "Day 12: Nordic PPK2: Per-Microsecond Current Profiling"
date: 2026-06-24
tags: ["til", "power-management", "ppk2", "nordic", "current"]
---

## What I Explored Today

Today I got hands-on with the Nordic Power Profiler Kit II (PPK2), a dedicated current measurement tool that samples at 100 kS/s — meaning one measurement every 10 microseconds. Unlike a multimeter that gives you a smoothed average, the PPK2 captures the true instantaneous current draw of your embedded system, revealing microsecond-level events like radio bursts, sensor wake-ups, and sleep-to-active transitions that would be invisible otherwise. I connected it to an nRF52840 DK running a BLE peripheral, and within minutes I was staring at the exact current profile of a connection interval.

## The Core Concept

The fundamental problem with power profiling is that embedded systems spend most of their time in low-power sleep states, punctuated by short, high-current bursts. A typical BLE device might draw 2 µA in sleep, then spike to 6 mA for 3 ms during a radio event. A multimeter averaging over 1 second would show something like 20 µA — technically correct, but useless for understanding where the energy actually goes.

The PPK2 solves this by acting as both a programmable power supply and a high-speed ammeter in one unit. It can source up to 1V–5V at 1A while simultaneously measuring current across a 10 mΩ sense resistor. The key specification is the 100 kS/s sample rate with 14-bit resolution, giving you 0.1 µA resolution in the low-current range (200 µA full scale) and 1 µA resolution in the high-current range (1 A full scale).

The device connects via USB to the nRF Connect Power Profiler software, which displays the current waveform in real time. You can set trigger conditions, export raw CSV data, and overlay events from your firmware (e.g., "radio TX start") using GPIO markers. This lets you correlate software behavior directly with power consumption at the microsecond scale.

## Key Commands / Configuration / Code

### Hardware Setup
Connect the PPK2 to your target board using the included Sense and Source cables. For a standalone target (not the nRF DK), use the 4-pin header:
- VOUT (pin 1) → target VDD
- GND (pin 2) → target GND
- SWD (pin 3) → SWDIO (optional for programming)
- SWCLK (pin 4) → SWCLK (optional)

### Software Configuration
1. Open nRF Connect for Desktop → Power Profiler
2. Select PPK2 device from the dropdown
3. Choose mode: **Source Meter** (supplies power and measures) or **Ammeter** (external power, measures only)
4. Set voltage to 3.3V, current limit to 50 mA
5. Click **Start** to begin capture

### Firmware Markers for Correlation
To align firmware events with the current trace, toggle a GPIO and connect it to the PPK2's DIO pin:

```c
// nRF52840 example: toggle GPIO 0.13 for event marking
#define MARKER_PIN   13

void marker_high(void) {
    nrf_gpio_pin_set(MARKER_PIN);
}

void marker_low(void) {
    nrf_gpio_pin_clear(MARKER_PIN);
}

void ble_radio_tx_start(void) {
    marker_high();
    // ... radio TX code ...
    marker_low();
}
```

Connect the marker GPIO to PPK2 DIO (pin 5 on the 10-pin header). In Power Profiler, enable DIO overlay — you'll see the marker as a colored bar on the timeline.

### Exporting Raw Data
For offline analysis, export CSV:
```
File → Export → Export All Samples
```
This gives you a timestamped list of current values. I use Python to compute energy per event:

```python
import pandas as pd
df = pd.read_csv('trace.csv')
# Compute energy in µJ: I (µA) * V (V) * dt (s)
df['energy_uJ'] = df['current_uA'] * 3.3 * 10e-6
event_energy = df[df['marker'] == 1]['energy_uJ'].sum()
print(f"Event energy: {event_energy:.2f} µJ")
```

## Common Pitfalls & Gotchas

1. **Ground loops through USB** — When using Source Meter mode, the PPK2 and target share ground through the USB cable. If your target has its own USB connection (e.g., a dev board with a debugger), you create a ground loop that adds noise and can bypass the sense resistor. Always disconnect the target's USB when profiling, or use Ammeter mode with an external supply.

2. **Sample rate vs. event duration** — 100 kS/s means one sample every 10 µs. If your event is shorter than 10 µs (e.g., a 1 µs SPI transaction), you'll miss the peak entirely. The PPK2's analog bandwidth is about 200 kHz, so it can capture the event, but the sample timing might alias it. Use the "peak hold" feature or trigger on the event's rising edge to capture it.

3. **Voltage drop across the sense resistor** — The 10 mΩ sense resistor drops 10 µV per mA. At 100 mA, that's 1 mV — negligible for most systems. But if your target is sensitive to supply voltage (e.g., a sensor requiring exactly 3.3V ± 0.1V), the drop matters. Compensate by setting the PPK2 output voltage 1–2 mV higher, or use the "compensated" mode in newer firmware.

## Try It Yourself

1. **Profile a BLE connection interval** — Set up an nRF52840 as a BLE peripheral with a 100 ms connection interval. Capture the current trace and identify the radio TX/RX events. Measure the average current over one interval and compute the charge consumed (in µC). Compare to the datasheet's typical values.

2. **Find the sleep current floor** — Put your MCU into System OFF (or deep sleep) and measure the quiescent current. Use the PPK2's low-current range (200 µA full scale). Verify that no peripherals are leaking. If you see periodic spikes, trace them back to an RTC or LFRCO that wasn't disabled.

3. **Correlate a sensor readout** — Connect a GPIO marker to the PPK2 DIO. In firmware, toggle the marker before and after reading an I2C sensor (e.g., BME280). Capture the trace and measure the energy consumed by the sensor transaction alone. Optimize by reducing the I2C clock speed or using a single-shot mode.

## Next Up

Tomorrow, we'll move from hardware profiling to software control: **Zephyr Power Management: pm_state & Device PM**. We'll explore how to configure CPU idle states, device runtime PM, and the `pm_state` API to put the system into the exact low-power mode you measured today.
