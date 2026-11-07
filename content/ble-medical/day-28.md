---
title: "Day 28: Compliance: Bluetooth SIG Qualification, FCC & FDA Wireless Coexistence (ANSI C63.27)"
date: 2026-11-07
tags: ["til", "ble-medical", "qualification", "coexistence"]
---

## What I Explored Today

Today I pulled together the three compliance threads that have been lurking in the background of this whole series: Bluetooth SIG qualification (so my device is legally allowed to use the BLE logo and reference the spec), FCC Part 15 certification (so it can radiate legally in the US), and FDA wireless coexistence testing per ANSI C63.27 (so a regulator believes my pulse oximeter keeps working when a Wi-Fi AP is blasting next to a patient). These are three different regimes with three different owners, and conflating them is the classic first-timer mistake. I spent the day mapping which artifacts each one actually needs, then wrote a small script to pull the SIG qualification data out of my build so the submission isn't a manual copy-paste exercise.

## The Core Concept

The "why" here is that a BLE medical device sits at the intersection of three regulators who don't talk to each other:

- **Bluetooth SIG** governs *interoperability and the spec*. You cannot ship a product that claims "Bluetooth" without a Declaration ID. Qualification is a self-declaration against the appropriate ICS (Implementation Conformance Statement) plus test evidence from a recognized test facility (or the SIG's own test tooling for some profiles). It is not an RF regulator — it's a trademark/spec conformance body.
- **FCC Part 15** governs *unlicensed RF emission*. For a 2.4 GHz BLE radio you're operating under Part 15.247 (hopping/DTS) or 15.249 depending on the modulation and power. You need an FCC ID, and the module you integrate may already carry one — but only if you don't exceed the module's grant conditions (antenna, power, shielding).
- **FDA** governs *safety and effectiveness*. For a wireless medical device, ANSI C63.27 ("Evaluation of Wireless Coexistence") is the consensus standard FDA recognizes for demonstrating that your device tolerates interference from other radios in its environment. It's a risk-based test: you define the *intended coexistence environment* (e.g., hospital, home), identify *coexisting signals* (Wi-Fi, other BLE, LTE), and run *functional wireless performance* (FWP) tests while injecting interference.

The key insight: SIG qualification proves your stack is correct; FCC proves your radio is legal; C63.27 proves your *clinical function* survives the RF neighborhood. A device can pass the first two and still fail the third because the failure mode is at the application layer (dropped notifications, reconnection storms), not the PHY.

## Key Commands / Configuration / Code

Pulling the SIG qualification inputs out of a Zephyr build — the ICS and the profile/ service declarations need to match what's actually compiled in:

```c
/* prj.conf — the Kconfig symbols that map to your GATT declarations.
 * Every one of these that ends up =y must be reflected in your ICS. */
CONFIG_BT=y
CONFIG_BT_PERIPHERAL=y
CONFIG_BT_GATT_DIS=y            /* Device Information Service — required by many profiles */
CONFIG_BT_DIS_MODEL_NUMBER_STR="POX-100"
CONFIG_BT_DIS_MANUF_NAME_STR="Acme Medical"
CONFIG_BT_DIS_FW_REV_STR="1.4.2"
CONFIG_BT_BAS=y                 /* Battery Service */
CONFIG_BT_PASSKEY_KEYPRESS=y    /* if you claim LE Secure Connections passkey */
```

```bash
# Dump the resolved config so the ICS reviewer sees exactly what shipped.
west build -b nrf52840dk_nrf52840 -- -DCONFIG_BT_DIS=y
grep -E '^CONFIG_BT_(DIS|BAS|PERIPHERAL|GATT)' build/zephyr/.config \
  | sort > artifacts/sig_ics_inputs.txt

# Confirm the actual GATT database the radio will expose (nRF Connect / btmon).
# btmon decodes the ATT server database from the air — this is your ground truth.
sudo btmon -w artifacts/gatt_capture.snoop &
# ...connect with nRF Connect, discover services, then stop btmon...
```

FCC: verify the module grant before you assume you're covered — the grant lists the exact antenna and max conducted power:

```bash
# Look up the module's FCC ID grant (example: Nordic nRF52840 module).
# The grant PDF lists "Output Power" and "Antenna Type" — stay inside both.
# If you change the antenna, you are a new grantee and need your own FCC ID.
```

ANSI C63.27 test-matrix skeleton (this is what the test lab will ask you to fill in — define it *before* you call them):

```yaml
# coexistence_plan.yaml — intended environment drives everything downstream
intended_environment: healthcare_facility   # vs. home_healthcare
functional_wireless_performance:
  metric: spo2_notification_latency_p95_ms
  pass_threshold: 500        # clinical decision must arrive within 500 ms p95
  baseline: 120              # measured in quiet RF
coexisting_signals:
  - type: wifi_80211n
    band: 2.4GHz
    duty_cycle: 100%         # saturated AP is the worst realistic case
    level_dbm: -40           # near-field, ~1 m
  - type: ble_peer
    connections: 8           # crowded waiting room
  - type: lte_band_7
    note: "uplink harmonics land in 2.4 GHz"
test_method: radiated         # vs. conducted; radiated is what FDA expects for a wearable
```

## Common Pitfalls & Gotchas

1. **Assuming the module's FCC ID covers your product.** It only covers the module *as granted* — same antenna, same power, same shielding, and often a specific host integration note. Swap the chip antenna for a PCB trace antenna and you've invalidated the grant; you now need your own certification. Read the grant's "Class II Permissive Change" history before reusing an ID.

2. **ICS drift between firmware and submission.** You enable `CONFIG_BT_PASSKEY_KEYPRESS` for a demo, forget it, and your ICS still claims "No" for LE Secure Connections keypress. The SIG auditor compares your declared ICS against the actual GATT/security behavior. Generate the ICS inputs from the resolved `.config` (as above), not from memory.

3. **Treating C63.27 as a checkbox instead of a risk analysis.** The standard is explicitly risk-based: you must justify *which* coexisting signals and *what* FWP metric. A lab will happily run a generic Wi-Fi test, but if your intended environment is a home with a microwave and a baby monitor, a 2.4 GHz Wi-Fi-only matrix doesn't demonstrate coexistence for your actual use case. Define the environment and the clinical failure mode first; the test follows.

## Try It Yourself

1. **Generate your ICS inputs from the build.** Add the `grep` one-liner above to your CI, and diff the output against a checked-in `sig_ics_inputs.txt`. Any config change that alters your GATT/security surface should fail the build until the ICS is updated.

2. **Audit your module's FCC grant.** Find the FCC ID on your radio module, pull the grant PDF from the FCC OET database, and write down the exact antenna type and max output power. Then measure or look up your actual conducted power and antenna — note any delta. If you're outside the grant, flag it now, not at certification.

3. **Draft a one-page C63.27 plan.** For your device, fill in the `coexistence_plan.yaml` fields: intended environment, one FWP metric with a pass threshold, and the two most likely interferers. You don't need the lab yet — you need to know what you'd ask them to test.

## Next Up

Tomorrow we close the series: **Full Review & Project — Secure BLE Pulse Oximeter Peripheral to Mobile App.** We'll assemble everything from the last 28 days into one end-to-end build — pairing, bonding, encrypted SpO₂ notifications, DFU, and the compliance artifacts we generated today — and walk the full test plan from power-on to app-displayed reading.
