---
title: "Day 09: GPIO Control from Host: Controlling DUT via Relay"
date: 2026-06-22
tags: ["til", "hil-testing", "gpio", "relay", "dut"]
---

## What I Explored Today

Today I wired up a relay-controlled power path between the host machine and the Device Under Test (DUT), using a standard GPIO header on a Raspberry Pi as the host controller. The goal was simple: toggle the DUT's power supply on and off programmatically from the CI/CD pipeline. What I learned is that the gap between "GPIO toggles a pin" and "GPIO safely switches a 12V/3A DUT load" is filled with flyback diodes, optocouplers, and careful current calculations. I now have a working relay driver circuit that the host can command via sysfs or libgpiod, and I can confirm the DUT boots and shuts down cleanly under software control.

## The Core Concept

The fundamental problem: your host machine (a Linux SBC like a Raspberry Pi or BeagleBone) runs at 3.3V logic and can source maybe 16mA per GPIO pin. Your DUT might need 12V at 2A. You cannot directly drive that load from a GPIO pin—you'll fry the host's SoC.

The solution is a relay as an isolation switch. A relay's coil is a low-power electromagnet that, when energized, physically closes a high-power contact. The host GPIO drives a transistor (usually an NPN BJT or MOSFET) that switches the relay coil. The relay's contacts then handle the DUT's power rail. Critically, the relay provides galvanic isolation: the host's delicate 3.3V domain never touches the DUT's power domain.

For HIL testing, this means you can:
- Power-cycle the DUT to simulate brownouts or cold starts.
- Inject faults by cutting power mid-operation.
- Sequence power rails (e.g., 3.3V before 5V) using multiple relays.

The key design parameters are:
- **Coil voltage and current**: Match the relay to your host's available supply (e.g., 5V coil from the Pi's 5V rail).
- **Contact rating**: Must exceed DUT's max voltage and current (derate by 50% for inductive loads).
- **Flyback diode**: Absolutely mandatory across the relay coil to absorb the inductive kickback when de-energizing. Without it, the voltage spike can destroy the driving transistor and the GPIO pin.

## Key Commands / Configuration / Code

### Circuit Schematic (simplified)

```
Host GPIO (3.3V) ──┬─ 1kΩ resistor ── Base of 2N2222 (NPN)
                   │
                   └─ 10kΩ pull-down to GND (keeps transistor off during boot)

Collector of 2N2222 ── Relay coil (5V, ~70mA) ── +5V (from host)
Emitter of 2N2222 ── GND

Across relay coil: 1N4007 diode, cathode to +5V, anode to collector.

Relay COM terminal ── DUT power supply positive (e.g., 12V)
Relay NO terminal  ── DUT VIN
Relay NC terminal  ── (unused, or for "always on" fail-safe)
```

### Host GPIO Control via libgpiod (recommended over sysfs)

```bash
# Install libgpiod tools on Raspberry Pi OS
sudo apt install gpiod libgpiod-dev

# List available GPIO chips and lines
gpioinfo

# Example output:
# gpiochip0 - 54 lines:
#     line  0:      unnamed       unused   input  active-high
#     line  1:      unnamed       unused   input  active-high
# ...
#     line 17:      unnamed       unused   output active-high  <-- we'll use this

# Set GPIO17 high (energize relay, power ON DUT)
gpioset gpiochip0 17=1

# Set GPIO17 low (de-energize relay, power OFF DUT)
gpioset gpiochip0 17=0

# Read back the state
gpioget gpiochip0 17
```

### Python Control for CI/CD Integration

```python
#!/usr/bin/env python3
"""hil_relay.py - Control DUT power via GPIO relay"""

import gpiod
import time
import sys

CHIP = "gpiochip0"
LINE = 17          # GPIO17 (physical pin 11 on Pi header)
ACTIVE_HIGH = True # Relay energizes on HIGH

class DUTPowerController:
    def __init__(self):
        self.chip = gpiod.Chip(CHIP)
        self.line = self.chip.get_line(LINE)
        # Request exclusive ownership, set initial state to OFF
        self.line.request(consumer="hil_relay", type=gpiod.LINE_REQ_DIR_OUT, default_val=0)
    
    def on(self):
        """Power ON the DUT"""
        self.line.set_value(1 if ACTIVE_HIGH else 0)
        print("DUT power ON")
    
    def off(self):
        """Power OFF the DUT"""
        self.line.set_value(0 if ACTIVE_HIGH else 0)
        print("DUT power OFF")
    
    def cycle(self, off_time=2.0, on_time=1.0):
        """Power cycle the DUT with configurable delays"""
        self.off()
        time.sleep(off_time)
        self.on()
        time.sleep(on_time)
    
    def cleanup(self):
        self.line.release()

if __name__ == "__main__":
    ctrl = DUTPowerController()
    try:
        if len(sys.argv) > 1:
            cmd = sys.argv[1]
            if cmd == "on":
                ctrl.on()
            elif cmd == "off":
                ctrl.off()
            elif cmd == "cycle":
                ctrl.cycle()
            else:
                print(f"Usage: {sys.argv[0]} [on|off|cycle]")
        else:
            # Default: cycle once
            ctrl.cycle()
    finally:
        ctrl.cleanup()
```

### Verifying DUT Response

```bash
# After power-on, check DUT is reachable (assuming serial or SSH)
# Using a serial console:
screen /dev/ttyUSB0 115200
# Or ping if DUT has network:
ping -c 3 192.168.1.100

# Monitor DUT boot log via serial while cycling power
# In one terminal:
python3 hil_relay.py cycle
# In another:
tail -f /var/log/dut_serial.log
```

## Common Pitfalls & Gotchas

1. **Missing flyback diode = dead GPIO.** I've seen engineers skip the 1N4007 because "it works without it for a few cycles." It doesn't. The inductive kick from the relay coil can exceed 50V on a 3.3V GPIO line. The diode must be placed as close to the coil as possible, cathode to the positive supply rail. Use a fast-recovery diode (e.g., 1N4148) for small relays, or a 1N4007 for larger ones.

2. **GPIO state at boot is undefined.** On most SBCs, GPIO pins float or have internal pull-ups/downs that change during boot. If your relay is active-high, the DUT might power on unexpectedly during host reboot. Fix: add an external 10kΩ pull-down resistor on the transistor base, and ensure your init script sets the GPIO low before the relay driver loads. In systemd, use `ExecStartPre=/usr/bin/gpioset gpiochip0 17=0`.

3. **Contact bounce on mechanical relays.** When the relay closes, the contacts physically bounce for 1-10ms, causing brief power interruptions. For DUTs with sensitive power-on reset circuits, this can cause boot failures. Mitigations: use a solid-state relay (SSR) for silent switching, or add a 100µF electrolytic capacitor across the DUT's power input to ride through the bounce. For most HIL testing, the bounce is harmless—but test your specific DUT.

## Try It Yourself

1. **Build the relay driver circuit** on a breadboard using a 2N2222 transistor, 1kΩ base resistor, 10kΩ pull-down, 1N4007 flyback diode, and a 5V relay (e.g., SRD-05VDC-SL-C). Connect it to a Raspberry Pi GPIO pin and a 12V LED strip as a dummy DUT load. Verify you can toggle the LED on/off from the command line.

2. **Write a Python script** that powers the DUT on, waits for a "login:" prompt on its serial console (use `pexpect` or `pyserial`), then powers it off. Log the boot time. This is the foundation of automated boot testing.

3. **Add a safety check**: Before powering on, read the DUT's current consumption via a current-sense resistor or INA219 sensor. If current exceeds a threshold (e.g., 2.5A for a 2A-rated supply), abort the power-on and log an error. This prevents damage if the DUT has a short circuit.

## Next Up

Tomorrow: **Power Cycling the DUT: Automated Reset & Fault Injection**. We'll move beyond simple on/off to scripted power-loss scenarios—cutting power at specific points during DUT boot, measuring recovery time, and injecting undervoltage faults to test brownout detection. We'll also integrate this into a Jenkins pipeline so every build gets a cold-start test.
