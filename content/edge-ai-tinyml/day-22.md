---
title: "Day 22: Model Versioning & OTA-Updating Deployed ML Models"
date: 2026-07-22
tags: ["til", "edge-ai-tinyml", "model-versioning", "ota"]
---

## What I Explored Today

Today I tackled one of the most painful realities of production TinyML: you can't just `git push` to a microcontroller. Once a model is flashed onto an ESP32, STM32, or Cortex-M device, updating it means either a full firmware reflash (brick risk, user friction) or an over-the-air (OTA) update pipeline. I spent the day building a minimal but production-ready model versioning and OTA update flow using an ESP32-S3, TensorFlow Lite Micro, and a custom partition scheme. The key insight: treat the model as a separate, swappable asset—not part of the firmware binary.

## The Core Concept

In traditional embedded development, the ML model is compiled into the firmware image. This is fine for prototypes, but in production you face three realities:

1. **Models drift** — new data means retraining, and you need to push updates without a full firmware OTA (which risks bricking the device if power fails mid-flash).
2. **Firmware and model have different release cadences** — firmware might change quarterly, models weekly.
3. **Rollback matters** — a bad model update shouldn't require a JTAG debugger to recover.

The solution is **partitioned model storage**. Reserve a dedicated flash partition for the model binary (`.tflite`), decoupled from the application firmware. The bootloader or application checks a version header, downloads the new model to a staging partition, validates it (CRC, magic bytes, input/output tensor signatures), then swaps it into the active partition. This is exactly how smartphone OS updates work—just scaled down to kilobytes.

## Key Commands / Configuration / Code

### 1. Partition Table (ESP-IDF `partitions.csv`)

```csv
# Name,   Type, SubType, Offset,  Size, Flags
nvs,      data, nvs,     0x9000,  0x4000,
otadata,  data, ota,     0xd000,  0x2000,
app0,     app,  ota_0,   0x10000, 0x1E0000,
app1,     app,  ota_1,   0x1F0000,0x1E0000,
model_v1, data, unknown, 0x3D0000,0x10000,  # 64KB model slot
model_v2, data, unknown, 0x3E0000,0x10000,  # staging slot
coredump, data, coredump,0x3F0000,0x10000,
```

**Why this matters:** We reserve two 64KB partitions (`model_v1` and `model_v2`). One is active, one is staging. The firmware never writes to the active partition directly—it always downloads to staging, validates, then swaps.

### 2. Model Version Header (C struct)

```c
// model_header.h
#pragma once
#include <stdint.h>

#define MODEL_MAGIC 0xDEADBEEF
#define MODEL_MAX_NAME 32

typedef struct __attribute__((packed)) {
    uint32_t magic;          // 0xDEADBEEF
    uint32_t version;        // monotonic version number
    uint32_t model_size;     // bytes of .tflite data
    uint32_t crc32;          // CRC-32 of the model data
    uint32_t input_size;     // expected input tensor bytes
    uint32_t output_size;    // expected output tensor bytes
    char     name[MODEL_MAX_NAME]; // e.g., "person_detector_v3"
} model_header_t;
```

### 3. OTA Update Logic (simplified)

```c
// ota_model_update.c
#include "esp_ota_ops.h"
#include "esp_partition.h"
#include "esp_http_client.h"
#include "esp_crc.h"

static const esp_partition_t *find_model_partition(const char *label) {
    return esp_partition_find_first(
        ESP_PARTITION_TYPE_DATA,
        ESP_PARTITION_SUBTYPE_ANY,
        label);
}

esp_err_t download_and_swap_model(const char *url) {
    // 1. Get staging partition (model_v2)
    const esp_partition_t *staging = find_model_partition("model_v2");
    const esp_partition_t *active  = find_model_partition("model_v1");

    // 2. Stream HTTP download directly to staging partition
    esp_http_client_config_t config = {
        .url = url,
        .timeout_ms = 10000,
    };
    esp_http_client_handle_t client = esp_http_client_init(&config);
    esp_http_client_open(client, 0);  // GET request

    // 3. Read header first (first sizeof(model_header_t) bytes)
    model_header_t header;
    int read_len = esp_http_client_read(client, (char*)&header, sizeof(header));
    assert(read_len == sizeof(header));
    assert(header.magic == MODEL_MAGIC);

    // 4. Validate CRC before writing
    uint8_t *model_data = malloc(header.model_size);
    read_len = esp_http_client_read(client, (char*)model_data, header.model_size);
    uint32_t computed_crc = esp_crc32_le(0, model_data, header.model_size);
    assert(computed_crc == header.crc32);

    // 5. Erase staging partition and write
    esp_partition_erase_range(staging, 0, staging->size);
    esp_partition_write(staging, 0, &header, sizeof(header));
    esp_partition_write(staging, sizeof(header), model_data, header.model_size);

    // 6. Swap: copy staging to active (or use a boot-time flag)
    esp_partition_erase_range(active, 0, active->size);
    esp_partition_write(active, 0, &header, sizeof(header));
    esp_partition_write(active, sizeof(header), model_data, header.model_size);

    free(model_data);
    esp_http_client_cleanup(client);
    return ESP_OK;
}
```

### 4. Runtime Model Loading (TFLite Micro)

```c
// model_loader.c
#include "tensorflow/lite/micro/all_ops_resolver.h"
#include "tensorflow/lite/micro/micro_interpreter.h"

static const esp_partition_t *model_partition;
static model_header_t current_header;

esp_err_t load_active_model() {
    model_partition = find_model_partition("model_v1");

    // Read header from flash
    esp_partition_read(model_partition, 0, &current_header, sizeof(current_header));
    assert(current_header.magic == MODEL_MAGIC);

    // Memory-map or read the model data
    uint8_t *model_data = heap_caps_malloc(current_header.model_size, MALLOC_CAP_SPIRAM);
    esp_partition_read(model_partition, sizeof(current_header), model_data, current_header.model_size);

    // Initialize TFLite interpreter
    static tflite::MicroMutableOpResolver<10> resolver;
    static tflite::MicroInterpreter static_interpreter(
        tflite::GetModel(model_data), resolver,
        tensor_arena, TENSOR_ARENA_SIZE);

    // Verify input/output sizes match header
    TfLiteTensor* input = static_interpreter.input(0);
    assert(input->bytes == current_header.input_size);
    return ESP_OK;
}
```

## Common Pitfalls & Gotchas

1. **Partition alignment and wear leveling.** Flash partitions must be aligned to the sector size (usually 4KB for ESP32). Writing a 32KB model to a misaligned offset will silently corrupt adjacent data. Always use `esp_partition_erase_range()` with sector-aligned offsets. Also, if you're doing frequent updates (daily), consider wear leveling—ESP-IDF's `wear_levelling` component can wrap the model partition.

2. **CRC validation before write, not after.** I made the mistake of downloading the model, writing it to staging, then reading it back to validate. If the download was corrupted, I'd already erased the staging partition and had no fallback. Always validate the CRC in RAM before touching flash. If validation fails, abort and keep the old model.

3. **Model version mismatch with firmware.** Your firmware might expect a specific input tensor shape (e.g., 96x96 grayscale), but an OTA model could be 128x128. The version header's `input_size` field is your safety net. At boot, compare the header's `input_size` against the firmware's compile-time constant. If they mismatch, refuse to load and log an error. Better to run an old model than crash on a tensor shape mismatch.

## Try It Yourself

1. **Add a rollback mechanism.** Modify the OTA code to keep the previous model version in `model_v2` after a swap. If the new model causes a watchdog reset (detected by a boot counter), the bootloader should swap back to `model_v1` automatically.

2. **Implement a version server.** Write a simple Python Flask server that serves models at `/api/models/latest` and returns a JSON manifest with version, CRC, and download URL. Have the ESP32 poll this endpoint every 24 hours.

3. **Compression for bandwidth-constrained links.** If your device uses BLE or LoRaWAN, the model binary might be too large. Add zlib decompression on the device: compress the `.tflite` on the server, decompress it in RAM on the ESP32 before writing to flash. Measure the tradeoff between flash write time and download time.

## Next Up

Tomorrow: **Testing & Validating TinyML Models on Real Hardware** — I'll cover how to build a hardware-in-the-loop test harness that streams sensor data to a host PC, runs inference on the device, and compares outputs against a golden reference model. No more "it works in the simulator."
