---
title: "Day 11: Automatic Rollback on Boot Failure & Watchdog-Triggered Recovery"
date: 2026-07-11
tags: ["til", "secure-ota", "rollback", "watchdog"]
---

## What I Explored Today

Today I implemented the safety net that every OTA system needs: automatic rollback when a new update fails to boot, combined with a hardware watchdog that catches even kernel panics or hung userspace. I wired up a dual-bank A/B scheme on an i.MX6ULL target, where the bootloader (U-Boot) checks a `bootcount` variable, increments it on each boot attempt, and if it exceeds a threshold before userspace clears it, the bootloader flips back to the known-good partition. The hardware watchdog provides the final hammer: if the application or kernel locks up before the watchdog is fed, the SoC resets, the bootcounter increments again, and after N failures the rollback triggers automatically.

## The Core Concept

The fundamental problem: an OTA update can flash perfectly but the new firmware might hang on boot due to a driver regression, corrupted filesystem, or a race condition in init. Without automatic recovery, the device becomes a brick. The solution is a two-layer safety net:

1. **Bootcounter + Bootloader Logic** – The bootloader (U-Boot, GRUB, or custom) maintains a persistent counter in environment storage (e.g., MMC boot partition, EEPROM). On each boot, it increments the counter. The newly booted userspace must explicitly reset the counter to zero after it has verified system health. If the counter exceeds a threshold (e.g., 3), the bootloader switches to the alternate slot.

2. **Hardware Watchdog** – A dedicated timer peripheral (or external watchdog IC) that must be periodically "kicked" by software. If the kernel or init process hangs, the watchdog fires a hardware reset. This reset triggers the bootcounter increment, eventually causing a rollback. The watchdog prevents "soft" hangs that don't crash the kernel but leave the system unresponsive.

The key insight: the bootcounter alone can't detect a hung kernel (it never runs userspace to clear the counter), and the watchdog alone can't distinguish between a transient glitch and a persistent bad update. Together, they form a robust recovery mechanism.

## Key Commands / Configuration / Code

### U-Boot Environment Setup (on target, via `fw_setenv` or U-Boot shell)

```bash
# Set bootcounter limit and initial value
fw_setenv bootlimit 3
fw_setenv bootcount 0

# Define the rollback logic in U-Boot's bootcmd
# This goes into the board's U-Boot source or saved environment
setenv bootcmd 'if test ${bootcount} -ge ${bootlimit}; then echo "Boot limit reached, rolling back"; run altbootcmd; else setexpr bootcount ${bootcount} + 1; saveenv; echo "Boot attempt ${bootcount}"; run mmcboot; fi'

# altbootcmd points to the other slot (e.g., mmc 0:2 instead of mmc 0:1)
setenv altbootcmd 'setenv mmcdev 0; setenv mmcpart 2; run mmcargs; bootz ${loadaddr} - ${fdt_addr}'
saveenv
```

### Userspace Bootcounter Reset Script (systemd service)

```ini
# /etc/systemd/system/clear-bootcounter.service
[Unit]
Description=Clear U-Boot bootcounter after successful boot
DefaultDependencies=no
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/usr/sbin/fw_setenv bootcount 0
RemainAfterExit=yes

[Install]
WantedBy=sysinit.target
```

```bash
# Enable the service
systemctl enable clear-bootcounter.service
```

### Watchdog Configuration (Linux kernel watchdog daemon)

```bash
# Install watchdog daemon
apt-get install watchdog

# /etc/watchdog.conf
watchdog-device = /dev/watchdog
watchdog-timeout = 30
interval = 10
# If watchdog daemon itself hangs, hardware reset fires after 30s
realtime = yes
priority = 1

# Enable and start
systemctl enable watchdog
systemctl start watchdog
```

### Kernel Watchdog Driver (if using internal SoC watchdog)

```c
// Example: i.MX6 watchdog initialization in device tree
// arch/arm/boot/dts/imx6ull.dtsi
&wdog1 {
    status = "okay";
    timeout-sec = <30>;  // 30 second timeout
};
```

## Common Pitfalls & Gotchas

1. **Bootcounter Storage Corruption** – If the bootcounter is stored in the same flash partition as the bootloader environment, a failed write during a power loss can corrupt the environment entirely. Mitigation: use redundant environment blocks (U-Boot supports `CONFIG_ENV_IS_IN_MMC` with redundant copies) or store the counter in a separate EEPROM/OTP region.

2. **Watchdog Timeout Too Short** – A 5-second watchdog might fire during a slow filesystem check (fsck) on a large rootfs. Always set the watchdog timeout to at least 2x the worst-case boot time, including kernel decompression, initramfs, and fsck. Measure with `systemd-analyze blame` or `bootchart`.

3. **Userspace Bootcounter Clear Before System Ready** – If the bootcounter is cleared too early (e.g., in an initramfs script before critical services start), a subsequent hang won't trigger rollback. Always clear the counter only after confirming core services (network, watchdog daemon, application) are healthy. Use a `ConditionPathExists` or a health-check script.

## Try It Yourself

1. **Simulate a bad update**: Flash a deliberately broken kernel (e.g., add `panic=1` to cmdline) to the inactive slot. Configure bootcounter limit to 2. Power cycle the device and observe U-Boot's rollback after two failed boots. Verify with `fw_printenv bootcount`.

2. **Test watchdog recovery**: Disable the watchdog daemon (`systemctl stop watchdog`). Write a small kernel module that enters an infinite loop in a workqueue (no schedule()). Observe the hardware reset after the watchdog timeout (check kernel ring buffer for "watchdog: BUG: soft lockup"). Confirm bootcounter increments on next boot.

3. **Implement a health-check service**: Write a systemd service that runs a connectivity test (e.g., ping gateway) and only clears the bootcounter if the test passes. If the test fails 3 times in a row, force a rollback by setting `bootcount` to `bootlimit` and rebooting.

## Next Up

Tomorrow, I'll dive into the internals of two production-grade open-source OTA frameworks: **mender.io** and **RAUC**. We'll compare their update strategies, artifact formats, and how they handle rollback and recovery out of the box.
