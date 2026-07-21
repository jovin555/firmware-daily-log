---
title: "Day 21: IEC 62443: Industrial Cybersecurity Threat Modeling"
date: 2026-07-21
tags: ["til", "threat-modeling", "iec62443"]
---

## What I Explored Today

I dove into IEC 62443, the international standard series for industrial communication network security, specifically how it structures threat modeling for Industrial Control Systems (ICS) and Operational Technology (OT). Unlike IT-focused frameworks (like STRIDE or PASTA), IEC 62443 forces you to think in zones, conduits, and security levels (SLs). I worked through mapping a real PLC-based water treatment system to the standard's foundational requirements (FRs) and found that the biggest shift is moving from "what can go wrong" to "what security level must this zone sustain."

## The Core Concept

IEC 62443 is not a checklist; it's a risk-based framework built on the premise that industrial environments have different priorities than enterprise IT. The core model is **zones and conduits**. A zone is a logical or physical grouping of assets that share common security requirements. A conduit is the communication path between zones (or between a zone and an external network).

The "why" is critical: in a factory, you can't just patch a PLC every Tuesday. Availability and safety come first. IEC 62443 provides a structured way to answer: *What is the required Security Level (SL) for this zone?* SLs range from SL 1 (protection against casual violation) to SL 4 (protection against intentional, sophisticated attacks using advanced resources). You then perform a threat model to determine the *achieved* SL (SL-A) and identify gaps.

The seven Foundational Requirements (FRs) are the threat modeling lens:
- FR 1: Identification and authentication control
- FR 2: Use control
- FR 3: System integrity
- FR 4: Data confidentiality
- FR 5: Restricted data flow
- FR 6: Timely response to events
- FR 7: Resource availability

When threat modeling, you don't ask "Is this vulnerable to SQL injection?" You ask "Does this zone's conduit meet FR 5 (restricted data flow) for SL 3?" This shifts the conversation from finding bugs to verifying architectural security properties.

## Key Commands / Configuration / Code

IEC 62443 is a paper standard, but you operationalize it with tools. Here's a practical approach using a simple Python script to parse a zone/conduit model from a YAML file and check foundational requirement coverage.

**File: `iec62443_model.yaml`**
```yaml
zones:
  - name: "Safety-Critical PLC Zone"
    assets: ["PLC-01", "PLC-02", "Safety Relay"]
    target_sl: 3
    conduits:
      - name: "HMI-to-PLC"
        protocol: "Modbus/TCP"
        source_zone: "Operator HMI Zone"
        destination_zone: "Safety-Critical PLC Zone"
        fr_requirements:
          fr1: true   # auth required
          fr2: true   # role-based access
          fr3: true   # integrity check
          fr4: false  # no confidentiality needed
          fr5: true   # firewall between zones
          fr6: false  # no real-time event logging
          fr7: true   # redundant path
```

**File: `check_62443_coverage.py`**
```python
import yaml
import sys

def load_model(filepath):
    with open(filepath, 'r') as f:
        return yaml.safe_load(f)

def check_zone_sl(zone, model):
    """Check if a zone's conduit FRs meet its target SL."""
    target = zone['target_sl']
    # Simplified mapping: SL 3 requires at least 5 of 7 FRs active
    # Real mapping is per FR in the standard (SL 3 for FR 1 means X)
    for conduit in zone['conduits']:
        active_frs = sum(1 for v in conduit['fr_requirements'].values() if v)
        print(f"  Conduit '{conduit['name']}': {active_frs}/7 FRs active")
        if target >= 3 and active_frs < 5:
            print(f"  WARNING: Conduit '{conduit['name']}' may not meet SL {target}")
        elif target == 4 and active_frs < 7:
            print(f"  WARNING: SL 4 requires all 7 FRs active for conduit '{conduit['name']}'")

if __name__ == "__main__":
    model = load_model("iec62443_model.yaml")
    for zone in model['zones']:
        print(f"Zone: {zone['name']} (Target SL: {zone['target_sl']})")
        check_zone_sl(zone, model)
```

Run it:
```bash
python3 check_62443_coverage.py iec62443_model.yaml
```

Output:
```
Zone: Safety-Critical PLC Zone (Target SL: 3)
  Conduit 'HMI-to-PLC': 5/7 FRs active
```

This is a toy, but the pattern scales: you define your zones, assign target SLs, then systematically check each conduit's FR coverage. In practice, you'd use a tool like **Microsoft Threat Modeling Tool** with a custom ICS stencil or **OWASP Threat Dragon** with zone diagrams.

## Common Pitfalls & Gotchas

1. **Confusing SL-Target with SL-Capability.** Engineers often say "my PLC is SL 3 certified." That's the *capability* of the device (SL-C). Your threat model must determine the *target* SL (SL-T) for the zone, which may be lower or higher. A certified SL 4 device in a zone with SL-T 1 is overkill and expensive. A zone with SL-T 3 using SL 1 devices is a gap.

2. **Forgetting the "Conduit" is the attack surface.** Most threat models focus on the devices (PLCs, HMIs). IEC 62443 forces you to model the *conduit*—the network path, protocol, and firewall rules. I've seen teams spend weeks hardening a PLC while leaving the Modbus/TCP conduit wide open to any device on the OT network. The conduit is where you apply FR 5 (restricted data flow).

3. **Treating SLs as binary.** SL 3 doesn't mean "secure." It means the zone can resist *systematic* attacks with moderate resources. If your threat model assumes an insider threat with physical access, you need SL 4. Always map the attacker profile (casual, sophisticated, nation-state) to the SL requirement, not the other way around.

## Try It Yourself

1. **Map your lab's OT network into zones and conduits.** Draw a diagram with three zones: "Untrusted (Internet)", "DMZ (Historian)", and "Control (PLCs)". List every conduit (e.g., "Historian to PLC via OPC-UA"). For each, write down which of the 7 FRs are currently enforced.

2. **Run the Python checker on your model.** Create a YAML file for your lab setup. Assign target SLs based on a realistic threat: SL 2 for the DMZ (casual attacker), SL 3 for the control zone (targeted attack). Run the script and see which conduits fail.

3. **Identify one conduit with a gap.** Pick a conduit that fails the SL check (e.g., missing FR 5 for restricted data flow). Propose a concrete mitigation: a unidirectional gateway, a firewall rule, or protocol deep packet inspection. Write the rule in iptables or Suricata syntax.

## Next Up

Tomorrow: **Vulnerability Disclosure & CVE Response for Firmware Vendors** — how to handle a researcher finding a buffer overflow in your RTOS-based bootloader, from initial report to coordinated disclosure and patch release.
