---
title: "Day 10: Power Cycling the DUT: Automated Reset & Fault Injection"
date: 2026-06-22
tags: ["til", "hil-testing", "power-cycling", "fault-injection"]
---

## What I Explored Today

Today I integrated a programmable DC power supply into our HIL test bench to automate power cycling of the Device Under Test (DUT). The goal was twofold: first, to validate boot-up sequences and brownout recovery under software control, and second, to inject power faults (glitches, dropouts, overvoltage spikes) that the DUT must survive without corrupting firmware or state. I used a Rigol DP832A controlled over Ethernet via SCPI commands, with a Python test harness that orchestrates power state transitions between test cases.

## The Core Concept

Manual power cycling—plugging and unplugging a barrel jack or flipping a bench supply switch—is the enemy of repeatable HIL testing. It introduces timing jitter, human error, and cannot scale to the thousands of cycles needed for reliability validation. Automated power control turns the DUT's power rail into a first-class test instrument.

The key insight: a power supply with programmable output and readback is not just a voltage source—it's a fault injector. By scripting precise voltage ramps, glitch durations, and sequence timing, you can simulate real-world power quality issues that embedded systems face in the field: cold starts, hot plugs, transient dips from motor inrush, and even intentional brownout attacks to test watchdog behavior.

In CI/CD terms, power cycling becomes a test fixture that resets the DUT to a known state between test suites, eliminating the need for manual button presses or JTAG resets. This is critical for unattended overnight regression runs.

## Key Commands / Configuration / Code

### Hardware Setup
- Power supply: Rigol DP832A (or any SCPI-compatible supply)
- Connection: Ethernet (static IP `192.168.1.100`)
- DUT: STM32H743 board with 3.3V and 5V rails

### Python Control Library (using `pyvisa`)

```python
import pyvisa
import time

class PowerController:
    def __init__(self, ip="192.168.1.100", port=5555):
        rm = pyvisa.ResourceManager()
        # VXI-11 protocol for Rigol DP800 series
        self.psu = rm.open_resource(f"TCPIP0::{ip}::{port}::SOCKET")
        self.psu.write_termination = "\n"
        self.psu.read_termination = "\n"
        self.psu.timeout = 5000  # ms

    def set_channel(self, channel, voltage, current_limit):
        """Configure channel: 1=3.3V, 2=5V, 3=12V"""
        self.psu.write(f":INST CH{channel}")
        self.psu.write(f":VOLT {voltage}")
        self.psu.write(f":CURR {current_limit}")

    def output_on(self, channel):
        self.psu.write(f":OUTP CH{channel},ON")

    def output_off(self, channel):
        self.psu.write(f":OUTP CH{channel},OFF")

    def measure_voltage(self, channel):
        self.psu.write(f":MEAS:VOLT? CH{channel}")
        return float(self.psu.read())

    def power_cycle(self, channel, off_time=2.0):
        """Full power cycle with configurable off duration"""
        self.output_off(channel)
        time.sleep(off_time)
        self.output_on(channel)
        # Wait for DUT boot (adjust based on your system)
        time.sleep(3.0)
```

### Fault Injection: Brownout Glitch

```python
def inject_brownout(psu, channel, nominal_v=3.3, dip_v=2.0, duration=0.05):
    """Drop voltage below operational threshold for <100ms"""
    psu.set_channel(channel, dip_v, 0.5)  # lower voltage, reduce current limit
    time.sleep(duration)
    psu.set_channel(channel, nominal_v, 1.0)  # restore
    # DUT should survive if brownout detector and reset circuit work
```

### Test Sequence Example

```python
def test_boot_sequence():
    psu = PowerController()
    
    # Configure both rails
    psu.set_channel(1, 3.3, 1.0)  # 3.3V rail
    psu.set_channel(2, 5.0, 2.0)  # 5V rail
    
    # Cold start test
    psu.output_off(1)
    psu.output_off(2)
    time.sleep(1)
    psu.output_on(1)
    time.sleep(0.1)  # sequence: 3.3V first
    psu.output_on(2)
    
    # Verify boot voltage
    v3 = psu.measure_voltage(1)
    v5 = psu.measure_voltage(2)
    assert abs(v3 - 3.3) < 0.05, f"3.3V rail out of spec: {v3}"
    assert abs(v5 - 5.0) < 0.1, f"5V rail out of spec: {v5}"
    
    # Inject glitch on 3.3V rail
    inject_brownout(psu, 1, dip_v=1.8, duration=0.08)
    
    # DUT should still be alive (check UART heartbeat)
    # ... read UART from DUT ...
```

## Common Pitfalls & Gotchas

1. **Power sequencing dependencies**: Many SoCs require specific rail turn-on order (e.g., core voltage before I/O). If you power-cycle all channels simultaneously, you might latch up the DUT. Always sequence channels according to the datasheet, and add `time.sleep()` between rail enables.

2. **SCPI command buffering**: Cheap programmable supplies sometimes buffer commands and execute them out of order. Always send a `*OPC?` (operation complete) query after critical commands and wait for the response before proceeding. I learned this the hard way when my brownout glitch arrived 200ms late.

3. **Capacitive discharge time**: After turning off a rail, the DUT's bulk capacitors may hold voltage for seconds. If you power back on too quickly, you won't actually reset the DUT. Measure the actual discharge curve with an oscilloscope, then set your `off_time` to at least 2x the RC time constant.

## Try It Yourself

1. **Write a power cycle test for your DUT**: Using any programmable supply (even a $50 Korad KA3005P with USB), script a sequence that powers off the DUT, waits for all LEDs to extinguish, then powers back on and checks that the boot log appears on UART within 5 seconds.

2. **Inject a brownout glitch**: Set your supply to drop the main rail by 40% for 50ms while the DUT is running. Monitor the DUT's voltage supervisor output pin with an oscilloscope. Does the reset signal assert? Does the DUT recover cleanly?

3. **Automate 1000 power cycles**: Write a loop that power-cycles the DUT 1000 times, logging the boot time and any UART errors. Add a check that the DUT's RTC retains time across power loss (if battery-backed). Run this overnight and review the log in the morning.

## Next Up

Tomorrow: **GitHub Actions for Embedded: Self-Hosted Runners** — why cloud runners can't talk to your oscilloscope, and how to set up a ruggedized runner on the HIL bench that survives 24/7 automated testing.
