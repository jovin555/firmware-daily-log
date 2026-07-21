---
title: "Day 21: Chaos Engineering for Firmware Release Pipelines"
date: 2026-07-21
tags: ["til", "embedded-cicd", "chaos-engineering"]
---

## What I Explored Today

Today I injected controlled failures into our firmware release pipeline to validate that our CI/CD system degrades gracefully, not just when everything works perfectly. Chaos engineering—pioneered by Netflix for distributed systems—applies directly to embedded release pipelines: network partitions between build agents and artifact repositories, disk-full scenarios on runners, corrupted firmware images mid-transfer, and simulated OTA server failures. I built a small chaos toolkit using shell scripts and pytest fixtures that systematically disrupts pipeline stages while monitoring recovery behavior.

## The Core Concept

Most firmware release pipelines are tested only in the "happy path." Build succeeds → tests pass → artifact published → OTA update delivered. But real-world failures happen: a build agent runs out of disk space during a 4GB firmware image compilation, an artifact repository returns 503 errors during upload, or a network partition drops the connection between CI and the firmware signing server.

Chaos engineering for release pipelines means intentionally injecting these failures in a controlled, observable way to answer: *Does the pipeline detect the failure? Does it retry correctly? Does it leave the system in a consistent state?* For embedded systems, the stakes are higher—a corrupted firmware image that passes through a non-resilient pipeline could brick devices in the field.

The key insight: you don't chaos-test the firmware itself (that's destructive testing). You chaos-test the *pipeline infrastructure*—the build, test, signing, and deployment machinery. The goal is to prove your CI/CD system has proper circuit breakers, retry logic with exponential backoff, idempotent artifact handling, and clean failure rollbacks.

## Key Commands / Configuration / Code

### 1. Chaos Injection via Shell (disk-full simulation)

```bash
#!/bin/bash
# chaos_inject.sh — Simulate disk-full on a CI build agent
# Run this on the build agent before a firmware compilation job

TARGET_DIR="/var/lib/build-agent/workspace"
FILL_SIZE_MB=500

echo "[CHAOS] Filling $TARGET_DIR with $FILL_SIZE_MB MB of garbage..."
dd if=/dev/zero of="$TARGET_DIR/.chaos_fill" bs=1M count=$FILL_SIZE_MB status=none

# Verify disk usage crosses threshold
USAGE_PCT=$(df "$TARGET_DIR" | tail -1 | awk '{print $5}' | sed 's/%//')
echo "[CHAOS] Disk usage now at ${USAGE_PCT}%"

# Cleanup function — MUST run after test
cleanup_chaos() {
    echo "[CHAOS] Cleaning up..."
    rm -f "$TARGET_DIR/.chaos_fill"
}
trap cleanup_chaos EXIT

# Let the CI job proceed — it will fail on write
# The pipeline must handle this gracefully
```

### 2. Network Partition Chaos (using iptables)

```yaml
# .gitlab-ci-chaos.yml — Chaos stage that drops packets to artifact server
chaos-network-partition:
  stage: chaos
  script:
    # Block all traffic to artifact server on port 443
    - iptables -A OUTPUT -d artifacts.internal.io -p tcp --dport 443 -j DROP
    - echo "[CHAOS] Network partition active — artifact server unreachable"
    
    # Trigger the actual upload job (defined elsewhere)
    - curl --fail -X POST "${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/jobs/${CI_JOB_ID}/play"
    
    # Wait for job to attempt upload and fail/retry
    - sleep 30
    
    # Remove the block — simulate recovery
    - iptables -D OUTPUT -d artifacts.internal.io -p tcp --dport 443 -j DROP
    - echo "[CHAOS] Network restored"
  rules:
    - if: '$CI_COMMIT_BRANCH == "chaos-testing"'
```

### 3. Pytest Fixture for Corrupted Firmware Injection

```python
# tests/chaos/test_artifact_corruption.py
import pytest
import hashlib
import struct

@pytest.fixture
def corrupt_firmware(tmp_path):
    """Generate a valid-looking firmware image with corrupted payload."""
    # Create a minimal valid firmware header + payload
    fw_path = tmp_path / "firmware.bin"
    header = struct.pack('<II', 0xDEADBEEF, 1024)  # magic, size
    payload = b'\x00' * 1024
    checksum = hashlib.sha256(payload).digest()
    
    with open(fw_path, 'wb') as f:
        f.write(header + payload + checksum)
    
    # Corrupt byte 500 in the payload
    with open(fw_path, 'r+b') as f:
        f.seek(500)
        f.write(b'\xFF')
    
    return fw_path

def test_pipeline_rejects_corrupt_artifact(corrupt_firmware):
    """Verify the release pipeline rejects a corrupted firmware image."""
    # Simulate CI uploading this artifact
    result = subprocess.run(
        ["firmware-signer", "verify", str(corrupt_firmware)],
        capture_output=True,
        text=True
    )
    assert result.returncode != 0
    assert "checksum mismatch" in result.stderr.lower()
```

### 4. Chaos Monitoring with Prometheus Metrics

```yaml
# docker-compose.chaos.yml — Monitor pipeline health during chaos
version: '3.8'
services:
  chaos-monitor:
    image: prom/prometheus:v2.45.0
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--web.enable-lifecycle'
    ports:
      - "9090:9090"

  # Export key pipeline metrics
  pipeline-exporter:
    build: ./exporters
    environment:
      - CI_SERVER_URL=https://gitlab.internal.io
      - CI_ACCESS_TOKEN=${CHAOS_CI_TOKEN}
    ports:
      - "8000:8000"
```

## Common Pitfalls & Gotchas

1. **Chaos cleanup failures**: The most common mistake is leaving the system in a broken state after chaos tests. Always use `trap` (bash) or `finally` blocks (Python) to restore network rules, delete fill files, and reset configurations. I once forgot to remove an iptables rule and blocked all production artifact uploads for 20 minutes.

2. **Testing chaos on production pipelines**: Never run chaos experiments against pipelines that deploy to production devices. Use a dedicated `chaos-testing` branch or GitLab environment with `rules:if` conditions. The chaos branch should mirror production infrastructure but point to staging artifact repositories and OTA servers.

3. **Ignoring idempotency in retry logic**: Many pipelines retry failed jobs but don't clean up partial artifacts. If a firmware upload fails after writing 50% of the image, the retry might append to the partial file, creating a corrupted artifact. Test this explicitly: inject a failure mid-upload, then verify the retry starts from scratch.

## Try It Yourself

1. **Disk-full chaos**: On a CI build agent, fill 90% of the disk using `dd`, then trigger a firmware compilation job. Verify the pipeline fails with a clear "disk space" error, not a cryptic compiler crash. Implement a pre-build check that halts with a descriptive message when disk usage exceeds 85%.

2. **Network partition test**: Write a GitLab CI job (or GitHub Actions step) that uses `iptables` to block traffic to your artifact repository for 60 seconds. Run a firmware upload job during that window. Confirm the pipeline retries with exponential backoff (1s, 2s, 4s...) and eventually succeeds when the network is restored.

3. **Corrupted artifact injection**: Create a pytest fixture that generates a firmware image with a single byte flipped in the payload. Add a pipeline stage that runs `firmware-signer verify` on every artifact before signing. Verify the stage fails and prevents the corrupted image from reaching the OTA server.

## Next Up

Tomorrow: **Compliance Artifacts: Auto-Generating Traceability from CI Runs** — We'll build a system that extracts SBOMs, test results, and signing certificates from every pipeline run and assembles them into a compliance-ready PDF, complete with cryptographic hashes and timestamps for audit trails.
