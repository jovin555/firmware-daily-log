---
title: "Day 26: CI/CD for Yocto: KAS, Docker & GitHub Actions"
date: 2026-07-08
tags: ["til", "yocto", "ci-cd", "kas", "docker"]
---

## What I Explored Today

Today I tackled the holy grail of embedded Linux development: reproducible, automated Yocto builds in CI/CD. After weeks of watching builds fail because of host toolchain drift, missing dependencies, or bitbake cache corruption, I finally wired up a pipeline using KAS for build configuration, Docker for environment isolation, and GitHub Actions for orchestration. The result is a build that runs identically on my laptop, a teammate's workstation, and a cloud runner.

## The Core Concept

Yocto builds are notoriously non-deterministic. The same source tree can produce different outputs depending on the host's `gcc` version, `make` version, available `pkg-config` packages, or even the timezone. This is unacceptable for CI/CD, where reproducibility is the entire point.

The solution has three layers:

1. **Docker** provides the host environment. A fixed base image (Ubuntu 22.04 with specific package versions) ensures every build starts from the same system state. No more "works on my machine."

2. **KAS** (originally "Kickoff Auto Setup") is a Yocto-specific tool that wraps bitbake with a declarative configuration file. Instead of manually sourcing `oe-init-build-env` and editing `local.conf`, you define everything—layers, machine, distro, and build targets—in a YAML file. KAS handles layer fetching, configuration merging, and build execution.

3. **GitHub Actions** ties it together. A workflow triggers on push or PR, pulls the Docker image, runs KAS inside it, and archives the resulting artifacts. The key insight: the CI runner never needs Yocto installed. It only needs Docker.

## Key Commands / Configuration / Code

### 1. The Dockerfile (yocto-builder.Dockerfile)

```dockerfile
FROM ubuntu:22.04

# Install essential Yocto host dependencies
RUN apt-get update && apt-get install -y \
    gawk wget git diffstat unzip texinfo gcc build-essential \
    chrpath socat cpio python3 python3-pip python3-pexpect \
    xz-utils debianutils iputils-ping python3-git python3-jinja2 \
    libegl1-mesa libsdl1.2-dev pylint3 xterm python3-subunit \
    mesa-common-dev zstd liblz4-tool file locales \
    && rm -rf /var/lib/apt/lists/*

# Set locale for bitbake
RUN locale-gen en_US.UTF-8 && update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8

# Install KAS
RUN pip3 install kas

# Create non-root user for build (bitbake refuses to run as root)
RUN useradd -m -u 1000 builder
USER builder
WORKDIR /home/builder
```

### 2. The KAS configuration file (kas-project.yml)

```yaml
# kas-project.yml
header:
  version: 14

machine: raspberrypi4-64
distro: poky
target:
  - core-image-minimal

repos:
  poky:
    url: https://git.yoctoproject.org/git/poky
    refspec: kirkstone
    layers:
      meta:
      meta-poky:
      meta-yocto-bsp:

  meta-raspberrypi:
    url: https://git.yoctoproject.org/git/meta-raspberrypi
    refspec: kirkstone
    layers:
      meta-raspberrypi:

local_conf_header:
  standard: |
    MACHINE = "raspberrypi4-64"
    PACKAGE_CLASSES = "package_rpm"
    # Enable sstate cache for faster CI
    SSTATE_DIR = "/home/builder/sstate-cache"
    DL_DIR = "/home/builder/downloads"
  ci_optimizations: |
    # Reduce build time in CI
    INHERIT += "rm_work"
    BB_NUMBER_THREADS = "4"
    PARALLEL_MAKE = "-j 4"
```

### 3. GitHub Actions workflow (.github/workflows/yocto-build.yml)

```yaml
name: Yocto Build

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Cache sstate and downloads
        uses: actions/cache@v3
        with:
          path: |
            sstate-cache
            downloads
          key: yocto-${{ hashFiles('kas-project.yml') }}

      - name: Build Docker image
        run: docker build -t yocto-builder -f yocto-builder.Dockerfile .

      - name: Run KAS build
        run: |
          docker run --rm \
            -v ${{ github.workspace }}:/home/builder/workspace \
            -v ${{ github.workspace }}/sstate-cache:/home/builder/sstate-cache \
            -v ${{ github.workspace }}/downloads:/home/builder/downloads \
            yocto-builder \
            bash -c "cd workspace && kas build kas-project.yml"

      - name: Archive build artifacts
        uses: actions/upload-artifact@v4
        with:
          name: yocto-image
          path: build/tmp/deploy/images/raspberrypi4-64/
          retention-days: 7
```

### 4. Running KAS locally (for testing)

```bash
# Build the Docker image once
docker build -t yocto-builder -f yocto-builder.Dockerfile .

# Run KAS interactively
docker run --rm -it \
  -v $(pwd):/home/builder/workspace \
  -v $(pwd)/sstate-cache:/home/builder/sstate-cache \
  -v $(pwd)/downloads:/home/builder/downloads \
  yocto-builder \
  bash -c "cd workspace && kas shell kas-project.yml"
```

## Common Pitfalls & Gotchas

1. **Root user in Docker**: Bitbake explicitly refuses to run as root. Always create a non-root user in your Docker image with a known UID (1000 is standard). If your CI runner uses a different UID, volume mounts will have permission issues—use `--user` flag or match the UID.

2. **Sstate cache invalidation**: The GitHub Actions cache key uses `hashFiles('kas-project.yml')`. This means any change to the KAS config invalidates the entire cache. A better approach is to use a hash of the layer lockfiles or a version string you manually bump. Otherwise, every config tweak triggers a full rebuild.

3. **Disk space exhaustion**: Yocto builds can consume 50-100 GB. GitHub Actions runners have only 14 GB of free space by default. Add a step to clean Docker images and prune the build directory between runs. Use `rm_work` in your local config to delete intermediate build artifacts.

## Try It Yourself

1. **Set up a minimal KAS project**: Create a `kas-project.yml` for `qemuarm64` with only the Poky layer. Build `core-image-minimal` using the Docker image above. Time the first build vs. a second build with sstate caching.

2. **Add a custom layer**: Extend the KAS config to include a `meta-custom` layer from a private GitHub repo. Use `kas`'s `url` and `refspec` fields with an SSH deploy key stored as a GitHub Actions secret.

3. **Implement matrix builds**: Modify the GitHub Actions workflow to build for two machines (e.g., `raspberrypi4-64` and `qemuarm64`) in parallel using a build matrix. Archive each image separately.

## Next Up

Tomorrow we tie everything together: **Full Review: Build a Complete Embedded Image**. We'll walk through a real-world project from `bitbake` invocation to flashing the SD card, covering every step we've learned in the past 26 days.
