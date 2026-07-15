---
title: "Day 15: Canary & Staged Deployment Pipelines for Firmware"
date: 2026-07-15
tags: ["til", "embedded-cicd", "canary", "staged-deployment"]
---

## What I Explored Today

Today I tackled the problem of rolling out firmware updates without bricking a fleet. The answer is a staged deployment pipeline—specifically a canary release strategy adapted for embedded systems. I built a pipeline that pushes firmware to 1% of devices, monitors telemetry for 24 hours, then ramps to 10%, 50%, and finally 100%. The key insight: embedded canary deployments aren't about traffic splitting (you can't route HTTP to a microcontroller), but about *device cohort selection* and *rollback automation*.

## The Core Concept

In web apps, canary deployments route a percentage of live traffic to a new version. For firmware, the equivalent is selecting a subset of devices by hardware revision, geographic region, or device ID hash, then pushing the update only to that cohort. The "why" is brutal: a bad firmware release can brick devices in the field, requiring physical recovery or expensive recalls. Staged deployment mitigates this by limiting blast radius.

The pipeline has three stages:
1. **Ring 0 (Canary)**: 1-5% of devices, often internal or beta testers
2. **Ring 1 (Staged)**: 10-50% of devices, with automated health checks
3. **Ring 2 (Production)**: 100% rollout, gated by success metrics

Each stage requires a *rollback trigger*—a metric threshold (e.g., crash rate > 0.1%, connection failures > 2%) that automatically reverts the cohort to the previous firmware version.

## Key Commands / Configuration / Code

Here's a practical implementation using GitHub Actions and a device management API (simulated with curl). The device cohort is selected by a modulo of the device's unique ID.

```yaml
# .github/workflows/canary-firmware-deploy.yml
name: Canary Firmware Deploy

on:
  workflow_dispatch:
    inputs:
      firmware_version:
        description: 'Firmware version tag (e.g., v2.1.0)'
        required: true
      canary_percent:
        description: 'Canary percentage (1-100)'
        default: '1'

jobs:
  canary:
    runs-on: ubuntu-latest
    steps:
      - name: Select canary cohort
        id: cohort
        run: |
          # Use device ID modulo to select 1% of devices
          # Assumes device IDs are integers 1..10000
          echo "canary_ids=$(seq 1 10000 | awk 'NR % 100 == 0' | tr '\n' ',')" >> $GITHUB_OUTPUT

      - name: Push firmware to canary devices
        run: |
          IFS=',' read -ra DEVICES <<< "${{ steps.cohort.outputs.canary_ids }}"
          for device_id in "${DEVICES[@]}"; do
            # Simulated OTA push via device management API
            curl -X POST "https://ota.example.com/devices/${device_id}/update" \
              -H "Authorization: Bearer ${{ secrets.OTA_TOKEN }}" \
              -d "firmware_version=${{ github.event.inputs.firmware_version }}"
          done

      - name: Monitor canary health (24h wait)
        run: |
          echo "Monitoring canary devices for 24 hours..."
          # In production, this would poll a metrics endpoint
          sleep 86400  # 24 hours

      - name: Check canary health
        id: health
        run: |
          # Simulated health check: query crash rate
          CRASH_RATE=$(curl -s "https://metrics.example.com/crash-rate?cohort=canary" | jq '.rate')
          if (( $(echo "$CRASH_RATE > 0.001" | bc -l) )); then
            echo "status=failed" >> $GITHUB_OUTPUT
            echo "CRASH_RATE=$CRASH_RATE" >> $GITHUB_ENV
          else
            echo "status=passed" >> $GITHUB_OUTPUT
          fi

      - name: Rollback if canary fails
        if: steps.health.outputs.status == 'failed'
        run: |
          echo "Canary failed (crash rate $CRASH_RATE). Rolling back..."
          IFS=',' read -ra DEVICES <<< "${{ steps.cohort.outputs.canary_ids }}"
          for device_id in "${DEVICES[@]}"; do
            # Rollback to previous firmware version
            curl -X POST "https://ota.example.com/devices/${device_id}/rollback" \
              -H "Authorization: Bearer ${{ secrets.OTA_TOKEN }}"
          done
          exit 1

  stage-10:
    needs: canary
    if: success()
    runs-on: ubuntu-latest
    steps:
      - name: Select 10% cohort
        run: |
          echo "stage_ids=$(seq 1 10000 | awk 'NR % 10 == 0' | tr '\n' ',')" >> $GITHUB_OUTPUT
      # ... (similar push, monitor, rollback pattern)
```

For device-side rollback, the firmware must store two bootable images (A/B update scheme). Here's the critical bootloader logic:

```c
// bootloader.c - A/B slot selection with rollback counter
#define MAX_ROLLBACK_ATTEMPTS 3

typedef struct {
    uint8_t active_slot;      // 0 or 1
    uint8_t rollback_count;
    uint32_t firmware_crc;
} BootConfig;

void select_boot_slot(void) {
    BootConfig *cfg = (BootConfig*)BOOT_CONFIG_ADDR;
    
    // If current slot fails to boot (watchdog reset), increment rollback
    if (detect_watchdog_reset()) {
        cfg->rollback_count++;
        if (cfg->rollback_count >= MAX_ROLLBACK_ATTEMPTS) {
            // Switch to other slot
            cfg->active_slot ^= 1;
            cfg->rollback_count = 0;
            save_boot_config(cfg);
        }
    }
    
    // Boot from active slot
    jump_to_slot(cfg->active_slot);
}
```

## Common Pitfalls & Gotchas

1. **Cohort selection bias**: If you select devices by device ID modulo, ensure the IDs are uniformly distributed. A common mistake: using device IDs that are sequential by manufacturing date, which can select all devices from the same production batch. Instead, hash the device ID with a cryptographic hash and take modulo—this gives a uniform distribution regardless of ID assignment.

2. **Rollback without A/B slots**: If your device only has one firmware image slot, rollback requires re-flashing the old image over the air. This is slow and risky (power loss during re-flash bricks the device). Always use dual-bank flash (A/B update) for any staged deployment. The cost of extra flash is trivial compared to a field bricking.

3. **Monitoring latency**: Embedded telemetry often reports on a 15-minute to 1-hour cycle (to save battery). A 24-hour canary window might not catch issues that manifest only after 48 hours. Extend your canary window based on your device's reporting interval. For battery-powered devices, consider a 72-hour canary.

## Try It Yourself

1. **Implement a device cohort selector**: Write a Python script that takes a list of device IDs (1-10000) and a percentage (e.g., 5%) and outputs the selected device IDs using a hash-based modulo (SHA256 of the device ID string). Verify the output is uniformly distributed across the ID range.

2. **Build a rollback trigger**: Extend the GitHub Actions workflow above to poll a Prometheus metrics endpoint (or simulated JSON file) every 5 minutes during the canary window. If the crash rate exceeds 0.5% for two consecutive polls, trigger an automatic rollback.

3. **Simulate an A/B update failure**: Write a C program that emulates a dual-bank bootloader. On boot, randomly simulate a watchdog reset with 10% probability. If the rollback counter exceeds 3, switch slots. Print the active slot and rollback count after each simulated boot. Run 100 iterations and verify the slot switches correctly.

## Next Up

Tomorrow: **Metrics & Dashboards: Tracking Build Health & Flaky Tests**. We'll wire up Prometheus and Grafana to monitor firmware build times, test pass rates, and device telemetry—then use that data to automatically flag flaky integration tests that waste CI hours.
