---
title: "Day 17: Cybersecurity as a Failure Mode: FDA Premarket Guidance & Security Risk"
date: 2026-10-27
tags: ["til", "medical-iot-dfmea", "cybersecurity", "fda"]
---

## What I Explored Today

Today I stopped treating cybersecurity as a separate workstream bolted onto the DFMEA and started folding it into the failure-mode analysis itself. The FDA's 2023 premarket cybersecurity guidance ("Content of Premarket Submissions for Device Software Functions") makes this explicit: security risk must be assessed as part of the device's risk management file, not as a parallel document. That means a spoofed BLE command, a replayed session token, or an unauthenticated firmware update is a *failure mode* with a severity, an occurrence, and a detection rating — exactly like a cracked solder joint or a stuck sensor. I spent the day mapping STRIDE threats onto our DFMEA spreadsheet and wiring a small threat-modeling script to keep the two artifacts in sync.

## The Core Concept

The reason this matters is that traditional DFMEA asks "what happens when this component fails?" — but an attacker doesn't wait for a component to fail. They *cause* the failure deliberately, often through a path the design team never modeled (a debug port left open, a default credential, an unsigned OTA payload). If your DFMEA only enumerates hardware and software faults, your risk file has a blind spot the FDA reviewer will find.

The guidance reframes this: cybersecurity risk is a *subset* of safety risk. A ransomware lockout on a drug-infusion pump isn't an IT problem — it's a hazardous situation that can reach a patient. So the DFMEA needs failure modes like "attacker replays a bolus command," "firmware downgrade to vulnerable version," or "session token reused after logout." Each gets an S/O/D score, and the mitigations (signed updates, nonce-based replay protection, secure boot) become design controls traceable in the risk management file.

The practical trick is to run a STRIDE pass over each trust boundary in your data-flow diagram, then translate each credible threat into a DFMEA row. STRIDE gives you the *what*; DFMEA gives you the *so what* and the *how bad*.

## Key Commands / Configuration / Code

A small Python helper that turns a STRIDE threat list into DFMEA rows, so the two artifacts don't drift. RPN = Severity × Occurrence × Detection, same as your hardware rows.

```python
# threat_to_dfmea.py — map STRIDE threats to DFMEA rows
import csv

# Severity/Occurrence/Detection on the standard 1-10 scales.
# Detection: 10 = cannot detect, 1 = certain detection (inverse of hardware DFMEA convention).
THREATS = [
    # (id, STRIDE category, failure mode, effect, S, O, D, mitigation)
    ("CY-01", "Spoofing",   "Forged BLE command accepted as clinician",
     "Unauthorized therapy change", 9, 4, 6, "LE Secure Connections + app-layer auth"),
    ("CY-02", "Tampering",  "Unsigned OTA firmware installed",
     "Arbitrary code execution", 10, 3, 4, "Secure boot + signed image (ECDSA P-256)"),
    ("CY-03", "Repudiation", "Audit log writable by device user",
     "No forensic trail for adverse event", 5, 5, 7, "Append-only log, HMAC-chained"),
    ("CY-04", "Info disc.", "PHI in plaintext on debug UART",
     "Privacy breach / data exfil", 7, 6, 5, "Disable UART in production fuse"),
    ("CY-05", "DoS",        "Replayed pairing flood exhausts radio queue",
     "Loss of monitoring", 8, 4, 5, "Rate limit + nonce replay cache"),
    ("CY-06", "Elev. priv.", "Default admin creds on config web UI",
     "Full device takeover", 9, 5, 3, "Forced provisioning, no default creds"),
]

with open("dfmea_cyber.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["ID", "STRIDE", "Failure Mode", "Effect",
                "S", "O", "D", "RPN", "Mitigation"])
    for tid, stride, fm, eff, s, o, d, mit in THREATS:
        rpn = s * o * d
        w.writerow([tid, stride, fm, eff, s, o, d, rpn, mit])
        print(f"{tid} RPN={rpn:>4}  {fm}")
```

Verify the output and sort by RPN to prioritize mitigations:

```bash
# Sort DFMEA rows by RPN descending (skip header, numeric sort on col 8)
{ head -1 dfmea_cyber.csv; tail -n +2 dfmea_cyber.csv | sort -t, -k8 -nr; } > dfmea_sorted.csv
column -s, -t dfmea_sorted.csv
```

A quick check that your firmware image signing is actually enforced — this is the mitigation behind CY-02, and it's worth confirming the bootloader rejects a bad signature rather than trusting the build script:

```bash
# Confirm the image is signed and the signature verifies against the pinned key
openssl dgst -sha256 -verify pubkey.pem -signature fw.sig fw.bin
# Expected: "Verified OK"  — anything else means secure boot is a paper control

# Inspect the ELF for a secure-boot header / signature section
readelf -S fw.elf | grep -iE 'sig|secure|manifest'
```

## Common Pitfalls & Gotchas

**1. Scoring Detection backwards.** Hardware DFMEA convention often has D=1 meaning "easy to detect." Security controls frequently *can't* detect an attack in real time (a spoofed packet looks valid), so teams either inflate detection or silently flip the scale mid-spreadsheet. Pick one convention, document it in the DFMEA header, and keep it consistent — a reviewer will catch a mixed scale.

**2. Treating "encrypted" as "mitigated."** Encryption addresses information disclosure (the I in CIA) but does nothing for replay, spoofing, or elevation of privilege. A row that says "AES-128 mitigates all threats on this link" is a red flag. Map each mitigation to the specific STRIDE category it actually closes.

**3. Forgetting the supply chain and update path.** The most common real-world medical device compromises come through unsigned updates, exposed debug interfaces, and third-party libraries (log4j-style). If your DFMEA has no rows for "malicious/corrupted update" and "vulnerable SBOM component," the threat model is incomplete — and the FDA's SBOM expectations will surface it.

## Try It Yourself

1. **Run a STRIDE pass on one trust boundary.** Take your device's BLE or Wi-Fi link, list every STRIDE category, and write one credible threat per category. Translate each into a DFMEA row with S/O/D and an RPN. You'll likely find 2-3 threats your hardware DFMEA missed entirely.

2. **Verify one security control is real, not paper.** Pick your firmware update path and confirm the bootloader actually rejects a tampered image (flip a byte in `fw.bin`, re-run the `openssl dgst -verify` check, and confirm the device refuses to boot it). A control you can't demonstrate is a control you can't claim.

3. **Reconcile your SBOM against your threat model.** Export your SBOM (CycloneDX or SPDX), grep for components with known CVEs, and add a DFMEA row for each exploitable one. Bonus: confirm your `Detection` rating reflects whether you'd actually *notice* exploitation in the field.

## Next Up

Tomorrow: **Use-Related Failure Modes: IEC 62366 Usability Engineering & uFMEA** — how to fold use errors (misread alarms, wrong-mode selection, confusing connectors) into the same risk file, and why a use-related failure mode often scores higher severity than the hardware fault it triggers.
