---
title: "Day 17: TinyML for Computer Vision: Person Detection on a Cortex-M7"
date: 2026-07-17
tags: ["til", "edge-ai-tinyml", "vision", "person-detection"]
---

## What I Explored Today

Today I took a deep dive into deploying a person detection model on a Cortex-M7 microcontroller using TensorFlow Lite for Microcontrollers. The goal was to run a quantized MobileNetV1 SSD model on an STM32F746 Discovery board, processing 96x96 grayscale images from a camera module at ~15 FPS. I walked through model conversion, quantization, arena sizing, and the inference loop—ending with a working demo that lights an LED when a person is detected.

## The Core Concept

Person detection on a Cortex-M7 is a textbook example of why TinyML exists. A full-resolution MobileNetV2 SSD runs at hundreds of megaflops—impossible on a 200 MHz MCU with 320 KB of SRAM. The trick is aggressive quantization and input size reduction. By dropping to 8-bit integer weights and activations, and shrinking the input to 96x96 grayscale, we cut memory and compute by roughly 10x. The model becomes a 250 KB `.tflite` file that fits in flash, with a runtime arena of ~150 KB.

Why grayscale? Color adds no value for person detection in typical security camera or smart home scenarios—silhouette and motion are sufficient. Why 96x96? It’s the smallest resolution where a MobileNetV1 backbone still produces meaningful feature maps for bounding box regression. Below that, the spatial resolution collapses too early and detection accuracy plummets.

The inference pipeline on the MCU is brutally simple: grab a frame from the camera, downscale to 96x96, convert to uint8, run the interpreter, parse the output tensor for bounding boxes and scores, and threshold at 0.5. No OS, no heap fragmentation—just a flat buffer and a while loop.

## Key Commands / Configuration / Code

### Model Conversion (Python, on dev machine)

```python
import tensorflow as tf

# Load the pretrained model (from TensorFlow Model Garden)
model = tf.saved_model.load('ssd_mobilenet_v1_coco_2018_01_28/saved_model')

# Convert to quantized TFLite
converter = tf.lite.TFLiteConverter.from_saved_model(model)
converter.optimizations = [tf.lite.Optimize.DEFAULT]
converter.representative_dataset = representative_dataset  # 100 sample images
converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
converter.inference_input_type = tf.uint8
converter.inference_output_type = tf.uint8
tflite_model = converter.convert()

with open('person_detection_96x96_uint8.tflite', 'wb') as f:
    f.write(tflite_model)
```

### C++ Inference Loop (on STM32F746)

```cpp
// Arena allocation (must be static for MCU)
constexpr int kTensorArenaSize = 150 * 1024;  // 150 KB
alignas(16) uint8_t tensor_arena[kTensorArenaSize];

// Load model from flash (embedded as byte array)
const tflite::Model* model = tflite::GetModel(g_person_detection_model_data);
tflite::MicroMutableOpResolver<10> resolver;
resolver.AddQuantize();
resolver.AddConv2D();
resolver.AddDepthwiseConv2D();
resolver.AddReshape();
resolver.AddDetectionPostprocess();  // custom op for SSD

tflite::MicroInterpreter interpreter(model, resolver, tensor_arena, kTensorArenaSize);
interpreter.AllocateTensors();

// Input tensor: uint8, shape [1, 96, 96, 1]
uint8_t* input = interpreter.input(0)->data.uint8;

while (1) {
    camera_capture_frame(frame_buffer);       // 640x480 RGB
    downscale_to_96x96_grayscale(frame_buffer, input);  // bilinear + grayscale
    interpreter.Invoke();

    // Output tensor: [1, 10, 4] for boxes, [1, 10] for scores
    float* boxes = interpreter.output(0)->data.f;
    float* scores = interpreter.output(1)->data.f;

    for (int i = 0; i < 10; i++) {
        if (scores[i] > 0.5f) {
            HAL_GPIO_WritePin(LED_GPIO_Port, LED_Pin, GPIO_PIN_SET);
            break;
        }
    }
    HAL_Delay(66);  // ~15 FPS
}
```

### Memory Map Verification

```bash
# After compiling with ARM GCC, check flash and RAM usage
arm-none-eabi-size build/person_detection.elf
   text    data     bss     dec     hex
 287456    1024  153600  442080   6BE60
# text = flash (model + code), bss = tensor arena + globals
```

## Common Pitfalls & Gotchas

**1. Arena size miscalculation.** The `MicroInterpreter` will silently fail or return garbage if the tensor arena is too small. Always compute the required size by calling `interpreter.arena_used_bytes()` after `AllocateTensors()` and add 20% headroom. On the STM32F746, I started with 128 KB and got mysterious crashes—bumping to 150 KB fixed it.

**2. Input data type mismatch.** The quantized model expects uint8 input in the range [0, 255], but the camera sensor often outputs 10-bit or 12-bit raw data. If you don’t clamp and rescale properly, the model sees garbage. Always verify the input tensor quantization parameters: `input->params.zero_point` and `input->params.scale`. For most uint8 models, zero_point is 128 and scale is 0.0078125.

**3. Detection post-processing op.** The SSD model’s output is raw box coordinates—you need the `DetectionPostprocess` custom op to decode them. If you’re using the default TFLite Micro ops resolver, this op is not included. You must add it manually via `resolver.AddDetectionPostprocess()`, and link the corresponding C++ implementation from the TFLite Micro source tree. Forgetting this results in a runtime error that’s hard to debug.

## Try It Yourself

1. **Quantize a different backbone.** Take the same SSD pipeline but swap MobileNetV1 for MobileNetV2 (or even a tiny custom CNN). Compare the resulting model size and inference time on your Cortex-M7 board. Use `micro_benchmark` from the TFLite Micro examples.

2. **Add motion triggering.** Before running inference, compute the frame difference between two consecutive 96x96 grayscale images. Only invoke the interpreter if the mean absolute difference exceeds a threshold (e.g., 10). This can cut power consumption by 5x in idle scenes.

3. **Visualize the bounding boxes.** Instead of just lighting an LED, output the box coordinates over UART at 115200 baud. On the host side, write a Python script that reads the serial port and overlays the boxes on a saved frame. This is invaluable for debugging false positives.

## Next Up

Tomorrow, I’ll dive into **Neural Network Accelerators in Modern MCUs: Ethos-U & MVE**. We’ll look at how the Arm Ethos-U55 microNPU and the M-profile Vector Extension (MVE) can offload convolution and pooling operations, pushing TinyML inference from 15 FPS to over 100 FPS on the same Cortex-M7 class hardware.
