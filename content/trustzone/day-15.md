---
title: "Day 15: OP-TEE Client API: Calling TAs from Normal World"
date: 2026-06-27
tags: ["til", "trustzone", "client-api", "optee"]
---

## What I Explored Today

Today I dove into the OP-TEE Client API — the user-space library that allows Normal World (REE) applications to invoke Trusted Applications (TAs) running in the Secure World. After weeks of building and booting OP-TEE, it's time to actually *use* it. I implemented a minimal CA (Client Application) that opens a session with a TA, invokes a command, and handles the shared memory buffer lifecycle. The API is deceptively simple, but the memory model and error handling require careful attention.

## The Core Concept

The OP-TEE Client API (`libteec`) is the bridge between the untrusted Linux userspace and the trusted execution environment. When your CA calls `TEEC_InvokeCommand`, the following happens under the hood:

1. The CA opens `/dev/teepriv` (or `/dev/tee0` for legacy) — a TEE driver interface.
2. A `TEEC_Session` is established via a SMC (Secure Monitor Call) that transitions to Secure Monitor, then to OP-TEE OS, which loads or locates the TA.
3. Shared memory is pinned in Linux and its physical address is passed to the TA via a registered buffer.
4. The TA processes the command, writes results into the shared buffer, and returns.

The key insight: **shared memory is the only data transfer mechanism**. You cannot pass pointers to TA-private memory. Every input/output buffer must be explicitly registered with the TEE driver. This is fundamentally different from normal IPC — the Normal World and Secure World have separate page tables, and the MMU in each world enforces isolation.

## Key Commands / Configuration / Code

### Minimal CA Skeleton

```c
#include <tee_client_api.h>
#include <ta_hello_world.h>  // Generated from TA UUID

int main(void) {
    TEEC_Result res;
    TEEC_Context ctx;
    TEEC_Session sess;
    TEEC_Operation op;
    uint32_t err_origin;

    // 1. Initialize context (connects to TEE driver)
    res = TEEC_InitializeContext(NULL, &ctx);
    if (res != TEEC_SUCCESS) {
        printf("TEEC_InitializeContext failed: 0x%x\n", res);
        return -1;
    }

    // 2. Open session with TA
    TEEC_UUID uuid = TA_HELLO_WORLD_UUID;
    res = TEEC_OpenSession(&ctx, &sess, &uuid,
                           TEEC_LOGIN_PUBLIC,  // No authentication
                           NULL,               // No client data
                           NULL,               // No operation for open
                           &err_origin);
    if (res != TEEC_SUCCESS) {
        printf("TEEC_OpenSession failed: 0x%x, origin: %u\n", res, err_origin);
        TEEC_FinalizeContext(&ctx);
        return -1;
    }

    // 3. Prepare operation with shared memory
    memset(&op, 0, sizeof(op));
    op.paramTypes = TEEC_PARAM_TYPES(
        TEEC_MEMREF_TEMP_INPUT,  // Param 0: temp input buffer
        TEEC_MEMREF_TEMP_OUTPUT, // Param 1: temp output buffer
        TEEC_NONE,               // Param 2: unused
        TEEC_NONE                // Param 3: unused
    );

    char input[] = "Hello from Normal World!";
    char output[64] = {0};

    op.params[0].tmpref.buffer = input;
    op.params[0].tmpref.size   = sizeof(input);
    op.params[1].tmpref.buffer = output;
    op.params[1].tmpref.size   = sizeof(output);

    // 4. Invoke command (TA command ID 0)
    res = TEEC_InvokeCommand(&sess, TA_HELLO_WORLD_CMD_ECHO,
                             &op, &err_origin);
    if (res == TEEC_SUCCESS) {
        printf("TA replied: %s\n", output);
    } else {
        printf("InvokeCommand failed: 0x%x\n", res);
    }

    // 5. Cleanup
    TEEC_CloseSession(&sess);
    TEEC_FinalizeContext(&ctx);
    return 0;
}
```

### Compilation

```bash
# Cross-compile for ARM64 (typical on Raspberry Pi 4 or QEMU)
aarch64-linux-gnu-gcc \
    -I/path/to/optee_client/public/include \
    -L/path/to/optee_client/build/lib \
    ca_hello.c -lteec -o ca_hello

# Deploy to target and run
scp ca_hello root@target:/tmp/
ssh root@target /tmp/ca_hello
```

### TA Side Skeleton (for reference)

```c
// ta_hello_world.c
TEE_Result TA_InvokeCommandEntryPoint(void *session_context,
                                      uint32_t cmd_id,
                                      uint32_t param_types,
                                      TEE_Param params[4]) {
    switch (cmd_id) {
    case TA_HELLO_WORLD_CMD_ECHO:
        // params[0] = input string
        // params[1] = output buffer
        TEE_MemMove(params[1].memref.buffer,
                    params[0].memref.buffer,
                    params[0].memref.size);
        params[1].memref.size = params[0].memref.size;
        return TEE_SUCCESS;
    }
    return TEE_ERROR_NOT_SUPPORTED;
}
```

## Common Pitfalls & Gotchas

1. **Shared memory registration failure**: If your buffer is not page-aligned or its size is not a multiple of the page size, `TEEC_RegisterSharedMemory` will fail with `TEEC_ERROR_BAD_PARAMETERS`. Use `TEEC_AllocateSharedMemory` instead — it handles alignment internally. For temp memory references (`TEEC_MEMREF_TEMP_*`), the driver copies data internally, so alignment is less strict, but performance suffers.

2. **Session login method mismatch**: `TEEC_LOGIN_PUBLIC` works for most development, but some TAs require `TEEC_LOGIN_USER` or `TEEC_LOGIN_GROUP`. If you get `TEEC_ERROR_ACCESS_DENIED` on `TEEC_OpenSession`, check the TA's `TA_FLAG_USER_MODE` and login method. The TA manifest (`manifest.txt`) defines which login methods are accepted.

3. **Forgetting to set `paramTypes`**: The `paramTypes` field is a bitmask that tells the TEE driver how to interpret each of the four `params[]` entries. If you leave it as zero (all `TEEC_NONE`), the TA will receive no data. This is the #1 bug I've seen in new CA code — the operation appears to succeed, but the TA sees empty buffers.

## Try It Yourself

1. **Modify the CA to use registered shared memory**: Replace `TEEC_MEMREF_TEMP_INPUT` with `TEEC_MEMREF_WHOLE` and call `TEEC_RegisterSharedMemory` before `TEEC_InvokeCommand`. Measure the latency difference using `clock_gettime` for both approaches.

2. **Add error handling for all TEE errors**: Extend the CA to print human-readable error strings for `TEEC_ERROR_OUT_OF_MEMORY`, `TEEC_ERROR_TARGET_DEAD`, and `TEEC_ERROR_COMMUNICATION`. Test by killing the TA daemon (`tee-supplicant`) mid-session.

3. **Implement a multi-session CA**: Open two sessions to the same TA with different login methods. Verify that each session gets its own context and that shared memory from one session is not accessible from the other.

## Next Up

Tomorrow: **Secure Boot on Embedded Linux: U-Boot Verified Boot** — we'll move from runtime TEE usage to boot-time integrity, examining how U-Boot's verified boot mechanism chains trust from the first stage bootloader to the Linux kernel, and how it interacts with OP-TEE for measured boot attestation.
