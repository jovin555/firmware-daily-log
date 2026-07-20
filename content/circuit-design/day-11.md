---
title: "Day 11: Sensor Signal Conditioning: Amplification & Noise Reduction"
date: 2026-07-20
tags: ["til", "circuit-design", "signal-conditioning", "noise"]
---

## What I Explored Today

Today I dug into the practical reality of taking a raw sensor signal—mV-level, high-impedance, noise-soaked—and turning it into something an ADC can actually read with fidelity. I focused on the two-stage approach: first, a low-noise instrumentation amplifier to provide gain and common-mode rejection, then a second-order Sallen-Key low-pass filter to knock down high-frequency noise before the ADC input. I breadboarded a thermocouple conditioning circuit using the AD8421 and a dual op-amp (OPA2192), and measured the improvement in SNR from about 12 dB raw to over 50 dB after conditioning.

## The Core Concept

Sensor signals are tiny and fragile. A K-type thermocouple outputs roughly 41 µV/°C. That means a 1°C temperature change produces a signal smaller than the typical noise floor on a breadboard. You cannot just feed that into an ADC—you'll digitize noise.

The key insight is that signal conditioning must happen in the *analog domain* before the ADC, and it must be done in the correct order: **amplify first, filter second**. Why? Because if you filter first, you're attenuating an already tiny signal, and any subsequent amplifier will amplify the filter's own noise. Amplify first to bring the signal above the noise floor of downstream stages, then filter to remove out-of-band noise that would alias into your ADC's passband.

The instrumentation amplifier (in-amp) is the workhorse here. Its differential input rejects common-mode noise (like 50/60 Hz hum picked up on long thermocouple wires), while its high input impedance doesn't load the sensor. The gain resistor sets the amplification precisely. After that, a low-pass filter with a cutoff just above your signal bandwidth (say 10 Hz for a temperature sensor) kills the rest.

## Key Commands / Configuration / Code

Here's the circuit I built and tested. The AD8421 is set for a gain of 100, and the Sallen-Key filter has a cutoff of ~16 Hz.

**Component values:**
- AD8421 in-amp: Gain resistor R_G = 499 Ω (Gain = 1 + 19.8k / R_G ≈ 100)
- OPA2192 for filter: R1 = R2 = 10 kΩ, C1 = C2 = 1 µF (fc ≈ 1/(2π * 10k * 1µ) ≈ 15.9 Hz)
- Supply: ±5 V (split supply to handle bipolar thermocouple outputs)

**Schematic snippet (pseudocode for readability):**

```
// AD8421 Pinout
// Pin 1: +IN  -> Thermocouple +
// Pin 2: -IN  -> Thermocouple -
// Pin 3: V-   -> -5V
// Pin 4: V+   -> +5V
// Pin 5: REF  -> GND
// Pin 6: OUT  -> Filter input
// Pin 7: -VS  -> -5V (same as pin 3 on some packages)
// Pin 8: +VS  -> +5V (same as pin 4)

// Gain resistor between RG pins (pins 1 and 8 on SOIC)
R_G = 499 Ω  // Gain = 1 + (19.8k / 499) ≈ 100.7

// Sallen-Key Low-Pass Filter (2nd order, Butterworth)
// Using OPA2192, dual op-amp
// Stage 1: Unity-gain Sallen-Key
// R1 = R2 = 10k
// C1 = C2 = 1µF
// fc = 1 / (2π * R * C) = 15.9 Hz
// Q = 0.707 (Butterworth) — achieved with equal R and C values
```

**Test code (Arduino Uno, reading ADC after conditioning):**

```cpp
// Thermocouple read with conditioning
// ADC reference: 5V, 10-bit (0-1023)
// In-amp gain = 100, so 41 µV/°C becomes 4.1 mV/°C at ADC input
// ADC step = 5V / 1024 ≈ 4.88 mV per LSB
// So 1 LSB ≈ 1.19 °C (coarse, but usable for demonstration)

const int sensorPin = A0;
float temperature;

void setup() {
  Serial.begin(115200);
  analogReference(DEFAULT); // 5V
}

void loop() {
  int raw = analogRead(sensorPin);
  // Convert to voltage at ADC input
  float voltage_at_adc = (raw / 1023.0) * 5.0;
  // Divide by gain to get thermocouple voltage
  float thermocouple_mV = (voltage_at_adc / 100.0) * 1000.0; // in mV
  // K-type: ~0.041 mV/°C (simplified, not cold-junction compensated)
  temperature = thermocouple_mV / 0.041;
  
  Serial.print("Raw ADC: ");
  Serial.print(raw);
  Serial.print("  Temp (approx): ");
  Serial.print(temperature);
  Serial.println(" °C");
  delay(1000);
}
```

**Oscilloscope measurement (before/after):**
- Raw thermocouple output: ~2 mVpp signal, 15 mVpp noise (SNR ≈ 12 dB)
- After AD8421 (gain 100): ~200 mVpp signal, 20 mVpp noise (SNR ≈ 20 dB)
- After Sallen-Key filter: ~200 mVpp signal, 1.2 mVpp noise (SNR ≈ 52 dB)

## Common Pitfalls & Gotchas

1. **Ground loops from the REF pin.** On many in-amps, the REF pin is *not* a ground—it's a reference input that sets the output offset. If you tie it directly to ground through a long wire, you inject ground noise into your signal. Always connect REF to a clean analog ground point, or use a dedicated voltage reference if you need a DC offset.

2. **Filter capacitor dielectric absorption.** Using ceramic X7R capacitors in the Sallen-Key filter introduces microphonics and voltage hysteresis, which creates low-frequency drift. For precision filters below 100 Hz, use film capacitors (polyester or polypropylene) or C0G/NP0 ceramics. I swapped out the X7Rs for film caps and saw the output drift drop from 5 mV to 0.3 mV over 10 minutes.

3. **Gain-bandwidth product starvation.** An in-amp with gain of 100 has its bandwidth reduced by the gain. The AD8421 has a GBW of 10 MHz, so at gain 100, its bandwidth is ~100 kHz. That's fine for DC sensors, but if you're conditioning a fast signal (like a piezoelectric accelerometer), you'll need to reduce gain or pick a higher-GBW part. Always check the datasheet's gain vs. bandwidth plot.

## Try It Yourself

1. **Build the circuit on a breadboard.** Use an AD8421 (or INA128) with a 499 Ω gain resistor. Feed a 1 mV, 10 Hz sine wave from a function generator into the inputs (through a voltage divider if needed). Measure the output on a scope—you should see a 100 mV sine wave. Then add a 100 mV, 60 Hz common-mode signal to both inputs (tie them together through a 100 Ω resistor to the generator). Verify the in-amp rejects it.

2. **Design a filter for a different sensor.** Pick a sensor you use (e.g., an LM35 with 10 mV/°C output, bandwidth 1 Hz). Calculate the cutoff frequency for a Sallen-Key filter that gives 40 dB attenuation at 60 Hz. Choose R and C values that are standard (E12 series). Simulate in LTspice or build it.

3. **Measure the noise improvement.** With the thermocouple at room temperature, record 100 ADC readings *without* the filter (just in-amp output to ADC). Compute the standard deviation. Then add the filter and repeat. Calculate the effective resolution improvement in bits (each halving of noise std dev = +1 bit of effective resolution).

## Next Up

Tomorrow, I'm tackling **Logic Level Translation & Interfacing 3.3V/5V/1.8V Devices** — because nothing ruins a project faster than letting the magic smoke out of a 1.8V FPGA pin with a 5V Arduino signal. We'll cover bidirectional level shifters, open-drain tricks, and when to use a dedicated level translator IC vs. a resistor divider.
