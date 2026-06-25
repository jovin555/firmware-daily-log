---
title: "Day 13: OP-TEE: Trusted Execution Environment Architecture"
date: 2026-06-25
tags: ["til", "trustzone", "optee", "tee"]
---

## What I Explored Today

After weeks of building up the hardware-level TrustZone foundations, today I finally dove into the software layer that makes it all usable: OP-TEE (Open Portable Trusted Execution Environment). I’ve been reading through the official documentation and building the reference stack for QEMUv8. OP-TEE is the de facto open-source TEE for Armv7-A and Armv8-A, maintained by Linaro. It provides a complete framework for running trusted applications (TAs) in the Secure World, with a standardized client API in the Normal World. I walked through the architecture, built the entire stack from source, and ran the xtest regression suite. The key takeaway: OP-TEE abstracts the complexity of Secure Monitor Calls (SMCs) and world switching into a clean, POSIX-like API.

## The Core Concept

Why do we need OP-TEE? Without it, writing Secure World code means hand-rolling SMC handlers, managing page tables for two worlds, and implementing your own inter-world communication protocol. That’s a recipe for security bugs and insane development time.

OP-TEE solves this by providing three layers:

1. **OP-TEE OS** – The secure kernel that runs in Secure EL1. It manages memory, schedules trusted applications, and handles SMCs from the Normal World.
2. **OP-TEE Client API** (libteec) – A library in the Normal World that lets Rich Execution Environment (REE) applications open sessions, invoke commands, and share memory with TAs.
3. **OP-TEE Linux Kernel Driver** – A TEE subsystem driver that routes client API calls to the secure monitor (ATF/OPTEE) via SMCs.

The genius is the **GlobalPlatform TEE Client API** compliance. This means any TA written for OP-TEE can theoretically run on any GP-compliant TEE. The architecture uses a **thread pool** model in the secure world: each Normal World session maps to a secure thread, with a limited number of concurrent threads (typically 8). Memory is shared via **registered shared memory** – the client allocates a buffer, registers it with the TEE driver, and the secure world maps it into its own address space.

## Key Commands / Configuration / Code

### Building the OP-TEE Stack for QEMUv8

The reference build uses a repo manifest. Here’s the minimal setup:

```bash
# Clone the manifest for QEMUv8 (Armv8-A)
repo init -u https://github.com/OP-TEE/manifest.git -m qemu_v8.xml
repo sync -j$(nproc)

# Build everything (ATF, OP-TEE OS, Linux kernel, rootfs)
cd build
make -j$(nproc) toolchains
make -j$(nproc) all

# Run in QEMU
make run-only
```

Once booted, log in as `root` (no password) and run the test suite:

```bash
# Inside QEMU
xtest
```

### A Minimal Client Application (Normal World)

This snippet opens a session with a TA and invokes a command:

```c
#include <tee_client_api.h>

TEEC_Result res;
TEEC_Context ctx;
TEEC_Session sess;
TEEC_Operation op;
TEEC_UUID uuid = { 0x12345678, 0x1234, 0x1234,
                   { 0x12, 0x34, 0x56, 0x78, 0x9a, 0xbc, 0xde, 0xf0 } };

// Initialize context
res = TEEC_InitializeContext(NULL, &ctx);
if (res != TEEC_SUCCESS) { /* handle error */ }

// Open session with TA
res = TEEC_OpenSession(&ctx, &sess, &uuid,
                       TEEC_LOGIN_PUBLIC, NULL, NULL, NULL);
if (res != TEEC_SUCCESS) { /* handle error */ }

// Prepare operation (no parameters for this example)
memset(&op, 0, sizeof(op));
op.paramTypes = TEEC_PARAM_TYPES(TEEC_NONE, TEEC_NONE,
                                  TEEC_NONE, TEEC_NONE);

// Invoke command ID 0
res = TEEC_InvokeCommand(&sess, 0, &op, NULL);
if (res != TEEC_SUCCESS) { /* handle error */ }

TEEC_CloseSession(&sess);
TEEC_FinalizeContext(&ctx);
```

### OP-TEE OS Configuration (build/optee_os.mk)

Key build flags that matter in production:

```makefile
# Number of secure threads (default 8, max 32)
CFG_NUM_THREADS ?= 8

# Enable shared memory debugging
CFG_SHMEM_STATS ?= y

# Enable TA profiling (adds overhead)
CFG_TA_GPROF_SUPPORT ?= n

# Set TA load address (must match linker script)
CFG_TA_LOAD_ADDR ?= 0x40000000
```

## Common Pitfalls & Gotchas

### 1. Shared Memory Alignment
The most frequent bug I see: passing a stack-allocated buffer to `TEEC_RegisterSharedMemory`. Stack buffers are not page-aligned. OP-TEE requires shared memory to be aligned to the page size (4K on Armv8-A). Always use `malloc()` or `mmap()` with alignment, or use `TEEC_AllocateSharedMemory()` which handles this.

```c
// WRONG: stack buffer
char buf[256];
TEEC_RegisterSharedMemory(&ctx, &shm, buf, 256); // fails

// CORRECT: heap-allocated
TEEC_SharedMemory shm;
shm.buffer = malloc(256);
shm.size = 256;
shm.flags = TEEC_MEM_INPUT;
TEEC_RegisterSharedMemory(&ctx, &shm, NULL, 0);
```

### 2. TA UUID Mismatch
The UUID in your TA's `user_ta_header.c` must exactly match the UUID used in the client application. A single byte off and `TEEC_OpenSession` returns `TEEC_ERROR_ITEM_NOT_FOUND`. I’ve burned an hour on this. Use `uuidgen` to generate and paste consistently.

### 3. Thread Starvation in Secure World
OP-TEE has a fixed thread pool. If you open 9 concurrent sessions on a build with `CFG_NUM_THREADS=8`, the 9th session blocks indefinitely. Always check `TEEC_OpenSession` return code, and design your client to limit concurrent sessions or use a queue.

## Try It Yourself

1. **Build the full OP-TEE stack for QEMUv8** using the repo manifest above. Run `xtest` and verify at least the core regression tests pass (look for `[PASSED]` lines). This validates your toolchain and build environment.

2. **Modify the client example** to pass a 64-byte input buffer to the TA. Use `TEEC_AllocateSharedMemory` and set `op.params[0].memref` accordingly. Print the buffer content in the TA (you’ll need to write a minimal TA stub – or use the `hello_world` TA from the OP-TEE source).

3. **Check shared memory alignment** in your own code. Write a small test that intentionally passes a stack buffer to `TEEC_RegisterSharedMemory` and observe the error code. Then fix it with a heap allocation.

## Next Up

Tomorrow, we stop being spectators. I’ll walk through writing a Trusted Application from scratch – the TA entry points, command handlers, and how to securely store a secret in the Secure World’s trusted storage. We’ll build a password vault TA that your REE app can call. See you for **Day 14: OP-TEE Trusted Application: Writing a TA from Scratch**.
