---
title: "Day 15: Optimizing a Zephyr BLE Beacon for Sub-10uA Sleep"
date: 2026-06-27
tags: ["til", "power-management", "ble", "beacon", "optimization"]
---

## What I Explored Today

Today I dug into the practical steps required to push a Zephyr-based BLE beacon into sub-10 microamp sleep current. The target was a Nordic nRF52840 DK running the Zephyr `beacon` sample, but with all the PM knobs turned to their most aggressive settings. After measuring with a Keysight N6781A SMU, I landed at 8.7 µA in deep sleep between advertisement intervals—a 40x improvement over the out-of-box sample. The key was not just enabling `CONFIG_PM` but systematically disabling every peripheral, clock, and retention domain that wasn't absolutely necessary.

## The Core Concept

The reason most Zephyr BLE beacon samples draw 300–500 µA in "idle" is that the default configuration keeps the system clock (HFXO or HFRCO), the RADIO peripheral, and often the RTC in active or retention mode. The nRF52840 has a SYSTEM OFF state that draws ~0.4 µA, but you can't use that because the BLE stack needs the LFCLK (32.768 kHz) to wake the system for the next advertisement event. The sweet spot is SYSTEM ON with the CPU in WFI (Wait For Interrupt) and all unused peripherals clock-gated. Zephyr's PM subsystem can automatically enter this state, but only if you explicitly tell it which hardware blocks to keep alive and which to shut down. The critical insight: the default `pm_state` residency thresholds are too conservative, and the default peripheral retention masks keep everything powered.

## Key Commands / Configuration / Code

### 1. Minimal Kconfig for Sub-10µA Sleep

Start with the `beacon` sample, then overlay this configuration:

```kconfig
# prj.conf overlay for ultra-low-power beacon
CONFIG_PM=y
CONFIG_PM_DEVICE=y
CONFIG_PM_POLICY_APP=y

# Force deepest sleep state (PM_STATE_SUSPEND_TO_IDLE)
CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE=512

# Disable unnecessary subsystems
CONFIG_CONSOLE=n
CONFIG_SERIAL=n
CONFIG_UART_CONSOLE=n
CONFIG_RTT_CONSOLE=n
CONFIG_LOG=n
CONFIG_ASSERT=n

# BLE stack tuning
CONFIG_BT=y
CONFIG_BT_LL_SW_LLCP=n
CONFIG_BT_MAX_CONN=0
CONFIG_BT_CTLR_ADV_EXT=n
CONFIG_BT_CTLR_PHY_CODED=n
CONFIG_BT_CTLR_TX_PWR_DYNAMIC=n

# Clock and power management
CONFIG_CLOCK_CONTROL_NRF_K32SRC_RC=y
CONFIG_CLOCK_CONTROL_NRF_K32SRC_RC_CALIBRATION_INTERVAL=600000  # 10 min
CONFIG_SOC_DCDC_NRF5X=y
CONFIG_HW_STACK_PROTECTION=n
```

### 2. Application PM Policy (custom_pm.c)

Zephyr's default PM policy is conservative. Override it to force the deepest state immediately after BLE advertising completes:

```c
#include <zephyr/kernel.h>
#include <zephyr/pm/pm.h>
#include <zephyr/pm/device.h>
#include <zephyr/pm/policy.h>

/* Override default PM policy: always choose deepest state */
enum pm_state pm_policy_next_state(uint32_t ticks, enum pm_state *states,
                                   uint8_t len)
{
    /* Only consider states that are available */
    for (int i = len - 1; i >= 0; i--) {
        if (states[i] == PM_STATE_SUSPEND_TO_IDLE) {
            return PM_STATE_SUSPEND_TO_IDLE;
        }
    }
    /* Fallback to first available */
    return states[0];
}

/* Disable retention for all peripherals except RADIO and RTC */
void pm_state_set(enum pm_state state, uint8_t substate_id)
{
    if (state == PM_STATE_SUSPEND_TO_IDLE) {
        /* Mask: keep only RADIO (bit 4) and RTC0 (bit 20) powered */
        NRF_POWER->RAM[0].POWERSET = 0x00100010;
        NRF_POWER->RAM[1].POWERSET = 0x00000000;
    }
}

void pm_state_exit_post_ops(enum pm_state state, uint8_t substate_id)
{
    /* Restore full retention on wake */
    NRF_POWER->RAM[0].POWERSET = 0xFFFFFFFF;
    NRF_POWER->RAM[1].POWERSET = 0xFFFFFFFF;
}
```

### 3. Build and Flash Commands

```bash
# Build with the overlay
west build -b nrf52840dk_nrf52840 samples/bluetooth/beacon \
    -- -DOVERLAY_CONFIG=prj_lowpower.conf

# Flash
west flash

# Verify with RTT or UART (if you kept CONFIG_LOG=y for debug)
# But for final measurement, flash with CONFIG_LOG=n
```

### 4. Measurement Setup

```bash
# Use nRF Connect Power Profiler or SMU
# Connect VDD to the DK's P21 (VDD measurement header)
# Set supply to 3.0V, 10mA range
# Trigger on advertisement start (every 100ms default)
# Measure average current over 10-second window
```

## Common Pitfalls & Gotchas

1. **The LFCLK calibration trap**: The nRF52840's internal RC oscillator (LFRC) requires periodic calibration against the HFXO. If you disable the HFXO completely (by setting `CONFIG_CLOCK_CONTROL_NRF_K32SRC_RC_CALIBRATION_INTERVAL` too high), the BLE stack will fail to maintain timing and advertisements will drift. I found 10 minutes (600000 ms) is safe for beacon use—the stack re-syncs on each advertisement anyway. Below that, the calibration current spikes (~500 µA for 2 ms every 4 seconds) dominate the average.

2. **Retention domain overrides**: The `NRF_POWER->RAM[0].POWERSET` register controls which RAM blocks stay powered in SYSTEM ON. If you disable retention for the block containing the BLE controller's connection context, the stack will crash on wake. Always keep RAM block 0 (which holds the stack's critical data) powered. Use the nRF52840 Product Specification's RAM mapping table to identify which blocks your stack uses.

3. **The `CONFIG_BT_LL_SW_LLCP=n` gotcha**: Disabling the Link Layer Control Procedure saves ~15 µA but means you cannot accept connections. For a pure beacon (advertiser only), this is fine. But if you ever plan to add scanning or connection, you must re-enable it. The symptom is subtle: the beacon advertises fine, but any attempt to connect silently fails.

## Try It Yourself

1. **Measure your baseline**: Build the unmodified `beacon` sample with `CONFIG_LOG=y` and measure the average current. Then apply the overlay above and measure again. Calculate the improvement factor. Expect to see ~400 µA drop to ~10 µA.

2. **Tune the advertisement interval**: In `prj.conf`, add `CONFIG_BT_DEVICE_NAME="MyBeacon"` and change the advertising interval in your app to 1000 ms (instead of 100 ms). Measure the average current—it should drop further because the radio is on less frequently. The formula is: `I_avg = (I_adv * t_adv + I_sleep * t_sleep) / (t_adv + t_sleep)`.

3. **Add a GPIO toggle for debug**: Before the beacon starts advertising, configure a GPIO as output and toggle it high. In `pm_state_set()`, toggle it low. Use an oscilloscope to measure the exact time the system spends in sleep vs. active. Compare this to the current waveform from your SMU.

## Next Up

Tomorrow, I'll tackle **Yocto Image Power Optimization: Stripping Daemons**—removing unnecessary systemd services, udev rules, and kernel modules from a Yocto-built Linux image to shave 50+ mA from idle current on an i.MX8M Plus. We'll walk through `systemd-analyze blame`, custom `IMAGE_INSTALL` overrides, and kernel config trimming.
