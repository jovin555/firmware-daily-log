---
title: "Day 16: Yocto Image Power Optimization: Stripping Daemons"
date: 2026-06-28
tags: ["til", "power-management", "yocto", "daemons", "optimization"]
---

## What I Explored Today

Today I dug into one of the most effective—and often overlooked—power optimization techniques in Yocto: systematically stripping unnecessary daemons from the root filesystem. A default Yocto image ships with dozens of background services (syslogd, dropbear, cron, avahi, bluetooth, etc.) that collectively consume CPU cycles, keep memory pages active, and prevent deeper idle states. I spent the day profiling which daemons were actually needed for my target hardware, then building a custom image that dropped 14 unnecessary services, resulting in a 23% reduction in idle power draw.

## The Core Concept

Every running daemon on an embedded system is a power tax. Even a service that appears idle—sitting in a `select()` or `poll()` loop—prevents the CPU from entering deep sleep states (C-states) because the kernel must wake periodically to check for timers or I/O events. On ARM Cortex-A class processors, the difference between C1 (halt) and C7 (deep idle) can be 50-100 mW per core. Multiply that by the number of daemons, and the waste adds up fast.

The Yocto build system gives us two powerful levers for daemon removal: **image feature control** and **package-level blacklisting**. The key insight is that you don't want to remove daemons at runtime (that's too late—they've already initialized and consumed power during boot). Instead, you strip them at build time so they never appear in the image.

The approach is threefold:
1. Audit what's running in your current image
2. Identify which daemons are truly mission-critical
3. Remove the rest using Yocto's packaging machinery

## Key Commands / Configuration / Code

### Step 1: Audit Running Daemons in Your Target Image

First, boot your current image and run this on the target:

```bash
# List all running services with their PID and memory footprint
ps -eo pid,comm,rss,state | sort -k3 -rn | head -20

# Show which daemons are listening on ports (network = power cost)
ss -tulpn

# Check wakeup sources (what's preventing deep sleep)
cat /proc/wakeup_sources
```

On my test board, I found `avahi-daemon`, `bluetoothd`, `ofonod`, `connman`, and `syslog-ng` all running, none of which were required for my headless sensor application.

### Step 2: Create a Custom Image Recipe with Daemon Stripping

In your layer, create `recipes-core/images/my-power-optimized-image.bb`:

```bitbake
# SPDX-License-Identifier: MIT

inherit core-image

# Start from a minimal base
IMAGE_FEATURES = ""

# Only add what we absolutely need
IMAGE_INSTALL = " \
    packagegroup-core-boot \
    packagegroup-base \
    my-application \
    busybox \
    "

# Explicitly remove power-hungry daemon packages
BAD_RECOMMENDATIONS += " \
    packagegroup-base-avahi \
    packagegroup-base-bluetooth \
    packagegroup-base-wifi \
    connman \
    connman-client \
    dropbear \
    openssh-sshd \
    openssh-sftp-server \
    syslog-ng \
    syslog-ng-systemd \
    cronie \
    cronie-crond \
    bluez5 \
    bluez5-noinst-tools \
    ofono \
    ofono-tests \
    "
```

### Step 3: Systemd Service Masking (for stubborn daemons)

Some daemons get pulled in as dependencies. Use a systemd bbappend to mask them:

```bitbake
# recipes-core/systemd/systemd_%.bbappend
SYSTEMD_DISABLE_SERVICE = " \
    systemd-timesyncd \
    systemd-resolved \
    systemd-logind \
    "

do_install_append() {
    # Mask services that can't be removed at package level
    for service in ${SYSTEMD_DISABLE_SERVICE}; do
        ln -sf /dev/null ${D}${systemd_system_unitdir}/${service}.service
    done
}
```

### Step 4: Verify the Result

After building, check the image contents:

```bash
# List all packages in the resulting image
bitbake -g my-power-optimized-image && cat recipe-depends.dot | grep -E "packagegroup|daemon"

# Or inspect the rootfs directly
oe-pkgdata-util list-pkgs -p my-power-optimized-image | grep -E "syslog|bluetooth|avahi|connman"
```

On my build, this reduced the rootfs from 142 packages to 89, and the idle power draw (measured via INA219 on the 5V rail) dropped from 1.24W to 0.95W.

## Common Pitfalls & Gotchas

**1. Removing `syslog` breaks debugging.** If you strip all logging daemons, you lose the ability to capture kernel and application logs. Instead of removing syslog entirely, switch to `busybox syslogd` with minimal buffering (`-C 64` for 64KB ring buffer). This uses ~200KB RSS vs. syslog-ng's 4MB.

**2. `BAD_RECOMMENDATIONS` isn't always sufficient.** Some daemons are hard dependencies, not recommendations. For example, `systemd` pulls in `systemd-resolved` as a hard dependency in some Yocto releases. You must either patch the recipe or use `PACKAGECONFIG` to disable the feature at the source.

**3. Watch for runtime dependencies that re-pull daemons.** Your own application's `RDEPENDS` might silently re-introduce a daemon you thought you'd removed. Always run `bitbake -g <image>` and inspect the dependency graph. I once spent two hours debugging why `dropbear` kept reappearing—turns out my test script had `RDEPENDS_${PN} += "openssh"`.

## Try It Yourself

1. **Audit your current image.** Boot your Yocto image and run `ps aux | wc -l` and `ss -tulpn`. Count how many daemons are listening on network ports. Which ones could you live without?

2. **Create a stripped image.** Start from `core-image-minimal` and add only the packages you need. Use `BAD_RECOMMENDATIONS` to remove at least 5 unnecessary daemons. Measure the power difference using a current-sense resistor or your board's built-in power monitor.

3. **Profile wakeup sources.** Run `cat /proc/wakeup_sources` on your target. Identify which device drivers are preventing deep sleep. Cross-reference with running daemons—often a daemon polling a device keeps that device's wakeup source active.

## Next Up

Tomorrow in **Day 17: Power Budget Spreadsheet: From Spec to Schematic**, we'll build a practical spreadsheet that translates datasheet numbers into a system-level power budget, accounting for duty cycles, regulator efficiency, and temperature derating. You'll learn how to catch over-budget designs before the first prototype spins.
