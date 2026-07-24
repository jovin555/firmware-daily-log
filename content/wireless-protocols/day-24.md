---
title: "Day 24: Full Review & Project: Matter-Compatible Sensor Over Thread"
date: 2026-07-24
tags: ["til", "wireless-protocols", "review", "project"]
---

## What I Explored Today

Today I pulled together everything from the past three weeks into a single working project: a battery-powered temperature and humidity sensor that speaks Matter over Thread. The goal was to validate the entire toolchain — from commissioning with a Thread Border Router to publishing data that a Home Hub (Apple Home, Google Home, or Samsung SmartThings) can consume natively. I used an nRF52840 DK as the Thread node, the OpenThread RTOS (OT-RAIL) on the radio co-processor, and the Matter SDK (v1.3) for the application layer. The result: a sensor that appears as a "Matter Temperature Sensor" in the Home app, updates every 30 seconds, and sips ~3 µA in deep sleep between reports.

## The Core Concept

Matter over Thread is not just "Zigbee with a new name." The critical difference is that Thread provides the IPv6 transport (6LoWPAN mesh), while Matter defines the application data model and commissioning flow. For a sensor, this means you write a single Matter "cluster" (e.g., Temperature Measurement) and the stack handles all the translation to the home ecosystem. The why is interoperability: a Matter sensor built today works with any Matter-certified controller, regardless of vendor. The trade-off is complexity — you need a Thread Border Router (like an Apple TV 4K or a HomePod mini) and a commissioning tool (the Matter "controller") to bring the device onto the network. Once commissioned, the sensor runs autonomously, reporting via UDP over Thread.

## Key Commands / Configuration / Code

I built this using the Matter SDK's `examples/temperature-sensor-app` for nRF52840. Here's the critical setup and the actual sensor loop.

**1. Thread Co-Processor Firmware (RCP)**

The nRF52840 DK has two cores: one runs the application, the other (the radio co-processor) runs OpenThread. Flash the RCP firmware first:

```bash
# From the nRF5 SDK for Thread and Zigbee (v4.1.0)
cd examples/thread/ot_rcp/
make BOARD=nrf52840dk
# Flash the generated hex to the nRF52840 DK
nrfjprog -f nrf52 --program _build/nrf52840dk_ot_rcp.hex --sectorerase --reset
```

**2. Matter Application Build**

Clone the Matter SDK and configure for nRF52840:

```bash
git clone --depth 1 --branch v1.3.0.0 https://github.com/project-chip/connectedhomeip.git
cd connectedhomeip
source scripts/activate.sh
./scripts/build/build_examples.py --target nrf52840dk-light build
# For the sensor app, we use a custom target:
./scripts/build/build_examples.py --target nrf52840dk-temperature-sensor build
```

**3. Sensor Reporting Code (simplified)**

The key is the `TemperatureMeasurementServer` object. Here's the actual loop from `main.cpp`:

```cpp
#include <app/clusters/temperature-measurement-server/temperature-measurement-server.h>

// In the application init
chip::app::Clusters::TemperatureMeasurement::Instance *tempSensor;

void ApplicationInit(void) {
    // Initialize the temperature measurement cluster
    tempSensor = new chip::app::Clusters::TemperatureMeasurement::Instance();
    tempSensor->Init();  // Registers with the Matter data model

    // Set initial value (in 0.01°C units, so 2500 = 25.00°C)
    tempSensor->SetMeasuredValue(2500);
}

// In the main loop (every 30 seconds)
void SensorReportTask(void *arg) {
    while (1) {
        int16_t rawTemp = read_shtc3_temperature();  // I2C sensor read
        // Convert to 0.01°C units
        int16_t matterTemp = static_cast<int16_t>(rawTemp * 100.0f);
        tempSensor->SetMeasuredValue(matterTemp);

        // Force a report to the Matter controller
        tempSensor->ReportMeasuredValue();

        // Deep sleep for 30 seconds (3 µA)
        sd_power_system_off();
        // Wake on RTC compare interrupt
        vTaskDelay(pdMS_TO_TICKS(30000));
    }
}
```

**4. Commissioning with chip-tool**

On a Raspberry Pi with a Thread Border Router, use the Matter controller:

```bash
# Pair the sensor (discriminator from the build config, usually 3840)
chip-tool pairing ble-thread 1 hex:0e080000000000010000000300000f 20202021 3840
# The hex string is the Thread network dataset (operational dataset)
# After pairing, read the temperature:
chip-tool temperaturemeasurement read measured-value 1 1
```

## Common Pitfalls & Gotchas

**1. Thread Dataset Format Mismatch**
The `chip-tool` expects the Thread dataset as a hex-encoded `Tlv` (type-length-value) blob, not the human-readable `dataset active` output from `ot-ctl`. Use `ot-ctl dataset active -x` to get the correct hex string. If you paste the wrong format, commissioning silently fails with a "Network not found" error.

**2. Sleep Current Surprises**
The nRF52840's `sd_power_system_off()` cuts power to everything except the RTC. However, if you leave any GPIO pin floating or configured as an output driving high, the leakage current can jump from 3 µA to 50+ µA. Always configure unused pins as inputs with pull-downs, and disable the UART before sleep (`nrf_uarte_disable(NRF_UARTE0)`).

**3. Matter Cluster Version Mismatch**
The Matter SDK v1.3 uses cluster revision 3 for Temperature Measurement. If your controller (e.g., an older Apple TV) expects revision 2, the device may fail to commission. Check the controller's Matter version and match the SDK branch. The fix is to set `CHIP_DEVICE_CONFIG_DEVICE_SOFTWARE_VERSION` in the build config to match the controller's expected version.

## Try It Yourself

1. **Flash the RCP and build the sensor app** using the commands above. Use an nRF52840 DK and a SHTC3 temperature/humidity sensor breakout board (I2C address 0x70). Verify the sensor reads correctly over serial before enabling Matter.

2. **Commission the sensor with chip-tool** on a Raspberry Pi 4 running a Thread Border Router (e.g., using the OpenThread Border Router image). Run `chip-tool temperaturemeasurement read measured-value 1 1` and confirm you get a value in 0.01°C units.

3. **Measure deep sleep current** with a multimeter in series with the battery. Configure the sensor to report every 60 seconds instead of 30, and verify the average current is below 5 µA. If not, check GPIO states and disable all peripherals before sleep.

## Next Up

Tomorrow is the final review of the entire series. I'll compile a cheat sheet of all the key commands, configuration files, and debugging techniques from the past 24 days, plus a decision tree for choosing between BLE, Zigbee, Thread, and Matter for your next low-power wireless project.
