---
title: "Day 04: Model Pruning & Distillation for Constrained Devices"
date: 2026-07-04
tags: ["til", "edge-ai-tinyml", "pruning", "distillation"]
---

## What I Explored Today

Today I dug into two critical techniques for shrinking neural networks down to fit on microcontrollers: **weight pruning** and **knowledge distillation**. While quantization (which we covered on Day 3) reduces the bit-width of weights, pruning physically removes connections or neurons, and distillation transfers knowledge from a large "teacher" model to a tiny "student." I tested both on a 1D CNN for keyword spotting (KWS) targeting a Cortex-M4 with 256 KB RAM.

## The Core Concept

The fundamental tension in TinyML is: *we need accuracy, but we have no memory or compute*. Pruning and distillation attack this from opposite ends.

**Pruning** is about sparsity. You start with a trained model, then remove weights (or entire neurons) that contribute least to the output. The key insight: most neural networks are over-parameterized. You can often remove 50-90% of weights with minimal accuracy loss, then fine-tune to recover. For MCUs, this directly translates to fewer MAC operations and smaller model footprints. The hardware must support sparse computation to realize speedups—otherwise you only save memory.

**Knowledge distillation** is about compression through imitation. You train a large, accurate teacher model (e.g., a ResNet-18), then use its softmax outputs (the "soft targets") to train a much smaller student model (e.g., a 3-layer CNN). The student learns not just the correct class, but the teacher's confidence distribution across classes. This often yields a smaller model that outperforms one trained from scratch on the same architecture.

Together, these techniques let you start with a high-accuracy baseline and carve it down to fit your target device, rather than guessing a tiny architecture upfront.

## Key Commands / Configuration / Code

I used TensorFlow Model Optimization Toolkit (TF-MOT) for pruning and a manual distillation loop in TensorFlow.

### 1. Weight Pruning with TF-MOT

```python
import tensorflow as tf
import tensorflow_model_optimization as tfmot

# Define a simple 1D CNN for KWS (10 classes, 40 MFCC features)
def build_model():
    inputs = tf.keras.Input(shape=(40, 1))
    x = tf.keras.layers.Conv1D(32, 3, activation='relu')(inputs)
    x = tf.keras.layers.GlobalAveragePooling1D()(x)
    x = tf.keras.layers.Dense(16, activation='relu')(x)
    outputs = tf.keras.layers.Dense(10, activation='softmax')(x)
    return tf.keras.Model(inputs, outputs)

# Apply pruning schedule: start after 2 epochs, prune for 10 epochs
pruning_params = {
    'pruning_schedule': tfmot.sparsity.keras.PolynomialDecay(
        initial_sparsity=0.30,   # start at 30% sparsity
        final_sparsity=0.80,     # target 80% sparsity
        begin_step=2000,         # after ~2 epochs (1000 steps/epoch)
        end_step=10000           # finish pruning by epoch 10
    )
}

model = build_model()
pruned_model = tfmot.sparsity.keras.prune_low_magnitude(model, **pruning_params)

# Compile with a smaller learning rate for fine-tuning
pruned_model.compile(
    optimizer=tf.keras.optimizers.Adam(1e-4),
    loss='sparse_categorical_crossentropy',
    metrics=['accuracy']
)

# Use a special callback to update pruning masks each step
callbacks = [
    tfmot.sparsity.keras.UpdatePruningStep(),
    tfmot.sparsity.keras.PruningSummaries(log_dir='./logs')
]

# Train (assume train_ds, val_ds are tf.data.Dataset objects)
pruned_model.fit(train_ds, validation_data=val_ds, epochs=15, callbacks=callbacks)

# Strip pruning wrappers for deployment
final_model = tfmot.sparsity.keras.strip_pruning(pruned_model)
final_model.save('kws_pruned_80pct.h5')
```

### 2. Knowledge Distillation (Manual Loop)

```python
# Teacher: a larger model (e.g., 4 conv layers, 64 filters each)
teacher = tf.keras.models.load_model('kws_teacher.h5')
teacher.trainable = False  # freeze teacher

# Student: tiny 2-layer model
student = build_tiny_student()  # 16 filters, 1 conv layer
student.compile(optimizer='adam', loss='kld', metrics=['accuracy'])

# Distillation loss: weighted sum of hard (CE) and soft (KL divergence) losses
temperature = 4.0
alpha = 0.7  # weight for soft loss

for epoch in range(30):
    for x_batch, y_batch in train_ds:
        # Get teacher soft targets
        teacher_logits = teacher(x_batch, training=False)
        teacher_soft = tf.nn.softmax(teacher_logits / temperature)

        # Student forward pass
        with tf.GradientTape() as tape:
            student_logits = student(x_batch, training=True)
            student_soft = tf.nn.softmax(student_logits / temperature)

            # Soft loss (KL divergence)
            soft_loss = tf.keras.losses.KLDivergence()(teacher_soft, student_soft)
            # Hard loss (cross-entropy with true labels)
            hard_loss = tf.keras.losses.SparseCategoricalCrossentropy(
                from_logits=True)(y_batch, student_logits)

            total_loss = alpha * (temperature**2) * soft_loss + (1 - alpha) * hard_loss

        grads = tape.gradient(total_loss, student.trainable_variables)
        student.optimizer.apply_gradients(zip(grads, student.trainable_variables))
```

## Common Pitfalls & Gotchas

1. **Pruning without fine-tuning is catastrophic.** If you prune a trained model and don't retrain, accuracy often drops 20-30%. Always fine-tune with a reduced learning rate (1e-4 or lower) for at least 5-10 epochs after pruning ends.

2. **Temperature matters more than you think in distillation.** A temperature of 1.0 gives almost no soft-target signal (teacher outputs are near one-hot). I found T=4 to T=8 works best for audio tasks. Too high (T>10) and the soft targets become uniform noise, confusing the student.

3. **Strip pruning before deployment.** The `prune_low_magnitude` wrapper adds overhead. If you convert to TFLite without calling `strip_pruning()`, the model will be larger and slower than the original. Always strip, then convert.

## Try It Yourself

1. **Prune a dense layer to 90% sparsity.** Take a simple MNIST MLP (2 hidden layers, 128 units each). Apply magnitude pruning targeting 90% sparsity. Measure the accuracy before and after fine-tuning. Plot the weight distribution histogram before and after.

2. **Compare student vs. teacher accuracy.** Train a large teacher (e.g., ResNet-20 on CIFAR-10) and a small student (3 conv layers, 16 filters). Train the student from scratch, then with distillation (alpha=0.7, T=4). Report the accuracy gap: how much does distillation close it?

3. **Combine pruning + distillation.** Take your distilled student model from task 2, then prune it to 70% sparsity. Fine-tune for 5 epochs. Compare the final model size (in KB) and accuracy against the original student. This is the real-world pipeline.

## Next Up

Tomorrow we convert: **TensorFlow → TFLite → TFLite Micro**. I'll cover the exact converter flags for int8 quantization, handling of custom ops, and how to verify the .tflite model runs on a simulated Cortex-M target. Bring your pruned/distilled models.
