---
title: "Day 23: Case Study: Building a Zero-Touch Pipeline from Commit to Field"
date: 2026-07-23
tags: ["til", "embedded-cicd", "case-study"]
---

## What I Explored Today

Today I walked through a real production pipeline for a battery management system (BMS) controller that ships to 10,000+ field units annually. The team needed a zero-touch release: developer commits to `main`, and within 90 minutes, signed firmware images are available on the OTA server, with a bill of materials (SBOM) and test artifacts archived. I traced the pipeline from the developer’s `git push` through build, hardware-in-the-loop (HIL) validation, signing, and deployment. The key insight: every step is gated by cryptographic attestation, not human judgment.

## The Core Concept

A zero-touch pipeline means no engineer presses a button to release. The pipeline itself decides, based on policy, whether a commit is safe to ship. For embedded systems, this is harder than for cloud services because you cannot hot-patch a bricked device in the field. The pipeline must prove:

1. **Build reproducibility** — the binary matches what was tested.
2. **HIL pass rate** — every test case passed on real hardware.
3. **Signing integrity** — the binary is signed by a hardware security module (HSM), not a developer’s laptop.
4. **Artifact traceability** — every component’s version is recorded in a signed SBOM.

The pipeline I studied uses GitLab CI with a custom runner on a dedicated build server (no shared runners for security). The HSM is a YubiHSM 2 connected via USB to the build server. The HIL rack is a separate machine that the pipeline triggers via a REST API.

## Key Commands / Configuration / Code

### 1. Pipeline Trigger (GitLab CI `.gitlab-ci.yml` excerpt)

```yaml
# Only run on main branch, never on MRs
release:
  stage: deploy
  only:
    - main
  variables:
    # Force rebuild even if cache exists
    GIT_STRATEGY: clone
  script:
    - ./ci/build.sh
    - ./ci/test.sh
    - ./ci/sign.sh
    - ./ci/archive.sh
  artifacts:
    paths:
      - firmware.bin.signed
      - firmware.bin.sig
      - sbom.json
    expire_in: 1 year
```

### 2. Build Script (`ci/build.sh`) — Reproducible Build

```bash
#!/bin/bash
set -euo pipefail

# Use fixed toolchain version from Docker image
TOOLCHAIN="gcc-arm-none-eabi-10.3-2021.10"
BUILD_DIR="build_$(git rev-parse --short HEAD)"

# Clean build to ensure reproducibility
rm -rf "$BUILD_DIR"
mkdir "$BUILD_DIR"

# Build with hash of source tree as build ID
cmake -S . -B "$BUILD_DIR" \
  -DCMAKE_TOOLCHAIN_FILE=toolchain.cmake \
  -DBUILD_ID="$(git rev-parse HEAD)" \
  -DCMAKE_BUILD_TYPE=Release

cmake --build "$BUILD_DIR" -- -j$(nproc)

# Verify build hash matches source tree hash
BUILD_HASH=$(sha256sum "$BUILD_DIR/firmware.bin" | cut -d' ' -f1)
SOURCE_HASH=$(git rev-parse HEAD)
echo "Build hash: $BUILD_HASH, Source hash: $SOURCE_HASH"
# Store for later attestation
echo "$BUILD_HASH" > build_hash.txt
```

### 3. HIL Trigger Script (`ci/test.sh`) — Hardware-in-the-Loop

```bash
#!/bin/bash
set -euo pipefail

# HIL rack API endpoint
HIL_API="https://hil-rack-01.internal:8443/api/v1"
HIL_TOKEN=$(cat /etc/hil_token)

# Upload firmware to HIL rack
curl -s -X POST "$HIL_API/firmware" \
  -H "Authorization: Bearer $HIL_TOKEN" \
  -F "file=@build_$(git rev-parse --short HEAD)/firmware.bin"

# Start test suite (returns test run ID)
TEST_RUN_ID=$(curl -s -X POST "$HIL_API/test-run" \
  -H "Authorization: Bearer $HIL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"suite": "full_regression", "timeout_sec": 600}' | jq -r '.id')

# Poll for results (max 15 minutes)
for i in $(seq 1 90); do
  STATUS=$(curl -s "$HIL_API/test-run/$TEST_RUN_ID" \
    -H "Authorization: Bearer $HIL_TOKEN" | jq -r '.status')
  if [ "$STATUS" = "passed" ]; then
    echo "HIL tests passed"
    exit 0
  elif [ "$STATUS" = "failed" ]; then
    echo "HIL tests failed"
    exit 1
  fi
  sleep 10
done

echo "HIL tests timed out"
exit 1
```

### 4. Signing Script (`ci/sign.sh`) — HSM-Based Signing

```bash
#!/bin/bash
set -euo pipefail

# YubiHSM 2 configuration
HSM_SLOT=0
HSM_KEY_ID=0x1234
FIRMWARE="build_$(git rev-parse --short HEAD)/firmware.bin"

# Sign with HSM (requires yubihsm-shell)
yubihsm-shell --slot $HSM_SLOT \
  --action sign-ecdsa \
  --in $FIRMWARE \
  --out $FIRMWARE.sig \
  --key-id $HSM_KEY_ID \
  --algorithm ecp256

# Append signature to firmware for field verification
cat $FIRMWARE.sig >> $FIRMWARE.signed
echo "Signed firmware: $FIRMWARE.signed"
```

### 5. SBOM Generation (`ci/archive.sh`)

```bash
#!/bin/bash
set -euo pipefail

# Generate CycloneDX SBOM using cve-bin-tool
python3 -m cve_bin_tool.cli \
  --sbom cyclonedx \
  --output sbom.json \
  --sbom-output-format json \
  --sbom-package-name "bms-firmware" \
  --sbom-package-version "$(git describe --tags --always)" \
  build_$(git rev-parse --short HEAD)/

# Sign the SBOM with the same HSM key
yubihsm-shell --slot $HSM_SLOT \
  --action sign-ecdsa \
  --in sbom.json \
  --out sbom.json.sig \
  --key-id $HSM_KEY_ID \
  --algorithm ecp256

# Upload to artifact server
curl -s -X PUT "https://artifacts.internal/firmware/$(git rev-parse HEAD)/" \
  -F "firmware=@build_*/firmware.bin.signed" \
  -F "signature=@build_*/firmware.bin.sig" \
  -F "sbom=@sbom.json" \
  -F "sbom_sig=@sbom.json.sig" \
  -F "build_hash=@build_hash.txt"
```

## Common Pitfalls & Gotchas

### 1. HSM Timeout During Signing
The YubiHSM 2 has a 5-second inactivity timeout. If your CI runner takes too long between HSM commands, the session drops. **Fix**: Use `yubihsm-shell --session-timeout 120` to extend the session lifetime, or re-authenticate before each sign operation.

### 2. HIL Rack Network Partitions
The HIL rack runs on a separate VLAN. If the CI runner’s network changes (e.g., VPN disconnect), the curl to the HIL API fails silently. **Fix**: Add a retry loop with exponential backoff and a health-check endpoint (`GET /api/v1/health`) before uploading firmware.

### 3. Build Reproducibility Drift
Even with a fixed Docker image, `cmake` can pull in system libraries if `find_package` is used without a locked conan or vcpkg manifest. **Fix**: Use a `conanfile.txt` with pinned versions for all dependencies, and run `conan install` inside the CI script to ensure no system-level resolution.

## Try It Yourself

1. **Set up a local HSM simulation**: Use `yubihsm-sim` (part of the YubiHSM SDK) to create a virtual HSM. Write a script that signs a test binary and verifies the signature with OpenSSL. This will expose the session timeout issue immediately.

2. **Add a build hash attestation step**: Modify your existing CMake build to embed the Git commit hash as a `#define BUILD_ID` in the firmware. Then, in your CI, compute the SHA256 of the binary and compare it to the expected hash from the source tree. Fail the pipeline if they don’t match.

3. **Create a mock HIL API**: Write a simple Python Flask server that accepts firmware uploads and returns a test result after a random delay (simulating real HIL). Wire your CI to call this mock instead of the real rack. This lets you test the polling loop and timeout logic without hardware.

## Next Up

Tomorrow is **Day 24: Full Review & Project: Release Engineering for a Multi-Board Product Line**. We’ll take everything from the past 23 days and apply it to a real-world scenario: a product line with three boards (sensor node, gateway, and cloud bridge) that share a common HAL but have different signing keys, OTA channels, and test matrices. You’ll design a unified pipeline that handles all three without duplicating code.
