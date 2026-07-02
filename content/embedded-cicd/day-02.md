---
title: "Day 02: Reproducible Builds: Pinning Compiler, SDK & Dependency Versions"
date: 2026-07-02
tags: ["til", "embedded-cicd", "reproducible-builds"]
---

## What I Explored Today

Today I dug into the single most frustrating failure mode in embedded CI/CD: the "works on my machine" problem, but amplified across a team of firmware engineers. I spent the morning breaking a build intentionally by upgrading a toolchain, then spent the afternoon locking everything down with version pinning. The result? A build that produces identical binaries regardless of who runs it, when, or on which host.

## The Core Concept

Embedded builds are notoriously fragile because they depend on a chain of tools: the ARM GCC compiler, the vendor SDK (STM32Cube, ESP-IDF, Zephyr), linker scripts, Python-based build tools, and often proprietary flashing utilities. If any link in that chain changes—even a minor patch version—your binary can change behavior silently.

**Reproducible builds** mean that given the same source code at the same commit, you get *bit-for-bit identical* output artifacts. This isn't just about convenience; it's about safety. When a field failure occurs, you need to prove the binary matches the source. When an auditor asks for SBOM compliance, you need to know exactly which toolchain built your firmware. When a new hire clones your repo and `make` fails, you need to know it's their environment, not your code.

The solution is ruthless version pinning. Every tool, every SDK, every Python package gets a specific version, and the build system enforces it.

## Key Commands / Configuration / Code

### 1. Toolchain Version Pinning with a Manifest File

Instead of assuming `arm-none-eabi-gcc` is installed, create a `toolchain.yml` manifest:

```yaml
# toolchain.yml
toolchain:
  name: arm-gnu-toolchain
  version: "12.3.rel1"
  url: "https://developer.arm.com/-/media/Files/downloads/gnu/12.3.rel1/binrel/arm-gnu-toolchain-12.3.rel1-x86_64-arm-none-eabi.tar.xz"
  sha256: "a7e5c2c1d3f4b5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0"
```

Then in your `Makefile`, validate before building:

```makefile
# Makefile (excerpt)
TOOLCHAIN_VERSION := 12.3.rel1
REQUIRED_SHA := a7e5c2c1d3f4b5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0

check-toolchain:
	@echo "Checking toolchain version..."
	@CURRENT_VERSION=$$(arm-none-eabi-gcc --version | head -1 | grep -oP '[\d]+\.[\d]+\.[\w]+'); \
	if [ "$$CURRENT_VERSION" != "$(TOOLCHAIN_VERSION)" ]; then \
		echo "ERROR: Expected toolchain $(TOOLCHAIN_VERSION), got $$CURRENT_VERSION"; \
		exit 1; \
	fi
	@echo "Toolchain version OK"
```

### 2. SDK Version Locking with Git Submodules

Vendor SDKs change constantly. Pin them to a specific commit:

```bash
# Instead of git clone with latest, use a specific tag
git submodule add https://github.com/STMicroelectronics/STM32CubeF4.git \
  third_party/STM32CubeF4
cd third_party/STM32CubeF4
git checkout v1.28.0  # Pin to a release tag
cd ../..
git add .gitmodules third_party/STM32CubeF4
git commit -m "Pin STM32CubeF4 to v1.28.0"
```

In your build script, enforce the submodule state:

```bash
# ci/build.sh
git submodule update --init --recursive --checkout
# --checkout ensures we stay on the pinned commit, not the branch HEAD
```

### 3. Python Dependency Pinning with pip freeze

Most modern embedded toolchains (ESP-IDF, Zephyr, PlatformIO) use Python. Lock every dependency:

```bash
# Generate a locked requirements file
pip install -r requirements.in
pip freeze > requirements.txt
```

Your `requirements.in` might look like:

```
# requirements.in (loose constraints)
pyserial>=3.5
cryptography>=41.0.0
```

And the generated `requirements.txt` pins everything:

```
# requirements.txt (exact versions)
cryptography==41.0.7
pyserial==3.5
cffi==1.16.0
pycparser==2.21
```

### 4. Docker as the Ultimate Pin

For maximum reproducibility, wrap everything in a Docker image:

```dockerfile
# Dockerfile
FROM ubuntu:22.04

# Pin apt packages
RUN apt-get update && apt-get install -y \
    build-essential=12.9ubuntu3 \
    cmake=3.22.1-1ubuntu1.22.04.2 \
    python3=3.10.12-1~22.04.4 \
    && rm -rf /var/lib/apt/lists/*

# Install pinned toolchain
RUN wget -q https://developer.arm.com/.../arm-gnu-toolchain-12.3.rel1-x86_64-arm-none-eabi.tar.xz \
    && echo "a7e5c2c1...  arm-gnu-toolchain-12.3.rel1-x86_64-arm-none-eabi.tar.xz" | sha256sum -c \
    && tar -xf arm-gnu-toolchain-12.3.rel1-x86_64-arm-none-eabi.tar.xz -C /opt

ENV PATH="/opt/arm-gnu-toolchain-12.3.rel1-x86_64-arm-none-eabi/bin:${PATH}"
```

Then build with:

```bash
docker build -t firmware-builder:v1.0.0 .
docker run --rm -v $(pwd):/workspace firmware-builder:v1.0.0 make
```

## Common Pitfalls & Gotchas

1. **Semantic versioning lies to you.** Vendor SDKs often bump the minor version but break APIs silently. Always pin to the exact tag or commit hash, not a version range like `>=1.0, <2.0`. I've seen `STM32Cube_FW_F4 v1.27.0` compile fine while `v1.28.0` introduced a HAL API change that caused a hard fault.

2. **Host OS packages drift.** Even with a Dockerfile, `apt-get install build-essential` pulls the latest patch version available in the Ubuntu repo at build time. Pin the exact package version as shown above, or use a Docker image tag like `ubuntu:22.04-20240126` to freeze the entire OS snapshot.

3. **Python virtual environments in CI are ephemeral.** If you run `pip install` without a lockfile in CI, you'll get whatever versions are latest that day. Always commit `requirements.txt` and install with `pip install -r requirements.txt --no-deps` to avoid pulling in unpinned transitive dependencies.

## Try It Yourself

1. **Pin your toolchain today.** Find your current compiler version (`arm-none-eabi-gcc --version`), add a version check to your Makefile or CMakeLists.txt, and commit it. Watch it fail on a teammate's machine if they have a different version.

2. **Lock your Python dependencies.** Run `pip freeze > requirements.txt` in your project's virtual environment. Add a CI step that runs `pip install -r requirements.txt` and verify the build still works.

3. **Create a minimal Docker build image.** Write a Dockerfile that installs your exact toolchain and SDK versions. Build it, tag it with a version number, and run your firmware build inside it. Compare the binary hash with a native build.

## Next Up

Tomorrow we'll tackle **GitLab CI & Jenkins Pipelines for Multi-Board Firmware Projects**—how to structure pipeline definitions that build, test, and deploy firmware for three different MCU targets from a single repository, without duplicating configuration. We'll cover matrix builds, artifact passing, and the dreaded "but it worked on the other board" problem.
