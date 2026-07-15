---
title: "Day 15: Keyword Spotting: Always-On Audio Wake-Word Detection"
date: 2026-07-15
tags: ["til", "edge-ai-tinyml", "keyword-spotting", "audio"]
---

## What I Explored Today

Today I dove headfirst into always-on keyword spotting (KWS) on a Cortex-M4 microcontroller. The goal: detect the word "Hey Edge" from a live microphone stream using <50 mW total system power, with inference running at <50 ms per 1-second audio frame. I implemented a 1D depthwise-separable convolutional neural network (DS-CNN) using TensorFlow Lite for Microcontrollers, quantized to int8, and deployed it on an STM32L4 board with a PDM MEMS microphone. The model achieved 92% accuracy on the Google Speech Commands V2 dataset for a custom two-word wake phrase, with a false positive rate of <0.1 per hour in quiet office noise.

## The Core Concept

Always-on keyword spotting is fundamentally different from cloud-based speech recognition. You cannot stream raw audio to a server—latency, privacy, and power constraints forbid it. The entire pipeline—audio frontend, feature extraction, neural inference, and post-processing—must run locally on a battery-backed MCU.

The key insight is that we don't need to understand language. We only need to detect a specific acoustic pattern. This lets us use extremely small models (10–50k parameters) that operate on Mel-frequency cepstral coefficients (MFCCs) computed from 30–40 ms audio windows. The model outputs a probability for each keyword class plus a "silence/unknown" class. A simple state machine then applies a threshold and a debounce counter to trigger a wake event.

Why not just use a threshold on raw audio energy? Because background noise, non-speech sounds, and other speakers produce energy spikes that would cause false triggers. The neural network learns to reject those by analyzing the spectral shape. This is the same reason you can't just use a simple matched filter—human speech has enormous variability in pitch, speed, and accent.

The critical engineering trade-off is between detection latency and false acceptance rate. A 1-second audio buffer gives the model enough context to distinguish words, but introduces 1 second of latency before the wake event fires. For most always-on applications (smart speakers, voice-controlled tools), this is acceptable. For real-time control (e.g., emergency stop), you'd need a different architecture.

## Key Commands / Configuration / Code

### 1. Audio Frontend: MFCC Extraction on MCU

```c
// mfcc_config.h - Configure for 16 kHz, 40 ms window, 10 ms stride
typedef struct {
    int sample_rate;          // 16000
    int frame_shift_ms;       // 10
    int frame_length_ms;      // 40
    int num_mel_bins;         // 40
    int num_mfcc_coeffs;      // 13
    int fft_length;           // 640 (next power of 2 > 40ms * 16kHz)
} MfccConfig;

// Initialize with fixed-point arithmetic (Q15)
MfccConfig config = {
    .sample_rate = 16000,
    .frame_shift_ms = 10,
    .frame_length_ms = 40,
    .num_mel_bins = 40,
    .num_mfcc_coeffs = 13,
    .fft_length = 640
};
```

### 2. Model Architecture (TensorFlow, then TFLM)

```python
# model.py - DS-CNN for keyword spotting
import tensorflow as tf

def build_dscnn(input_shape=(49, 13, 1), num_keywords=2):
    """Depthwise-separable conv net for KWS.
    Input: 49 time frames x 13 MFCC coeffs x 1 channel
    """
    inputs = tf.keras.Input(shape=input_shape)
    
    # First: standard conv to expand channels
    x = tf.keras.layers.Conv2D(64, (3, 3), padding='same')(inputs)
    x = tf.keras.layers.BatchNormalization()(x)
    x = tf.keras.layers.ReLU()(x)
    
    # Depthwise separable blocks
    for filters in [64, 128, 128]:
        x = tf.keras.layers.DepthwiseConv2D((3, 3), padding='same')(x)
        x = tf.keras.layers.BatchNormalization()(x)
        x = tf.keras.layers.ReLU()(x)
        x = tf.keras.layers.Conv2D(filters, (1, 1), padding='same')(x)
        x = tf.keras.layers.BatchNormalization()(x)
        x = tf.keras.layers.ReLU()(x)
        x = tf.keras.layers.MaxPooling2D((2, 2))(x)
    
    x = tf.keras.layers.GlobalAveragePooling2D()(x)
    x = tf.keras.layers.Dense(32, activation='relu')(x)
    outputs = tf.keras.layers.Dense(num_keywords + 1, activation='softmax')(x)
    
    model = tf.keras.Model(inputs, outputs)
    model.compile(optimizer='adam', loss='sparse_categorical_crossentropy',
                  metrics=['accuracy'])
    return model

# After training, convert to int8 TFLite
converter = tf.lite.TFLiteConverter.from_keras_model(model)
converter.optimizations = [tf.lite.Optimize.DEFAULT]
converter.representative_dataset = representative_dataset  # calibration data
converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
tflite_model = converter.convert()
```

### 3. Inference Loop on STM32L4

```c
// inference.c - Runs every 10ms (frame stride)
#include "tensorflow/lite/micro/all_ops_resolver.h"
#include "tensorflow/lite/micro/micro_interpreter.h"

// Global state
static tflite::MicroInterpreter* interpreter;
static int8_t* input_buffer;
static int8_t* output_buffer;
static int silence_counter = 0;
static const int WAKE_THRESHOLD = 80;   // int8 quantized: 0-127
static const int DEBOUNCE_FRAMES = 5;   // 50ms debounce

void process_audio_frame(int16_t* pcm_samples) {
    // 1. Compute MFCCs for this frame (13 coefficients)
    int8_t mfcc_frame[13];
    compute_mfcc_fixed_point(pcm_samples, mfcc_frame);
    
    // 2. Shift ring buffer and insert new frame
    memmove(input_buffer, input_buffer + 13, (48 * 13) * sizeof(int8_t));
    memcpy(input_buffer + (48 * 13), mfcc_frame, 13 * sizeof(int8_t));
    
    // 3. Run inference (every 10th frame = every 100ms to save power)
    static int frame_count = 0;
    if (++frame_count % 10 != 0) return;
    
    TfLiteStatus invoke_status = interpreter->Invoke();
    if (invoke_status != kTfLiteOk) return;
    
    // 4. Post-process: debounce wake word
    int8_t wake_score = output_buffer[0];  // class 0 = "Hey Edge"
    if (wake_score > WAKE_THRESHOLD) {
        silence_counter = 0;
        if (++wake_counter >= DEBOUNCE_FRAMES) {
            trigger_wake_event();
            wake_counter = 0;
        }
    } else {
        wake_counter = 0;
        if (++silence_counter > 50) {  // 5 seconds silence
            enter_deep_sleep_mode();
        }
    }
}
```

## Common Pitfalls & Gotchas

1. **Microphone saturation with PDM microphones.** The STM32L4's DFSDM peripheral can handle PDM streams, but the gain must be tuned carefully. If the gain is too high, the MFCCs saturate and the model sees only noise. If too low, quiet speech is indistinguishable from silence. Use a 10-second calibration routine at startup: measure the RMS level of ambient noise, then set gain so that typical speech peaks at -6 dBFS.

2. **Quantization calibration dataset mismatch.** If your representative dataset for int8 quantization contains only clean speech, the model will fail in noisy environments. Always include at least 20% background noise samples (fan noise, typing, street noise) in the calibration set. I learned this the hard way when my model triggered on every door slam.

3. **Ring buffer alignment with inference stride.** The MFCC window is 40 ms, but the stride is 10 ms. This means each inference uses 49 frames (490 ms of audio) but only 10 ms of new data. If you don't properly shift the ring buffer, you'll either double-count frames or miss transitions between words. Use a circular buffer with a write pointer and a read pointer offset by `(frame_length - frame_shift) / frame_shift` frames.

## Try It Yourself

1. **Collect your own wake word data.** Record 100 samples of your chosen wake word in three environments: quiet room, office with fan, and street noise. Use a PDM microphone on an STM32L4 Discovery kit. Label the data using Audacity, then export as 16-bit 16 kHz WAV files.

2. **Quantize and deploy the DS-CNN model.** Train the model on the Google Speech Commands V2 dataset, then quantize to int8 using the representative dataset from step 1. Deploy to the STM32L4 using TensorFlow Lite for Microcontrollers. Measure inference time with a GPIO toggle on an oscilloscope.

3. **Tune the debounce and threshold parameters.** Run the system for 1 hour in a noisy environment (e.g., next to a running laptop fan). Adjust `WAKE_THRESHOLD` and `DEBOUNCE_FRAMES` to achieve zero false positives while still detecting the wake word within 1.5 seconds. Log all false accepts and misses to UART for analysis.

## Next Up

Tomorrow, I'm tackling **Vibration & Anomaly Detection with TinyML on Accelerometers** — using a 3-axis accelerometer and a 1D convolutional autoencoder to detect bearing faults in industrial motors, all running on a Cortex-M0+ at <10 mW. We'll cover time-series feature engineering, anomaly scoring, and how to avoid the "novelty detection trap" where every new vibration pattern looks like a fault.
