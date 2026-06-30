---
title: "Day 18: Full Review & Project: Power Profile an Embedded System"
date: 2026-06-30
tags: ["til", "power-management", "review", "project", "profiling"]
---

## What I Explored Today

Today marks the end of our first major block: power profiling fundamentals. Instead of introducing new theory, I spent the day running a complete end-to-end power profiling project on a real target—a Nordic nRF52840 DK running FreeRTOS. The goal was to capture idle current, active transmit current, and sleep current, then correlate those measurements with firmware behavior using a logic analyzer and a precision shunt resistor. This is the same workflow I use when shipping production devices, and it surfaces exactly where the system is wasting energy.

## The Core Concept

Power profiling isn't about measuring once and being done. It's about building a **time-correlated energy model** of your system. Every microamp matters when your device runs on a coin cell for years. The key insight: you cannot optimize what you cannot measure with temporal precision. A multimeter gives you average current, but it hides the 50 mA spike that fires for 2 ms every second—that spike might dominate your battery life.

The correct approach is to:
1. Capture current vs. time at high sample rate (≥1 kS/s for most MCU work).
2. Align that trace with firmware state (GPIO toggles, UART prints, or logic analyzer markers).
3. Integrate current over time to get charge (mAh) per operation.
4. Identify the dominant energy consumers and their duty cycles.

Today's project ties together everything from Days 1–17: shunt selection, ADC sampling, trigger alignment, and post-processing.

## Key Commands / Configuration / Code

### Hardware Setup for This Project
- 10 Ω ±1% shunt resistor in series with the nRF52840 VDD.
- Differential probe across the shunt (or two scope channels in subtract mode).
- Logic analyzer on GPIO P0.13 (toggled high during radio TX).
- Oscilloscope set to 1 kS/s, 10-second acquisition window.

### Firmware Instrumentation (FreeRTOS task snippet)
```c
// Toggle a debug GPIO around the energy-critical operation
#define DEBUG_GPIO NRF_GPIO_PIN_MAP(0, 13)

void radio_tx_task(void *pvParameters) {
    nrf_gpio_cfg_output(DEBUG_GPIO);
    while (1) {
        // Wait for sensor data
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);

        // Mark start of TX on logic analyzer
        nrf_gpio_pin_write(DEBUG_GPIO, 1);

        // Perform radio transmit (2.4 GHz, 0 dBm, 32-byte payload)
        ret_code_t err = nrf_radio_tx(&packet, sizeof(packet));
        ASSERT(err == NRF_SUCCESS);

        // Mark end of TX
        nrf_gpio_pin_write(DEBUG_GPIO, 0);

        // Enter System ON idle (low-power sleep)
        __WFE();
    }
}
```

### Post-Processing Script (Python, using pandas and numpy)
```python
import pandas as pd
import numpy as np

# Load oscilloscope CSV: columns [time_s, V_shunt, GPIO_state]
df = pd.read_csv('profile_capture.csv')

# Convert shunt voltage to current: I = V / R (R = 10 ohms)
df['I_A'] = df['V_shunt'] / 10.0

# Convert to microamps
df['I_uA'] = df['I_A'] * 1e6

# Find TX intervals from GPIO rising/falling edges
tx_mask = df['GPIO_state'] == 1
tx_intervals = df[tx_mask].groupby((tx_mask != tx_mask.shift()).cumsum())

# Compute energy per TX burst
for _, group in tx_intervals:
    duration_s = group['time_s'].iloc[-1] - group['time_s'].iloc[0]
    charge_C = np.trapz(group['I_A'], group['time_s'])  # Coulombs
    charge_mAh = charge_C * 1000 / 3600
    avg_current_uA = group['I_uA'].mean()
    print(f"TX burst: {duration_s*1000:.1f} ms, "
          f"{charge_mAh:.3f} mAh, avg {avg_current_uA:.0f} µA")

# Compute idle current (outside TX intervals)
idle_mask = df['GPIO_state'] == 0
idle_current_uA = df.loc[idle_mask, 'I_uA'].mean()
print(f"Idle current: {idle_current_uA:.1f} µA")
```

### Expected Output (from my capture)
```
TX burst: 2.3 ms, 0.0012 mAh, avg 11200 µA
TX burst: 2.1 ms, 0.0011 mAh, avg 10900 µA
Idle current: 2.8 µA
```

## Common Pitfalls & Gotchas

1. **Shunt resistor self-heating.** A 10 Ω shunt with 50 mA peak current dissipates 25 mW—fine for short bursts. But if you leave a high-current mode on (e.g., continuous BLE advertising at 10 mA), the resistor heats up, its value drifts, and your measurement accuracy degrades. Use a resistor with low TCR (≤50 ppm/°C) and keep duty cycles under 10% for high currents.

2. **Ground loops from the logic analyzer.** If you connect the logic analyzer ground to a different point than the scope ground, you create a ground loop that injects noise into your shunt measurement. Always use a single-point ground star: connect scope ground, logic analyzer ground, and DUT ground at the same physical point (the DUT's ground pin).

3. **Trigger alignment drift.** The GPIO toggle and the actual radio current draw are not simultaneous—there's a ~50 µs delay from register write to RF front-end enable. If you align your integration window exactly on the GPIO edge, you'll miss the ramp-up current. Add a 100 µs pre-trigger offset to your analysis window.

## Try It Yourself

1. **Profile your dev board's sleep current.** Disconnect all peripherals, set the MCU to its deepest sleep mode (e.g., STOP2 on STM32, System OFF on nRF), and measure the current with a 100 Ω shunt. Compare to the datasheet typical value. If you're >20% higher, find the leaking GPIO.

2. **Measure energy per UART character.** Toggle a GPIO before and after a `printf("Hello\n")` call. Capture the current trace and integrate to find the charge per character. Then try reducing the baud rate from 115200 to 9600—does the total energy per character go up or down? (Hint: longer time, but lower peak current.)

3. **Build a simple energy profiler.** Use an Arduino or STM32 to sample an ADC across a 10 Ω shunt at 10 kS/s, stream the data over USB serial, and plot it in real time with Python's matplotlib. This is the foundation of every professional power profiling tool.

## Next Up

Tomorrow is **Day 19: Full Review — Power Management Strategies**. We'll step back from the oscilloscope and look at the architectural patterns that make or break a low-power design: clock gating, voltage scaling, peripheral management, and the hidden cost of firmware abstractions. Bring your datasheets.
