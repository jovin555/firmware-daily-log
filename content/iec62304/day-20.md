---
title: "Day 20: Software Release: Notes, Version Labels & Archiving"
date: 2026-07-02
tags: ["til", "iec62304", "release", "versioning"]
---

## What I Explored Today

Today I dug into the release management requirements of IEC 62304 Clause 8 — specifically how to formally ship a software unit or SOUP update to manufacturing or the field. The standard demands that every release includes a unique identifier, a complete release note, and an archive that can be reproduced exactly years later. I spent the morning auditing our current release pipeline against these requirements and realized we were missing several critical artifacts: no signed manifest, no reproducible build record, and release notes that were just Jira ticket dumps. Here’s what I learned about doing it right.

## The Core Concept

IEC 62304 treats a software release as a legal and regulatory handoff. The moment you label something “RELEASE-1.2.3”, you are asserting that this specific binary has passed all verification activities, that its known anomalies are documented, and that it can be exactly reconstructed if a field failure occurs five years from now. The standard doesn’t care about your CI/CD pipeline’s elegance — it cares about traceability and reproducibility.

Three pillars support a compliant release:

1. **Unique Version Label** — Every release must have a globally unique identifier that ties back to the software item’s configuration management system. Semantic versioning (MAJOR.MINOR.PATCH) is common, but the label must also include a build timestamp or commit hash to prevent ambiguity.

2. **Release Notes** — These are not changelogs. IEC 62304 requires that release notes document: the list of software items included, the results of all verification activities, known residual anomalies (bugs you shipped with), and any special installation or configuration instructions. If you shipped with a known bug, you must say so explicitly.

3. **Archiving** — You must preserve the exact source code, build environment, toolchain versions, build scripts, and all configuration files needed to reproduce the binary. This means freezing your compiler, your OS SDK, and even your CI server’s OS image. A Docker image of the build environment is the modern gold standard.

## Key Commands / Configuration / Code

Here’s a practical release workflow using Git, Docker, and a signed manifest.

### 1. Tag the release with a unique, signed label

```bash
# Create an annotated, signed tag that includes the release candidate hash
git tag -s v1.2.3 -m "Release v1.2.3 — based on commit abc1234"
git push origin v1.2.3

# Verify the tag signature
git tag -v v1.2.3
# Output: gpg: Signature made ... using RSA key ID DEADBEEF
# Output: gpg: Good signature from "Release Engineer <releases@meddev.com>"
```

### 2. Build inside a frozen environment (Docker)

```dockerfile
# Dockerfile.release — pinned to exact toolchain versions
FROM ubuntu:20.04@sha256:abc123...  # pin by digest, not tag
RUN apt-get update && apt-get install -y \
    gcc-arm-none-eabi=9-2019-q4-major \
    cmake=3.16.3-1ubuntu1 \
    python3=3.8.10-0ubuntu1~20.04
COPY . /src
WORKDIR /src/build
RUN cmake .. -DCMAKE_BUILD_TYPE=Release && make
```

```bash
# Build the release binary inside the frozen container
docker build -t meddev-build-env:v1.2.3 -f Dockerfile.release .
docker run --rm -v $(pwd)/output:/output meddev-build-env:v1.2.3 \
    cp /src/build/firmware.bin /output/
```

### 3. Generate a signed release manifest

```bash
# Create a manifest with SHA-256 hashes of every artifact
sha256sum firmware.bin > release-v1.2.3.sha256
sha256sum bootloader.bin >> release-v1.2.3.sha256
sha256sum release-notes-v1.2.3.pdf >> release-v1.2.3.sha256

# Sign the manifest with your release key
gpg --detach-sign --armor release-v1.2.3.sha256
# Produces: release-v1.2.3.sha256.asc
```

### 4. Archive everything for reproducibility

```bash
# Archive the exact source tree at the tag
git archive --format=tar.gz -o source-v1.2.3.tar.gz v1.2.3

# Archive the build environment (Docker image)
docker save meddev-build-env:v1.2.3 | gzip > build-env-v1.2.3.tar.gz

# Archive the CI pipeline definition (e.g., Jenkinsfile or GitHub Actions YAML)
cp .github/workflows/release.yml release-pipeline-v1.2.3.yml

# Store in immutable object storage with retention policy
aws s3 cp ./release-artifacts/ s3://meddev-releases/v1.2.3/ --recursive \
    --storage-class GLACIER_IR
```

### 5. Release notes template (minimal compliant)

```markdown
# Release Notes — v1.2.3
**Date:** 2026-07-02
**Software Item:** Infusion Pump Firmware (SW-001)
**Based on Commit:** abc1234def5678

## Included Software Items
- Firmware binary: firmware.bin (SHA256: a1b2c3...)
- Bootloader: bootloader.bin (SHA256: d4e5f6...)
- SOUP: FreeRTOS v10.4.3 (unmodified)

## Verification Results
- Unit tests: 142/142 passed
- Integration tests: 38/38 passed
- System tests: 12/12 passed
- Static analysis: 0 critical, 3 minor warnings (waived per SOP-007)

## Known Anomalies
- ANOM-0042: LCD backlight flickers on battery <10% (severity: minor, no patient impact)
- ANOM-0051: Log timestamps drift by ~2 seconds after 72h uptime (severity: minor)

## Installation Instructions
1. Verify firmware.bin SHA-256 against release manifest
2. Flash via JTAG at address 0x08000000
3. Perform power-on self-test (POST) per SOP-012
```

## Common Pitfalls & Gotchas

**1. Tagging the wrong commit.** I’ve seen teams tag a release after hotfixes were already merged to main, but the tag pointed to an older commit. Always tag the exact commit that produced the verified binary. Use `git tag -a` (annotated) and push the tag separately — never move a tag after it’s pushed.

**2. Forgetting to archive the build environment.** Your source code is useless if you can’t compile it. I once had to rebuild a two-year-old release and discovered the compiler was no longer available from the vendor. Now I archive the entire Docker image and the base OS image digest. Bonus: also archive the exact `apt` sources list.

**3. Release notes that omit known anomalies.** IEC 62304 auditors will ask: “Did you ship with any unresolved bugs?” If your release notes are silent, they assume you hid something. Be explicit. Even a minor cosmetic bug must be documented with a risk assessment showing why it’s acceptable to ship.

## Try It Yourself

1. **Audit your last release.** Find the tag, the commit it points to, and the build environment. Can you reproduce the exact binary today? If not, identify what’s missing and create a Dockerfile that freezes the toolchain.

2. **Write a compliant release note** for your current development branch. Include a “Known Anomalies” section even if it’s empty. Practice the format: software items, verification results, known anomalies, installation instructions.

3. **Implement a signed manifest pipeline.** Add a step to your CI that generates SHA-256 hashes of all release artifacts and GPG-signs the manifest. Store the public key in your repository and document the verification procedure in your release SOP.

## Next Up

Tomorrow we pivot to a critical adjacent standard: **Cybersecurity for Medical Devices: IEC 81001-5-1**. This is the framework that overlays IEC 62304 with security risk management, threat modeling, and secure coding requirements. If you thought release management was paperwork-heavy, wait until you see the security artifacts required for a connected insulin pump. See you then.
