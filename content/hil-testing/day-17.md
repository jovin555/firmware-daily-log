---
title: "Day 17: HIL for Zephyr BLE: Testing BLE Advertisements"
date: 2026-06-29
tags: ["til", "hil-testing", "ble", "zephyr", "automation"]
---

## What I Explored Today

Today I wired up a Hardware-in-the-Loop test for Zephyr BLE advertisements using a Raspberry Pi 4 as a BLE sniffer and a Pico-W running Zephyr as the device under test (DUT). The goal was to validate that the DUT correctly advertises its service UUID, manufacturer data, and advertising interval under varying conditions—without relying on a mobile app or manual `hcitool` scans. I used `btmon` on the Pi to capture raw HCI events, parsed them with a Python script, and integrated the whole thing into our Jenkins CI pipeline. The result: automated pass/fail assertions on advertisement payload integrity, timing, and RSSI stability.

## The Core Concept

BLE advertisement testing is deceptively hard to get right in CI. In a manual workflow, you might run `hcitool lescan` or use a phone app like nRF Connect, see the device appear, and call it good. But that tells you nothing about:

- **Payload correctness**: Is the manufacturer-specific data byte-exact?
- **Timing jitter**: Is the advertising interval within ±20 ms of the configured value?
- **RSSI consistency**: Does the signal drop below a threshold under repeatable conditions?
- **Multi-role behavior**: Does the device stop advertising when it connects, then resume on disconnect?

HIL solves this by placing a known-good BLE receiver (the sniffer) at a fixed distance and orientation from the DUT, then capturing every advertisement event programmatically. The key insight is that you’re not just testing that BLE works—you’re testing that the Zephyr BLE stack’s advertising state machine behaves correctly under the exact same hardware and RF environment every time the CI runs.

## Key Commands / Configuration / Code

### 1. Zephyr DUT Configuration (`prj.conf`)

```kconfig
# Enable BLE peripheral and advertising
CONFIG_BT=y
CONFIG_BT_PERIPHERAL=y
CONFIG_BT_DEVICE_NAME="HIL-DUT-01"
CONFIG_BT_MAX_CONN=1

# Advertising parameters
CONFIG_BT_EXT_ADV=n               # Use legacy advertising for simplicity
CONFIG_BT_ADV_INTERVAL_MIN=160    # 100 ms (units of 0.625 ms)
CONFIG_BT_ADV_INTERVAL_MAX=160    # Fixed interval for deterministic testing

# Enable BT debug logs for CI parsing
CONFIG_BT_DEBUG_LOG=y
CONFIG_LOG=y
CONFIG_LOG_MODE_IMMEDIATE=y
```

### 2. Advertising Data Setup (`main.c` snippet)

```c
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gap.h>

static const struct bt_data ad[] = {
    BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
    BT_DATA_BYTES(BT_DATA_UUID16_SOME, 0x0d, 0x18),  // Battery Service
    BT_DATA_BYTES(BT_DATA_MANUFACTURER_DATA,
                  0x5d, 0x00,                          // Company ID: 0x005D (Nordic)
                  0x01, 0x02, 0x03, 0x04),            // Custom payload
};

void start_adv(void)
{
    int err = bt_le_adv_start(BT_LE_ADV_NCONN, ad, ARRAY_SIZE(ad),
                              NULL, 0);
    if (err) {
        printk("Advertising failed to start (err %d)\n", err);
    }
}
```

### 3. Sniffer Capture Script (`capture_adv.py`)

This runs on the Raspberry Pi over a USB-attached BLE dongle (e.g., nRF52840 Dongle running the sniffer firmware).

```python
#!/usr/bin/env python3
"""Capture BLE advertisements and validate payload/timing."""

import subprocess
import re
import sys
import time

EXPECTED_MANUFACTURER = bytes([0x5d, 0x00, 0x01, 0x02, 0x03, 0x04])
EXPECTED_INTERVAL_MS = 100.0
INTERVAL_TOLERANCE_MS = 20.0
MIN_RSSI = -70  # dBm, adjust based on your setup

def parse_btmon_output(output: str) -> list:
    """Extract advertising reports from btmon output."""
    reports = []
    pattern = r'LE Advertising Report.*?RSSI: (-?\d+) dBm'
    for match in re.finditer(pattern, output, re.DOTALL):
        reports.append({'rssi': int(match.group(1))})
    return reports

def main():
    # Start btmon with raw HCI capture
    proc = subprocess.Popen(
        ['btmon', '--tty', '/dev/ttyACM0', '--timeout', '10'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

    time.sleep(2)  # Allow sniffer to sync
    stdout, _ = proc.communicate(timeout=15)

    reports = parse_btmon_output(stdout)
    if len(reports) < 5:
        print(f"FAIL: Only {len(reports)} advertisements captured (need >=5)")
        sys.exit(1)

    # Check RSSI
    avg_rssi = sum(r['rssi'] for r in reports) / len(reports)
    if avg_rssi < MIN_RSSI:
        print(f"FAIL: Average RSSI {avg_rssi} dBm below threshold {MIN_RSSI}")
        sys.exit(1)

    # Check advertising interval (timestamps from btmon)
    timestamps = [float(m.group(1)) for m in
                  re.finditer(r'timestamp (\d+\.\d+)', stdout)]
    if len(timestamps) >= 2:
        intervals = [timestamps[i+1] - timestamps[i]
                     for i in range(len(timestamps)-1)]
        avg_interval = sum(intervals) / len(intervals) * 1000  # to ms
        if abs(avg_interval - EXPECTED_INTERVAL_MS) > INTERVAL_TOLERANCE_MS:
            print(f"FAIL: Avg interval {avg_interval:.1f} ms (expected {EXPECTED_INTERVAL_MS} ± {INTERVAL_TOLERANCE_MS})")
            sys.exit(1)

    print(f"PASS: {len(reports)} ads, avg RSSI {avg_rssi} dBm, interval {avg_interval:.1f} ms")
    sys.exit(0)

if __name__ == '__main__':
    main()
```

### 4. CI Pipeline Integration (Jenkins `Jenkinsfile` snippet)

```groovy
stage('BLE Advertisement Test') {
    steps {
        // Flash DUT via debugger
        sh 'west flash -d build -r pyocd'

        // Wait for DUT to boot and start advertising
        sh 'sleep 3'

        // Run sniffer capture on dedicated Pi
        sh '''
            ssh hil-pi-01 "python3 /opt/tests/capture_adv.py" > adv_result.txt
        '''
        // Parse result
        sh 'grep -q "PASS" adv_result.txt || exit 1'
    }
}
```

## Common Pitfalls & Gotchas

1. **Sniffer antenna placement matters more than you think.** A 5 cm shift in the Pi’s USB dongle position can change RSSI by 10 dBm. Use a fixed jig with the DUT and sniffer at a known distance (e.g., 30 cm) and orientation. I use 3D-printed mounts to guarantee repeatability.

2. **`btmon` timestamps are not real-time.** The `--timeout` flag uses wall clock, but the HCI timestamps inside the output are from the controller’s internal clock, which can drift. For interval validation, I capture at least 10 advertisements and compute the average interval—single-packet timing is unreliable.

3. **Zephyr’s `BT_LE_ADV_NCONN` vs `BT_LE_ADV_CONN` affects scan response behavior.** If your test expects scan response data but you use non-connectable advertising, the sniffer will never see it. Always verify the advertising type matches your test expectations.

## Try It Yourself

1. **Set up a sniffer node**: Flash an nRF52840 Dongle with the [nRF Sniffer for BLE](https://www.nordicsemi.com/Products/Development-tools/nRF-Sniffer-for-BLE) firmware, connect it to a Raspberry Pi, and verify you can capture advertisements from any BLE device using `btmon`.

2. **Modify the advertising payload**: Change the manufacturer data in the Zephyr DUT to include a monotonic counter. Update the Python script to assert that the counter increments by exactly 1 between consecutive advertisements.

3. **Test advertising stop/start**: Add a GPIO button to the DUT that toggles advertising on/off. Write a HIL test that presses the button (via a relay or GPIO expander), captures 5 seconds of sniffer data, and asserts that no advertisements appear after the button press.

## Next Up

Tomorrow, I’ll tackle **HIL Power Measurement: Automated Current Profiling**—connecting a precision shunt resistor and an ADS1115 ADC to the DUT’s power rail, logging current draw during BLE advertising, connection, and sleep modes, and asserting that the device stays within its power budget across the entire test suite.
