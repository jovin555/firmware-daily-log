---
title: "Day 15: Update Scheduling: Bandwidth, Power & Maintenance Windows"
date: 2026-07-15
tags: ["til", "secure-ota", "scheduling", "power-budget"]
---

## What I Explored Today

Today I dug into the fleet-level scheduling engine for OTA updates—specifically how to balance bandwidth constraints, device power budgets, and maintenance windows across thousands of heterogeneous devices. The naive approach of "push update immediately" breaks at scale: you'll saturate your CDN, drain batteries on battery-powered nodes, and violate maintenance blackout periods. I implemented a constraint-aware scheduler that respects per-device power thresholds, network link budgets, and time-of-day maintenance windows, all while maximizing fleet update velocity.

## The Core Concept

The fundamental tension in fleet OTA scheduling is that you have three competing constraints, and violating any one of them causes real operational failures:

1. **Bandwidth** — Your update server or CDN has a finite egress pipe. If 10,000 devices all request a 50 MB firmware blob simultaneously, you either drop connections or degrade service for other traffic. More subtly, each device's network link (cellular, LoRa, Wi-Fi) has its own throughput ceiling.

2. **Power** — For battery-powered devices, downloading and applying an update is one of the most energy-intensive operations. A 50 MB download over cellular can consume 5–10% of a typical IoT device's battery. If you schedule updates during low-battery states, devices brown out mid-flash and brick.

3. **Maintenance Windows** — Many devices operate in environments where downtime is unacceptable: industrial controllers during production shifts, medical devices during patient monitoring, or automotive ECUs while driving. You must respect time-of-day or event-based windows.

The scheduler's job is to find the feasible intersection of these constraints for each device, then stagger updates to avoid thundering herds while still completing the rollout within a target deadline.

## Key Commands / Configuration / Code

Here's a practical scheduler implementation in Python that models these constraints using a priority queue and per-device constraint profiles:

```python
# scheduler.py — Constraint-aware OTA fleet scheduler
import heapq
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class DeviceConstraint:
    device_id: str
    battery_pct: float          # 0.0 to 100.0
    link_kbps: int              # measured or provisioned throughput
    maintenance_window_start: int  # hour of day (0-23), UTC
    maintenance_window_end: int    # hour of day (0-23), UTC
    update_size_bytes: int = 50 * 1024 * 1024  # 50 MB default

@dataclass
class ScheduledSlot:
    device_id: str
    start_time: datetime
    duration_seconds: int
    priority: float = field(compare=True)  # lower = more urgent

class FleetScheduler:
    def __init__(self, max_concurrent_downloads: int = 50,
                 server_egress_mbps: int = 1000):
        self.max_concurrent = max_concurrent_downloads
        self.server_egress_bps = server_egress_mbps * 1_000_000
        self.active_slots: List[ScheduledSlot] = []
        self.pending_queue: List[ScheduledSlot] = []

    def _compute_priority(self, device: DeviceConstraint) -> float:
        """Lower priority value = schedule sooner."""
        # Penalize low battery (below 30% is critical)
        battery_penalty = max(0, 30.0 - device.battery_pct) * 10.0
        # Penalize slow links (takes longer, so start earlier)
        link_penalty = 1.0 / max(device.link_kbps, 1) * 1000
        # Reward devices inside their maintenance window
        now_hour = datetime.utcnow().hour
        in_window = (device.maintenance_window_start <= now_hour <
                     device.maintenance_window_end)
        window_bonus = 0.0 if in_window else 50.0
        return battery_penalty + link_penalty + window_bonus

    def _estimate_duration(self, device: DeviceConstraint) -> int:
        """Estimate download time in seconds, including overhead."""
        # 20% protocol overhead (TLS handshake, HTTP headers, retransmits)
        total_bits = device.update_size_bytes * 8 * 1.2
        link_bps = device.link_kbps * 1000
        return int(total_bits / link_bps) + 30  # +30s for flash write

    def schedule_device(self, device: DeviceConstraint,
                        now: datetime) -> Optional[ScheduledSlot]:
        """Return a ScheduledSlot or None if constraints cannot be met."""
        # Reject if battery too low (< 15%)
        if device.battery_pct < 15.0:
            print(f"Device {device.device_id}: battery too low ({device.battery_pct}%)")
            return None

        duration = self._estimate_duration(device)
        priority = self._compute_priority(device)

        # Find next valid start time within maintenance window
        start = now
        for _ in range(48):  # look ahead 48 hours max
            window_start = start.replace(hour=device.maintenance_window_start,
                                         minute=0, second=0, microsecond=0)
            window_end = start.replace(hour=device.maintenance_window_end,
                                       minute=0, second=0, microsecond=0)
            if window_end <= window_start:
                window_end += timedelta(days=1)  # wraps past midnight
            if start < window_start:
                start = window_start
            if start + timedelta(seconds=duration) <= window_end:
                break
            start += timedelta(hours=1)
        else:
            print(f"Device {device.device_id}: no valid window in 48h")
            return None

        slot = ScheduledSlot(device.device_id, start, duration, priority)
        heapq.heappush(self.pending_queue, slot)
        return slot

    def tick(self, now: datetime) -> List[ScheduledSlot]:
        """Advance scheduler: promote pending to active if bandwidth permits."""
        # Remove completed active slots
        self.active_slots = [s for s in self.active_slots
                             if s.start_time + timedelta(seconds=s.duration_seconds) > now]

        # Calculate current bandwidth usage
        current_bps = sum((s.duration_seconds * 8 * 1.2) / s.duration_seconds
                          for s in self.active_slots) if self.active_slots else 0

        # Promote pending slots while bandwidth available
        promoted = []
        while self.pending_queue and len(self.active_slots) < self.max_concurrent:
            slot = heapq.heappop(self.pending_queue)
            # Estimate this slot's bandwidth consumption
            slot_bps = (slot.duration_seconds * 8 * 1.2) / slot.duration_seconds
            if current_bps + slot_bps <= self.server_egress_bps:
                self.active_slots.append(slot)
                promoted.append(slot)
                current_bps += slot_bps
            else:
                # Re-queue with increased priority (aging)
                slot.priority -= 0.5  # becomes more urgent
                heapq.heappush(self.pending_queue, slot)
                break
        return promoted
```

The scheduler runs a `tick()` loop every minute, promoting pending updates to active when bandwidth headroom exists. Priority aging ensures slow-link devices don't starve.

## Common Pitfalls & Gotchas

**1. Assuming symmetric bandwidth.** Devices often have asymmetric links (e.g., cellular downlink is fast, uplink is slow). The scheduler must use *measured* download throughput, not provisioned link speed. I've seen devices with "10 Mbps LTE" actually get 200 Kbps during peak hours. Always use a bandwidth probe or historical throughput data.

**2. Ignoring flash write power.** The energy cost of writing to flash (especially NAND) can exceed the download cost. A 50 MB download over Wi-Fi might consume 200 mAh, but the subsequent flash erase/write cycle can consume another 150 mAh. Your power budget must include both phases. I add a 30-second "flash penalty" to the duration estimate to account for this.

**3. Maintenance window drift.** Devices with inaccurate RTCs (common in low-cost IoT) will drift out of their maintenance window. Always use NTP sync before scheduling, and add a 10-minute guard band on each side of the window to prevent edge-case failures.

## Try It Yourself

1. **Instrument your fleet's link throughput.** Add a 10-second bandwidth probe to your device's boot sequence that measures download speed from your update server. Log the results to a cloud database. Then modify the scheduler above to use the 90th percentile of the last 10 measurements instead of a static `link_kbps`.

2. **Implement battery-aware deferral.** Extend the `DeviceConstraint` class to include a `critical_battery_threshold` field (default 20%). Modify `schedule_device()` to return `None` and log a warning when battery is below threshold, but also schedule a re-check in 1 hour using a `asyncio` timer or cron job.

3. **Build a maintenance window validator.** Write a unit test that creates 100 devices with random maintenance windows (some overlapping, some disjoint) and verifies that no two devices with overlapping windows are scheduled concurrently if their combined bandwidth exceeds the server egress limit. Use `pytest` with parametrized fixtures.

## Next Up

Tomorrow we tackle **Resuming Interrupted Downloads: Chunked Transfer & Integrity** — because in the real world, devices lose connectivity mid-update, and starting over from byte 0 is not acceptable. We'll implement HTTP Range requests, Merkle tree chunk verification, and a resume state machine that survives power loss.
