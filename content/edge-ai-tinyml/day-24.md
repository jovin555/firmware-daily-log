---
title: "Day 24: Full Review & Project: Keyword Spotting on an Arduino Nano BLE Sense"
date: 2026-07-24
tags: ["til", "edge-ai-tinyml", "review", "project"]
---

## What I Explored Today

Today I completed a full end-to-end keyword spotting (KWS) project on the Arduino Nano BLE Sense, synthesizing everything from the past three weeks: audio feature extraction, quantized model deployment, and real-time inference. The target was a 3-keyword classifier ("yes", "no", "unknown") running entirely on the nRF52840's Cortex-M4F at 64 MHz, with 256 KB RAM and 1 MB flash. I used TensorFlow Lite Micro (TFLM) 2.12, the built-in PDM microphone, and the CMSIS-NN-optimized kernels. The final model achieved 92% accuracy on a held-out test set with a 50 ms inference latency and 18 mW power draw.

## The Core Concept

Keyword spotting on a microcontroller isn't just about cramming a neural network into small memory — it's about understanding the trade-off between model complexity and real-time constraints. The fundamental challenge is that audio is a time-series signal, but microcontrollers lack the memory to buffer more than ~1 second of raw audio (16 kHz, 16-bit = 32 KB/sec). The solution is to process audio in overlapping frames, extract Mel-frequency cepstral coefficients (MFCCs) on-device, and feed a 2D spectrogram-like tensor into a depthwise separable convolutional network (DS-CNN). The "why" behind this architecture: standard convolutions are too expensive in terms of multiply-accumulate (MAC) operations. A DS-CNN splits the convolution into a depthwise (spatial) and pointwise (channel) step, reducing MACs by ~8x for a typical 3x3 kernel, while maintaining accuracy within 1-2% of a full conv net. This makes real-time inference possible within the 256 KB RAM budget.

## Key Commands / Configuration / Code

**1. On-device MFCC extraction (Arduino sketch snippet):**
```cpp
// AudioFrontend.h from TensorFlow Lite Micro
// Configures MFCC with 40 mel bins, 30 ms window, 10 ms stride
static constexpr int kNumMelBins = 40;
static constexpr int kWindowSize = 480; // 30 ms at 16 kHz
static constexpr int kStride = 160;     // 10 ms at 16 kHz

// Initialize frontend
TfLiteAudioFrontend frontend;
frontend.Initialize(kNumMelBins, kWindowSize, kStride);

// Process 1 second of audio (100 frames)
for (int i = 0; i < 100; i++) {
    int16_t* audio_buffer = get_next_window(); // from PDM
    float* mfcc_output = frontend.ComputeMFCC(audio_buffer);
    // mfcc_output is 40 floats per frame
    // Copy into model input tensor (shape [1, 100, 40, 1])
    memcpy(input_tensor->data.f + (i * 40), mfcc_output, 40 * sizeof(float));
}
```

**2. Model quantization and conversion (Python, outside the MCU):**
```bash
# Convert Keras model to TFLite with int8 quantization
# Representative dataset: 1000 audio clips from training set
import tensorflow as tf

def representative_dataset():
    for i in range(1000):
        audio = load_audio_clip(f"train/audio_{i}.wav")
        mfcc = extract_mfcc(audio)
        yield [mfcc.astype(np.float32).reshape(1, 100, 40, 1)]

converter = tf.lite.TFLiteConverter.from_keras_model(model)
converter.optimizations = [tf.lite.Optimize.DEFAULT]
converter.representative_dataset = representative_dataset
converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
converter.inference_input_type = tf.int8
converter.inference_output_type = tf.int8
tflite_model = converter.convert()
# Output: model.tflite (48 KB, down from 320 KB float)
```

**3. Deploying with TFLM (Arduino CLI):**
```bash
# Install TFLM library for Nano BLE Sense
arduino-cli lib install "Arduino_TensorFlowLite@2.12.0-ALPHA"

# Compile with CMSIS-NN optimizations (add to platformio.ini)
# build_flags = -DARM_MATH_CM4 -DOPTIMIZE_FOR_CMSIS_NN

# Flash the board
arduino-cli compile --fqbn arduino:mbed_nano:nano33ble --output-dir build
arduino-cli upload --fqbn arduino:mbed_nano:nano33ble --input-dir build
```

## Common Pitfalls & Gotchas

**1. PDM Microphone Buffer Underflow:** The PDM microphone on the Nano BLE Sense uses a 256-sample hardware buffer. If your inference loop takes longer than 16 ms (256 samples / 16 kHz), you'll miss samples and get audio glitches. Fix: use double-buffering with DMA and run inference in the main loop only when a full 480-sample window is ready. I added a `volatile bool audio_ready` flag set in the PDM interrupt.

**2. Quantization Calibration Mismatch:** The representative dataset must cover the full dynamic range of your target environment. I initially used clean studio recordings for calibration, but the model failed on noisy room audio. The int8 quantization clipped values above the calibration range, causing 15% accuracy drop. Solution: include 20% background noise clips in the representative dataset.

**3. Memory Fragmentation from Arena Size:** TFLM requires a pre-allocated tensor arena. I set it to 120 KB initially, but the DS-CNN model needed 148 KB for intermediate tensors. The error message is cryptic (`arena size too small`). Use the `tflite::MicroInterpreter::arena_used_bytes()` debug function to find the exact size. Final arena: 160 KB (leaving 96 KB for stack and buffers).

## Try It Yourself

1. **Modify the model to add a fourth keyword** (e.g., "stop"). Retrain the DS-CNN with the Google Speech Commands v2 dataset (35 keywords available). Re-quantize and deploy — note the increase in flash and RAM usage.

2. **Benchmark inference latency** with and without CMSIS-NN. In your Arduino sketch, toggle a GPIO pin before and after `interpreter->Invoke()` and measure with a logic analyzer. Expect ~50 ms with CMSIS-NN vs ~120 ms without.

3. **Implement a simple voice activity detector (VAD)** before the KWS model. Use the RMS energy of the audio window — if below a threshold (e.g., 1000 for 16-bit samples), skip inference and save power. Measure the mAh reduction over 1 hour of continuous operation.

## Next Up

Tomorrow is the final review of this series. I'll compile all 24 days into a single reference architecture for edge AI deployment, including a decision tree for choosing between TFLM, Edge Impulse, and ONNX Runtime for microcontrollers, plus a checklist for production-ready TinyML systems.
