---
title: "Day 14: Staged Rollouts: Canary Groups & Percentage-Based Deployment"
date: 2026-07-14
tags: ["til", "secure-ota", "staged-rollout", "canary"]
---

## What I Explored Today

Today I dug into the fleet management side of OTA updates: how to safely roll out firmware to thousands of devices without taking down the entire fleet. The key insight is that you never push to 100% of devices at once. Instead, you use staged rollouts with canary groups and percentage-based deployment to catch failures early, limit blast radius, and maintain service continuity. I implemented a working rollout controller that manages update groups, tracks health metrics, and automatically halts deployment when error rates spike.

## The Core Concept

The fundamental problem: an OTA update that works perfectly in the lab can fail catastrophically in the field. Environmental conditions, hardware revisions, network topology, and usage patterns all vary. A staged rollout treats the fleet as a statistical sample space rather than a monolithic target.

**Canary groups** are small, representative subsets of devices that receive the update first. They should mirror the production fleet's diversity—different hardware revisions, geographic regions, and network conditions. If the canary survives 24-48 hours without regression, you proceed.

**Percentage-based deployment** then ramps the update across the remaining fleet in controlled increments: 5%, 25%, 50%, 100%. Each step has a cooldown period where you monitor key metrics (crash rate, connectivity, sensor accuracy, power consumption). If any metric exceeds a threshold, the rollout auto-rolls back.

The math matters: with a 5% canary group on a 10,000-device fleet, you expose 500 devices to risk. That's acceptable. Pushing to all 10,000 at once is gambling.

## Key Commands / Configuration / Code

Here's a practical rollout controller I built today. It uses a JSON-based rollout policy and a simple state machine.

```python
# rollout_controller.py — manages staged OTA deployment
import json
import time
import requests
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class RolloutStage:
    percentage: float          # e.g., 0.05 for 5%
    cooldown_hours: int        # monitoring window
    max_error_rate: float      # threshold to halt (e.g., 0.02 = 2%)
    canary_only: bool = False  # is this a canary stage?

class FleetRolloutController:
    def __init__(self, fleet_api_url: str, rollout_policy: dict):
        self.api = fleet_api_url
        self.policy = rollout_policy
        self.stages = self._build_stages()
        self.current_stage = 0
        self.halted = False
        
    def _build_stages(self) -> List[RolloutStage]:
        # Parse policy: {"canary": {"percentage": 0.05, "cooldown": 48, "max_error": 0.01},
        #                "stages": [{"percentage": 0.25, "cooldown": 24, "max_error": 0.02}, ...]}
        stages = []
        canary = self.policy.get("canary", {})
        if canary:
            stages.append(RolloutStage(
                percentage=canary["percentage"],
                cooldown_hours=canary["cooldown_hours"],
                max_error_rate=canary["max_error_rate"],
                canary_only=True
            ))
        for stage in self.policy.get("stages", []):
            stages.append(RolloutStage(**stage))
        return stages
    
    def execute_rollout(self, firmware_version: str, firmware_url: str):
        """Run the staged rollout, halting on error threshold breach."""
        for idx, stage in enumerate(self.stages):
            self.current_stage = idx
            print(f"[ROLLOUT] Stage {idx}: {stage.percentage*100:.0f}% of fleet")
            
            # Select devices for this stage
            devices = self._select_devices(stage.percentage, stage.canary_only)
            
            # Push update to selected devices
            for device_id in devices:
                self._push_update(device_id, firmware_url, firmware_version)
            
            # Monitor during cooldown
            start_time = time.time()
            while time.time() - start_time < stage.cooldown_hours * 3600:
                error_rate = self._get_fleet_error_rate(devices)
                if error_rate > stage.max_error_rate:
                    print(f"[ALERT] Error rate {error_rate:.3f} exceeds threshold {stage.max_error_rate}")
                    self._rollback(devices, firmware_version)
                    self.halted = True
                    return
                time.sleep(300)  # check every 5 minutes
            print(f"[ROLLOUT] Stage {idx} passed — error rate {error_rate:.3f}")
    
    def _select_devices(self, fraction: float, canary_only: bool) -> List[str]:
        # In production, query fleet DB with device metadata filters
        # For canary: select devices matching diversity criteria
        # For percentage: random sample across remaining devices
        pass
    
    def _push_update(self, device_id: str, url: str, version: str):
        # POST to device's OTA endpoint
        # requests.post(f"{self.api}/devices/{device_id}/update", json={"url": url, "version": version})
        pass
    
    def _get_fleet_error_rate(self, device_ids: List[str]) -> float:
        # Query monitoring system for crash rate / connectivity loss
        # Return fraction of devices reporting errors
        return 0.0  # placeholder
    
    def _rollback(self, device_ids: List[str], bad_version: str):
        # Push previous known-good firmware to affected devices
        pass
```

**Rollout policy JSON** (stored in a secure config service):
```json
{
  "firmware": {
    "version": "2.4.1",
    "url": "https://ota.example.com/firmware/v2.4.1.bin",
    "sha256": "a1b2c3d4e5f6..."
  },
  "rollout": {
    "canary": {
      "percentage": 0.05,
      "cooldown_hours": 48,
      "max_error_rate": 0.01
    },
    "stages": [
      {"percentage": 0.25, "cooldown_hours": 24, "max_error_rate": 0.02},
      {"percentage": 0.50, "cooldown_hours": 24, "max_error_rate": 0.02},
      {"percentage": 1.00, "cooldown_hours": 48, "max_error_rate": 0.03}
    ]
  }
}
```

## Common Pitfalls & Gotchas

**1. Canary groups that aren't representative.** If you only select devices on the same network or hardware revision, you'll miss failures that occur in other environments. Always stratify your canary: include at least 3 hardware variants, 2 geographic regions, and both high- and low-connectivity devices.

**2. Cooldown periods that are too short.** A 1-hour cooldown might catch immediate crashes but miss memory leaks that take 12 hours to manifest. For firmware changes affecting power management or long-running processes, extend cooldown to 48-72 hours. I've seen rollouts pass canary only to fail at 50% because the bug required 24 hours of uptime to trigger.

**3. Ignoring the "silent failure" metric.** Crash rate is obvious. But what about devices that stop reporting telemetry? If a device goes silent after an update, it might be stuck in a boot loop. Always monitor device heartbeat as a separate metric, and treat loss of connectivity as an error.

## Try It Yourself

1. **Build a canary selection script** that queries your fleet database and returns a stratified sample of 50 devices (5 hardware revisions × 2 regions × 5 devices each). Use device metadata like `hw_rev`, `region`, and `last_seen`.

2. **Implement a health check endpoint** on your device that returns `{"status": "ok", "uptime": 12345, "error_count": 0}`. Then modify the rollout controller to poll this endpoint during cooldown, not just the fleet-level error rate.

3. **Create a rollback trigger** in your CI/CD pipeline: if the canary group's error rate exceeds 1% within 48 hours, automatically revert the firmware version in the rollout policy and notify the team via Slack webhook.

## Next Up

Tomorrow: **Update Scheduling: Bandwidth, Power & Maintenance Windows** — how to avoid bricking devices mid-operation by coordinating updates with device state, network capacity, and user activity patterns. We'll build a scheduler that respects maintenance windows and throttles bandwidth to prevent network congestion.
