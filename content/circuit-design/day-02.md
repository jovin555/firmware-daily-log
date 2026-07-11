---
title: "Day 02: Op-Amp Circuits: Inverting, Non-Inverting & Buffer Configurations"
date: 2026-07-11
tags: ["til", "circuit-design", "op-amp", "buffer"]
---

## What I Explored Today

Today I dove into the three fundamental operational amplifier configurations that form the backbone of analog signal conditioning: the inverting amplifier, the non-inverting amplifier, and the voltage follower (buffer). While these circuits appear in every textbook, I focused on the practical design decisions—choosing resistor values for noise performance, understanding input impedance trade-offs, and recognizing when a buffer is not just nice but necessary. I breadboarded each configuration with an LM358 and an MCP6001 to compare real-world behavior against ideal predictions.

## The Core Concept

An op-amp is a differential amplifier with extremely high open-loop gain (typically 100,000–1,000,000). We never use that raw gain directly—instead, we apply negative feedback to trade gain for predictability, linearity, and bandwidth. The magic happens because the op-amp will drive its output to make the voltage difference between its inverting (−) and non-inverting (+) inputs essentially zero (the "virtual short" assumption). This holds as long as the output can swing within the supply rails and the input common-mode range is respected.

The three configurations differ in how they apply feedback:

- **Inverting amplifier**: Signal goes to the inverting input through R1; feedback resistor Rf connects output to inverting input. Non-inverting input is grounded. Gain = -Rf/R1. Input impedance = R1 (often a limitation).
- **Non-inverting amplifier**: Signal goes to the non-inverting input. Feedback divider (R1 to ground, Rf from output to inverting input) sets gain = 1 + Rf/R1. Input impedance is extremely high (op-amp's own input impedance, typically MΩ).
- **Buffer (voltage follower)**: Output directly connected to inverting input, signal to non-inverting input. Gain = 1. Input impedance is the op-amp's (very high), output impedance is the op-amp's (very low, <1Ω with feedback). Use it to isolate a high-impedance source from a low-impedance load.

The key insight: the buffer is not "doing nothing." It's a unity-gain amplifier with massive current gain. If your sensor has 100kΩ output impedance and your ADC expects <10kΩ source impedance, a buffer is mandatory.

## Key Commands / Configuration / Code

Below are the resistor calculations and a practical test routine for verifying each configuration on a breadboard. I use an MCP6001 (rail-to-rail, 5V single supply) for these examples.

### Inverting Amplifier (Gain = -5)

```
Component values:
R1 = 2kΩ (1% metal film)
Rf = 10kΩ (1% metal film)
Gain = -Rf/R1 = -10k/2k = -5

Input impedance = R1 = 2kΩ
Output swing: limited by supply rails (0V to 5V for MCP6001)
```

### Non-Inverting Amplifier (Gain = 6)

```
Component values:
R1 = 2kΩ (to ground)
Rf = 10kΩ (feedback)
Gain = 1 + Rf/R1 = 1 + 10k/2k = 6

Input impedance = MCP6001 input impedance (~1e12Ω || 10pF)
Output swing: rail-to-rail (0V to 5V)
```

### Buffer (Voltage Follower)

```
No external resistors needed (direct wire from output to inverting input)
Gain = 1
Input impedance = op-amp input impedance
Output impedance < 1Ω with feedback
```

### Test Procedure (Python script for signal generator + oscilloscope)

```python
# test_opamp_configs.py
# Assumes: Siglent SDG1032X (CH1 output), Rigol DS1054Z (CH1 input, CH2 output)
import pyvisa
import time

rm = pyvisa.ResourceManager()
sig_gen = rm.open_resource('USB0::0xF4EC::0x1430::SDG1XCAQ3R0001::INSTR')
scope = rm.open_resource('USB0::0x1AB1::0x04CE::DS1ZA123456789::INSTR')

# Configure signal generator: 1kHz sine, 500mVpp, 0V offset
sig_gen.write('C1:BSWV WVTP,SINE,FRQ,1000,AMP,0.5,OFST,0')
sig_gen.write('C1:OUTP ON')

# Configure scope
scope.write(':CHAN1:SCAL 0.5')   # 500mV/div for input
scope.write(':CHAN2:SCAL 2.0')   # 2V/div for output (gain=5)
scope.write(':TIM:SCAL 0.0002')  # 200us/div

# Measure and verify gain
scope.write(':MEAS:CHAN2:VPP?')
vout_pp = float(scope.read())
scope.write(':MEAS:CHAN1:VPP?')
vin_pp = float(scope.read())
gain_measured = vout_pp / vin_pp
print(f"Measured gain: {gain_measured:.2f} (expected: -5.00)")

sig_gen.write('C1:OUTP OFF')
sig_gen.close()
scope.close()
```

## Common Pitfalls & Gotchas

1. **Input common-mode voltage range (CMVR)**: With a single 5V supply, many op-amps (like the LM358) cannot handle inputs within 1.5V of the positive rail. If your non-inverting input is at 4V, the op-amp may rail or behave nonlinearly. Always check the datasheet's CMVR spec. Rail-to-rail input op-amps (MCP6001, OPA333) solve this but cost more.

2. **Output swing limitations**: The LM358 can only swing to within ~1.5V of VCC and ~0.1V of GND. If you need a 4V output from a 5V supply, you'll clip. Use a rail-to-rail output op-amp, or increase the supply voltage. For the inverting configuration, the virtual ground at the inverting input means the output must swing symmetrically—this is harder with single supplies.

3. **Resistor tolerance and gain accuracy**: Using 5% resistors means your gain could be off by ±10%. For precision applications (instrumentation, ADC drivers), use 0.1% thin-film resistors or a precision resistor network. Also, resistor thermal drift (tempco) matters—standard thick-film resistors drift ~100-200 ppm/°C; metal film are 25-50 ppm/°C.

## Try It Yourself

1. **Build an inverting amplifier with gain -10** using an MCP6001 on a breadboard. Use R1=1kΩ, Rf=10kΩ. Feed a 200mVpp, 1kHz sine wave from a signal generator. Measure the output on an oscilloscope. Verify the gain and check for any phase shift (should be 180°). Now swap Rf to 100kΩ—does the output clip? Why?

2. **Design a non-inverting amplifier to drive a 10-bit ADC** with a 3.3V reference. Your sensor outputs 0-0.5V. Calculate the gain needed to map 0.5V to 3.3V (gain = 6.6). Choose standard resistor values (E96 series) to get as close as possible. Build and test with a 0.5V DC input—measure the output with a multimeter.

3. **Demonstrate the buffer's necessity**: Connect a 100kΩ potentiometer as a voltage divider (wiper to output). First, connect the wiper directly to a 1kΩ load resistor. Measure the voltage at the wiper as you turn the pot—it will drop significantly. Now insert an MCP6001 buffer between the wiper and the load. Measure again—the wiper voltage should now track the pot position linearly.

## Next Up

Tomorrow we move from linear amplification to nonlinear op-amp applications: comparators with hysteresis (Schmitt triggers), the precision integrator (and its drift problems), and the differentiator (and why it's practically unusable without a series resistor). We'll also cover how to build a window comparator for over/under-voltage detection.
