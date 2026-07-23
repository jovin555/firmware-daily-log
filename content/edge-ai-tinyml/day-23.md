---
title: "Day 23: Testing & Validating TinyML Models on Real Hardware"
date: 2026-07-23
tags: ["til", "edge-ai-tinyml", "validation", "hardware-testing"]
---

## What I Explored Today

After weeks of training and quantizing models in simulation, I finally put my TensorFlow Lite Micro model onto an actual Cortex-M4 board today. The gap between simulated accuracy and real-world performance was sobering — my carefully tuned 95% validation accuracy dropped to 72% on hardware due to sensor noise, clock jitter, and uncalibrated ADC readings. Today’s deep dive covered the systematic process of validating TinyML models on physical hardware: from setting up reproducible test harnesses with serial logging, to measuring inference latency with cycle-accurate timers, to catching silent data corruption from memory alignment issues.

## The Core Concept

The fundamental reason we must test on real hardware is that TinyML models are not just algorithms — they are cyber-physical systems. The model’s inputs come from real sensors with noise, drift, and non-linearities that synthetic datasets cannot replicate. The model’s execution happens on resource-constrained MCUs where memory fragmentation, cache misses (if any), and interrupt latency directly affect timing and correctness.

A model that achieves 98% accuracy in a Python notebook on a desktop GPU can fail catastrophically on hardware for three reasons:
1. **Quantization drift** — int8 arithmetic introduces rounding errors that compound differently on actual sensor data distributions.
2. **Sensor mismatch** — the training data was collected with a different sensor model or gain setting.
3. **Timing constraints** — the inference must complete within a real-time window (e.g., 50ms for audio keyword spotting), and any violation causes dropped frames.

The validation process must therefore be a closed loop: collect real sensor data → run inference on-device → log predictions and ground truth → compute metrics offline. This is not optional — it is the only way to know if your model works in the field.

## Key Commands / Configuration / Code

Below is a practical test harness for an Arduino Nano BLE Sense (nRF52840) that streams inference results over serial for offline validation.

```cpp
// test_harness.ino — Real hardware validation sketch
#include <TensorFlowLite.h>
#include "model.h"  // quantized .tflite model as C array

// Pin definitions
const int sensorPin = A0;  // microphone or accelerometer
const int ledPin = LED_BUILTIN;

// TFLite globals
tflite::MicroErrorReporter micro_error;
tflite::MicroInterpreter* interpreter;
constexpr int tensor_arena_size = 16 * 1024;  // 16KB for nRF52840
uint8_t tensor_arena[tensor_arena_size];

// Ground truth label (set manually or from button press)
int ground_truth = -1;

void setup() {
  Serial.begin(115200);
  while (!Serial);  // wait for serial monitor
  
  // Load model
  static tflite::Model* model = tflite::GetModel(g_model);
  if (model->version() != TFLITE_SCHEMA_VERSION) {
    Serial.println("Model schema mismatch!");
    while(1);
  }
  
  static tflite::MicroInterpreter static_interpreter(
    model, micro_resolver, tensor_arena, tensor_arena_size, &micro_error);
  interpreter = &static_interpreter;
  
  // Allocate tensors
  TfLiteStatus allocate_status = interpreter->AllocateTensors();
  if (allocate_status != kTfLiteOk) {
    Serial.println("Allocation failed!");
    while(1);
  }
  
  pinMode(ledPin, OUTPUT);
  Serial.println("READY");  // handshake for Python script
}

void loop() {
  // 1. Capture sensor data (example: 128 samples @ 16kHz)
  float input_buffer[128];
  for (int i = 0; i < 128; i++) {
    input_buffer[i] = analogRead(sensorPin) * (3.3 / 1023.0);
    delayMicroseconds(62);  // ~16kHz sampling
  }
  
  // 2. Preprocess and quantize to int8
  int8_t* input = interpreter->input(0)->data.int8;
  float scale = interpreter->input(0)->params.scale;
  int zero_point = interpreter->input(0)->params.zero_point;
  for (int i = 0; i < 128; i++) {
    input[i] = (int8_t)(input_buffer[i] / scale + zero_point);
  }
  
  // 3. Run inference with cycle-accurate timing
  uint32_t start = micros();
  TfLiteStatus invoke_status = interpreter->Invoke();
  uint32_t elapsed = micros() - start;
  
  if (invoke_status != kTfLiteOk) {
    Serial.println("INFERENCE_FAIL");
    return;
  }
  
  // 4. Read output (assumes classification with 3 classes)
  int8_t* output = interpreter->output(0)->data.int8;
  int predicted_class = 0;
  int8_t max_val = output[0];
  for (int i = 1; i < 3; i++) {
    if (output[i] > max_val) {
      max_val = output[i];
      predicted_class = i;
    }
  }
  
  // 5. Stream CSV: timestamp, ground_truth, prediction, latency_us
  Serial.print(millis());
  Serial.print(",");
  Serial.print(ground_truth);
  Serial.print(",");
  Serial.print(predicted_class);
  Serial.print(",");
  Serial.println(elapsed);
  
  digitalWrite(ledPin, !digitalRead(ledPin));  // heartbeat
  delay(100);  // throttle to ~10 inferences/sec
}
```

On the host side, capture and evaluate:

```bash
# capture_validation.py — collect and score
import serial, csv, sys

ser = serial.Serial('/dev/ttyACM0', 115200, timeout=5)
# Wait for handshake
while ser.readline().strip() != b'READY':
    pass

with open('validation_log.csv', 'w') as f:
    writer = csv.writer(f)
    writer.writerow(['timestamp', 'ground_truth', 'prediction', 'latency_us'])
    for _ in range(1000):  # collect 1000 samples
        line = ser.readline().decode().strip()
        if line and line != 'INFERENCE_FAIL':
            writer.writerow(line.split(','))

# Compute metrics
import pandas as pd
df = pd.read_csv('validation_log.csv')
accuracy = (df['ground_truth'] == df['prediction']).mean()
print(f"Hardware accuracy: {accuracy:.2%}")
print(f"Avg latency: {df['latency_us'].mean():.0f} us")
```

## Common Pitfalls & Gotchas

1. **Silent tensor arena overflow** — The `tensor_arena_size` must be at least what `interpreter->arena_used_bytes()` returns after allocation. If you guess too small, the interpreter silently corrupts memory. Always print `arena_used_bytes()` in setup and verify it’s ≤ your arena size.

2. **ADC sampling jitter** — Using `delayMicroseconds()` for precise sampling is unreliable because interrupts (USB, timers) cause jitter. For audio or high-frequency sensor data, use a hardware timer or DMA to sample. On nRF52840, use the PDM or I2S peripheral directly.

3. **Serial bottleneck** — Streaming every inference result at 115200 baud limits throughput. If you need >100 inferences/sec, buffer results in RAM and burst-transmit every 100ms, or use binary protocol (e.g., send raw int8 bytes instead of ASCII CSV).

## Try It Yourself

1. **Baseline accuracy gap** — Take a model that achieved >90% accuracy in your Python validation. Run it on hardware with the test harness above. Compute the accuracy difference. Identify the top-3 misclassified inputs and inspect the raw sensor data — you’ll likely see distribution shift.

2. **Latency profiling** — Add `micros()` calls around the `Invoke()` call (as shown) and also around the preprocessing loop. Plot latency histograms. Is there a worst-case latency >2x the average? If so, investigate interrupt nesting or memory bandwidth contention.

3. **Sensor calibration** — Collect 100 samples of a known input (e.g., silence for audio, flat surface for accelerometer). Compute the mean and standard deviation of the raw ADC values. Adjust your preprocessing normalization constants to match real hardware statistics, then re-run the accuracy test.

## Next Up

Tomorrow is the capstone: **Full Review & Project: Keyword Spotting on an Arduino Nano BLE Sense**. We’ll integrate everything from the past 23 days — data collection pipeline, model training with quantization-aware training, on-device inference with the PDM microphone, and a real-time LED feedback system. Bring your board and a soldering iron (for the microphone breakout).
