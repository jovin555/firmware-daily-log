---
title: "Day 11: Trusted Firmware-A (TF-A): Architecture & Boot Stages"
date: 2026-06-23
tags: ["til", "trustzone", "tfa", "boot-stages", "arm64"]
---

## What I Explored Today

Today I dove into the architectural skeleton of Trusted Firmware-A (TF-A), the reference implementation of the Arm Trusted Software stack for A-profile processors. TF-A is the de facto standard for booting Linux on Armv8-A and later systems with TrustZone. I traced the boot flow from the first instruction after SoC reset to the EL2 hypervisor or EL1 kernel entry, understanding how TF-A partitions the boot process into distinct stages that each run at progressively higher exception levels. The key insight: TF-A doesn't just boot the kernel—it establishes the entire Secure World foundation, including the Secure Monitor that mediates all Non-secure-to-Secure transitions.

## The Core Concept

TF-A exists because booting an Armv8-A system with TrustZone is fundamentally a multi-stage privilege escalation problem. At reset, the CPU starts at the highest privilege level (EL3) in Secure World. But you don't want your bootloader running at EL3 forever—that's a massive attack surface. Instead, TF-A uses a chain-of-trust model where each stage validates the next, then drops privilege before handing off.

The architecture defines four boot stages: BL1 (Boot ROM), BL2 (Trusted Boot Firmware), BL31 (EL3 Runtime Firmware), and optionally BL32 (Trusted OS) and BL33 (Non-secure firmware, typically UEFI or U-Boot). BL1 is immutable silicon ROM. BL2 is the first updatable firmware, loaded by BL1 after cryptographic verification. BL31 stays resident in Secure memory as the Secure Monitor, handling SMC calls and PSCI power management. BL32 runs a Trusted OS like OP-TEE. BL33 is the Non-secure world bootloader that eventually loads Linux.

The critical architectural decision: BL31 is the only stage that permanently occupies EL3. BL1 and BL2 execute at EL3 but terminate. This minimizes the EL3 attack surface to a single, auditable runtime component.

## Key Commands / Configuration / Code

Building TF-A for a typical platform (e.g., QEMU virt or Raspberry Pi 4) requires understanding the build system and platform-specific configuration.

**Basic TF-A build for QEMU (AArch64):**
```bash
# Clone the repository
git clone https://git.trustedfirmware.org/TF-A/trusted-firmware-a.git
cd trusted-firmware-a

# Build BL1, BL2, BL31 for QEMU virt platform
make PLAT=qemu ARCH=aarch64 DEBUG=1 \
     BL33=../edk2/Build/QemuVirt/RELEASE_GCC5/FV/QEMU_EFI.fd \
     all fip

# Outputs in build/qemu/debug/
# bl1.bin - Boot ROM stage
# bl2.bin - Trusted Boot Firmware
# bl31.bin - EL3 Runtime Firmware
# fip.bin - Firmware Image Package (contains BL2, BL31, BL33)
```

**Platform memory layout configuration (example from `plat/qemu/include/platform_def.h`):**
```c
/* QEMU virt platform memory map */
#define BL1_RAM_BASE          0x00000000
#define BL1_RAM_SIZE          0x00008000  /* 32KB for BL1 */

#define BL2_BASE              0x04000000
#define BL2_LIMIT             0x04020000  /* 128KB for BL2 */

#define BL31_BASE             0x04020000
#define BL31_LIMIT            0x04060000  /* 256KB for BL31 */

/* Shared memory for passing boot arguments between stages */
#define PARAMS_BASE           0x04000000
#define PARAMS_SIZE           0x00001000  /* 4KB for boot params */
```

**Boot flow handoff sequence (pseudocode from TF-A source):**
```c
// BL1 entry point (reset_handler in bl1/aarch64/bl1_entrypoint.S)
void bl1_main(void) {
    // 1. Set up EL3 MMU with identity mapping
    // 2. Load BL2 from flash to SRAM
    // 3. Authenticate BL2 image (hash chain verification)
    // 4. Erase BL1's data section from SRAM
    // 5. Jump to BL2 entry point at EL3
    smc(PSCI_CPU_ON, BL2_ENTRY_POINT, MPIDR_ANY);
}

// BL2 entry point (bl2_main in bl2/bl2_main.c)
void bl2_main(void) {
    // 1. Initialize platform (UART, GIC, TZASC)
    // 2. Load BL31, BL32, BL33 images from FIP
    // 3. Authenticate each image
    // 4. Populate boot arguments for BL31
    // 5. Jump to BL31 entry point at EL3
    bl31_entrypoint();
}

// BL31 entry point (bl31_main in bl31/bl31_main.c)
void bl31_main(void) {
    // 1. Set up SMC dispatching table
    // 2. Initialize PSCI handler for CPU power management
    // 3. Initialize Secure interrupt controller
    // 4. Drop to EL2 and jump to BL33 (Non-secure)
    // 5. Remain resident for SMC calls
    runtime_svc_init();
    smc(PSCI_CPU_ON, BL33_ENTRY_POINT, MPIDR_ANY);
}
```

**Inspecting the FIP (Firmware Image Package):**
```bash
# Dump FIP contents to verify images are packed correctly
tools/fiptool/fiptool info build/qemu/debug/fip.bin

# Output example:
# Trusted Boot Firmware BL2: offset=0x100, size=0x12345
# EL3 Runtime Firmware BL31: offset=0x12445, size=0x23456
# Non-Trusted Firmware BL33: offset=0x3589B, size=0x56789
```

## Common Pitfalls & Gotchas

**1. BL2 memory corruption from BL1 data overlap**
The most frequent boot failure I've seen: BL1 writes its data section to SRAM, then loads BL2 to an overlapping address. BL1 must erase its own data before jumping to BL2, or BL2's .bss initialization will corrupt BL1's stack. Always verify `BL1_RAM_SIZE` and `BL2_BASE` don't overlap in your platform port.

**2. Forgetting to set `ARM_ARCH_MAJOR` for your CPU**
TF-A defaults to Armv8.0. If you're on Cortex-A76 (Armv8.2) or Neoverse-N1 (Armv8.4), build with `ARM_ARCH_MAJOR=8 ARM_ARCH_MINOR=2` or higher. Missing this causes undefined instruction exceptions when TF-A tries to use FEAT_RAS or FEAT_SEL2 instructions that your CPU supports but the build doesn't enable.

**3. BL33 must be compiled for EL2, not EL1**
This one bit me for days. UEFI or U-Boot must be built with `-DARM_EL2=1` or equivalent. If BL33 expects to run at EL1, BL31's eret to EL2 will fault immediately. Check your BL33 build flags: `make CROSS_COMPILE=aarch64-linux-gnu- PLAT=qemu ARCH=aarch64 DEBUG=1 BL33=...` doesn't validate BL33's exception level.

## Try It Yourself

1. **Build TF-A for QEMU with debug output enabled**: Clone TF-A, build with `PLAT=qemu ARCH=aarch64 DEBUG=1 LOG_LEVEL=50`, and run in QEMU with `-d cpu_reset -D qemu.log`. Observe the boot stage transitions in the log. Verify BL1 prints its version before loading BL2.

2. **Modify the BL2 memory layout**: In your platform's `platform_def.h`, reduce `BL2_SIZE` to 64KB and rebuild. Observe the build failure when BL2 exceeds the limit. Then increase it to 256KB and verify the FIP tool shows the new offset.

3. **Add a custom SMC service to BL31**: Create a new file in `services/` that registers a runtime service with `DECLARE_RT_SVC()`. Implement a handler that returns the current exception level. Build, run in QEMU, and call your SMC from U-Boot using `smc #0`. Verify the return value matches EL3.

## Next Up

Tomorrow: **TF-A BL1, BL2, BL3: Each Stage Explained** — We'll dissect each boot stage's responsibilities, memory footprint, and the exact handshake protocol between stages. I'll show you the assembly entry points, the authentication chain implementation, and how BL31's runtime services framework dispatches SMC calls to the correct handler.
