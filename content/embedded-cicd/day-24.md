---
title: "Day 24: Full Review & Project: Release Engineering for a Multi-Board Product Line"
date: 2026-07-24
tags: ["til", "embedded-cicd", "review", "project"]
---

## What I Explored Today

Today I stepped back from individual pipeline stages to tackle the full release engineering problem for a product line shipping firmware across three distinct hardware variants: a high-end sensor hub (STM32H7), a mid-range actuator controller (STM32G4), and a low-power edge node (nRF52840). Each board shares about 60% of the application code but diverges in HAL layers, linker scripts, and peripheral drivers. The goal was a single CI/CD pipeline that produces auditable, versioned, and signed firmware artifacts for all three targets from one repository, with zero manual intervention between commit and release.

## The Core Concept

Release engineering for multi-board products is fundamentally a **matrix build with conditional composition**. The naive approach—three separate pipelines or manual branch-per-board—guarantees drift, missed patches, and release chaos. The correct pattern is a single pipeline that parameterizes the build matrix by board target, then uses preprocessor defines and board-specific configuration files to produce distinct artifacts. The critical insight is that the *release process* (versioning, signing, packaging) is identical across boards; only the *build configuration* changes. This means your CI/CD system should treat the board as a build matrix dimension, not a separate workflow.

The real challenge isn't the build—it's **traceability**. When you ship three different binaries from the same commit, you must be able to prove which source version produced which binary, for each board. This requires deterministic build IDs, signed manifests, and a release artifact naming convention that encodes board, version, and hash.

## Key Commands / Configuration / Code

Below is a working GitHub Actions matrix configuration that handles three boards with shared build logic. The key is the `strategy.matrix` block combined with board-specific config files.

```yaml
# .github/workflows/release.yml
name: Multi-Board Release

on:
  push:
    tags:
      - 'v*'  # Trigger on version tags only

jobs:
  build:
    strategy:
      matrix:
        board: [sensor-h7, actuator-g4, edge-nrf52]
        include:
          - board: sensor-h7
            mcu: STM32H743
            toolchain: arm-none-eabi
            linkerscript: boards/sensor-h7/STM32H743ZI_FLASH.ld
            config: boards/sensor-h7/board_config.h
          - board: actuator-g4
            mcu: STM32G474
            toolchain: arm-none-eabi
            linkerscript: boards/actuator-g4/STM32G474RETx_FLASH.ld
            config: boards/actuator-g4/board_config.h
          - board: edge-nrf52
            mcu: nRF52840
            toolchain: arm-none-eabi
            linkerscript: boards/edge-nrf52/nrf52840.ld
            config: boards/edge-nrf52/board_config.h

    runs-on: ubuntu-22.04
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Full history for version info

      - name: Install toolchain
        run: |
          sudo apt-get update
          sudo apt-get install -y gcc-arm-none-eabi cmake python3-pip
          pip3 install imgtool  # For MCUboot signing

      - name: Extract version from tag
        id: version
        run: echo "VERSION=${GITHUB_REF_NAME#v}" >> $GITHUB_OUTPUT

      - name: Configure build
        run: |
          cmake -B build/${{ matrix.board }} \
            -DCMAKE_TOOLCHAIN_FILE=toolchains/${{ matrix.toolchain }}.cmake \
            -DBOARD_CONFIG=${{ matrix.config }} \
            -DLINKER_SCRIPT=${{ matrix.linkerscript }} \
            -DFW_VERSION=${{ steps.version.outputs.VERSION }} \
            -DBOARD_NAME=${{ matrix.board }}

      - name: Build firmware
        run: cmake --build build/${{ matrix.board }} --parallel

      - name: Sign firmware (MCUboot)
        run: |
          imgtool sign \
            --key keys/release-${{ matrix.board }}.pem \
            --align 8 \
            --version ${{ steps.version.outputs.VERSION }} \
            --header-size 0x200 \
            --slot-size 0x100000 \
            build/${{ matrix.board }}/firmware.bin \
            build/${{ matrix.board }}/firmware-signed.bin

      - name: Generate manifest
        run: |
          cat > build/${{ matrix.board }}/manifest.json << EOF
          {
            "board": "${{ matrix.board }}",
            "version": "${{ steps.version.outputs.VERSION }}",
            "commit": "${{ github.sha }}",
            "build_id": "${{ github.run_id }}",
            "sha256": "$(sha256sum build/${{ matrix.board }}/firmware-signed.bin | cut -d' ' -f1)"
          }
          EOF

      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: firmware-${{ matrix.board }}-${{ steps.version.outputs.VERSION }}
          path: |
            build/${{ matrix.board }}/firmware-signed.bin
            build/${{ matrix.board }}/manifest.json
```

The CMakeLists.txt snippet that consumes the board config:

```cmake
# CMakeLists.txt (top-level)
project(multi-board-firmware C ASM)

# Board-specific config is included as a header
add_definitions(-DBOARD_CONFIG="${BOARD_CONFIG}")
add_definitions(-DFW_VERSION="${FW_VERSION}")
add_definitions(-DBOARD_NAME="${BOARD_NAME}")

# Common source files shared across all boards
set(COMMON_SOURCES
    src/main.c
    src/scheduler.c
    src/communication.c
)

# Board-specific sources resolved at configure time
if(BOARD_NAME STREQUAL "sensor-h7")
    list(APPEND BOARD_SOURCES src/hal/stm32h7_hal.c src/drivers/sensor_driver.c)
elseif(BOARD_NAME STREQUAL "actuator-g4")
    list(APPEND BOARD_SOURCES src/hal/stm32g4_hal.c src/drivers/motor_driver.c)
elseif(BOARD_NAME STREQUAL "edge-nrf52")
    list(APPEND BOARD_SOURCES src/hal/nrf52_hal.c src/drivers/ble_driver.c)
endif()

add_executable(firmware ${COMMON_SOURCES} ${BOARD_SOURCES})
target_link_options(firmware PRIVATE -T ${LINKER_SCRIPT})
```

## Common Pitfalls & Gotchas

**1. Forgetting to pin toolchain versions across matrix entries.** If the sensor board builds with GCC 12.2 and the edge board with GCC 10.3, you'll get different codegen and potentially different bugs. Always use a fixed toolchain version (e.g., `gcc-arm-none-eabi-10.3-2021.10`) across all matrix cells. Pin it in a `toolchains/versions.json` and validate at pipeline start.

**2. Signing keys in the repository.** I see teams commit private signing keys alongside the firmware. Never. Use GitHub Actions secrets or a hardware security module (HSM) for release keys. The example above uses `keys/release-*.pem` only for demonstration—in production, fetch keys from a secure vault at build time.

**3. Ignoring linker script divergence.** Each board has unique memory maps. If you share a single linker script template, you'll silently corrupt the actuator board's RAM layout when adding a new sensor buffer. Keep board-specific linker scripts in version control under `boards/<board_name>/` and validate them with a post-build memory map check.

## Try It Yourself

1. **Create a board matrix in your CI.** If you have one board, simulate a second by adding a `board: [prod, dev]` matrix with different `-D` flags (e.g., different optimization levels or feature sets). Verify both artifacts are produced and named distinctly.

2. **Implement a manifest generation step.** After your build, write a JSON manifest containing board name, commit SHA, build timestamp, and firmware hash. Upload it alongside the binary. Then write a script that validates the manifest hash matches the binary.

3. **Add a post-build memory map check.** For each board in your matrix, parse the `.map` file and assert that `.text` + `.data` + `.bss` fit within the board's flash and RAM limits. Fail the pipeline if any board exceeds its constraints.

## Next Up

Tomorrow is **Day 25: Full Review & Project: End-to-End CI/CD Pipeline for a Production Embedded System**. We'll tie together everything from the past 24 days into a single, deployable pipeline that handles linting, unit testing, hardware-in-the-loop validation, signed release, and OTA update packaging—all triggered from one commit.
