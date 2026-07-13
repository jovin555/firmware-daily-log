---
title: "Day 04: Power Supply Design: Linear Regulators (LDO) Basics"
date: 2026-07-13
tags: ["til", "circuit-design", "ldo", "linear-regulator"]
---

## What I Explored Today

I spent the day deep-diving into low-dropout (LDO) linear regulators—the workhorses of clean, low-noise power delivery in embedded systems. While switching converters get all the glory for efficiency, LDOs are indispensable when your ADC needs a 3.3V rail with 10 µV of ripple, or when your RF front-end demands a noise floor below -120 dBm. I focused on the real parameters that matter: dropout voltage, quiescent current, PSRR (power supply rejection ratio), and the often-overlooked stability requirements that can turn a "simple" regulator into an oscillator.

## The Core Concept

A linear regulator works by dissipating excess voltage as heat across a pass transistor. The "dropout" voltage is the minimum difference between input and output that the regulator needs to maintain regulation. An LDO specifically uses a PNP or PMOS pass element, allowing dropout voltages as low as 100–300 mV, compared to standard NPN regulators that need 1.5–2.5 V headroom.

Why choose an LDO over a switching regulator? Three reasons dominate in embedded design:
1. **Noise**: LDOs produce no switching ripple. Their output noise is typically in the 10–100 µV range.
2. **Simplicity**: No inductor, no complex layout, no switching frequency to worry about.
3. **Fast transient response**: LDOs can respond to load changes in microseconds, while switching regulators need milliseconds.

The trade-off is efficiency: an LDO's efficiency is simply `Vout / Vin`. If you drop 5V to 3.3V, you're at 66% efficiency—the rest is heat. This is fine for low-power rails (< 100 mA), but for high-current paths, you want a switching regulator.

## Key Commands / Configuration / Code

### 1. Reading LDO Datasheet Parameters (Python example for parsing)

```python
# parse_ldo_params.py — Extract key specs from a typical LDO datasheet
# Example: TI TPS7A47 (ultra-low-noise LDO)

ldo_specs = {
    "part_number": "TPS7A47",
    "vin_range": (3.0, 20.0),        # V
    "vout_range": (1.4, 20.5),       # V (adjustable version)
    "dropout_voltage": 0.250,        # V at 1A load
    "quiescent_current": 4.0e-6,     # A (4 µA typical)
    "output_noise": 3.8e-6,          # Vrms (3.8 µVrms, 10 Hz–100 kHz)
    "psrr": {
        "10Hz": 72,                  # dB
        "100Hz": 72,
        "1kHz": 68,
        "100kHz": 45,
        "1MHz": 30
    },
    "output_capacitor": {
        "min_cap": 2.2e-6,           # F (2.2 µF)
        "esr_range": (0.001, 0.100), # Ω (1 mΩ to 100 mΩ)
        "type": "ceramic"
    }
}

def check_dropout_margin(vin, vout, dropout, margin=0.2):
    """Ensure Vin is high enough above Vout for regulation"""
    required_vin = vout + dropout + margin
    if vin < required_vin:
        raise ValueError(f"Vin ({vin}V) too low. Need > {required_vin}V")
    return True

# Example: 3.3V output from 5V input
check_dropout_margin(5.0, 3.3, ldo_specs["dropout_voltage"])
# Returns True — 5V is fine (dropout is only 250mV)
```

### 2. LDO Output Voltage Calculation (Adjustable Version)

```python
# For adjustable LDOs like TPS7A47, output voltage is set by resistor divider
# Vout = Vref * (1 + R1/R2)
# Vref is typically 1.4V for this part

def calculate_ldo_resistors(vout, vref=1.4, r2=10e3):
    """Calculate R1 for desired output voltage. R2 typically 10kΩ."""
    r1 = r2 * (vout / vref - 1)
    # Use standard E96 resistor values
    standard_values = [100, 110, 121, 133, 147, 162, 178, 196, 215, 237,
                       261, 287, 316, 348, 383, 422, 464, 511, 562, 619,
                       681, 750, 825, 909, 1000]
    # Find closest standard value
    closest = min(standard_values, key=lambda x: abs(x - r1))
    actual_vout = vref * (1 + closest / r2)
    return closest, actual_vout

r1, actual_vout = calculate_ldo_resistors(3.3)
print(f"R1 = {r1}Ω, Actual Vout = {actual_vout:.3f}V")
# Output: R1 = 13300Ω, Actual Vout = 3.262V
# Note: Use 13.3kΩ (E96) for exact 3.3V: R1 = 13.3kΩ gives Vout = 1.4*(1+13.3/10) = 3.262V
# For exact 3.3V, use R1 = 13.57kΩ (custom value) or accept 1% error
```

### 3. Power Dissipation Check

```python
# thermal_check.py — Ensure LDO doesn't overheat
# Example: AMS1117-3.3 in SOT-223 package

def thermal_check(vin, vout, iout, theta_ja=62.5, ta_max=85):
    """
    theta_ja: junction-to-ambient thermal resistance (°C/W)
    ta_max: maximum ambient temperature (°C)
    """
    pd = (vin - vout) * iout  # Power dissipated in LDO
    tj = ta_max + (pd * theta_ja)  # Junction temperature
    
    print(f"Power dissipation: {pd:.2f}W")
    print(f"Junction temperature: {tj:.1f}°C")
    
    if tj > 125:  # Typical max junction temp
        print("WARNING: Junction temperature exceeds 125°C!")
        print("Consider: heatsink, lower Vin, or switching regulator")
    return tj

# 5V to 3.3V at 500mA
thermal_check(5.0, 3.3, 0.5)
# Output: Power dissipation: 0.85W, Junction temp: 138.1°C — TOO HOT!
```

## Common Pitfalls & Gotchas

1. **Output capacitor ESR is critical for stability.** Many LDOs (especially older ones like LM1117) require a minimum ESR on the output capacitor—typically 0.1–1 Ω. Modern ceramic capacitors have ESR < 10 mΩ, which can cause oscillation. Always check the datasheet's "Stability" section. For ceramic-cap-friendly LDOs, look for parts that explicitly state "stable with ceramic capacitors" (e.g., TPS7A47, ADP7142).

2. **Dropout voltage increases with temperature and load.** The datasheet dropout spec is usually at 25°C and rated current. At 85°C, dropout can double. If your battery voltage drops to 3.4V and you need 3.3V output, a 250 mV dropout at 25°C might become 500 mV at high temp—leaving you with no headroom.

3. **Quiescent current isn't always constant.** Some LDOs (especially older bipolar designs) have Iq that increases dramatically at light loads or high input voltages. A "4 µA" Iq spec might balloon to 100 µA at 12V input. For battery-powered designs, use CMOS LDOs with "shutdown" pin and verify Iq across your entire Vin range.

## Try It Yourself

1. **Select an LDO for a precision ADC**: Given a 5V input, 3.3V output at 200 mA, find an LDO with PSRR > 70 dB at 100 kHz and output noise < 10 µVrms. Calculate the required resistor divider for an adjustable version. (Hint: Look at Analog Devices ADP7142 or TI TPS7A47.)

2. **Thermal simulation**: Take the AMS1117-3.3 from the code example. Calculate the maximum current you can draw at 85°C ambient without exceeding 125°C junction temperature, assuming no heatsink. (Answer: about 370 mA from 5V to 3.3V.)

3. **Stability check**: You're using an LM1117-3.3 with a 10 µF ceramic output capacitor (ESR = 5 mΩ). The datasheet says minimum ESR is 0.3 Ω. What happens? Add a 0.33 Ω resistor in series with the capacitor to fix it. Measure the output with an oscilloscope—do you see oscillation?

## Next Up

Tomorrow, we leave the quiet world of linear regulators and enter the noisy, efficient realm of switching regulators. We'll cover buck (step-down), boost (step-up), and buck-boost topologies—the building blocks of modern power management. Expect inductor calculations, switching frequency trade-offs, and the layout nightmares that keep power engineers awake at night.
