---
title: "Day 09: Observer Pattern for Sensor Data & Event Callbacks"
date: 2026-07-09
tags: ["til", "hal-patterns", "observer-pattern", "callbacks"]
---

## What I Explored Today

Today I tackled the Observer pattern applied to sensor drivers and event callbacks in embedded C. The problem is universal: you have a temperature sensor that updates at 10 Hz, a button that generates interrupts, and a UART that receives asynchronous data. Polling each one in a super-loop works until you need to add a second consumer, then a third, and suddenly your main loop is a tangled mess of state checks and function calls. The Observer pattern decouples the sensor (the subject) from the modules that react to its data (the observers), letting you register and unregister callbacks at runtime without modifying the driver code.

## The Core Concept

The Observer pattern defines a one-to-many dependency between objects so that when one object changes state, all its dependents are notified automatically. In embedded firmware, this translates to a driver maintaining a list of function pointers (observers) and calling each one when new data arrives or an event fires.

Why not just hardcode the callback? Because requirements change. Today you log sensor data to UART. Tomorrow you also need to feed it to a Kalman filter, update an OLED display, and trigger a buzzer if temperature exceeds a threshold. With hardcoded callbacks, you modify the driver every time. With an observer list, you just register a new handler from your application layer. The driver stays generic, testable, and reusable across projects.

The key trade-off is memory versus flexibility. Each observer slot costs a few bytes for the function pointer and optional context pointer. On a Cortex-M0+ with 16 KB of RAM, you might limit observers to 4 or 8. On a Cortex-M4 with 256 KB, you can afford a dynamic list. The pattern also introduces a tiny latency penalty — iterating through observers adds microseconds, which is irrelevant for a 10 Hz sensor but matters in a 1 MHz interrupt context.

## Key Commands / Configuration / Code

Here’s a minimal but production-ready implementation in C. I’m using a fixed-size array of observers to avoid malloc in interrupt context.

```c
// sensor_observer.h
#ifndef SENSOR_OBSERVER_H
#define SENSOR_OBSERVER_H

#include <stdint.h>

typedef struct {
    uint8_t id;
    int16_t temperature_celsius;
    uint16_t humidity_percent;
} sensor_data_t;

// Observer callback signature: receives data and an optional context pointer
typedef void (*sensor_observer_t)(const sensor_data_t *data, void *context);

// Maximum number of registered observers (adjust for your RAM budget)
#define MAX_OBSERVERS 8

// Returns 0 on success, -1 if list is full
int sensor_observer_register(sensor_observer_t callback, void *context);

// Returns 0 on success, -1 if callback not found
int sensor_observer_unregister(sensor_observer_t callback, void *context);

// Called by the driver's ISR or polling loop to notify all observers
void sensor_observer_notify(const sensor_data_t *data);

#endif
```

```c
// sensor_observer.c
#include "sensor_observer.h"

static struct {
    sensor_observer_t callback;
    void *context;
} observer_list[MAX_OBSERVERS];

static uint8_t observer_count = 0;

int sensor_observer_register(sensor_observer_t callback, void *context) {
    if (observer_count >= MAX_OBSERVERS) return -1;
    observer_list[observer_count].callback = callback;
    observer_list[observer_count].context = context;
    observer_count++;
    return 0;
}

int sensor_observer_unregister(sensor_observer_t callback, void *context) {
    for (uint8_t i = 0; i < observer_count; i++) {
        if (observer_list[i].callback == callback &&
            observer_list[i].context == context) {
            // Replace with last element and decrement count
            observer_list[i] = observer_list[observer_count - 1];
            observer_count--;
            return 0;
        }
    }
    return -1; // Not found
}

void sensor_observer_notify(const sensor_data_t *data) {
    for (uint8_t i = 0; i < observer_count; i++) {
        observer_list[i].callback(data, observer_list[i].context);
    }
}
```

Now the driver side — a simplified SHT30 temperature/humidity sensor driver that uses the observer:

```c
// sht30_driver.c (excerpt)
#include "sensor_observer.h"
#include "i2c.h"

static sensor_data_t latest_data;

void sht30_isr_handler(void) {
    // Read from I2C peripheral (non-blocking DMA complete callback)
    latest_data.temperature_celsius = read_i2c_register(0x44, 0x00);
    latest_data.humidity_percent = read_i2c_register(0x44, 0x01);
    latest_data.id = 0;

    // Notify all registered observers
    sensor_observer_notify(&latest_data);
}
```

And the application layer — registering two observers:

```c
// app_main.c
#include "sensor_observer.h"
#include "uart_logger.h"
#include "display_driver.h"

static void log_to_uart(const sensor_data_t *data, void *ctx) {
    char buf[64];
    snprintf(buf, sizeof(buf), "Temp: %d, Hum: %d\r\n",
             data->temperature_celsius, data->humidity_percent);
    uart_send_string(UART_ID, buf);
    (void)ctx; // unused in this callback
}

static void update_display(const sensor_data_t *data, void *ctx) {
    display_show_temperature(data->temperature_celsius);
    display_show_humidity(data->humidity_percent);
    (void)ctx;
}

void app_init(void) {
    sensor_observer_register(log_to_uart, NULL);
    sensor_observer_register(update_display, NULL);
    // Start sensor polling (e.g., start a timer or enable sensor interrupt)
    sht30_start_continuous_mode();
}
```

## Common Pitfalls & Gotchas

1. **Calling observer functions from ISR context** — If your sensor driver notifies observers from an interrupt service routine, every registered callback must be ISR-safe. No blocking calls, no `printf` (unless your UART driver is interrupt-driven and reentrant), no mutexes that could cause deadlock. The safest approach is to use a deferred handler pattern: set a flag in the ISR and process the observer list from the main loop or a task.

2. **Modifying the observer list during notification** — If an observer tries to unregister itself (or another observer) inside the `sensor_observer_notify` loop, you'll corrupt the iteration. Always defer list modifications. A common fix is to set a "pending update" flag and process registrations/unregistrations after the notification loop completes, or use a double-buffered list.

3. **Forgetting the context pointer** — Without a context pointer, every callback must use global variables or hardcoded handles. Always pass a `void *context` so the callback can access its own state (e.g., a specific UART handle, a display buffer, a filter instance). This makes the observer pattern truly reusable.

## Try It Yourself

1. **Add a threshold observer** — Write a callback that checks if `temperature_celsius > 50` and toggles an LED. Register it with the observer list. Test by feeding fake data through `sensor_observer_notify`.

2. **Implement deferred notification** — Modify the observer list so that `sensor_observer_notify` can be called from an ISR. Use a volatile flag and process the actual callbacks from the main loop. Measure the ISR exit latency improvement.

3. **Add priority ordering** — Extend the observer list to support a priority field. When notifying, call higher-priority observers first. This is useful when one observer must log data before another processes it (e.g., raw data logging before filtering).

## Next Up

Tomorrow we step up from C to C++: **HAL Design in C++: Templates & Zero-Cost Abstraction**. We'll explore how templates eliminate callback boilerplate, how to use CRTP for static polymorphism without vtable overhead, and why C++ can actually produce smaller, faster firmware than C when used correctly.
