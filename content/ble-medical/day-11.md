---
title: "Day 11: Standard Medical Profiles: Heart Rate, Health Thermometer, Pulse Oximeter & GHS"
date: 2026-10-21
tags: ["til", "ble-medical", "profiles", "health"]
---

## What I Explored Today

Today I dug into the four GATT profiles that show up in almost every medical BLE product I've touched: Heart Rate (HRS, `0x180D`), Health Thermometer (HTS, `0x1809`), Pulse Oximeter (PLX, `0x1822`), and the newer Generic Health Sensor profile (GHS, `0x1841`). What struck me is how much of the "medical BLE" work is actually just correctly interpreting the flags byte at the start of each measurement characteristic — the profiles themselves are thin, but the bitfields inside the measurement payloads are where all the real bugs live. I spent the afternoon walking through each one with `bluetoothctl` and a Nordic nRF52 dev kit, decoding raw notification bytes by hand to make sure I understood the layout before trusting any library.

## The Core Concept

The reason these profiles exist is interoperability: a phone or gateway shouldn't need vendor-specific drivers to read a heart rate. The Bluetooth SIG defines, for each profile, a small set of mandatory characteristics with a defined *service* UUID, a *characteristic* UUID, and — critically — a **flags field** as the first byte of every measurement value. That flags byte is a bitfield that tells you which optional fields follow. If you ignore it and assume a fixed layout, you'll parse garbage the moment a device enables a timestamp or a sensor-contact bit.

The pattern is consistent across all four:

- **Heart Rate Measurement** (`0x2A37`): flags byte, then HR value (uint8 or uint16 depending on bit 0), then optional energy expended, RR intervals.
- **Temperature Measurement** (`0x2A1C`): flags byte, then a 32-bit IEEE-11073 FLOAT (mantissa + exponent), then optional timestamp, temperature type.
- **PLX Spot-Check / Continuous Measurement** (`0x2A5E` / `0x2A5F`): flags, then SpO2 and pulse rate as SFLOATs, plus optional status and timestamp.
- **GHS**: a newer, more generic container that reuses the same measurement pattern but lets a device advertise multiple sensor types (HR, temp, SpO2) through one service — useful when you don't want to implement three separate profiles.

The "why" is that these are *transport-agnostic data contracts*. The same bytes flow over BLE, and a conformant parser on the other side produces the same clinical value regardless of silicon vendor. Your job as an engineer is to honor the contract exactly — especially the flags.

## Key Commands / Configuration / Code

Discovering and subscribing with BlueZ:

```bash
# Scan and connect
bluetoothctl
> scan on
> connect AA:BB:CC:DD:EE:FF

# List GATT services — look for 180D, 1809, 1822, 1841
> menu gatt
> list-attributes

# Subscribe to Heart Rate Measurement notifications
> select-attribute /org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF/service0010/char0011
> notify on
```

Decoding the Heart Rate Measurement flags byte (Python, `bleak`):

```python
# HR Measurement: flags bit0 = 0 -> uint8 HR, bit0 = 1 -> uint16 HR
# bit3 = energy expended present, bit4 = RR intervals present
def parse_hr(data: bytes):
    flags = data[0]
    idx = 1
    if flags & 0x01:
        hr = int.from_bytes(data[idx:idx+2], "little"); idx += 2
    else:
        hr = data[idx]; idx += 1
    energy = None
    if flags & 0x08:
        energy = int.from_bytes(data[idx:idx+2], "little"); idx += 2
    rr = []
    if flags & 0x10:
        # RR intervals are in 1/1024 s units, uint16 each
        while idx + 1 < len(data):
            rr.append(int.from_bytes(data[idx:idx+2], "little") / 1024.0)
            idx += 2
    return hr, energy, rr
```

Decoding an IEEE-11073 FLOAT (Health Thermometer, `0x2A1C`):

```python
# 32-bit FLOAT: 24-bit signed mantissa (LE) + 8-bit signed exponent
def parse_ieee11073_float(b: bytes) -> float:
    mantissa = int.from_bytes(b[0:3], "little", signed=True)
    exponent = int.from_bytes(b[3:4], "little", signed=True)
    return mantissa * (10 ** exponent)
# e.g. bytes 0x2A 0x1A 0x00 0xFF -> mantissa 6698, exp -1 -> 669.8 (0.1 degC units)
```

Enabling the Indicate on Temperature Measurement (HTS uses *indications*, not notifications, for `0x2A1C`):

```bash
> select-attribute .../char0005   # Temperature Measurement
> indicate on
```

## Common Pitfalls & Gotchas

1. **Assuming HTS uses notifications.** The Temperature Measurement characteristic is **Indicate**-only per spec. If you subscribe with `notify on` you'll get nothing and waste an hour. Use `indicate on` (and your stack must ACK the indication).

2. **Ignoring the flags byte on PLX.** Spot-Check Measurement (`0x2A5E`) has a status field and a timestamp that only appear when the corresponding flag bits are set. Hardcoding offsets gives you plausible-looking but wrong SpO2 values — dangerous in a clinical context.

3. **Treating RR intervals as milliseconds.** They're in units of 1/1024 second. Divide by 1024, not 1000. This is a classic off-by-2.4% error that shows up in HRV calculations.

## Try It Yourself

1. Connect to any HR sensor (a chest strap or the nRF52 with the HR sample) and log the raw notification bytes alongside your parsed HR. Toggle the sensor's RR-interval feature if it has one and confirm your parser handles the extra bytes.

2. Write a parser for the Health Thermometer `0x2A1C` that correctly handles the IEEE-11073 special values (`0x007FFFFF` = NaN, `0x007FFFFE` = NRes, `0x007FFFFD` = +INF). Feed it the raw bytes from a real device and verify against the vendor app.

3. Implement a minimal GHS (`0x1841`) client that enumerates the `0x2A5E`-style measurement characteristic and logs the sensor type from the flags. Compare the byte layout to the standalone PLX profile and note the differences.

## Next Up

Tomorrow: **BLE Security Overview: Pairing, Bonding & the Security Manager Protocol** — how LE Secure Connections actually work, why Just Works is a liability for medical devices, and how to configure your stack to require authenticated pairing on the measurement characteristics.
