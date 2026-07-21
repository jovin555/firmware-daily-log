---
title: "Day 21: Data Collection & Labeling Pipelines for Embedded Sensor Data"
date: 2026-07-21
tags: ["til", "edge-ai-tinyml", "data-collection", "labeling"]
---

## What I Explored Today

Today I tackled the most painful bottleneck in any TinyML project: building a production-grade data collection and labeling pipeline for raw sensor data. While everyone obsesses over model architectures, the reality is that garbage in equals garbage out—especially when your sensor is a 16-bit accelerometer spitting out 800 samples per second. I spent the day wiring up an ESP32-S3 to an ICM-20948 IMU, streaming raw XYZ data over USB-C to a Python daemon that segments, timestamps, and pushes labeled samples to a structured dataset store. The goal was a repeatable pipeline that doesn't require a PhD in data engineering to operate.

## The Core Concept

Embedded sensor data is fundamentally different from image or text data. You can't just point a camera and click "label." Sensor streams are continuous, high-frequency, and context-dependent. A single accelerometer reading means nothing—it's the *sequence* of readings over time that encodes the gesture, step, or vibration signature.

The core challenge is **temporal alignment**: you need to capture the exact moment an event starts and ends, and label that window correctly. If your labeling tool is off by 50ms, your model learns the wrong pattern. This is why you can't use generic labeling tools like LabelImg for sensor data. You need a pipeline that:
1. Buffers raw sensor frames with precise wall-clock timestamps
2. Provides a human-in-the-loop interface to mark event boundaries
3. Automatically segments the buffer into fixed-length windows (e.g., 128 samples at 100Hz = 1.28s)
4. Stores each window with its label in a format your training pipeline can consume (HDF5, TFRecord, or flat binary)

The pipeline I built today uses a **circular buffer** on the microcontroller side (to avoid data loss during USB latency spikes) and a **state-machine recorder** on the host side that toggles between "idle," "recording," and "labeling" modes.

## Key Commands / Configuration / Code

### Microcontroller Firmware (ESP32-S3 + ICM-20948)

```c
// Circular buffer for 3-axis accelerometer data
#define BUFFER_SIZE 1024
typedef struct {
    int16_t x, y, z;
    uint32_t timestamp_us;
} sensor_frame_t;

sensor_frame_t buffer[BUFFER_SIZE];
volatile uint16_t head = 0;
volatile uint16_t tail = 0;

// ISR: called at 100Hz from timer
void sensor_isr() {
    icm20948_read_accel(&buffer[head].x, &buffer[head].y, &buffer[head].z);
    buffer[head].timestamp_us = micros();
    head = (head + 1) % BUFFER_SIZE;
    if (head == tail) tail = (tail + 1) % BUFFER_SIZE; // overwrite oldest
}

// Main loop: drain buffer over UART
void loop() {
    while (tail != head) {
        Serial.printf("%d,%d,%d,%lu\n",
            buffer[tail].x, buffer[tail].y, buffer[tail].z,
            buffer[tail].timestamp_us);
        tail = (tail + 1) % BUFFER_SIZE;
    }
}
```

### Host-Side Python Data Recorder

```python
import serial
import numpy as np
import h5py
from datetime import datetime

# State machine: IDLE -> RECORDING -> LABELING
STATE_IDLE = 0
STATE_RECORDING = 1
STATE_LABELING = 2

class SensorRecorder:
    def __init__(self, port='/dev/ttyACM0', baud=921600):
        self.ser = serial.Serial(port, baud, timeout=1)
        self.buffer = []  # list of (x,y,z,timestamp_us)
        self.state = STATE_IDLE
        self.session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        
    def record_until_label(self, duration_s=5.0):
        """Record for `duration_s` seconds, then prompt for label."""
        start_time = time.time()
        while time.time() - start_time < duration_s:
            line = self.ser.readline().decode().strip()
            if line:
                x, y, z, ts = map(int, line.split(','))
                self.buffer.append((x, y, z, ts))
        # Segment into fixed windows (128 samples, 100Hz = 1.28s)
        windows = self._segment_buffer(window_size=128, stride=64)
        label = input("Enter label for this recording: ")
        self._save_to_hdf5(windows, label)
        self.buffer.clear()
        
    def _segment_buffer(self, window_size, stride):
        arr = np.array(self.buffer, dtype=np.int32)
        windows = []
        for start in range(0, len(arr) - window_size + 1, stride):
            windows.append(arr[start:start+window_size, :3])  # drop timestamp
        return np.array(windows)
    
    def _save_to_hdf5(self, windows, label):
        with h5py.File(f'sensor_data_{self.session_id}.h5', 'a') as f:
            if label not in f:
                f.create_dataset(label, data=windows, maxshape=(None, 128, 3))
            else:
                ds = f[label]
                ds.resize(ds.shape[0] + windows.shape[0], axis=0)
                ds[-windows.shape[0]:] = windows
```

### Labeling Workflow (CLI)

```bash
# Start recorder in interactive mode
python3 sensor_recorder.py --port /dev/ttyACM0 --baud 921600

# Press 'r' to start recording, perform gesture, press 's' to stop
# Enter label: "swipe_left"
# Automatically segments and appends to HDF5
```

## Common Pitfalls & Gotchas

1. **Clock drift between MCU and host timestamps.** The ESP32's `micros()` is based on its own crystal, which drifts. If you're fusing data from multiple sensors or synchronizing with video, use a PTP-capable Ethernet shield or at least log both MCU and host timestamps to compute offset. I wasted a day debugging misaligned windows because the MCU was 200ppm fast.

2. **Overlapping windows without proper stride.** If you use a stride of 1 (sliding window every sample), you'll generate 100x more training data than needed—and your model will overfit to temporal autocorrelation. For gesture recognition, a stride of 50-75% of window size is standard. For anomaly detection, use non-overlapping windows.

3. **Labeling latency bias.** Humans have reaction time (~200ms). If you press 's' to stop recording a gesture, you've already captured 20 extra samples. Always trim the first and last 10% of your recording window, or use a pre-trigger buffer that saves N samples *before* the label event.

## Try It Yourself

1. **Build a circular buffer on your dev board** (Arduino Nano 33 BLE, ESP32, or STM32) that streams IMU data at 100Hz over serial. Verify you don't drop frames by checking that `(head - tail) % BUFFER_SIZE` never exceeds 90% of buffer capacity.

2. **Write a Python script that records 10 seconds of "idle" data** (sensor sitting still) and 10 seconds of "shake" data. Segment into 128-sample windows with 50% overlap. Save to HDF5 and verify shapes: `h5ls sensor_data.h5` should show two datasets with shape `(N, 128, 3)`.

3. **Add a pre-trigger buffer** to your recorder: always keep the last 1 second of data in memory. When the user presses 'r', save that 1 second *before* the trigger plus 4 seconds after. This captures the natural start of a gesture.

## Next Up

Tomorrow: **Model Versioning & OTA-Updating Deployed ML Models** — how to tag, store, and wirelessly update models on resource-constrained devices without bricking them. We'll cover delta updates, rollback strategies, and the `model_manifest.json` pattern.
