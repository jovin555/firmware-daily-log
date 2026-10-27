---
title: "Day 17: Self-Hosted Runners for Embedded & Hardware-in-the-Loop Builds"
date: 2026-10-27
tags: ["til", "github-mastery", "self-hosted-runners", "hil"]
---

# Day 17: Self-Hosted Runners for Embedded & Hardware-in-the-Loop Builds

## What I Explored Today

Today I wired up a self-hosted GitHub Actions runner on a bench machine that has an ST-Link V3, a J-Link EDU, and a Raspberry Pi Pico permanently attached via USB. The goal: run hardware-in-the-loop (HIL) tests on every PR without shipping boards to the cloud. I walked through the runner registration flow, the `runs-on` label matching, and the service install on Linux. The interesting part wasn't getting a runner online — that's a five-minute job — it was making it *safe* to run untrusted PR code on a machine with real hardware and real credentials attached.

## The Core Concept

GitHub-hosted runners are ephemeral VMs. That's a feature for security and a bug for embedded work: no USB, no JTAG, no serial ports, no vendor toolchains that require a license dongle or a 4 GB installer. Self-hosted runners flip the tradeoff — you get persistent hardware and pre-installed toolchains, but you also inherit the responsibility for isolation, cleanup, and access control.

The mental model that matters: **a self-hosted runner is a long-lived process that executes arbitrary code from anyone who can open a PR against your repo** (unless you lock that down). For HIL specifically, that means a malicious PR could flash your board, brick a bootloader, or exfiltrate anything the runner's user can read. The mitigation isn't "trust the PRs" — it's label scoping, environment protection rules, and treating the bench machine as a semi-trusted appliance that gets reset between jobs.

The second concept is **label routing**. `runs-on: self-hosted` is a footgun; `runs-on: [self-hosted, linux, hil, stm32]` is a contract. Labels are how you ensure a job that needs a J-Link doesn't land on the runner that only has a Pico.

## Key Commands / Configuration / Code

Registering a runner on the bench machine (Linux, systemd):

```bash
# Download the runner tarball (check the latest release URL on the Actions/runners page)
mkdir -p ~/actions-runner && cd ~/actions-runner
curl -o actions-runner.tar.gz -L \
  https://github.com/actions/runner/releases/download/v2.319.1/actions-runner-linux-x64-2.319.1.tar.gz
tar xzf actions-runner.tar.gz

# Configure with custom labels — the token comes from
# Settings → Actions → Runners → New self-hosted runner
./config.sh \
  --url https://github.com/your-org/your-repo \
  --token <REGISTRATION_TOKEN> \
  --name bench-01 \
  --labels self-hosted,linux,hil,stm32,jlink \
  --work _work \
  --unattended

# Install as a systemd service so it survives reboots
sudo ./svc.sh install
sudo ./svc.sh start
sudo ./svc.sh status
```

A workflow that targets the HIL runner and gates on a protected environment:

```yaml
name: hil-test
on:
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: cmake -B build -DCMAKE_TOOLCHAIN_FILE=arm-none-eabi.cmake
      - run: cmake --build build
      - uses: actions/upload-artifact@v4
        with:
          name: firmware
          path: build/firmware.elf

  hil:
    needs: build
    # Label match is exact — this job only lands on runners with all four labels
    runs-on: [self-hosted, linux, hil, stm32]
    # Require manual approval before running untrusted code on real hardware
    environment: hil-bench
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: firmware
      - name: Flash and test
        run: |
          # openocd is pre-installed on the bench image
          openocd -f interface/stlink.cfg -f target/stm32f4x.cfg \
            -c "program firmware.elf verify reset exit"
          # pytest-hil drives the serial port and asserts on responses
          pytest tests/hil/ --serial /dev/ttyACM0 --timeout 30
      - name: Reset bench state
        if: always()
        run: ./scripts/reset-bench.sh   # power-cycle via USB hub, clear logs
```

The `environment: hil-bench` line is doing heavy lifting: configure it in repo settings with required reviewers so PRs from forks can't auto-execute on your hardware.

## Common Pitfalls & Gotchas

**1. `runs-on: self-hosted` matches *any* self-hosted runner in the org.** If you have a GPU runner and a HIL runner, a job labeled just `self-hosted` can land on either. Always use the full label set. I've seen a job silently pass because it ran on a machine that happened to have the right toolchain installed by accident.

**2. Workspace and hardware state leak between jobs.** Unlike hosted runners, `_work/` persists. A previous job's `firmware.elf` can shadow a fresh build if your paths collide, and a crashed HIL test can leave a board in DFU mode. Add an `if: always()` cleanup step and consider `actions/checkout` with `clean: true` (the default, but worth knowing).

**3. Fork PRs are a security boundary, not a convenience.** By default, workflows triggered by `pull_request` from forks run with a read-only `GITHUB_TOKEN` and no secrets — but they *do* run on your self-hosted runner if labels match. GitHub explicitly recommends against self-hosted runners on public repos for this reason. For private repos, use environment protection rules with required reviewers, or gate the HIL job behind a `workflow_run` trigger that only fires after a maintainer labels the PR.

## Try It Yourself

1. **Register a runner with a custom label set** on any machine you control (a spare laptop works). Confirm it appears under Settings → Actions → Runners with your labels, then write a trivial workflow with `runs-on: [self-hosted, <your-label>]` and watch it pick up the job.
2. **Break the label match on purpose.** Change the workflow to `runs-on: [self-hosted, nonexistent-label]` and observe the job queue forever. This is the single most common "why isn't my job running" question — now you'll recognize it instantly.
3. **Add an environment with required reviewers** to your HIL job and open a PR from a branch. Verify the job pauses at "Waiting for approval" and that the reviewer sees the environment name in the UI.

## Next Up

Tomorrow: **GITHUB_TOKEN Permissions & OIDC: Least Privilege in CI** — how to stop handing out `write-all` tokens, why `id-token: write` is the only permission you need for cloud auth, and how to audit what your workflows can actually do.
