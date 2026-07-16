---
title: "Day 07: Battery Charging Circuits: Li-Ion/LiPo Charge Management ICs"
date: 2026-07-16
tags: ["til", "circuit-design", "li-ion", "charging"]
---

## What I Explored Today

Today I dove into the practical design of Li-Ion and LiPo battery charging circuits using dedicated charge management ICs. While it's tempting to throw together a constant-voltage source with a current-limiting resistor, the reality is that lithium-based cells demand precise voltage regulation, current limiting, and temperature monitoring to avoid catastrophic failure. I focused on the MCP73831 and BQ24075 — two workhorses in portable and embedded designs — and worked through the external component selection, PCB layout considerations, and the constant-current/constant-voltage (CC/CV) charging profile that makes these ICs tick.

## The Core Concept

Lithium-ion and lithium-polymer cells are chemically different from lead-acid or NiMH. They have a very flat voltage curve near full charge, and overcharging above ~4.20V (or 4.35V for some newer chemistries) causes lithium plating, internal shorting, and thermal runaway. Undercharging leaves capacity on the table. The charging algorithm must therefore be a two-phase process:

1. **Constant Current (CC) phase**: The charger delivers a fixed current (typically 0.5C to 1C) until the cell voltage reaches the regulation threshold.
2. **Constant Voltage (CV) phase**: The charger holds the cell at the regulation voltage while the current naturally decays. Charging terminates when the current drops below a termination threshold (usually 10% of the CC value).

A charge management IC handles this entire sequence internally, including pre-conditioning for deeply discharged cells (trickle charge below ~2.9V) and temperature monitoring via an external NTC thermistor. The designer's job is to select the correct external resistors, capacitors, and inductor (for switching chargers) to set the charge current, voltage, and loop stability.

## Key Commands / Configuration / Code

### MCP73831 — Linear Charger (Simple, Low-Cost)

The MCP73831 is a single-cell linear charger with only three external components: a PROG resistor, an input capacitor, and an output capacitor. The charge current is set by:

```
I_CHARGE (mA) = 1000 / R_PROG (kΩ)
```

For a 500 mA charge current:
```
R_PROG = 1000 / 500 = 2.0 kΩ
```

Typical schematic snippet:

```
// MCP73831-2 (4.20V regulation variant)
// Pin 1: STAT (open-drain, active low)
// Pin 2: VDD (5V input)
// Pin 3: PROG (to GND via 2.0kΩ)
// Pin 4: GND
// Pin 5: VBAT (to battery +, 10µF ceramic to GND)

// Input: 5V DC from USB
// C_IN: 4.7µF ceramic (X5R, 10V)
// C_OUT: 10µF ceramic (X5R, 6.3V) — critical for stability
// R_PROG: 2.0kΩ ±1% (sets 500mA)
```

**Layout note**: Place C_OUT as close as possible to VBAT and GND pins. The MCP73831 can oscillate if the output cap ESR is too low or trace inductance is high.

### BQ24075 — Switching Charger (Higher Current, Power Path)

The BQ24075 is a 1.5A linear charger with power-path management, meaning the system can run from the input supply even with a dead battery. Key configuration:

```
// ISET1 resistor sets fast-charge current
// I_CHARGE (A) = K_ISET / R_ISET
// K_ISET = 1000 (from datasheet)
// For 1A charge current:
R_ISET = 1000 / 1.0 = 1.0 kΩ

// VREG resistor sets regulation voltage (default 4.20V)
// For 4.20V, leave VREG pin floating
// For 4.35V, connect 10kΩ to VSS

// TS pin: NTC thermistor divider
// Use a 10kΩ NTC (B=3435) with a 10kΩ pullup to VDD
// R_TS = 10kΩ (1%)
```

Power-path configuration example (Arduino-style pseudocode for monitoring):

```c
// Pseudocode for BQ24075 status monitoring
#define STAT1_PIN 3
#define STAT2_PIN 4

void setup() {
  pinMode(STAT1_PIN, INPUT_PULLUP);
  pinMode(STAT2_PIN, INPUT_PULLUP);
  Serial.begin(115200);
}

void loop() {
  bool s1 = digitalRead(STAT1_PIN);
  bool s2 = digitalRead(STAT2_PIN);
  
  if (!s1 && !s2) Serial.println("Charge in progress");
  else if (!s1 && s2) Serial.println("Charge complete");
  else if (s1 && !s2) Serial.println("Temperature fault");
  else Serial.println("No input power / sleep");
  
  delay(1000);
}
```

## Common Pitfalls & Gotchas

1. **Output capacitor ESR mismatch with linear chargers**: The MCP73831 and similar linear chargers require a minimum ESR on the output capacitor to maintain loop stability. Using a low-ESR ceramic (e.g., 10µF X7R) can cause oscillation. The fix: add a 0.5Ω to 1Ω resistor in series with the output cap, or use a tantalum capacitor (higher ESR). Always check the datasheet's "Output Capacitor" section.

2. **Thermal runaway in linear chargers**: A linear charger dissipates `(V_IN - V_BAT) * I_CHARGE` as heat. Charging a 3.0V battery at 1A from 5V input means 2W of heat — enough to melt a small SOT-23 package. Always calculate power dissipation and ensure the IC's thermal pad is properly soldered to a copper pour. If dissipation exceeds 0.8W, use a switching charger or reduce charge current.

3. **Reverse polarity and battery disconnect**: Many cheap charger modules omit reverse polarity protection. If the battery is connected backwards, the IC's internal body diode can conduct, destroying the chip and potentially the cell. Always include a series Schottky diode (e.g., SS34) on the battery input, or use an IC with built-in reverse polarity protection (like the BQ24075's BAT pin protection).

## Try It Yourself

1. **Design a 500mA single-cell Li-Ion charger using the MCP73831**: Select R_PROG, input/output capacitors, and calculate the maximum ambient temperature the IC can handle without thermal shutdown (assume θ_JA = 150°C/W for the SOT-23-5 package). Verify your thermal calculation.

2. **Build a charge current measurement circuit**: Insert a 0.1Ω sense resistor between the charger output and the battery. Use an oscilloscope to capture the CC-to-CV transition. Measure the voltage across the sense resistor during the CV phase and verify it decays to the termination threshold (typically 10% of CC current).

3. **Simulate a BQ24075 power-path design**: Using a 5V/2A input, a 3.7V/2000mAh battery, and a system load of 500mA, calculate the charge current available when the system is on. The BQ24075 prioritizes the system load; the charge current is `I_IN - I_SYS`. If the input is limited to 1.5A, what happens when the system draws 1.2A?

## Next Up

Tomorrow, we move from power to signal conditioning: **Filter Design: RC, RL & Active Filters**. We'll cover cutoff frequency calculations, op-amp based Sallen-Key topologies, and the practical trade-offs between passive and active filters in sensor signal chains.
