---
title: "Day 14: OP-TEE Trusted Application: Writing a TA from Scratch"
date: 2026-06-26
tags: ["til", "trustzone", "trusted-application", "optee"]
---

## What I Explored Today

Today I wrote my first OP-TEE Trusted Application (TA) from scratch — not from a template, but by understanding every line of the UUID, entry points, command handler, and the build system glue. I walked through the `hello_world` TA example in the OP-TEE source tree, then stripped it down and rebuilt it with my own logic: a simple secure counter that increments only inside the TrustZone secure world. The goal was to internalize the TA lifecycle and the contract between the TA and the OP-TEE core.

## The Core Concept

A Trusted Application runs in the Secure World, isolated from the Linux kernel and user space. It is not a process in the traditional sense — it's a signed, encrypted binary blob loaded by OP-TEE's supplicant when a client (in the Normal World) invokes it. The TA communicates with the outside world exclusively through a well-defined interface: a UUID (to identify the TA), a set of command IDs, and shared memory buffers.

Why write a TA from scratch? Because the template generators hide the essential plumbing. You need to understand three things:

1. **The TA entry points**: `TA_CreateEntryPoint`, `TA_OpenSessionEntryPoint`, `TA_InvokeCommandEntryPoint`, `TA_CloseSessionEntryPoint`, `TA_DestroyEntryPoint`. These are the lifecycle hooks the OP-TEE core calls.
2. **The command handler**: A switch statement that dispatches on `cmd_id` (a `uint32_t` you define). Each command receives a `struct tee_ta_session *` and `struct tee_ta_param *` for input/output.
3. **The build system**: The TA must be compiled with the OP-TEE OS toolchain, linked against `libutee`, and signed with a private key. The resulting `.ta` file is placed in the filesystem where the supplicant can find it.

The "why" is security and determinism. By moving sensitive logic (e.g., cryptographic key generation, secure counters, biometric matching) into a TA, you ensure that even a compromised Linux kernel cannot read or tamper with that data. The TA's memory is protected by the TrustZone hardware, and all communication is mediated by OP-TEE's secure monitor.

## Key Commands / Configuration / Code

### 1. TA Source File (`user_ta/hello_world/ta_entry.c`)

```c
#include <tee_internal_api.h>
#include <tee_internal_api_extensions.h>
#include <string.h>
#include "hello_world_ta.h"  // defines UUID and command IDs

// TA UUID: must match the UUID in the manifest and the client
#define TA_HELLO_WORLD_UUID \
    { 0x8aaaf200, 0x2450, 0x11e4, \
        { 0xab, 0xe2, 0x00, 0x02, 0xa5, 0xd5, 0xc5, 0x1b } }

static uint32_t counter;  // persistent across invocations in same session

TEE_Result TA_CreateEntryPoint(void) {
    // Called once when TA is first loaded
    counter = 0;
    return TEE_SUCCESS;
}

void TA_DestroyEntryPoint(void) {
    // Called when TA is unloaded
}

TEE_Result TA_OpenSessionEntryPoint(uint32_t param_types,
                                    TEE_Param params[4],
                                    void **session_ctx) {
    // Called for each new client session
    // session_ctx can store per-session data
    (void)param_types; (void)params;
    *session_ctx = NULL;
    return TEE_SUCCESS;
}

void TA_CloseSessionEntryPoint(void *session_ctx) {
    // Called when client closes session
    (void)session_ctx;
}

TEE_Result TA_InvokeCommandEntryPoint(void *session_ctx,
                                      uint32_t cmd_id,
                                      uint32_t param_types,
                                      TEE_Param params[4]) {
    (void)session_ctx;

    switch (cmd_id) {
    case TA_HELLO_WORLD_CMD_GET_COUNTER:
        // Return the current counter value via params[0].value.a
        params[0].value.a = counter;
        break;

    case TA_HELLO_WORLD_CMD_INCREMENT:
        counter++;
        params[0].value.a = counter;
        break;

    default:
        return TEE_ERROR_BAD_PARAMETERS;
    }

    return TEE_SUCCESS;
}
```

### 2. Header File (`hello_world_ta.h`)

```c
#ifndef HELLO_WORLD_TA_H
#define HELLO_WORLD_TA_H

#define TA_HELLO_WORLD_UUID \
    { 0x8aaaf200, 0x2450, 0x11e4, \
        { 0xab, 0xe2, 0x00, 0x02, 0xa5, 0xd5, 0xc5, 0x1b } }

// Command IDs
#define TA_HELLO_WORLD_CMD_GET_COUNTER    0
#define TA_HELLO_WORLD_CMD_INCREMENT      1

#endif
```

### 3. TA Manifest (`user_ta/hello_world/sub.mk`)

```makefile
# This file tells the build system how to compile the TA
# It must be placed in the TA source directory

# TA UUID (must match the C code)
TA_UUID := 8aaaf200-2450-11e4-abe2-0002a5d5c51b

# Source files
srcs-y += ta_entry.c

# Global platform flags (optional)
global-incdirs-y += .
```

### 4. Building and Signing

```bash
# Inside the OP-TEE build directory (e.g., build/)
make -j$(nproc) CFG_TEE_TA_LOG_LEVEL=3

# The signed TA will be at:
# out/arm-plat-vexpress/ta/8aaaf20-.../8aaaf20-....ta

# To install on the target:
# Copy to /lib/optee_armtz/ on the device
```

## Common Pitfalls & Gotchas

1. **UUID mismatch**: The UUID in the C code, the manifest (`sub.mk`), and the client (Normal World) must be identical. A single byte difference causes `TEEC_ERROR_ITEM_NOT_FOUND` when the client tries to open a session. Always define the UUID in one header and include it everywhere.

2. **Forgetting to handle `TEE_PARAM_TYPE`**: The `param_types` argument encodes the type of each of the four `TEE_Param` slots (value, memref, or none). If you pass a memref from the client but treat it as a value in the TA, you'll get undefined behavior or a panic. Always check `TEE_PARAM_TYPE_GET(param_types, i)` before accessing `params[i]`.

3. **Stack overflow in Secure World**: The TA stack is limited (typically 4–8 KB). Avoid large local arrays or deep recursion. Use heap allocation via `TEE_Malloc`/`TEE_Free` for buffers larger than a few hundred bytes. A stack overflow in a TA causes a secure panic, which may reboot the device.

## Try It Yourself

1. **Modify the counter TA** to persist the counter across sessions (hint: use `TEE_WritePersistentObject` and `TEE_ReadPersistentObject` from the `libutee` storage API). Verify that after a device reboot, the counter retains its value.

2. **Add a new command** `TA_HELLO_WORLD_CMD_SET_COUNTER` that takes a `uint32_t` from the client and sets the counter to that value. Update the client to call it and confirm the change.

3. **Instrument the TA with debug logs** using `DMSG("counter = %u", counter)`. Rebuild with `CFG_TEE_TA_LOG_LEVEL=4` and observe the output via `dmesg` or `xtest` logs. This is invaluable for debugging.

## Next up

Tomorrow: **OP-TEE Client API: Calling TAs from Normal World** — we'll write a Linux userspace application that opens a session to our TA, invokes commands, and handles errors. You'll see the full round-trip from Normal World to Secure World and back.
