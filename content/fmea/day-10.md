---
title: "Day 10: DFMEA Deep Dive: Design Interfaces & Boundary Diagrams"
date: 2026-07-19
tags: ["til", "fmea", "dfmea", "boundary-diagram"]
---

## What I Explored Today

Today I went deep on one of the most underutilized tools in DFMEA: the **boundary diagram**. Most teams jump straight to filling out the DFMEA worksheet without first mapping the physical and functional interfaces between components. That’s a mistake. I spent the day building a boundary diagram for a brushless DC motor controller (BLDC) and then using it to systematically identify failure modes at every interface—mechanical, electrical, thermal, and software. The result was a DFMEA that didn’t just list “capacitor fails open” but instead captured failures like “thermal interface between MOSFET and heatsink degrades, causing junction temperature runaway.” That level of precision comes directly from the boundary diagram.

## The Core Concept

A boundary diagram is a block diagram that shows the **system under analysis**, its **adjacent systems**, and all **interfaces** between them. It answers the question: *What touches what, and how?*

Why do this before the DFMEA? Because failure modes live at interfaces. A resistor doesn’t fail in isolation—it fails because of voltage stress from the upstream regulator, or thermal stress from the adjacent power transistor, or mechanical stress from the PCB flexing. The boundary diagram forces you to enumerate every interface type:

- **Physical** (bolted, press-fit, soldered)
- **Energy** (electrical, thermal, magnetic, optical)
- **Material** (fluid, gas, lubricant)
- **Information** (digital signals, analog voltages, PWM duty cycles)

Once you have the diagram, you walk each interface and ask: *What can go wrong at this specific connection?* This turns the DFMEA from a generic checklist into a targeted, interface-driven analysis.

## Key Commands / Configuration / Code

I use **draw.io** (diagrams.net) for boundary diagrams because it’s free, version-controllable, and exports to SVG. But the real power is in the structured naming convention. Here’s my template:

```
File: BLDC_Motor_Controller_Boundary.drawio
```

**Block naming convention:**
- `[System Name]` — the item under analysis (e.g., `BLDC Controller`)
- `[Adjacent System]` — external systems that interact (e.g., `Battery Pack`, `Motor`, `Host MCU`)
- Interfaces labeled as: `[Type]: [Signal/Energy/Material]`

**Example interface labels from my diagram:**

```
Interface: Electrical: 48V DC Bus (Battery → Controller)
Interface: Thermal: Conduction through TIM (MOSFET → Heatsink)
Interface: Information: PWM Gate Drive (Controller → MOSFET)
Interface: Mechanical: Bolted joint M3 (Heatsink → Enclosure)
```

**Export to SVG for documentation:**

```bash
# From draw.io CLI (drawio-desktop headless)
drawio --export --format svg --output ./boundary_diagrams/BLDC_Controller.svg BLDC_Motor_Controller_Boundary.drawio
```

**Embed in DFMEA worksheet (CSV example):**

```csv
Interface_ID,From_Block,To_Block,Interface_Type,Description,Failure_Mode,Effect
I-001,Battery Pack,BLDC Controller,Electrical,48V DC power input,Overvoltage transient >60V,Controller latch-up / destruction
I-002,BLDC Controller,MOSFET,Information,PWM gate signal 20kHz,Gate drive undershoot > -5V,MOSFET gate oxide breakdown
I-003,MOSFET,Heatsink,Thermal,Conduction via thermal pad,Pad delamination > 0.5mm gap,Junction temp rise > 25°C
```

**Python script to auto-generate interface list from diagram XML:**

```python
# parse_boundary.py — extracts interfaces from drawio XML
import xml.etree.ElementTree as ET

tree = ET.parse('BLDC_Motor_Controller_Boundary.drawio')
root = tree.getroot()

# Namespace for drawio
ns = {'drawio': 'http://www.diagrams.net'}

interfaces = []
for cell in root.iter('{http://www.diagrams.net}mxCell'):
    label = cell.get('value', '')
    if label.startswith('Interface:'):
        interfaces.append({
            'id': cell.get('id'),
            'label': label,
            'source': cell.get('source'),
            'target': cell.get('target')
        })

for iface in interfaces:
    print(f"{iface['id']}: {iface['label']}")
```

## Common Pitfalls & Gotchas

1. **Forgetting the “outside world” blocks.** Engineers often draw only the internal components. You must include everything that touches your system: power supply, load, user, environment (ambient temp, humidity, vibration). A missing “Ambient Air” block means you’ll miss failure modes like condensation on exposed terminals.

2. **Labeling interfaces too vaguely.** “Wire connection” is useless. Specify: “Crimped terminal, 14 AWG, tin-plated copper, mated to PCB header.” The failure mode for a crimped terminal (pull-out force degradation) is completely different from a soldered joint (solder fatigue). Precision in the interface label drives precision in the DFMEA.

3. **Skipping the “information” interfaces.** Electrical engineers are good at power interfaces but often ignore digital communication interfaces. A boundary diagram must include SPI, I2C, CAN, or PWM signal paths. Failure modes like “glitch on SCL line causes register miswrite” are real and should be captured.

## Try It Yourself

1. **Draw a boundary diagram for a simple system you know well** — like a USB-C charger or a temperature sensor module. Include at least 5 blocks and 8 interfaces. Label every interface with type (Electrical, Thermal, Mechanical, Information).

2. **Take one interface from your diagram and write a mini-DFMEA for it.** For example, the “USB-C VBUS (5V)” interface: list 3 failure modes (overvoltage, undervoltage, reverse polarity), their effects, and one existing control (e.g., TVS diode, current limit).

3. **Export your diagram as SVG and embed it in a DFMEA worksheet.** Use the Python script above (or manual CSV) to create a table mapping each interface to a row in your DFMEA. This forces you to ensure every interface has at least one failure mode.

## Next Up

Tomorrow: **DFMEA for Electronics: Component-Level Failure Modes** — we’ll drill into passive components (resistors, capacitors, inductors) and active devices (MOSFETs, op-amps, microcontrollers) to understand their physics-of-failure mechanisms and how to capture them in a DFMEA without drowning in detail.
