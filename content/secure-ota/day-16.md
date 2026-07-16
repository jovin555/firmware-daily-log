---
title: "Day 16: Resuming Interrupted Downloads: Chunked Transfer & Integrity"
date: 2026-07-16
tags: ["til", "secure-ota", "chunked-transfer", "resumability"]
---

## What I Explored Today

Today I tackled one of the most frustrating failure modes in OTA: a 90% complete download that dies because the device lost connectivity, battery dipped, or the server timed out. Without resumability, that means re-downloading the entire delta from scratch—wasting bandwidth, time, and flash write cycles. I implemented chunked transfer with per-chunk integrity verification, enabling the device to resume from the last verified byte rather than starting over.

## The Core Concept

The fundamental insight is that **download resumption is not about retrying—it's about proving what you already have**. A naive approach stores a single offset and hopes the server supports HTTP Range requests. That works for simple cases, but in embedded OTA, we need cryptographic proof that each chunk we claim to have is actually correct and hasn't been corrupted in flash.

The solution is to split the delta update into fixed-size chunks (typically 1-16 KB, depending on your flash page size and RAM budget), compute a SHA-256 hash for each chunk, and store a chunk manifest alongside the partially-downloaded data. When resuming, the device sends the manifest to the server, which responds with only the missing or corrupted chunks.

This approach also enables **parallel chunk validation**: you can verify chunks while others are still downloading, and you never waste time re-downloading data you already have. For delta updates where the patch is already small (often 10-30% of full image size), this makes resumption nearly free.

## Key Commands / Configuration / Code

Here's a practical implementation using a chunk manifest structure and a resume handshake:

```c
// chunk_ota.h - Chunked OTA with resumability support

#define CHUNK_SIZE 4096  // 4 KB chunks, aligns with common flash pages
#define MAX_CHUNKS 1024  // Supports up to 4 MB delta images
#define HASH_SIZE 32     // SHA-256 output

typedef struct {
    uint32_t chunk_index;
    uint8_t  hash[HASH_SIZE];   // SHA-256 of this chunk's data
    uint8_t  verified : 1;      // 1 = hash matches stored data
    uint8_t  present  : 1;      // 1 = chunk data is in flash
    uint8_t  reserved : 6;
} __attribute__((packed)) chunk_entry_t;

typedef struct {
    uint32_t total_chunks;
    uint32_t chunk_size;
    uint32_t total_size;        // Original delta file size
    uint8_t  image_hash[HASH_SIZE];  // SHA-256 of entire delta
    chunk_entry_t chunks[MAX_CHUNKS];
} __attribute__((packed)) chunk_manifest_t;
```

The resume handshake uses a compact bitmap to tell the server which chunks are needed:

```python
# server/resume_handler.py - Server-side resume logic

import hashlib
from flask import Flask, request, Response

app = Flask(__name__)

# In production, store this in a database keyed by device_id
PENDING_UPDATES = {}

@app.route('/ota/resume/<device_id>', methods=['POST'])
def handle_resume(device_id):
    """
    Client sends: { "manifest": { chunk_index: sha256_hex, ... } }
    Server responds with missing/corrupt chunks.
    """
    client_manifest = request.json.get('manifest', {})
    server_delta = PENDING_UPDATES.get(device_id)
    
    if not server_delta:
        return {"error": "No pending update"}, 404
    
    missing_chunks = []
    for idx, expected_hash in server_delta['chunk_hashes'].items():
        client_hash = client_manifest.get(str(idx))
        if client_hash != expected_hash:
            missing_chunks.append(int(idx))
    
    # Build response with only needed chunks
    response_data = {
        "chunk_size": server_delta['chunk_size'],
        "total_chunks": server_delta['total_chunks'],
        "chunks": {}
    }
    
    for idx in missing_chunks:
        chunk_data = server_delta['chunks'][idx]
        response_data['chunks'][str(idx)] = {
            "data": chunk_data.hex(),
            "sha256": hashlib.sha256(chunk_data).hexdigest()
        }
    
    return response_data
```

On the device side, the resume logic is straightforward:

```c
// chunk_ota.c - Device-side resume logic

ota_status_t ota_resume_download(chunk_manifest_t *manifest) {
    // Step 1: Build resume request from local manifest
    char request_body[4096];
    int offset = snprintf(request_body, sizeof(request_body), 
                          "{ \"manifest\": {");
    
    for (uint32_t i = 0; i < manifest->total_chunks; i++) {
        if (manifest->chunks[i].present && manifest->chunks[i].verified) {
            // Skip chunks we already have verified
            continue;
        }
        // Report chunk index and stored hash for server to validate
        char hash_hex[65];
        bytes_to_hex(manifest->chunks[i].hash, HASH_SIZE, hash_hex);
        offset += snprintf(request_body + offset, 
                          sizeof(request_body) - offset,
                          "\"%lu\":\"%s\",", i, hash_hex);
    }
    
    // Step 2: Send resume request, receive missing chunks
    http_response_t *resp = http_post("/ota/resume", request_body);
    
    // Step 3: Write each received chunk and verify immediately
    for (int i = 0; i < resp->chunk_count; i++) {
        uint32_t idx = resp->chunks[i].index;
        uint8_t *data = resp->chunks[i].data;
        uint32_t len = resp->chunks[i].length;
        
        // Verify hash before writing to flash
        uint8_t computed_hash[HASH_SIZE];
        sha256(data, len, computed_hash);
        
        if (memcmp(computed_hash, resp->chunks[i].expected_hash, HASH_SIZE) != 0) {
            return OTA_ERR_HASH_MISMATCH;
        }
        
        // Write to flash at chunk offset
        flash_write(CHUNK_BASE_ADDR + (idx * CHUNK_SIZE), data, len);
        manifest->chunks[idx].verified = 1;
        manifest->chunks[idx].present = 1;
    }
    
    return OTA_OK;
}
```

## Common Pitfalls & Gotchas

**1. Flash wear from partial writes.** If you write a chunk and then the device crashes, you might have a partially-written flash page. Always write chunks to a staging area, then use a two-phase commit: mark the chunk as "pending" in a separate metadata sector, write the data, then flip the flag to "verified." If you crash mid-write, the manifest tells you to re-download that chunk.

**2. Clock drift on timestamp-based resumption.** Some implementations use timestamps to decide if a chunk is stale. Don't. Embedded RTCs drift by minutes per day. Use content-addressed hashing instead: the server sends the hash of each chunk, and the device compares against its stored hash. No clock required.

**3. Manifest corruption is worse than data corruption.** If your chunk manifest gets corrupted, you lose all knowledge of what you have. Store the manifest in a separate flash sector with ECC, and keep a backup copy. On boot, compare both copies; if they differ, assume the worst and restart the download.

## Try It Yourself

1. **Implement a chunk verification pipeline.** Write a function that downloads a single chunk, computes its SHA-256, and only commits to flash if the hash matches. Test with intentionally corrupted data to ensure your error handling works.

2. **Build a resume handshake simulator.** Create a Python script that pretends to be the device, sends a manifest with half the chunks marked as "verified," and confirms the server only returns the missing chunks. Use a real delta file (e.g., a 256 KB firmware binary).

3. **Add a "chunk bitmap" to your manifest.** Instead of storing hashes for every chunk (which wastes flash), use a bitmap of 1s and 0s to indicate which chunks are present, then store hashes only for verified chunks. Measure the flash savings for a 1 MB delta with 4 KB chunks.

## Next Up

Tomorrow we expand from single-image updates to **Multi-Image Updates: Bootloader, App & Peripheral Firmware Together**. We'll design a coordinated update sequence that handles dependency ordering, version compatibility, and atomic rollback across three separate MCU images without bricking the device.
