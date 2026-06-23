---
title: "Day 11: GitHub Actions for Embedded: Self-Hosted Runners"
date: 2026-06-23
tags: ["til", "hil-testing", "github-actions", "self-hosted", "ci"]
---

## What I Explored Today

Today I dug into self-hosted GitHub Actions runners for embedded CI/CD. After weeks of fighting with GitHub-hosted runners that lack ARM cross-compilers, proprietary debug probes, and physical HIL hardware access, I finally set up a dedicated machine in our lab. The result: a runner that can flash firmware over JTAG, run tests on real hardware, and push artifacts to our artifact server—all triggered by a simple `git push`. Here’s what I learned about registration, security, and the gotchas that will bite you.

## The Core Concept

GitHub-hosted runners are great for web apps—they come with Node.js, Python, and Docker pre-installed. But embedded development needs specialized toolchains: ARM GCC, IAR Embedded Workbench, Segger J-Link drivers, or proprietary SDKs. You can’t install those on a shared runner, and even if you could, you wouldn’t want to expose your license keys.

Self-hosted runners solve this by letting you run GitHub Actions workflows on your own hardware. The runner agent is a small daemon that polls GitHub for jobs, executes them on your machine, and reports results. The key insight: **the runner is stateless from GitHub’s perspective**—it’s just a worker that pulls work. All state (tools, licenses, hardware) lives on your machine.

For HIL testing, this is critical. Your runner can be a beefy workstation with a USB-connected oscilloscope, a CAN bus interface, or a rack of target boards. The workflow triggers a build, flashes the firmware via JTAG, runs the HIL test suite, and reports pass/fail—all without human intervention.

## Key Commands / Configuration / Code

### 1. Registering a Self-Hosted Runner

First, add a runner at your repo or org level: **Settings → Actions → Runners → New self-hosted runner**. GitHub gives you a token and a registration command. On your machine:

```bash
# Create a dedicated user (security best practice)
sudo useradd -r -m -s /bin/bash ghrunner
sudo usermod -aG dialout ghrunner  # for serial/JTAG access

# Download and configure the runner
mkdir actions-runner && cd actions-runner
curl -o actions-runner-linux-x64-2.317.0.tar.gz \
  -L https://github.com/actions/runner/releases/download/v2.317.0/actions-runner-linux-x64-2.317.0.tar.gz
tar xzf actions-runner-linux-x64-2.317.0.tar.gz

# Configure (use the token from GitHub UI)
./config.sh --url https://github.com/your-org/your-repo \
            --token ABCDEF1234567890 \
            --name embedded-runner-01 \
            --labels arm,stm32,jlink \
            --work _work

# Install as a service (survives reboots)
sudo ./svc.sh install ghrunner
sudo ./svc.sh start
```

**Important**: The `--labels` flag lets you target specific runners in your workflow. I use `arm` for ARM builds, `stm32` for STM32-specific tasks, and `jlink` for JTAG flashing.

### 2. Workflow Targeting the Self-Hosted Runner

```yaml
# .github/workflows/hil-test.yml
name: HIL Test Suite

on:
  push:
    branches: [main, develop]
  workflow_dispatch:

jobs:
  build-and-test:
    # Target runner by label; 'self-hosted' is implicit
    runs-on: [self-hosted, arm, stm32, jlink]

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Build firmware
        run: |
          # ARM GCC is installed on the runner
          make -C firmware clean
          make -C firmware -j$(nproc)

      - name: Flash target via JTAG
        run: |
          # J-Link Commander script
          JLinkExe -device STM32F407VG -if SWD -speed 4000 -autoconnect 1 \
            -CommanderScript flash.jlink

      - name: Run HIL tests
        run: |
          # Python test harness that talks to DUT over UART
          python3 tests/hil_runner.py --port /dev/ttyUSB0 --baud 115200

      - name: Upload test artifacts
        uses: actions/upload-artifact@v4
        with:
          name: hil-results
          path: test_results/
```

### 3. Handling Secrets (License Keys, Tokens)

Never hardcode credentials in your runner’s environment. Use GitHub Actions secrets:

```yaml
- name: Activate IAR license
  env:
    IAR_LICENSE_SERVER: ${{ secrets.IAR_LICENSE_SERVER }}
  run: |
    # IAR license tool reads from environment
    /opt/iarbuild/bin/iarbuild --license-server $IAR_LICENSE_SERVER
```

Store secrets in **Settings → Secrets and variables → Actions**. They’re masked in logs.

## Common Pitfalls & Gotchas

### 1. Runner Goes Offline After Reboot
The `svc.sh install` command creates a systemd service, but it runs as the user you specified. If that user’s home directory is on an encrypted partition or network mount that isn’t available at boot, the runner won’t start. **Fix**: Use a local ext4 partition and test `sudo systemctl status actions.runner.*` after a reboot.

### 2. Permission Denied on /dev/ttyUSB0
Your runner user needs access to serial ports, JTAG adapters, and USB devices. Adding to `dialout` group handles most serial devices, but J-Link uses udev rules. **Fix**: Install the J-Link software package (it includes udev rules) and reboot. Verify with `ls -l /dev/ttyUSB*` and `groups ghrunner`.

### 3. Workflow Hangs Waiting for Runner
If you have multiple runners with overlapping labels, GitHub may assign the job to a runner that’s busy. **Fix**: Use unique labels (e.g., `stm32-hil-01`) and set `concurrency` in your workflow to prevent queue buildup:

```yaml
concurrency:
  group: hil-tests
  cancel-in-progress: true
```

## Try It Yourself

1. **Set up a self-hosted runner on a Raspberry Pi 4** (running Ubuntu Server). Register it with labels `arm64`, `gpio`. Write a workflow that blinks an LED via GPIO to verify the runner can control hardware.

2. **Add a JTAG flashing step** to an existing firmware workflow. Use a Segger J-Link or ST-Link. Create a `.jlink` script that erases, programs, and verifies the target. Run it as a GitHub Actions step.

3. **Implement a watchdog** that pings GitHub’s API every 5 minutes to check if your runner is online. If not, send a Slack alert. Use a cron job on the runner machine.

## Next Up

Tomorrow: **Docker for Embedded Build Environments**. We’ll containerize our ARM GCC toolchain, J-Link drivers, and Python test harness so every developer (and CI runner) gets identical builds—no more “works on my machine.” We’ll also cover multi-stage Dockerfiles for cross-compilation and how to mount USB devices into containers for HIL testing.
