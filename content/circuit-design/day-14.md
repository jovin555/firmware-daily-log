---
title: "Day 14: Clock Distribution & Crystal Oscillator Circuit Design"
date: 2026-07-23
tags: ["til", "circuit-design", "crystal", "oscillator"]
---

## What I Explored Today

Today I dove into the often-overlooked art of clock distribution and crystal oscillator circuit design. While it's tempting to slap a 25 MHz crystal on a microcontroller and call it done, real-world designs demand attention to signal integrity, load capacitance matching, and jitter management. I spent the morning simulating a Pierce oscillator with an AT-cut crystal, then moved to clock fan-out buffers for distributing a clean 100 MHz reference across a mixed-signal PCB. The difference between a system that works and one that passes EMC testing often comes down to a few picofarads and a well-placed series termination resistor.

## The Core Concept

A crystal oscillator is not a digital component—it is an analog feedback system operating at resonance. The crystal itself is a piezoelectric resonator modeled by the Butterworth-Van Dyke equivalent circuit: a series RLC branch (motional arm) in parallel with a static capacitance (C0). For oscillation to occur, the active circuit (typically an inverting amplifier inside the MCU) must provide 180° phase shift, and the crystal plus external load capacitors must provide the other 180° at the desired frequency.

The key design parameter is the **load capacitance (CL)**. Every crystal datasheet specifies a CL value (e.g., 18 pF, 12 pF, or 8 pF). The external capacitors C1 and C2 are chosen such that:

```
CL = (C1 * C2) / (C1 + C2) + Cstray
```

Where Cstray includes PCB trace capacitance (typically 2–5 pF) and pin capacitance. If CL is mismatched, the oscillator will pull frequency away from the nominal value, potentially causing baud rate errors or RF carrier drift.

For clock distribution, the challenge is maintaining signal integrity across multiple loads. A single-ended clock trace acts as a transmission line. Without proper termination, reflections cause overshoot, undershoot, and increased jitter. The standard approach is series termination at the source: place a resistor (Rs) such that Rs + R_driver_output = Z0 (trace impedance). For a 50 Ω trace and a typical 20 Ω output impedance, Rs = 33 Ω.

## Key Commands / Configuration / Code

### 1. Crystal Load Capacitor Calculation (Python snippet)

```python
# Calculate external capacitors for a Pierce oscillator
C_load = 18e-12  # Crystal load capacitance (18 pF)
C_stray = 4e-12  # Estimated stray capacitance (4 pF)

# For symmetrical capacitors: C1 = C2
C_ext = 2 * (C_load - C_stray)
print(f"External capacitor value: {C_ext*1e12:.1f} pF")
# Output: External capacitor value: 28.0 pF
# Use standard value: 27 pF or 30 pF

# Verify actual CL
C1 = 27e-12
C2 = 27e-12
CL_actual = (C1 * C2) / (C1 + C2) + C_stray
print(f"Actual load capacitance: {CL_actual*1e12:.1f} pF")
# Output: Actual load capacitance: 17.5 pF (close enough)
```

### 2. STM32CubeMX Clock Configuration (HAL example)

```c
/* Enable HSE (High-Speed External) oscillator */
RCC_OscInitTypeDef RCC_OscInitStruct = {0};
RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
RCC_OscInitStruct.HSEState = RCC_HSE_ON;
RCC_OscInitStruct.HSEPredivValue = RCC_HSE_PREDIV_DIV1;  // No prescaler
RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
RCC_OscInitStruct.PLL.PLLM = 8;   // Divide by 8 (8 MHz / 8 = 1 MHz)
RCC_OscInitStruct.PLL.PLLN = 336; // Multiply by 336 (1 MHz * 336 = 336 MHz)
RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2; // Divide by 2 (168 MHz)
RCC_OscInitStruct.PLL.PLLQ = 7;   // For USB: 48 MHz output
if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK) {
    Error_Handler();
}
```

### 3. Clock Fan-Out Buffer Layout (KiCad footprint note)

```
# SI53302-B-GM (1:4 LVCMOS fanout buffer)
# Pin 1: CLKIN (50 Ω trace from oscillator)
# Pin 2: VDD (decouple with 0.1 µF + 10 µF per pin)
# Pins 3-6: CLKOUT0..3 (each with 33 Ω series resistor at source)

# Critical layout rule:
# - Keep CLKIN trace < 10 mm from oscillator output
# - Route each CLKOUT as 50 Ω microstrip over solid ground plane
# - No vias on clock traces if possible
# - Add 0.1 µF cap within 2 mm of each VDD pin
```

### 4. Oscillator Startup Time Measurement (Oscilloscope setup)

```
# Measure startup time on a 25 MHz crystal
# Channel 1: MCU OSC_IN pin (1x probe, 10 MΩ, <10 pF load)
# Trigger: Rising edge at 0.5 V, single-shot mode
# Expected: 1-5 ms startup for typical AT-cut crystal

# Check for "sleepy" oscillation:
# If amplitude < 60% VDD after 10 ms, reduce feedback resistor
# Typical Rf range: 1 MΩ to 10 MΩ (check MCU datasheet)
```

## Common Pitfalls & Gotchas

1. **Parasitic capacitance from scope probes kills oscillation.** A 10x probe adds 10–15 pF of load. When probing the crystal pins, the oscillator may stop or frequency-pull by hundreds of ppm. Always use a low-capacitance active probe (≤1 pF) or measure indirectly via a buffered clock output pin.

2. **Ground loops in clock distribution cause common-mode noise.** If you route a clock trace over a split ground plane, the return current must find a path around the split, creating a large loop antenna. Always route clocks over a continuous ground reference plane. Never change layers without a nearby ground via.

3. **Load capacitor placement matters more than value.** A 27 pF capacitor placed 10 mm away from the crystal pin adds inductance that shifts the effective CL. Place load capacitors within 3 mm of the crystal pins, with the ground return via as close as possible. The loop area from crystal pin → capacitor → ground via must be minimized.

## Try It Yourself

1. **Calculate and validate load capacitors.** Take a 16 MHz crystal with CL = 12 pF. Estimate Cstray = 3 pF. Compute C1 and C2. Then measure the actual oscillation frequency with a frequency counter. Compare to the nominal value—the error should be < 50 ppm.

2. **Probe a crystal oscillator without killing it.** Build a simple Pierce oscillator on a breadboard using a 74HCU04 inverter. Measure the waveform at the output pin (not the crystal pins) using a 10x probe. Then add a 10 pF cap in parallel with one crystal pin and observe the frequency shift.

3. **Design a clock tree for a mixed-signal board.** Sketch a block diagram with a 50 MHz oscillator feeding an FPGA, an ADC, and a DAC. Add a clock fan-out buffer (e.g., NB3N551). Calculate the required series termination resistors for 50 Ω traces. Simulate the eye diagram in LTspice using a 100 MHz square wave with 1 ns rise time.

## Next Up: ESD Protection: TVS Diodes & Layout Considerations

Tomorrow we’ll tackle the silent killer of field returns—electrostatic discharge. You’ll learn how to select TVS diodes by clamping voltage and capacitance, where to place them on I/O lines, and why a 0.5 nH inductance difference can mean the difference between survival and latch-up. Bring your layout ruler.
