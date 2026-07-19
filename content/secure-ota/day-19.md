---
title: "Day 19: OTA Over Cellular: NB-IoT/LTE-M Bandwidth & Cost Considerations"
date: 2026-07-19
tags: ["til", "secure-ota", "cellular-ota"]
---

## What I Explored Today

Today I dug into the harsh realities of pushing firmware updates over cellular IoT networks—specifically NB-IoT and LTE-M. While these LPWAN technologies enable deep indoor coverage and low device cost, they impose brutal constraints on OTA payloads. I spent the day modeling bandwidth budgets, calculating data costs per update, and testing delta compression strategies on a real nRF9160 module. The numbers are sobering: a 500 KB firmware image over NB-IoT at 250 bps takes nearly 5 hours and can cost $0.15–$0.50 per device per update in data charges alone. LTE-M is faster (1 Mbps peak) but still constrained by power and data plan limits.

## The Core Concept

The fundamental tension in cellular OTA is between **update completeness** and **radio resource cost**. Unlike Wi-Fi or Ethernet, cellular data is metered—both in time-on-air (battery drain) and in bytes (carrier data plans). NB-IoT and LTE-M are designed for small, infrequent payloads (typically <1 KB per transaction). A full firmware image (100 KB–1 MB) violates this assumption.

The engineering solution is a layered approach:
1. **Delta compression** (bsdiff, xdelta3) to transmit only changed bytes between versions.
2. **Chunked download with resume** to survive intermittent coverage.
3. **Payload segmentation** into MTU-sized blocks (typically 512–1358 bytes for LTE-M) with per-block CRC.
4. **Data plan-aware scheduling**—choose off-peak hours or low-cost roaming partners.

The key metric is **cost-per-update-per-device**, which must be balanced against update frequency and fleet size. For a fleet of 10,000 devices, a $0.10 per-update cost means $1,000 per update cycle. If you push monthly updates, that’s $12,000/year—often more than the hardware cost.

## Key Commands / Configuration / Code

Below is a practical example of configuring an nRF9160-based device for OTA over LTE-M with chunked download and delta update. This uses the Zephyr RTOS and the modem shell.

```c
// prj.conf - Enable LTE-M and OTA support
CONFIG_LTE_NETWORK_MODE_LTE_M=y
CONFIG_LTE_LINK_CONTROL=y
CONFIG_MCUBOOT=y
CONFIG_IMG_MANAGER=y
CONFIG_IMG_ERASE_PROGRESSIVELY=y
CONFIG_UPDATE_HASH_CHECK=y
CONFIG_DOWNLOAD_CLIENT=y
CONFIG_DOWNLOAD_CLIENT_HTTP=y
CONFIG_DOWNLOAD_CLIENT_CHUNKED=y
CONFIG_DOWNLOAD_CLIENT_CHUNK_SIZE=1024  // 1 KB chunks
CONFIG_DOWNLOAD_CLIENT_MAX_RETRIES=5
CONFIG_FLASH_MAP=y
CONFIG_STREAM_FLASH=y
```

```bash
# Generate delta patch between firmware versions
# Requires old firmware binary (v1.0.0.bin) and new (v1.1.0.bin)
xdelta3 -e -s v1.0.0.bin v1.1.0.bin patch.xdelta3
# Result: patch.xdelta3 is typically 10-30% of full image size

# Check delta size
ls -lh patch.xdelta3
# Example output: -rw-r--r-- 1 user user 45K Jul 19 10:00 patch.xdelta3
# Full image was 500K, delta is 45K — 91% reduction
```

```python
# Python script to calculate cost per update
# Run on the cloud backend before scheduling OTA

def estimate_ota_cost(image_size_bytes, delta_ratio, data_price_per_mb, devices):
    """
    image_size_bytes: full firmware size
    delta_ratio: expected delta compression ratio (0.0-1.0)
    data_price_per_mb: carrier data cost (e.g., $0.05/MB for NB-IoT)
    devices: number of devices in fleet
    """
    delta_size = image_size_bytes * delta_ratio
    # Add 10% overhead for headers, retransmissions, metadata
    total_bytes = delta_size * 1.10
    total_mb = total_bytes / (1024 * 1024)
    cost_per_device = total_mb * data_price_per_mb
    fleet_cost = cost_per_device * devices
    return cost_per_device, fleet_cost

# Example: 500KB image, 10% delta, $0.10/MB LTE-M data, 10k devices
cost_per_dev, fleet_cost = estimate_ota_cost(500*1024, 0.10, 0.10, 10000)
print(f"Cost per device: ${cost_per_dev:.4f}")
print(f"Fleet cost: ${fleet_cost:.2f}")
# Output: Cost per device: $0.0054
# Output: Fleet cost: $53.76
```

```bash
# On-device: Download patch with resume support using curl
# This runs on the device after LTE-M attach
curl -C - -o /fs/patch.xdelta3 \
     http://ota.example.com/firmware/v1.1.0/patch.xdelta3 \
     --retry 3 --retry-delay 60 --max-time 3600
# -C - enables auto-resume from last byte received
# --max-time 3600 prevents hanging on dead connection
```

## Common Pitfalls & Gotchas

1. **Assuming symmetric bandwidth**: NB-IoT uplink is often slower than downlink (e.g., 62.5 kbps UL vs 250 kbps DL). If your update protocol requires ACKs per chunk, the uplink becomes the bottleneck. Solution: use cumulative ACKs or NACK-only schemes.

2. **Data plan fine print**: Many IoT data plans charge per kilobyte with a minimum daily charge (e.g., $0.01/day even if no data used). A 50 KB delta update might cost $0.01 for data + $0.01 for the day = $0.02 per device. Over a year of monthly updates, that’s $0.24/device—significant at scale.

3. **Delta generation on mismatched baselines**: If devices have different firmware versions in the field, a single delta won’t work. You must either (a) store multiple deltas per version pair, or (b) fall back to full image for devices on unknown versions. Always validate the source version hash before applying a delta.

## Try It Yourself

1. **Calculate your fleet’s OTA budget**: Take your current firmware size, estimate a delta ratio (measure with xdelta3 on two real builds), and plug it into the Python cost estimator above. Compare NB-IoT ($0.05/MB) vs LTE-M ($0.10/MB) pricing from your carrier.

2. **Test chunked download resilience**: On an nRF9160 or similar board, configure the download client with `CONFIG_DOWNLOAD_CLIENT_CHUNK_SIZE=512`. Force a network disconnect mid-download (e.g., move the device to a faraday cage). Verify that `curl -C -` resumes from the last complete chunk.

3. **Profile delta sizes over multiple releases**: Generate deltas between 5 consecutive firmware versions. Plot the delta size vs. number of changed source files. Identify which components (e.g., BSP, application, stack) cause the largest deltas and consider isolating them into separate update slots.

## Next Up

Tomorrow: **Bricking Prevention: Failsafe Bootloaders & Golden Images** — how to design a bootloader that never leaves a device in an unrecoverable state, even if the power fails mid-update.
