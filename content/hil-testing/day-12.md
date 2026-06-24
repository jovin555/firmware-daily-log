---
title: "Day 12: Docker for Embedded Build Environments"
date: 2026-06-24
tags: ["til", "hil-testing", "docker", "build-environment"]
---

## What I Explored Today

Today I tackled one of the most persistent pain points in embedded CI/CD: build environment reproducibility. After years of "works on my machine" syndrome with cross-compilers, toolchain versions, and vendor SDKs, I finally committed to containerizing our entire embedded build pipeline with Docker. The goal was simple—any developer, any CI runner, any OS should produce byte-identical firmware binaries from the same commit. I spent the day migrating our ARM Cortex-M build from a Jenkins slave with hand-configured GCC ARM Embedded to a Docker image that bakes in the exact toolchain, CMake version, and Python dependencies. The result: a 15-line Dockerfile that eliminated three pages of setup documentation.

## The Core Concept

Embedded build environments are notoriously fragile. A developer on Ubuntu 20.04 uses GCC ARM 9-2020-q2-update; another on macOS uses a Homebrew-installed arm-none-eabi-gcc 10.3; the CI server runs Debian 11 with yet another version. Each produces slightly different object code, and when a linker script relies on specific section alignment or a compiler bug fix, you get silent failures or "works in debug, crashes in release" nightmares.

Docker solves this by treating the entire build environment as a version-controlled artifact. Instead of documenting "install these 12 packages, set these 5 environment variables, and pray," you write a Dockerfile that declares the exact base OS, toolchain tarball, SDK version, and build dependencies. This image is built once, tagged with a version (e.g., `gcc-arm-10.3-2021.10`), and pulled by every developer and CI agent. The build itself runs inside a container—no host toolchain pollution, no "but I have Python 3.8" conflicts.

For HIL testing, this is critical. The binary flashed to the target must be the same binary that passed unit tests and static analysis. Docker guarantees that the CI build and the developer's local build use identical compiler flags, library versions, and even `ld` behavior. It also makes onboarding trivial: new engineers run `docker pull` and `docker run`, not a 30-minute setup script.

## Key Commands / Configuration / Code

Here's the Dockerfile I used for our STM32H7 project. It uses a multi-stage build to keep the final image small—only the toolchain and build tools, no source code.

```dockerfile
# Stage 1: Base toolchain
FROM ubuntu:22.04 AS toolchain

# Prevent interactive prompts during apt
ENV DEBIAN_FRONTEND=noninteractive

# Install build essentials and Python for scripting
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    xz-utils \
    make \
    cmake \
    ninja-build \
    python3 \
    python3-pip \
    git \
    && rm -rf /var/lib/apt/lists/*

# Download and install ARM GCC toolchain (exact version)
RUN wget -q https://developer.arm.com/-/media/Files/downloads/gnu-rm/10.3-2021.10/gcc-arm-none-eabi-10.3-2021.10-x86_64-linux.tar.bz2 \
    && tar -xjf gcc-arm-none-eabi-10.3-2021.10-x86_64-linux.tar.bz2 -C /opt \
    && rm gcc-arm-none-eabi-10.3-2021.10-x86_64-linux.tar.bz2

# Set path so CMake finds the cross-compiler
ENV PATH="/opt/gcc-arm-none-eabi-10.3-2021.10/bin:${PATH}"

# Install Python packages for test scripting
RUN pip3 install --no-cache-dir pyserial pytest

# Stage 2: Minimal runtime image
FROM ubuntu:22.04 AS runtime
COPY --from=toolchain /opt/gcc-arm-none-eabi-10.3-2021.10 /opt/gcc-arm-none-eabi-10.3-2021.10
COPY --from=toolchain /usr/bin/make /usr/bin/make
COPY --from=toolchain /usr/bin/cmake /usr/bin/cmake
COPY --from=toolchain /usr/bin/ninja /usr/bin/ninja
COPY --from=toolchain /usr/local/lib/python3.10 /usr/local/lib/python3.10
ENV PATH="/opt/gcc-arm-none-eabi-10.3-2021.10/bin:/usr/bin:${PATH}"
WORKDIR /workspace
```

Build and run the container:

```bash
# Build the image (do this once per toolchain update)
docker build -t embedded-builder:gcc-arm-10.3 .

# Build firmware from project root
docker run --rm -v $(pwd):/workspace embedded-builder:gcc-arm-10.3 \
    cmake -B build -G Ninja -DCMAKE_TOOLCHAIN_FILE=arm-gcc-toolchain.cmake && \
    cmake --build build
```

The `-v $(pwd):/workspace` mounts your source code into the container. The build outputs (`.elf`, `.hex`, `.bin`) land in the mounted directory, so you can flash them directly from the host.

For CI (GitHub Actions example):

```yaml
jobs:
  build:
    runs-on: ubuntu-22.04
    container:
      image: your-registry/embedded-builder:gcc-arm-10.3
    steps:
      - uses: actions/checkout@v4
      - name: Build firmware
        run: |
          cmake -B build -G Ninja -DCMAKE_TOOLCHAIN_FILE=arm-gcc-toolchain.cmake
          cmake --build build
```

## Common Pitfalls & Gotchas

1. **File ownership and permissions**: When you mount a host directory into a container, files created by the container (like build artifacts) are owned by the container's user (usually root). This causes permission headaches on the host. Fix by running the container with `--user $(id -u):$(id -g)` and ensuring the workspace directory is writable by that UID.

2. **Toolchain path inside CMake**: Don't hardcode the toolchain path in your CMakeLists.txt. Instead, set `CMAKE_TOOLCHAIN_FILE` at configure time and use `find_program` in the toolchain file. The toolchain path inside the container is fixed; on a developer's native machine, it may differ. Keep the Docker image's `PATH` correct and let CMake discover the compiler.

3. **Layer caching and apt updates**: If you run `apt-get update` without pinning the Ubuntu version tag, your Docker build cache breaks whenever the apt sources change. Always use a specific base image tag (e.g., `ubuntu:22.04`, not `ubuntu:latest`). For toolchain tarballs, pin the exact URL and version—don't use a "latest" redirect.

## Try It Yourself

1. **Containerize your current toolchain**: Pick an embedded project you maintain. Write a Dockerfile that installs your exact compiler version and build dependencies. Build the image and verify that `arm-none-eabi-gcc --version` inside the container matches your reference build.

2. **Add a build script entry point**: Create a `docker-build.sh` that wraps the `docker run` command with proper volume mounts and user ID mapping. Ensure the script accepts build targets (e.g., `./docker-build.sh release` runs `cmake --build build --config Release`).

3. **Integrate with your CI**: If you use GitHub Actions, GitLab CI, or Jenkins, modify your pipeline to use the Docker image as the build container. Run a full build and compare the SHA256 of the output binary with a local container build from the same commit—they should match exactly.

## Next Up

Tomorrow, I'll dive into **CMake & CTest: Unified Build & Test System**, showing how to structure embedded CMake projects so that `ctest` runs unit tests on the host, integration tests on the target, and reports results in a CI-friendly JUnit XML format—all from a single build tree.
