---
title: "Day 17: Rollback Pipelines: Automating Recovery from a Bad Release"
date: 2026-07-17
tags: ["til", "embedded-cicd", "rollback", "pipeline"]
---

## What I Explored Today

Today I dove into building automated rollback pipelines for embedded firmware releases. After a particularly painful incident last month where a bad CAN bus stack update bricked 12 field units and required a technician visit to each one, I decided we needed a systematic, automated way to reverse a deployment when things go sideways. I explored how to structure a rollback pipeline that reverts firmware, restores configuration parameters, and validates that the recovery actually worked—all without manual intervention.

## The Core Concept

In embedded systems, rollback isn't just "reinstall the old binary." You're dealing with bootloader constraints, persistent storage state migration, peripheral configuration drift, and often a two-stage update process. The core insight: a rollback pipeline must be a first-class citizen, designed and tested *before* the release pipeline ships the bad update.

Why automate this? Because when a release goes bad in the field, you're under maximum stress. The person on call is likely not the author of the firmware. Manual rollback procedures get skipped, commands get mistyped, and you end up with half-recovered devices. An automated rollback pipeline enforces a deterministic sequence: detect failure → trigger rollback → deploy previous artifact → restore saved state → run smoke tests → report success/failure.

The key architectural decision: your release pipeline must *always* save the previous firmware artifact and its configuration manifest as a tagged, immutable bundle. Without that, rollback is just hoping you have the right .hex file lying around.

## Key Commands / Configuration / Code

Here's a practical GitLab CI rollback pipeline structure. The critical piece is the `rollback` job that runs only when triggered manually or via a webhook from your monitoring system.

```yaml
# .gitlab-ci.yml - Rollback pipeline stage
stages:
  - rollback-prep
  - rollback-deploy
  - rollback-verify

variables:
  # Store the last known good release tag
  LAST_GOOD_RELEASE: ""
  # Device group to target (e.g., "prod-east", "prod-west")
  DEVICE_GROUP: ""

rollback:prepare:
  stage: rollback-prep
  script:
    # Fetch the previous release tag from the release registry
    - |
      LAST_GOOD=$(curl -s --header "PRIVATE-TOKEN: $CI_JOB_TOKEN" \
        "https://gitlab.com/api/v4/projects/$CI_PROJECT_ID/releases" \
        | jq -r '.[1].tag_name')  # index 1 = previous release
    - echo "LAST_GOOD_RELEASE=$LAST_GOOD" >> rollback.env
    # Download the firmware artifact and config manifest
    - |
      curl -L --header "PRIVATE-TOKEN: $CI_JOB_TOKEN" \
        "https://gitlab.com/api/v4/projects/$CI_PROJECT_ID/jobs/artifacts/$LAST_GOOD/download?job=build" \
        -o previous_firmware.zip
    - unzip previous_firmware.zip -d ./rollback_artifacts/
  artifacts:
    paths:
      - rollback_artifacts/
    reports:
      dotenv: rollback.env

rollback:deploy:
  stage: rollback-deploy
  needs: ["rollback:prepare"]
  script:
    # Step 1: Verify bootloader supports rollback
    - |
      if ! tool_bootloader_check --device-group $DEVICE_GROUP; then
        echo "Bootloader does not support rollback. Aborting."
        exit 1
      fi
    # Step 2: Save current configuration to non-volatile backup slot
    - tool_save_config --backup-slot 1 --device-group $DEVICE_GROUP
    # Step 3: Flash the previous firmware via OTA or JTAG
    - |
      tool_flash_firmware \
        --artifact ./rollback_artifacts/firmware.hex \
        --device-group $DEVICE_GROUP \
        --verify-after-write
    # Step 4: Restore configuration from backup slot
    - tool_restore_config --backup-slot 1 --device-group $DEVICE_GROUP
    # Step 5: Reboot devices into application mode
    - tool_reboot --device-group $DEVICE_GROUP --mode application
  environment:
    name: $DEVICE_GROUP
    action: rollback

rollback:verify:
  stage: rollback-verify
  needs: ["rollback:deploy"]
  script:
    # Run the same smoke tests as the original release pipeline
    - tool_run_smoke_tests --device-group $DEVICE_GROUP --timeout 120
    # Check that firmware version matches expected rollback version
    - |
      CURRENT_VERSION=$(tool_get_firmware_version --device-group $DEVICE_GROUP)
      EXPECTED_VERSION=$(cat ./rollback_artifacts/version.txt)
      if [ "$CURRENT_VERSION" != "$EXPECTED_VERSION" ]; then
        echo "Rollback verification failed: version mismatch"
        exit 1
      fi
    # Send notification to Slack/Teams
    - |
      curl -X POST -H 'Content-type: application/json' \
        --data "{\"text\":\"Rollback to $LAST_GOOD_RELEASE completed on $DEVICE_GROUP\"}" \
        $SLACK_WEBHOOK_URL
```

The Python helper script for saving/restoring configuration:

```python
#!/usr/bin/env python3
# tool_save_config.py - Save device config to backup slot
import argparse
import json
import subprocess

def save_config(device_group, backup_slot):
    # Fetch current config from all devices in group
    devices = get_device_list(device_group)
    config_snapshot = {}
    
    for device in devices:
        raw_config = subprocess.run(
            ["device-cli", "--device", device, "get-config"],
            capture_output=True, text=True, check=True
        ).stdout
        config_snapshot[device] = json.loads(raw_config)
    
    # Write to backup slot in persistent storage
    with open(f"/backup/slot_{backup_slot}/{device_group}.json", "w") as f:
        json.dump(config_snapshot, f, indent=2)
    
    print(f"Saved config for {len(devices)} devices to slot {backup_slot}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup-slot", type=int, required=True)
    parser.add_argument("--device-group", required=True)
    args = parser.parse_args()
    save_config(args.device_group, args.backup_slot)
```

## Common Pitfalls & Gotchas

**1. Bootloader version mismatch during rollback.** If your bootloader was also updated in the bad release, rolling back the application firmware might leave you with an incompatible bootloader. Always check that the bootloader version in the target device matches the one expected by the rollback firmware. I now include a `bootloader_compatibility_check` step that compares version strings before any flash operation.

**2. Configuration schema drift between releases.** The configuration parameters saved from the bad release might use fields or data types that the older firmware doesn't understand. Solution: maintain a configuration migration map in your release manifest. When rolling back, apply the inverse migration to transform the config back to the old schema. Without this, devices come up with default configs and lose calibration data.

**3. Partial rollback across a device group.** If you have 100 devices and the rollback fails on device #47, you now have a mixed fleet. Always use idempotent rollback operations and a state machine per device. Track each device's rollback status in a database. On retry, skip devices that already succeeded. Never assume a rollback either fully works or fully fails.

## Try It Yourself

1. **Create a rollback artifact bundle.** Modify your existing build pipeline to archive the firmware binary, version file, and configuration schema as a single tarball tagged with the release version. Verify you can extract and flash it manually.

2. **Implement a configuration backup/restore helper.** Write a script that connects to a test device, saves its current configuration to a JSON file, then restores it. Test that the device operates identically before and after the save/restore cycle.

3. **Build a rollback trigger webhook.** Set up a simple Flask or FastAPI endpoint that listens for a "rollback" POST request containing a device group name. Have it trigger your CI pipeline using the GitLab API's pipeline creation endpoint. Test it by sending a curl command.

## Next Up

Tomorrow: **Nightly & Long-Running Soak Test Orchestration** — how to schedule multi-hour stress tests that run firmware through temperature cycles, CAN bus saturation, and memory pressure scenarios, then automatically report regressions before your release goes to production.
