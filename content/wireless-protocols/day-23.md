---
title: "Day 23: Interoperability Testing & Certification: Bluetooth SIG, Thread Group"
date: 2026-07-23
tags: ["til", "wireless-protocols", "certification", "interop"]
---

## What I Explored Today

Today I dug into the formal certification and interoperability testing requirements for Bluetooth (via Bluetooth SIG) and Thread (via Thread Group), specifically as they apply to Matter-compliant devices. I ran through the actual test harnesses, qualification workflows, and the painful reality of getting a design through both a Bluetooth SIG declaration (QDID) and Thread Group certification (Thread Certified Component) before Matter can even sniff the device. The key takeaway: certification is not optional, and skipping it means your device will be silently rejected by every major smart home ecosystem.

## The Core Concept

Interoperability testing exists because wireless stacks are complex state machines, and two chips that both claim to implement "BLE 5.2" or "Thread 1.3.0" can still fail to talk to each other due to subtle timing, parameter, or implementation differences. The Bluetooth SIG and Thread Group each maintain a formal certification program that tests a device against a defined set of test specifications (TS). For Matter, the requirement is explicit: the device must have a valid Bluetooth SIG QDID for the BLE transport (used for commissioning) and a valid Thread Group certificate for the Thread radio (if using Thread as the network transport). Without both, the Matter certification body (CSA) will not issue a Matter certification.

The Bluetooth SIG qualification process uses the "Declaration ID" (DID) system. You submit your design, run the Bluetooth Test Suite (BTS) against your implementation, and generate a Test Report. The SIG then issues a Qualified Design ID (QDID). For Thread, you must pass the Thread Test Harness (TH) which validates the device against the Thread 1.3.0 specification, including the new "Matter Interoperability Profile" tests that check for correct handling of TLV-encoded data, network key provisioning, and border router discovery.

The practical implication: you cannot just buy a pre-certified module and assume it's plug-and-play. If you modify the BLE stack (e.g., change the GATT database, add custom services, or alter the advertisement interval), you may need a new QDID. Similarly, if you change the Thread MAC layer or the OpenThread configuration (e.g., channel mask, panid assignment), you may invalidate the Thread certification.

## Key Commands / Configuration / Code

### 1. Checking Bluetooth SIG Qualification Status (using the SIG Launcher API)

```bash
# Query the Bluetooth SIG API for a specific QDID
# Replace QDID with your actual Qualified Design ID
curl -X GET "https://launchstudio.bluetooth.com/api/v1/qdid/123456" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -H "Accept: application/json" | jq '.status, .product_name, .declaration_date'
```

### 2. Running the Thread Test Harness (THCI) for a DUT

The Thread Group provides the Thread Test Harness (TH) which runs on a Linux host. You connect your Device Under Test (DUT) via a serial or USB interface.

```bash
# Install the Thread Test Harness (version 1.3.0 or later)
# Requires Python 3.8+, pip, and a serial port
pip install thread-test-harness==1.3.0

# Start the harness in interactive mode
# The DUT must be flashed with a Thread 1.3.0-compliant stack (e.g., OpenThread)
thci --interface /dev/ttyUSB0 --baudrate 115200 --dut-type "nrf52840"
```

Inside the harness, you run the "Matter Interoperability" test suite:

```python
# Python snippet to execute a specific test case within the harness
from thci import TestHarness, DUTConfig

config = DUTConfig(
    interface="/dev/ttyUSB0",
    baudrate=115200,
    dut_type="nrf52840",
    thread_version="1.3.0"
)

harness = TestHarness(config)
# Run test case 5.2.1: "Matter Commissioning over Thread"
result = harness.run_test("TC_TH_5_2_1")
print(f"Test result: {result.status}")  # PASS / FAIL / INCONCLUSIVE
```

### 3. Generating a Bluetooth SIG Test Report (using the PTS tool)

The Bluetooth SIG's Profile Tuning Suite (PTS) is the official tool for generating test reports. You run it against your device over a Bluetooth HCI dongle.

```bash
# Example command to run the GATT test suite (for Matter BLE transport)
# Assumes PTS is installed at /opt/PTS
/opt/PTS/ptscli --device hci0 --test-suite "GATT" --output report.xml
# Then upload report.xml to the Bluetooth SIG Launch Studio
```

## Common Pitfalls & Gotchas

### 1. "Pre-Certified Module" Does Not Mean "Certified Product"
If you buy a pre-certified module (e.g., an nRF52840 module with a QDID and Thread certificate), that certification covers the module *as sold*. The moment you add an external antenna, change the PCB layout, or modify the firmware (even just the application layer), you may need a new certification. The Bluetooth SIG allows "end product listing" under the module's QDID only if you do not change the radio parameters. Thread Group is stricter: any change to the OpenThread stack configuration (e.g., changing `OPENTHREAD_CONFIG_MAC_SOFTWARE_ACK_TIMEOUT_ENABLE`) requires re-certification.

### 2. Matter Commissioning Uses BLE, But the BLE Stack Must Be "Matter-Aware"
Many developers assume any BLE 5.0 stack works for Matter commissioning. It does not. Matter requires a specific GATT service (the Matter Commissioning Service UUID: `0xFFF6`) with specific characteristics (e.g., `0xFFF7` for the "Commissioning Data" characteristic). If your BLE stack does not expose this exact GATT database, the Matter commissioner (e.g., Apple Home, Google Home) will not discover the device. I've seen teams waste weeks debugging "BLE connection failures" that were actually GATT database mismatches.

### 3. Thread Certification Tests Are Not Just for the Radio
The Thread Test Harness includes tests for the IPv6 stack, DNS-SD, and the Mesh Link Establishment (MLE) protocol. A common failure is the "MLE Link Quality" test (TC_TH_3_1_1) where the DUT must correctly respond to MLE Link Probe messages with the proper TLV format. If your OpenThread configuration has `OPENTHREAD_CONFIG_MLE_LINK_PROBE_ENABLE` set to 0 (default in some older SDKs), the test will fail immediately. Always verify this config is enabled before submitting for certification.

## Try It Yourself

1. **Verify your BLE stack's GATT database**: Use a BLE sniffer (e.g., nRF Connect or Wireshark with a BLE dongle) to capture the advertisement and GATT services of your device. Confirm that the Matter Commissioning Service UUID (`0xFFF6`) and its characteristics are present. If not, modify your GATT database definition.

2. **Run the Thread Test Harness on a development board**: Flash an nRF52840 DK with the OpenThread CLI example (commit `a1b2c3d` or later). Connect via USB, install the Thread Test Harness, and run `TC_TH_5_2_1` (Matter Commissioning over Thread). Observe the test output and fix any failures related to TLV parsing or network key provisioning.

3. **Generate a Bluetooth SIG PTS report**: If you have access to a PTS license, run the GATT test suite against your device. Export the XML report and inspect it for any "FAIL" entries. Common failures include "GATT Client Write Without Response" timeout or "Service Changed Indication" misconfiguration.

## Next Up

Tomorrow is the grand finale of this series: **Full Review & Project: Matter-Compatible Sensor Over Thread**. I'll walk through the complete design, from selecting the SoC and writing the Matter application cluster (temperature sensor) to passing the certification tests and deploying it in a real HomeKit/Google Home environment. We'll build a working prototype that you can replicate on your bench.
