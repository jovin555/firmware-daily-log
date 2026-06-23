---
title: "Day 11: powertop: Finding Power Hogs on Linux"
date: 2026-06-23
tags: ["til", "power-management", "powertop", "measurement", "tuning"]
---

## What I Explored Today

Today I dove into `powertop`, Intel's open-source tool that turns a Linux system into a power-profiling workstation. Unlike hardware current probes that measure total system draw, `powertop` attributes power consumption to specific processes, kernel threads, device drivers, and even individual timer frequencies. I spent the morning running it on a battery-powered ARM SBC running a custom Yocto build, then cross-checked its estimates against a shunt-resistor measurement. The correlation was within 12%—not lab-grade, but more than enough to identify the top three power hogs in my system.

## The Core Concept

`powertop` works by tapping into the kernel's existing power-management infrastructure: `perf_event_open`, `timer_stats`, and the device driver runtime PM (power management) callbacks. It doesn't measure voltage or current directly. Instead, it counts events—wakeups, C-state residency, device activity—and multiplies them by platform-specific power models derived from Intel's ACPI data or, on ARM, from the kernel's energy model.

The key insight: **wakeups are the enemy**. Every time a CPU core exits a deep idle state (C6, C7) to service an interrupt or timer, it burns a fixed overhead of energy just to ramp voltage and clock back up. A process that wakes the CPU 1000 times per second can consume more power than one that runs flat-out for 10 ms and then sleeps for 990 ms. `powertop` surfaces exactly these wakeup sources.

The tool has two modes:
- **Interactive** (`powertop`): Real-time curses UI with per-process and per-device power estimates.
- **Dump/Log** (`powertop --csv`): Machine-readable output for scripting and historical comparison.

## Key Commands / Configuration / Code

### Basic Interactive Session
```bash
# Run with default settings (requires root for full data)
sudo powertop

# Press Tab to cycle through tabs:
#   Overview  - Top power consumers (processes, interrupts, devices)
#   Idle stats - C-state residency per CPU core
#   Frequency stats - P-state (DVFS) usage
#   Device stats - Per-device runtime PM activity
#   Tunables - One-click toggles for power-saving settings
```

### CSV Dump for Analysis
```bash
# Generate a 60-second measurement, output CSV
sudo powertop --csv=/tmp/powertop_report.csv --iteration=1 --time=60

# Parse the CSV to find top processes by estimated power
awk -F',' '/Process:/ {print $2, $4, $5}' /tmp/powertop_report.csv | sort -k3 -rn | head -10
```

### Calibrating for Accurate Estimates
```bash
# First-run calibration (required on new hardware)
sudo powertop --calibrate
# This runs for ~20 minutes, cycling through C-states and P-states
# to build a power model for your specific SoC
```

### Automating Tunables
```bash
# Generate a persistent config from current tunables
sudo powertop --auto-tune

# To make tunables permanent, create a systemd service:
cat << 'EOF' | sudo tee /etc/systemd/system/powertop.service
[Unit]
Description=PowerTOP auto tune

[Service]
Type=oneshot
ExecStart=/usr/bin/powertop --auto-tune

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable powertop.service
```

### Measuring a Specific Workload
```bash
# Start logging before your workload
sudo powertop --csv=/tmp/baseline.csv --iteration=1 --time=30

# Run your workload (example: video encode)
ffmpeg -i input.mp4 -c:v libx264 output.mp4 &

# Wait for completion, then capture workload log
sudo powertop --csv=/tmp/workload.csv --iteration=1 --time=30

# Compare total estimated power
grep "Summary:" /tmp/baseline.csv /tmp/workload.csv
```

## Common Pitfalls & Gotchas

**1. Power estimates are relative, not absolute.**
`powertop` reports "estimated power" in Watts, but these are derived from generic power models. On an i.MX8M Plus, I saw it report 0.8 W for the GPU when the actual GPU rail was drawing 1.4 W. Use the numbers to find *ratios* and *trends*, not to size your battery. Always cross-check with a hardware power monitor for final validation.

**2. Requires root, and some kernels lack necessary stats.**
Without root, you get zero data. Worse, some embedded kernels disable `CONFIG_TIMER_STATS` or `CONFIG_POWERCAP` to save space. Run `sudo powertop --debug` to see which components are missing. On Yocto, add `powertop` and `kernel-module-intel-rapl` (even on ARM—it provides the energy model framework) to your image.

**3. Calibration is mandatory on new hardware, but can crash.**
`powertop --calibrate` forces the system through all C-states, including deep sleep. On some SBCs with flaky PMIC drivers, this can cause a lockup or watchdog reset. Run it over a serial console, not SSH, and be prepared to power-cycle. After calibration, the model is cached in `/var/run/powertop`.

## Try It Yourself

1. **Find your top wakeup source:** Run `sudo powertop` on your embedded Linux system. Switch to the "Idle stats" tab and note which CPU core has the lowest C6 residency. Then switch to "Overview" and identify the process or interrupt causing the most wakeups per second.

2. **Profile a workload delta:** Capture a 30-second baseline CSV, then run `stress --cpu 4 --timeout 30` and capture another CSV. Use `awk` to compute the difference in estimated power for the `stress` process. Compare it to the increase in total system power reported by `powertop`.

3. **Apply and verify a tunable:** On the "Tunables" tab, toggle "Autosuspend for USB devices" to "Good". Re-run your CSV capture and compare the "Device stats" section. Did the USB controller's wakeup count drop? Did total estimated power decrease?

## Next Up

Tomorrow, we go from software estimation to hardware precision: **Nordic PPK2: Per-Microsecond Current Profiling**. We'll wire up the PPK2 to a nRF52840 board, capture a current waveform from boot through BLE advertisement, and learn why microsecond-level resolution matters for battery life calculations.

---
*Day 11 of the Power Management & Energy Profiling Daily Log. All commands tested on Linux 6.6 with powertop v2.15.*
