---
title: "Day 03: GitLab CI & Jenkins Pipelines for Multi-Board Firmware Projects"
date: 2026-07-03
tags: ["til", "embedded-cicd", "gitlab-ci", "jenkins"]
---

## What I Explored Today

Today I dug into the practical differences between GitLab CI and Jenkins when building firmware for multiple target boards. My test project has three STM32 variants (F4, L4, and H7) and an ESP32 target, each requiring different toolchains, linker scripts, and peripheral drivers. I needed a pipeline that could build all four in parallel, cache the toolchains, and fail fast if any board fails. After prototyping both solutions, I have a clear picture of where each excels and where they hurt.

## The Core Concept

The fundamental challenge in multi-board firmware CI is **matrix builds** — running the same source tree through N different toolchains and configurations. Both GitLab CI and Jenkins support this via parallel job definitions, but they differ in how you define the matrix, manage environment isolation, and handle artifacts.

The "why" matters here: a naive pipeline that builds boards sequentially wastes developer time. A good matrix pipeline builds all boards in parallel, reports per-board status, and lets you trace a failure to a specific target without rerunning everything. The secondary concern is toolchain management — you don't want to download 4 different ARM GCC toolchains on every pipeline run.

Both tools solve this, but GitLab CI leans on YAML matrices and Docker images, while Jenkins uses declarative pipeline syntax with agents and shared libraries. The choice often comes down to your team's DevOps maturity and whether you already have a Jenkins instance with embedded plugins.

## Key Commands / Configuration / Code

### GitLab CI Matrix Pipeline (`.gitlab-ci.yml`)

```yaml
# Define the build matrix for 4 boards
variables:
  # Cache toolchains across runs
  TOOLCHAIN_CACHE: "${CI_PROJECT_DIR}/.toolchain_cache"

stages:
  - build

# Template job to avoid repeating build logic
.build_board: &build_board
  stage: build
  image: ${TOOLCHAIN_IMAGE}  # Per-board image from matrix
  script:
    - echo "Building for ${BOARD_NAME}"
    - make BOARD=${BOARD_NAME} TOOLCHAIN_PATH=${TOOLCHAIN_CACHE}/${TOOLCHAIN_DIR}
    - mv build/firmware.hex build/firmware_${BOARD_NAME}.hex
  artifacts:
    paths:
      - build/firmware_${BOARD_NAME}.hex
    expire_in: 1 week
  cache:
    key: ${TOOLCHAIN_DIR}
    paths:
      - ${TOOLCHAIN_CACHE}/${TOOLCHAIN_DIR}

# Parallel matrix: 4 boards × 2 build types
matrix:
  - BOARD_NAME: "stm32f4"
    TOOLCHAIN_IMAGE: "arm-gcc:10.3-2021.10"
    TOOLCHAIN_DIR: "gcc-arm-none-eabi-10.3"
  - BOARD_NAME: "stm32l4"
    TOOLCHAIN_IMAGE: "arm-gcc:10.3-2021.10"
    TOOLCHAIN_DIR: "gcc-arm-none-eabi-10.3"
  - BOARD_NAME: "stm32h7"
    TOOLCHAIN_IMAGE: "arm-gcc:11.3-2022.02"
    TOOLCHAIN_DIR: "gcc-arm-none-eabi-11.3"
  - BOARD_NAME: "esp32"
    TOOLCHAIN_IMAGE: "esp-idf:5.1"
    TOOLCHAIN_DIR: "esp-idf-5.1"

# Instantiate 4 parallel jobs from template
build:stm32f4:
  <<: *build_board
  variables:
    BOARD_NAME: "stm32f4"

build:stm32l4:
  <<: *build_board
  variables:
    BOARD_NAME: "stm32l4"

build:stm32h7:
  <<: *build_board
  variables:
    BOARD_NAME: "stm32h7"

build:esp32:
  <<: *build_board
  variables:
    BOARD_NAME: "esp32"
```

### Jenkins Declarative Pipeline (Jenkinsfile)

```groovy
// Jenkins pipeline with parallel matrix for 4 boards
pipeline {
    agent none  // Each stage selects its own agent

    stages {
        stage('Build All Boards') {
            parallel {
                stage('STM32F4') {
                    agent { label 'linux-arm-gcc-10' }
                    steps {
                        sh '''
                            make BOARD=stm32f4 TOOLCHAIN_PATH=/opt/gcc-arm-none-eabi-10.3
                            cp build/firmware.hex build/firmware_stm32f4.hex
                        '''
                    }
                    post {
                        success {
                            archiveArtifacts artifacts: 'build/firmware_stm32f4.hex'
                        }
                    }
                }
                stage('STM32L4') {
                    agent { label 'linux-arm-gcc-10' }
                    steps {
                        sh '''
                            make BOARD=stm32l4 TOOLCHAIN_PATH=/opt/gcc-arm-none-eabi-10.3
                            cp build/firmware.hex build/firmware_stm32l4.hex
                        '''
                    }
                    post {
                        success {
                            archiveArtifacts artifacts: 'build/firmware_stm32l4.hex'
                        }
                    }
                }
                stage('STM32H7') {
                    agent { label 'linux-arm-gcc-11' }
                    steps {
                        sh '''
                            make BOARD=stm32h7 TOOLCHAIN_PATH=/opt/gcc-arm-none-eabi-11.3
                            cp build/firmware.hex build/firmware_stm32h7.hex
                        '''
                    }
                    post {
                        success {
                            archiveArtifacts artifacts: 'build/firmware_stm32h7.hex'
                        }
                    }
                }
                stage('ESP32') {
                    agent { label 'linux-esp-idf-5' }
                    steps {
                        sh '''
                            . /opt/esp-idf/export.sh
                            make BOARD=esp32
                            cp build/firmware.bin build/firmware_esp32.bin
                        '''
                    }
                    post {
                        success {
                            archiveArtifacts artifacts: 'build/firmware_esp32.bin'
                        }
                    }
                }
            }
        }
    }
}
```

### Makefile Snippet (shared by both pipelines)

```makefile
# Simplified Makefile supporting multiple boards
BOARD ?= stm32f4

# Board-specific configurations
ifeq ($(BOARD), stm32f4)
    CROSS_COMPILE := $(TOOLCHAIN_PATH)/bin/arm-none-eabi-
    LINKER_SCRIPT := stm32f4.ld
    DEFINES += -DSTM32F4
else ifeq ($(BOARD), stm32l4)
    CROSS_COMPILE := $(TOOLCHAIN_PATH)/bin/arm-none-eabi-
    LINKER_SCRIPT := stm32l4.ld
    DEFINES += -DSTM32L4
else ifeq ($(BOARD), stm32h7)
    CROSS_COMPILE := $(TOOLCHAIN_PATH)/bin/arm-none-eabi-
    LINKER_SCRIPT := stm32h7.ld
    DEFINES += -DSTM32H7
else ifeq ($(BOARD), esp32)
    # ESP32 uses its own build system (idf.py)
    # This target delegates to idf.py
    build:
        idf.py build
endif

CFLAGS := $(DEFINES) -mcpu=cortex-m4 -mthumb -Wall -O2
LDFLAGS := -T $(LINKER_SCRIPT) --specs=nosys.specs

build/firmware.elf: $(SRCS)
    $(CROSS_COMPILE)gcc $(CFLAGS) $^ -o $@ $(LDFLAGS)
    $(CROSS_COMPILE)objcopy -O ihex $@ build/firmware.hex
```

## Common Pitfalls & Gotchas

1. **Toolchain version mismatch across boards** — The STM32H7 requires GCC 11+ for Cortex-M7 FPU support, while F4/L4 work fine with GCC 10. If you use a single Docker image for all ARM boards, you'll get linker errors on H7. Always pin toolchain versions per board in your matrix.

2. **Cache poisoning between parallel jobs** — GitLab CI's cache key must include the toolchain directory. Without it, two parallel jobs writing to the same cache path can corrupt each other's downloads. Use `key: ${TOOLCHAIN_DIR}` as shown above to isolate caches.

3. **Jenkins agent labels that don't exist** — If you label an agent `linux-arm-gcc-11` but no agent has that label, the pipeline hangs forever waiting. Always validate agent labels exist before running. I learned this the hard way after a 45-minute timeout on a Friday afternoon.

4. **Artifact naming collisions** — Both pipelines produce `firmware.hex` by default. Without renaming per board (e.g., `firmware_stm32f4.hex`), parallel jobs overwrite each other's artifacts. Always include the board name in output filenames.

## Try It Yourself

1. **Extend the matrix** — Add a fifth board (e.g., nRF52840) to the GitLab CI matrix. You'll need to create a new toolchain image or reuse an existing one. Verify the pipeline spawns 5 parallel jobs.

2. **Add a post-build step** — In the Jenkins pipeline, add a `stage('Firmware Size Report')` that runs `arm-none-eabi-size` on all built `.elf` files and prints a summary table. Use `script { ... }` to iterate over artifacts.

3. **Implement a "fail-fast" gate** — Modify the GitLab CI pipeline so that if any board build fails, the pipeline immediately cancels remaining jobs. Hint: use `needs` with `parallel:matrix` and a `failure` trigger.

## Next Up

Tomorrow I'm tackling **Build Caching Strategies: ccache & Artifact Reuse Across Pipelines**. When you're building 4 boards from the same source, 90% of the object files are identical — only the HAL layer and linker script differ. I'll show you how to shave 60% off your build time by caching compiled objects and reusing them across matrix jobs.
