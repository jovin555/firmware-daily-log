---
title: "Day 21: Cybersecurity for Medical Devices: IEC 81001-5-1"
date: 2026-07-03
tags: ["til", "iec62304", "cybersecurity", "iec81001"]
---

## What I Explored Today

Today I dug into IEC 81001-5-1, the cybersecurity standard that sits alongside IEC 62304 for medical device software. While 62304 covers safety (patient harm from malfunction), 81001-5-1 covers security (patient harm from malicious exploitation). I focused on how this standard integrates into the Release & Maintenance phase—specifically, what changes when you’re shipping a patch or a new firmware version and must now also prove you haven’t introduced a vulnerability. The key takeaway: security risk management isn’t a separate waterfall; it’s threaded into every release artifact, from SBOM updates to penetration test reports.

## The Core Concept

IEC 81001-5-1 (full title: *Health software and health IT systems safety, effectiveness and security—Part 5-1: Security—Activities in the product life cycle*) is the cybersecurity counterpart to 62304. It was published in 2021 and harmonizes with both 62304 and ISO 14971 (risk management). The standard defines 10 security-related processes that map onto the 62304 software life cycle processes.

For Release & Maintenance specifically, the critical processes are:

- **Process 7: Security risk management** — continuous assessment of threats, not just at design time.
- **Process 8: Security verification and validation** — evidence that security controls work as intended.
- **Process 9: Security problem resolution** — handling vulnerability reports post-market.

The practical shift: when you release a new version, you must now produce a **security delta analysis**—a document comparing the threat model of the previous release to the new one. If you added a new network protocol (say, TLS 1.3 support), you need a new attack tree and updated penetration test results before the release is approved.

## Key Commands / Configuration / Code

### 1. Generating an SBOM (Software Bill of Materials) with `syft`

The SBOM is a mandatory artifact for 81001-5-1 compliance. It lists every third-party component, version, and license.

```bash
# Scan a Docker image for its SBOM in SPDX format
syft packages mydevice:1.2.3 -o spdx-json > sbom_1.2.3.spdx.json

# Verify the SBOM against known vulnerabilities using grype
grype sbom:sbom_1.2.3.spdx.json --fail-on high
```

**Why this matters:** Without an SBOM, you cannot perform vulnerability scanning on your supply chain. IEC 81001-5-1 requires you to track and remediate known vulnerabilities (CVEs) in all third-party components.

### 2. Automated Threat Model Diff with `threat-dragon`

For a release delta, you need to compare the old and new threat models. I use a script that exports OWASP Threat Dragon models as JSON and diffs them.

```bash
# Export two threat models (previous and current release)
threat-dragon export -i threat_model_v1.2.2.json -o v1.2.2_tm.json
threat-dragon export -i threat_model_v1.2.3.json -o v1.2.3_tm.json

# Diff the threat models (custom Python script)
python threat_diff.py v1.2.2_tm.json v1.2.3_tm.json
```

The `threat_diff.py` script (simplified) checks for new threats, removed mitigations, or changed risk levels:

```python
import json, sys

old = json.load(open(sys.argv[1]))
new = json.load(open(sys.argv[2]))

old_threats = {t['id']: t for t in old['threats']}
new_threats = {t['id']: t for t in new['threats']}

added = set(new_threats) - set(old_threats)
removed = set(old_threats) - set(new_threats)

print(f"Added threats: {len(added)}")
print(f"Removed threats: {len(removed)}")
for tid in added:
    print(f"  NEW: {new_threats[tid]['title']} (risk: {new_threats[tid]['risk']})")
```

### 3. Security Regression Test in CI/CD

Add a gate that runs known security tests before release:

```yaml
# .gitlab-ci.yml snippet
security-gate:
  stage: release
  script:
    - syft packages ./firmware.bin -o cyclonedx-json > sbom.json
    - grype sbom:sbom.json --fail-on high
    - zap-cli quick-scan --self-contained --spider --ajax-spider \
      --start-options '-config api.disablekey=true' \
      http://device-simulator:8080
  only:
    - tags
```

This fails the pipeline if any high-severity CVE is found or if the OWASP ZAP scanner detects a critical web vulnerability.

## Common Pitfalls & Gotchas

1. **Treating security as a one-time activity.** I’ve seen teams do a threat model at design time and never update it. IEC 81001-5-1 requires that the threat model be a living document. Every release must include a delta analysis. If you skip this, a regulator will flag it as a non-conformance.

2. **Ignoring the SBOM for firmware.** Many embedded engineers think “we don’t use npm, so we don’t need an SBOM.” Wrong. Your RTOS, cryptographic library, and even the compiler toolchain are components. Use `syft` on your final binary or filesystem image. A missing SBOM is the #1 finding in FDA cybersecurity audits.

3. **Mixing safety and security risk management.** IEC 62304’s risk management (hazard analysis) and IEC 81001-5-1’s security risk management (threat modeling) are separate processes with different outputs. A buffer overflow is a safety hazard if it causes a patient shock; it’s a security vulnerability if an attacker triggers it remotely. You need both analyses, and they must be cross-referenced in the release documentation.

## Try It Yourself

1. **Generate an SBOM for your current device firmware.** Use `syft` on your build output (binary, filesystem image, or Docker container). Then run `grype` on that SBOM. How many high-severity CVEs do you have? Document them in your risk management file.

2. **Create a threat model delta for your last release.** If you have an old threat model, diff it against the current one. If you don’t have one, create a simple threat model for your device using OWASP Threat Dragon, then simulate a release that adds a new feature (e.g., OTA update). Update the threat model and document the delta.

3. **Add a security gate to your CI/CD pipeline.** Write a GitLab CI or GitHub Actions job that runs `grype` on your SBOM and fails if any critical vulnerability is found. Then add a step that runs a basic OWASP ZAP scan against your device’s web interface (if applicable). Commit and push a change that introduces a known vulnerable library—watch the pipeline fail.

## Next Up

Tomorrow: **Agile & IEC 62304: Making Iterative Dev Compliant** — how to run sprints without drowning in documentation, and where the standard actually *allows* you to defer risk management activities.
