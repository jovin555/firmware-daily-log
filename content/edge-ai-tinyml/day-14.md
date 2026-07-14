---
title: "Day 14: Edge Impulse: End-to-End TinyML Pipeline for Embedded Sensors"
date: 2026-07-14
tags: ["til", "edge-ai-tinyml", "edge-impulse", "pipeline"]
---

## What I Explored Today

Today I took Edge Impulse through its full paces — from raw sensor data ingestion on an STM32 B-L475E-IOT01A board, through feature engineering, model training, and finally deploying a quantized int8 model back to the target. The goal was to build a vibration anomaly detector for industrial motor monitoring using the onboard LSM6DSL accelerometer. What struck me most was how Edge Impulse handles the entire MLOps lifecycle for embedded targets without requiring a single line of Python on the developer's machine — though you can drop into Python notebooks if needed. The platform's DSP (Digital Signal Processing) block pipeline is particularly clever: it converts raw time-series sensor data into spectral features before the model ever sees it, dramatically reducing the model size and inference latency.

## The Core Concept

The fundamental insight behind Edge Impulse is that TinyML isn't just about model compression — it's about **data-to-deployment pipeline unification**. Most embedded ML workflows suffer from toolchain fragmentation: you collect data with one tool (e.g., serial logger), preprocess with Python scripts, train with TensorFlow/PyTorch, quantize with a separate tool, then manually port to C++. Each handoff introduces friction, versioning issues, and bit-exactness problems.

Edge Impulse solves this by providing a single, auditable pipeline where every transformation is recorded as a "block." The pipeline has four stages:
1. **Ingestion** — collect labeled sensor data via serial, BLE, or SD card
2. **Impulse design** — chain DSP blocks (spectral analysis, statistical features) with a learning block (classifier, regression, anomaly detection)
3. **Training & tuning** — automated hyperparameter search, on-devise accuracy testing
4. **Deployment** — generate a C++ library or firmware update with optimized int8 inference

The key technical detail: Edge Impulse uses **EON Tuner** (Edge Optimized Neural) to automatically search for the smallest model architecture that meets your accuracy target. It tries different layer counts, filter sizes, and quantization strategies, then reports the RAM/Flash footprint for your specific target MCU. This is a game-changer for production systems where you need to hit a 128KB Flash budget.

## Key Commands / Configuration / Code

Here's the actual workflow for the vibration anomaly detector. First, data collection via the CLI tool:

```bash
# Install Edge Impulse CLI
npm install -g edge-impulse-cli

# Connect to the board and start data collection
edge-impulse-daemon --clean

# In another terminal, collect 10 seconds of "normal" vibration data
edge-impulse-data-forwarder --frequency 1000 --samples 10000 --label normal
# Then collect 10 seconds of "anomaly" data (tap the board)
edge-impulse-data-forwarder --frequency 1000 --samples 10000 --label anomaly
```

The Impulse design in the Edge Impulse Studio (web UI) configures the processing pipeline. Here's the equivalent using the Python SDK for reproducibility:

```python
import edge_impulse as ei

# Configure the impulse
impulse = ei.Impulse.create(
    input_block=ei.Accelerometer(
        frequency=1000,
        window_size_ms=200,      # 200ms windows
        window_shift_ms=50       # 50% overlap
    ),
    dsp_blocks=[
        ei.SpectralFeatures(
            fft_length=256,
            mel_count=13,
            filter_banks=0
        )
    ],
    learning_block=ei.AnomalyDetection(
        features_per_axis=13,
        distance="euclidean"
    )
)

# Train with EON Tuner
tuner = ei.EONTuner(
    impulse=impulse,
    target="stm32l475vg",
    ram_limit=65536,     # 64KB
    flash_limit=262144   # 256KB
)
results = tuner.run()
best_model = results.best_model
print(f"Best model: {best_model.architecture}, accuracy: {best_model.accuracy}")
```

After training, deploy to the target:

```bash
# Generate a C++ library for the STM32
edge-impulse-run-impulse --deploy --library --target stm32l475vg

# Or flash firmware directly
edge-impulse-run-impulse --deploy --firmware
```

The generated C++ inference code looks like this:

```c
#include "edge-impulse-sdk/classifier/ei_run_classifier.h"

// Buffer for 200ms of accelerometer data at 1000Hz
float features[600]; // 3 axes * 200 samples

void loop() {
    // Fill features from sensor
    read_accelerometer(features, 600);

    // Run inference
    ei_impulse_result_t result = {0};
    EI_IMPULSE_ERROR err = run_classifier(features, &result, false);
    
    if (err == EI_IMPULSE_OK) {
        float anomaly_score = result.anomaly;
        if (anomaly_score > 0.5) {
            trigger_alarm();
        }
    }
}
```

## Common Pitfalls & Gotchas

1. **Window size mismatch between training and deployment.** Edge Impulse's DSP blocks compute features over fixed windows. If you train with 200ms windows but your deployment code feeds 100ms windows, the feature dimensions won't match and inference will silently return garbage. Always verify `EI_CLASSIFIER_INPUT_WIDTH` in the generated header matches your training configuration.

2. **Sensor sampling jitter on bare-metal.** The `edge-impulse-daemon` on a board with an RTOS can maintain consistent 1000Hz sampling, but on a bare-metal loop, interrupt latency from other peripherals (UART, SPI) can cause jitter. This degrades FFT quality. Solution: use a hardware timer to trigger ADC reads, or enable the board's RTOS (FreeRTOS on STM32) for deterministic scheduling.

3. **Forgetting to disable the DC bias in spectral features.** For accelerometer vibration analysis, the DC component (0 Hz) dominates the FFT and masks the vibration harmonics. In the Spectral Features block, enable "Remove DC bias" — otherwise your model will learn to classify based on static orientation rather than vibration patterns. This single toggle can improve accuracy from 60% to 95% on vibration tasks.

## Try It Yourself

1. **Collect your own vibration dataset.** Use any board with an accelerometer (Arduino Nano BLE, STM32 B-L475E, or even a phone via Edge Impulse's mobile app). Collect 5 minutes of "normal" data and 2 minutes of "anomaly" data (tap, shake, or run a motor nearby). Train an anomaly detection model and test it live.

2. **Compare DSP vs. raw time-series.** Create two Impulses: one using Spectral Features (FFT-based) and one using a raw time-series classifier (1D CNN). Train both with the same data and compare their RAM/Flash usage and accuracy. You'll likely find the spectral approach uses 4-5x less memory for similar accuracy.

3. **Deploy to a battery-powered target.** Use the generated C++ library to build a firmware that runs inference every 100ms and blinks an LED on anomaly. Measure current draw with a multimeter — aim for <1mA average. Edge Impulse's EON Tuner can help you find the smallest model that fits your power budget.

## Next Up

Tomorrow we dive into **Keyword Spotting: Always-On Audio Wake-Word Detection** — we'll use Edge Impulse's audio blocks to build a "Hey, device" wake-word detector on a Cortex-M4, covering MFCC extraction, time-delay neural networks, and the critical challenge of voice activity detection (VAD) to keep power consumption under 10mW.
