---
title: "Day 22: Compliance: EU Cyber Resilience Act Update Requirements"
date: 2026-07-22
tags: ["til", "secure-ota", "cra", "compliance"]
---

## What I Explored Today

Today I mapped the EU Cyber Resilience Act (CRA) update requirements against our existing OTA pipeline. The CRA mandates that all connected devices with digital elements must support secure update mechanisms, with specific timelines for vulnerability patching and mandatory update transparency. I focused on the practical engineering implications: what the CRA actually requires from an OTA implementation, not just the legal text. The key takeaway is that the CRA treats update capability as a security baseline, not a feature—and non-compliance means your product cannot be sold in the EU after the enforcement date (expected late 2027 for most products).

## The Core Concept

The CRA (Regulation (EU) 2024/2847) introduces three update-related obligations that directly impact OTA architecture:

1. **Security-by-design updates**: Updates must be delivered securely, with integrity verification and authenticity checks. This is not optional—the regulation explicitly requires cryptographic signing and verification of every update payload.

2. **Minimum support period**: For consumer IoT devices, the manufacturer must provide security updates for at least 5 years from the date of placing the product on the market. For industrial/medical devices, this extends to 10 years. Your OTA infrastructure must remain operational and secure for the entire support window.

3. **Update transparency**: The CRA requires that users be notified of available security updates, and that manufacturers maintain a Software Bill of Materials (SBOM) that is updated with each release. The SBOM must be available to regulators on request.

The "why" is straightforward: the EU learned from years of unpatched IoT botnets (Mirai, Mozi) that voluntary update mechanisms fail. The CRA makes secure, timely updates a legal requirement. For engineers, this means your OTA system must be designed for longevity—you cannot rely on a third-party update server that might go offline in 3 years.

## Key Commands / Configuration / Code

### 1. SBOM Generation with CycloneDX (Required for CRA compliance)

```bash
# Generate SPDX 2.3 SBOM for a Yocto-based embedded Linux build
# CycloneDX is the recommended format by EU cybersecurity agency (ENISA)
cd /build/tmp/deploy/images/arm64/
cyclonedx-bom -o sbom_ota_update_v2.3.spdx.json \
  --format spdx \
  --include-all-dependencies \
  --output-reproducible

# Verify SBOM includes all OTA-related components
cat sbom_ota_update_v2.3.spdx.json | jq '.packages[] | select(.name | test("swupdate|rauc|mender|ostree"))'
```

### 2. CRA-Compliant Update Manifest with Mandatory Fields

```json
{
  "manifest_version": 2,
  "product_id": "com.example.iot-gateway-v3",
  "firmware_version": "3.2.1",
  "security_patch_level": "2026-07-15",
  "cve_fixes": [
    "CVE-2026-1234: Buffer overflow in network stack",
    "CVE-2026-5678: Improper certificate validation"
  ],
  "signature_algorithm": "ECDSA-P256",
  "signature": "3045022100...",
  "sbom_url": "https://ota.example.com/sbom/v3.2.1.spdx.json",
  "mandatory_update": true,
  "support_end_date": "2031-07-22"
}
```

### 3. Update Server Endpoint with CRA-Mandated Transparency

```python
# FastAPI endpoint for CRA-compliant update check
# Must return update availability and support status
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import hashlib, time

app = FastAPI()

class UpdateCheckRequest(BaseModel):
    device_id: str
    current_version: str
    hw_revision: str

class UpdateResponse(BaseModel):
    update_available: bool
    latest_version: str
    update_url: str | None = None
    security_patch_level: str
    support_expired: bool
    support_expiry_date: str

@app.post("/api/v2/check-update", response_model=UpdateResponse)
async def check_update(req: UpdateCheckRequest):
    # CRA requires checking if device is still in support window
    support_end = datetime(2031, 7, 22)
    if datetime.now() > support_end:
        return UpdateResponse(
            update_available=False,
            latest_version=req.current_version,
            security_patch_level="N/A",
            support_expired=True,
            support_expiry_date=support_end.isoformat()
        )
    
    # Normal update logic with CRA-required metadata
    latest = get_latest_firmware(req.hw_revision)
    if latest.version > req.current_version:
        return UpdateResponse(
            update_available=True,
            latest_version=latest.version,
            update_url=f"https://ota.example.com/firmware/{latest.filename}",
            security_patch_level=latest.security_patch_date,
            support_expired=False,
            support_expiry_date=support_end.isoformat()
        )
    # ... fallback
```

## Common Pitfalls & Gotchas

**1. Assuming "5 years support" means 5 years from now.**
The CRA counts from the date the *product* is placed on the market, not from when you write the code. If your device ships in 2027, you must support updates until at least 2032. Plan your OTA infrastructure (servers, signing keys, certificate chains) for that full window. A common mistake is using short-lived TLS certificates (90 days) for the update server—you'll be rotating them 20+ times during support.

**2. Forgetting that SBOMs must be updated with every security patch.**
Many teams generate one SBOM at release and forget it. The CRA requires the SBOM to reflect the exact set of components in each update. If you backport a CVE fix to a library, the SBOM must change. Automate this in your CI/CD pipeline—manual SBOM updates will fail an audit.

**3. Treating "mandatory update" as a user preference.**
The CRA allows manufacturers to mark certain updates as mandatory (critical security fixes). Your OTA client must enforce these—no user opt-out. If your device has a "skip update" button that works on security patches, you're non-compliant. Implement a separate update class for security patches that cannot be deferred.

## Try It Yourself

1. **Audit your current update manifest**: Add the `security_patch_level`, `cve_fixes`, and `support_end_date` fields. Generate a test manifest and verify your OTA client parses and validates these new fields.

2. **Generate an SBOM for your firmware build**: Use `cyclonedx-bom` or `syft` to create a SPDX 2.3 SBOM. Then write a script that compares the SBOM between two firmware versions and reports changed dependencies—this is what regulators will ask for.

3. **Implement a support-window check**: Add logic to your OTA update server that returns a `support_expired: true` flag when the device's support window has passed. Test that your client refuses to install non-security updates after this date, but still allows critical security patches (CRA allows this exception).

## Next Up

Tomorrow: **Testing OTA Pipelines: Fault Injection & Power-Loss Simulation** — we'll build a fault injection framework that simulates network drops, corrupted payloads, and power failures mid-update, then verify your device recovers correctly.
