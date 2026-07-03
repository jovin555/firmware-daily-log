---
title: "Day 03: Data Flow Diagrams for Embedded Systems Threat Models"
date: 2026-07-03
tags: ["til", "threat-modeling", "dfd", "threat-modeling"]
---

## What I Explored Today

Today I dug into building Data Flow Diagrams (DFDs) specifically for embedded systems threat models. While DFDs are a staple of classic threat modeling (think STRIDE per element), embedded systems introduce unique challenges: hardware-software boundaries, real-time constraints, and physical attack surfaces. I explored how to adapt DFD notation to capture these nuances—specifically, how to model memory-mapped I/O, interrupt handlers, DMA channels, and the trust boundary between firmware and the physical world. The key insight: a DFD for an embedded system must represent *both* logical data flows and physical data flows (e.g., sensor readings, actuator commands) because the adversary can often touch the latter directly.

## The Core Concept

A DFD is a directed graph of **processes** (circles), **data stores** (parallel lines), **external entities** (rectangles), and **data flows** (arrows). In embedded threat modeling, the goal is to identify where data crosses trust boundaries—places where an attacker might inject, spoof, tamper, or observe data. The "why" is straightforward: without a DFD, you're guessing at attack surfaces. With one, you systematically enumerate every interaction point.

The twist for embedded systems: you must model **hardware registers**, **interrupt service routines (ISRs)**, and **DMA controllers** as processes or data stores, because they are active participants in data movement. A typical mistake is to treat a microcontroller as a single process. Instead, decompose it: the CPU core, the UART peripheral, the ADC, the DMA engine, and the flash memory are all separate trust domains. A buffer overflow in an ISR can corrupt data flowing to a main loop; a DMA write can bypass CPU memory protection entirely.

## Key Commands / Configuration / Code

Below is a concrete example: a DFD for a simple IoT temperature sensor with an ARM Cortex-M4 MCU, an I2C temperature sensor, and a UART-to-WiFi module. I'll represent the DFD using a text-based diagram (PlantUML style) and then show the corresponding threat enumeration snippet.

```plantuml
@startuml
!define RECTANGLE class
!define CIRCLE class
!define STORE class

' External Entities
rectangle "WiFi Module\n(UART)" as WIFI
rectangle "Temperature Sensor\n(I2C)" as SENSOR
rectangle "Power Supply\n(3.3V)" as POWER

' Processes
circle "Main Loop\n(CPU)" as MAIN
circle "I2C ISR" as I2C_ISR
circle "UART ISR" as UART_ISR
circle "DMA Controller" as DMA
circle "ADC (internal)" as ADC

' Data Stores
store "Flash\n(Firmware)" as FLASH
store "SRAM\n(Variables)" as SRAM
store "RTC Registers" as RTC

' Data Flows
SENSOR --> I2C_ISR : "I2C data (temperature)"
I2C_ISR --> SRAM : "write sample buffer"
MAIN --> SRAM : "read sample buffer"
MAIN --> UART_ISR : "send command"
UART_ISR --> WIFI : "UART TX (JSON)"
WIFI --> UART_ISR : "UART RX (config)"
UART_ISR --> SRAM : "write config"
MAIN --> FLASH : "read firmware"
DMA --> SRAM : "memcpy (bypass CPU)"
ADC --> SRAM : "write voltage reading"
POWER --> MAIN : "voltage level (GPIO)"

' Trust boundaries
rectangle "MCU Boundary" as MCU {
  rectangle "CPU Domain" {
    MAIN
    FLASH
    SRAM
  }
  rectangle "Peripheral Domain" {
    I2C_ISR
    UART_ISR
    DMA
    ADC
  }
}
@enduml
```

Now, here's a Python snippet that parses a DFD (represented as a JSON adjacency list) and prints potential threats using STRIDE per data flow:

```python
# threat_model_dfd.py
import json

# Example DFD adjacency list for the IoT sensor
dfd = {
    "data_flows": [
        {"from": "SENSOR", "to": "I2C_ISR", "data": "temperature", "crosses_boundary": True},
        {"from": "I2C_ISR", "to": "SRAM", "data": "sample_buffer", "crosses_boundary": False},
        {"from": "MAIN", "to": "UART_ISR", "data": "command", "crosses_boundary": False},
        {"from": "UART_ISR", "to": "WIFI", "data": "json_payload", "crosses_boundary": True},
        {"from": "WIFI", "to": "UART_ISR", "data": "config", "crosses_boundary": True},
        {"from": "DMA", "to": "SRAM", "data": "bulk_data", "crosses_boundary": True},  # DMA bypasses CPU
    ]
}

# STRIDE mapping per flow that crosses a trust boundary
stride_threats = {
    "Spoofing": "Attacker impersonates source",
    "Tampering": "Data modified in transit",
    "Repudiation": "No audit trail for action",
    "Information Disclosure": "Eavesdropping on flow",
    "Denial of Service": "Flood or corrupt flow",
    "Elevation of Privilege": "Flow used to gain higher access"
}

print("=== Threat Enumeration from DFD ===")
for flow in dfd["data_flows"]:
    if flow["crosses_boundary"]:
        print(f"\nFlow: {flow['from']} -> {flow['to']} ({flow['data']})")
        for threat, desc in stride_threats.items():
            print(f"  {threat}: {desc}")
```

Output snippet:
```
=== Threat Enumeration from DFD ===

Flow: SENSOR -> I2C_ISR (temperature)
  Spoofing: Attacker impersonates source
  Tampering: Data modified in transit
  ...

Flow: DMA -> SRAM (bulk_data)
  Spoofing: Attacker impersonates source
  Tampering: Data modified in transit
  Elevation of Privilege: Flow used to gain higher access
```

## Common Pitfalls & Gotchas

1. **Treating the MCU as a single process.** This is the #1 mistake. An MCU has multiple execution contexts (main loop, ISRs, DMA) that can run concurrently and share memory. An ISR can corrupt a buffer that the main loop is reading, creating a race condition that an attacker can exploit. Always decompose into at least: CPU core, each peripheral, and DMA.

2. **Ignoring hardware-level data flows.** In embedded systems, data doesn't just flow through software. A power glitch on the VDD line can corrupt an ADC reading. A clock glitch can skip instructions. Model physical flows (power, clock, reset) as data flows crossing trust boundaries. The adversary may have physical access.

3. **Forgetting that DMA is a separate trust domain.** DMA controllers often have their own memory access that bypasses the CPU's MPU (Memory Protection Unit). If an attacker can control a DMA channel (e.g., via a compromised peripheral), they can read or write any memory location. Always mark DMA-to-memory flows as crossing a trust boundary.

## Try It Yourself

1. **Draw a DFD for your current embedded project.** Decompose the MCU into at least three processes: main loop, one ISR, and the DMA controller. Identify at least two data flows that cross a trust boundary (e.g., sensor input, wireless output). Use PlantUML or draw.io.

2. **Run the Python script above with your own DFD.** Replace the `dfd` dictionary with your flows. Add a `crosses_boundary` field for each flow. Then extend the script to print only threats that apply to embedded systems (e.g., add "Fault Injection" as a threat type).

3. **Identify one "hidden" data flow in your system.** For example, a shared memory region between an ISR and the main loop, or a DMA channel that copies data from a peripheral to SRAM. Add it to your DFD and ask: what STRIDE threats apply?

## Next Up

Tomorrow: **Attack Trees: Modeling Adversary Goals & Paths**. We'll move from data-centric DFDs to adversary-centric attack trees, where we model how an attacker might chain exploits to achieve a goal (e.g., "exfiltrate encryption key" or "trigger a buffer overflow via UART"). We'll also cover how to combine DFDs and attack trees for a complete threat model.
