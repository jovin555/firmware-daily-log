---
title: "Day 22: Vulnerability Disclosure & CVE Response for Firmware Vendors"
date: 2026-07-22
tags: ["til", "threat-modeling", "cve", "disclosure"]
---

## What I Explored Today

Most firmware teams treat vulnerability disclosure as an afterthought — a panicked scramble when a researcher emails `security@` or a CVE drops on a public mailing list. Today I dug into the operational side of coordinated vulnerability disclosure (CVD) specifically for embedded firmware vendors. The key insight: you don't need a full-time security team to have a credible process, but you *do* need a documented, testable pipeline that covers receipt, triage, patch development, and coordinated release. I walked through setting up a `security.txt` file, configuring a private PGP key for encrypted researcher communication, and building a minimal CVE response checklist that fits into a sprint-based firmware release cycle.

## The Core Concept

Vulnerability disclosure for firmware is fundamentally different from web or mobile app disclosure. Your product ships in ROM, flash, or OTA update packages, and the window between disclosure and exploitation can be days — not months. The "why" behind a structured disclosure process is threefold:

1. **Legal liability**: Many jurisdictions (EU Cyber Resilience Act, US IoT Cybersecurity Improvement Act) now mandate a vulnerability disclosure policy and a point of contact. Without it, you risk non-compliance fines.
2. **Researcher trust**: If you respond within 48 hours with a clear triage timeline, researchers will give you 90+ days to patch. Ignore them, and they go public in 30 days — or sell the exploit.
3. **Supply chain risk**: Your firmware vulnerabilities affect your customers' products. A CVE in your bootloader or RTOS kernel cascades. A structured response lets you notify downstream integrators before public disclosure.

The core workflow is: **Receive → Validate → Triage → Patch → Coordinate → Publish**. Each step must have a documented owner and a maximum time budget.

## Key Commands / Configuration / Code

### 1. Setting up `security.txt` for your firmware product

Place this at `/.well-known/security.txt` on your product's support website or in the firmware's root filesystem (if accessible via a web interface):

```text
# security.txt for ACME IoT Gateway v3 firmware
Contact: mailto:security@acme-iot.com
Encryption: https://acme-iot.com/pgp-key.asc
Preferred-Languages: en, de
Canonical: https://acme-iot.com/.well-known/security.txt
Policy: https://acme-iot.com/security-policy.html
Hiring: https://acme-iot.com/careers
Expires: 2027-07-22T00:00:00.000Z
```

Validate the file with the `securitytxt` CLI tool:

```bash
# Install the validator
pip install securitytxt

# Validate your file
securitytxt validate --url https://acme-iot.com/.well-known/security.txt
# Expected output: "security.txt is valid"
```

### 2. Generating a dedicated PGP key for vulnerability reports

```bash
# Generate a 4096-bit RSA key, no passphrase (for automated decryption in CI)
gpg --batch --gen-key <<EOF
Key-Type: RSA
Key-Length: 4096
Subkey-Type: RSA
Subkey-Length: 4096
Name-Real: ACME IoT Security Team
Name-Email: security@acme-iot.com
Expire-Date: 2y
%commit
EOF

# Export the public key for the security.txt encryption field
gpg --armor --export security@acme-iot.com > pgp-key.asc

# Test encryption/decryption
echo "CVE-2026-1234 details" | gpg --armor --encrypt --recipient security@acme-iot.com > encrypted.asc
gpg --decrypt encrypted.asc  # Should output original message
```

### 3. Minimal CVE response checklist (Markdown, stored in your repo)

```markdown
# CVE Response Checklist v1.0

## Phase 1: Receipt (0-4 hours)
- [ ] Acknowledge receipt to reporter (template: `ack_email.md`)
- [ ] Assign CVE ID via MITRE or your CNA (if applicable)
- [ ] Create private GitHub issue with label `security/vulnerability`

## Phase 2: Triage (4-48 hours)
- [ ] Determine CVSS v3.1 score (use `cvss-calculator` CLI)
- [ ] Identify affected firmware versions (check `git tag --list`)
- [ ] Determine if exploit requires physical access or network
- [ ] Notify downstream integrators via encrypted email (list in `INTEGRATORS.md`)

## Phase 3: Patch (1-14 days, depending on CVSS)
- [ ] Create private branch `fix/CVE-2026-XXXX`
- [ ] Write unit test reproducing the vulnerability
- [ ] Apply fix, run full CI pipeline
- [ ] Generate signed firmware update (e.g., `imgtool sign --key priv.pem`)
- [ ] Test OTA update on staging hardware

## Phase 4: Coordination (48 hours before public)
- [ ] Send pre-disclosure draft to reporter (CC: MITRE if applicable)
- [ ] Update CVE entry with affected versions and fix commit hash
- [ ] Prepare public advisory (template: `advisory_template.md`)

## Phase 5: Publication (Day 0)
- [ ] Push advisory to website and mailing list
- [ ] Tag release `v2.3.1-CVE-2026-XXXX`
- [ ] Update `security.txt` expiry if needed
```

### 4. Automating CVE ID assignment with MITRE's API

```bash
# Requires CNA privileges; example using curl
curl -X POST https://cve.mitre.org/cve/cna/vulnerabilities \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${CVE_API_TOKEN}" \
  -d '{
    "product": "ACME IoT Gateway",
    "version": "2.3.0",
    "vulnerabilityName": "Buffer overflow in MQTT parser",
    "description": "A stack-based buffer overflow in the MQTT topic parser allows remote code execution.",
    "problemType": "CWE-121",
    "cvssScore": 9.8,
    "cvssVector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
  }'
```

## Common Pitfalls & Gotchas

1. **Using a shared email alias without PGP**: If `security@` forwards to a shared mailbox that anyone can read, you've broken confidentiality. Always encrypt initial communication. Set up auto-forwarding to a dedicated mailbox that only the security lead can decrypt.

2. **Forgetting to update `security.txt` expiry**: The `Expires` field must be refreshed annually. I've seen products with expired `security.txt` files that researchers treat as "no policy" — they go straight to public disclosure. Set a calendar reminder 30 days before expiry.

3. **Patching silently without a CVE**: Some firmware vendors fix vulnerabilities in the next release without assigning a CVE ID. This breaks downstream SBOM (Software Bill of Materials) tracking. If you fix a security bug, assign a CVE — even if you don't publish a full advisory. Your customers' compliance tools depend on it.

## Try It Yourself

1. **Generate a `security.txt` file** for a fictional firmware product (e.g., "Smart Thermostat v4"). Validate it with the `securitytxt` CLI tool. Ensure the `Expires` date is exactly one year from today.

2. **Simulate a full CVE response cycle**: Create a private GitHub repo, add the checklist above as `CVE_RESPONSE.md`, and walk through a mock vulnerability (e.g., "hardcoded SSH key in v1.0.0"). Time each phase — aim for under 48 hours total.

3. **Automate PGP key rotation**: Write a shell script that generates a new PGP key, updates `pgp-key.asc` in your repo, and commits the change. Add a cron job to run it every 18 months (6 months before key expiry).

## Next Up

Tomorrow: **Penetration Testing Embedded Devices: Tools & Methodology** — we'll break out the JTAGulator, Shikra, and firmware analysis toolchains to find the vulnerabilities before the researchers do.
