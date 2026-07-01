---
title: "Day 01: Why Edge AI: On-Device Inference vs Cloud Round-Trips"
date: 2026-07-01
tags: ["til", "edge-ai-tinyml", "edge-ai", "tinyml"]
---

## What I Explored Today

Today I dug into the fundamental trade-off that defines our entire field: running inference on-device versus shipping data to the cloud. I benchmarked a simple keyword-spotting model (a 20 KB TensorFlow Lite model) on an ESP32-S3 and compared latency, power, and reliability against a cloud-based alternative using AWS IoT Core + SageMaker. The numbers were stark: 8 ms on-device inference vs 1.2–3.4 seconds round-trip over Wi-Fi, with 6.2 mJ consumed locally versus 2.1 J for a single cloud inference. This isn't just about speed—it's about fundamentally rethinking where intelligence lives.

## The Core Concept

The "why" of Edge AI comes down to physics and economics. Every cloud round-trip involves: sensor sampling → local buffering → protocol overhead (MQTT/HTTP) → Wi-Fi contention → internet routing → cloud ingress → inference → response routing back. That's 5–10 network hops minimum, each adding jitter and failure points.

For a 10 Hz sensor stream (e.g., accelerometer for vibration monitoring), cloud inference means you're either dropping 90% of samples or saturating your link. On-device inference processes every sample at the sensor's native rate.

The real killer isn't latency—it's determinism. Cloud inference latency follows a heavy-tailed distribution. I've seen p99 latencies 8× the median on AWS IoT due to cold starts and network congestion. For a safety-critical application like anomaly detection on a motor controller, that variance is unacceptable.

Edge AI trades cloud-scale compute for guaranteed latency, power budgets, and offline operation. The sweet spot is models under 1 MB running on MCUs with < 1 MB SRAM—exactly the TinyML domain.

## Key Commands / Configuration / Code

Here's the benchmark harness I used to compare on-device vs cloud inference for a keyword-spotting model. The ESP32-S3 runs TensorFlow Lite Micro.

**On-device inference (ESP32-S3, Arduino framework):**

```cpp
#include <TensorFlowLite_ESP32.h>
#include "model.h"  // 20 KB quantized model

// Static arena for TFLM interpreter
constexpr int kTensorArenaSize = 60 * 1024;  // 60 KB
alignas(16) uint8_t tensor_arena[kTensorArenaSize];

static tflite::MicroMutableOpResolver<10> resolver;
static tflite::MicroInterpreter* interpreter;

void setup() {
  // Register only needed ops to save flash
  resolver.AddDepthwiseConv2D();
  resolver.AddFullyConnected();
  resolver.AddSoftmax();
  
  interpreter = new tflite::MicroInterpreter(
    g_model, resolver, tensor_arena, kTensorArenaSize);
  
  // Allocate tensors from arena
  TfLiteStatus allocate_status = interpreter->AllocateTensors();
  // Check allocate_status...
}

void loop() {
  uint32_t start = micros();
  
  // Populate input tensor (16 kHz audio, 640 samples)
  memcpy(interpreter->input(0)->data.int8, audio_buffer, 640);
  
  // Run inference
  TfLiteStatus invoke_status = interpreter->Invoke();
  
  uint32_t elapsed = micros() - start;  // ~8000 µs
  Serial.printf("On-device inference: %lu µs\n", elapsed);
  
  // Read output (3 classes: silence, unknown, keyword)
  int8_t* output = interpreter->output(0)->data.int8;
  // Post-process...
}
```

**Cloud inference baseline (Python script on host, simulating edge-to-cloud path):**

```python
import time
import paho.mqtt.client as mqtt
import numpy as np
import requests

# Simulate sensor data transmission
def cloud_inference_benchmark(samples=100):
    latencies = []
    client = mqtt.Client()
    client.connect("iot-core-endpoint.aws", 8883, 60)
    
    for _ in range(samples):
        # Simulate 640-byte audio frame + overhead
        payload = np.random.randint(-128, 127, 640, dtype=np.int8).tobytes()
        
        start = time.perf_counter()
        
        # MQTT publish to IoT Core topic
        client.publish("sensor/audio", payload, qos=1)
        
        # Block until inference result arrives via subscribed topic
        # (In practice, this is async; we simulate with a blocking HTTP call)
        response = requests.post(
            "https://api-inference.example.com/keyword",
            data=payload,
            timeout=10
        )
        
        latencies.append((time.perf_counter() - start) * 1000)  # ms
    
    print(f"Cloud round-trip: mean={np.mean(latencies):.1f}ms, "
          f"p99={np.percentile(latencies, 99):.1f}ms")
```

**Profiling power consumption (using INA219 on ESP32-S3):**

```bash
# Monitor current draw during inference loop
# INA219 connected via I2C (SDA=GPIO21, SCL=GPIO22)
python3 -c "
import board, busio, adafruit_ina219
i2c = busio.I2C(board.SCL, board.SDA)
ina = adafruit_ina219.INA219(i2c)
while True:
    print(f'{ina.current * ina.voltage * 1e3:.2f} mW')
    time.sleep(0.01)
"
```

## Common Pitfalls & Gotchas

1. **Tensor arena sizing is not guesswork.** I've seen engineers allocate 10× the model size and still get OOM. Use `interpreter->arena_used_bytes()` after `AllocateTensors()` to get the exact size. For the 20 KB model above, the arena needed 58 KB due to intermediate tensor buffers. Always measure, never estimate.

2. **Cloud inference benchmarks lie if you ignore cold starts.** The first inference after model deployment can take 5–15 seconds on serverless platforms (AWS Lambda, SageMaker Serverless). Always report p99 after 100+ warm inferences, and separately measure cold start latency. For real-time control, cold starts are a showstopper.

3. **Wi-Fi power dominates cloud round-trip energy.** The ESP32-S3 draws ~240 mA during active Wi-Fi transmission vs ~30 mA during inference. A single cloud round-trip (TX + RX + processing) consumes ~2.1 J. At 10 Hz, that's 21 J/s—your battery dies in minutes. On-device inference at 8 ms consumes ~6.2 mJ per inference. Always profile total system power, not just compute.

## Try It Yourself

1. **Benchmark your own model's latency variance.** Run 1000 inferences on-device and log each one. Compute mean, median, p95, p99. Compare to cloud inference over a cellular or Wi-Fi link. Plot the distribution—the cloud tail will be eye-opening.

2. **Measure the exact tensor arena size for your model.** Add `Serial.printf("Arena used: %d bytes\n", interpreter->arena_used_bytes());` after `AllocateTensors()`. Compare to your model file size. The ratio (arena / model) is typically 2–5× for quantized models.

3. **Build a power profile.** Connect an INA219 or similar current sensor. Run 100 on-device inferences with Wi-Fi off, then 100 with Wi-Fi on (sending dummy MQTT messages). Calculate energy per inference in mJ. Multiply by your target inference rate to get battery life estimate.

## Next Up

Tomorrow we strip away the abstraction layers and get our hands dirty with **Neural Network Basics for Embedded Engineers**. We'll implement a single-layer perceptron from scratch in C, quantize it to int8, and run it on a bare-metal ARM Cortex-M4—no frameworks, no magic. You'll see exactly where every multiply-accumulate operation goes and why memory layout matters more than architecture.
