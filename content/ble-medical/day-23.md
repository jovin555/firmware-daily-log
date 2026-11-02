---
title: "Day 23: Android BLE: Scanning, Connecting, GATT Operations & Bonding"
date: 2026-11-02
tags: ["til", "ble-medical", "android", "gatt-client"]
---

# Day 23: Android BLE: Scanning, Connecting, GATT Operations & Bonding

## What I Explored Today

Today I moved from the peripheral side of the stack to the central role on Android, wiring up a full BLE client against a medical peripheral: scanning with filters, connecting with autoConnect semantics, discovering services, and running the GATT operations a vitals monitor actually needs — reading battery, subscribing to a heart-rate measurement characteristic, and writing a control point. I also spent time on bonding, because our device requires an encrypted link for protected characteristics, and Android's bonding model has enough sharp edges that it deserves its own afternoon. The goal was a client that behaves correctly across the messy realities of Android: permission gates on API 31+, the 133 status code, and the MTU negotiation dance.

## The Core Concept

Android's BLE stack is a thin wrapper over the BluetoothGatt client, and almost every "weird" bug traces back to one of three architectural facts.

First, **all GATT callbacks arrive on a binder thread, not the main thread**, and they are serialized. If you block inside `onCharacteristicRead`, you stall every subsequent callback, including the one you're waiting for. The standard pattern is to post work to a handler or coroutine dispatcher and never call a GATT operation from inside a callback synchronously — Android's stack will silently drop or return `false` for re-entrant operations.

Second, **there is exactly one outstanding GATT operation per connection**. The stack does not queue reads and writes for you. You must serialize them yourself (a `Mutex` or a single-threaded dispatcher), otherwise you get `GATT_BUSY`-style failures or, worse, callbacks attributed to the wrong operation.

Third, **bonding is a link-layer state machine, not an app-level one**. When a characteristic has the `PERMISSION_READ_ENCRYPTED` flag, the stack triggers pairing automatically on first access. You don't call `createBond()` for that path — you just attempt the read and handle `GATT_INSUFFICIENT_AUTHENTICATION` by waiting for the bond to complete. Calling `createBond()` yourself races the stack and produces the classic "pairing dialog appears twice" bug.

## Key Commands / Configuration / Code

**Manifest permissions** (API 31+ split them; `neverForLocation` matters for medical devices that don't want location implied):

```xml
<!-- Android 12+ -->
<uses-permission android:name="android.permission.BLUETOOTH_SCAN"
    android:usesPermissionFlags="neverForLocation" />
<uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />
<!-- Legacy (API <= 30) -->
<uses-permission android:name="android.permission.BLUETOOTH"
    android:maxSdkVersion="30" />
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION"
    android:maxSdkVersion="30" />
```

**Scanning with a service filter** — filter at the controller level so you don't wake the app for every beacon in the room:

```kotlin
val filter = ScanFilter.Builder()
    .setServiceUuid(ParcelUuid(HEART_RATE_SERVICE))
    .build()

val settings = ScanSettings.Builder()
    .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY) // foreground only
    .setCallbackType(ScanSettings.CALLBACK_TYPE_ALL_MATCHES)
    .build()

scanner.startScan(listOf(filter), settings, scanCallback)
```

**Connecting** — `autoConnect = false` for a foreground connect (fast, ~seconds); `true` only for background reconnection where you accept minutes of latency:

```kotlin
val gatt = device.connectGatt(context, /* autoConnect = */ false, gattCallback,
    BluetoothDevice.TRANSPORT_LE)
```

**The callback skeleton** — note the `status == GATT_SUCCESS` gate and the MTU request on service discovery:

```kotlin
private val gattCallback = object : BluetoothGattCallback() {
    override fun onConnectionStateChange(g: BluetoothGatt, status: Int, newState: Int) {
        if (status != BluetoothGatt.GATT_SUCCESS) {
            // 133 here is usually a stack/controller hiccup — close and retry with backoff
            g.close(); return
        }
        if (newState == BluetoothProfile.STATE_CONNECTED) {
            g.requestMtu(247) // negotiate up front; default is 23
        }
    }

    override fun onMtuChanged(g: BluetoothGatt, mtu: Int, status: Int) {
        g.discoverServices() // discovery must follow MTU negotiation
    }

    override fun onServicesDiscovered(g: BluetoothGatt, status: Int) {
        if (status != BluetoothGatt.GATT_SUCCESS) return
        val hr = g.getService(HEART_RATE_SERVICE)
            ?.getCharacteristic(HEART_RATE_MEASUREMENT) ?: return
        // Enable notifications locally, then write the CCCD descriptor
        g.setCharacteristicNotification(hr, true)
        val cccd = hr.getDescriptor(CLIENT_CHARACTERISTIC_CONFIG)
        cccd.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
        g.writeDescriptor(cccd)
    }

    override fun onCharacteristicChanged(
        g: BluetoothGatt, c: BluetoothGattCharacteristic, value: ByteArray
    ) {
        // API 33+ overload delivers value directly; older uses c.value
        parseHeartRate(value)
    }
}
```

**Bonding for a protected characteristic** — attempt the operation, let the stack pair:

```kotlin
// Do NOT call createBond() first. Just read; the stack pairs on
// GATT_INSUFFICIENT_AUTHENTICATION and retries after the bond completes.
gatt.readCharacteristic(protectedChar)
```

## Common Pitfalls & Gotchas

- **Status 133 on connect.** Not a real error code — it's the catch-all for "the stack gave up." Almost always caused by calling `connectGatt` too soon after `close()`, or by a peripheral that drops the link during discovery. Fix: always `close()` the old `BluetoothGatt`, wait ~200 ms, and retry with exponential backoff. Never reuse a `BluetoothGatt` object after a disconnect.

- **Calling GATT ops from inside a callback.** `writeDescriptor` inside `onServicesDiscovered` is fine *only* if you return immediately after; chaining a second op before the first callback fires will fail. Serialize with a `Mutex` or a `Channel<GattOp>` and a single consumer coroutine.

- **`setCharacteristicNotification` is not enough.** It only flips a local flag. Without writing `ENABLE_NOTIFICATION_VALUE` to the CCCD descriptor (`00002902-0000-1000-8000-00805f9b34fb`), you will never receive `onCharacteristicChanged`. This trips up nearly everyone once.

## Try It Yourself

1. **Build a scan-and-connect harness.** Filter on the Heart Rate service (`0000180d-...`), connect with `autoConnect = false`, request MTU 247, and log the negotiated MTU. Confirm you see `onMtuChanged` before `onServicesDiscovered`.

2. **Subscribe to Heart Rate Measurement** and decode the flags byte (bit 0 = 8- vs 16-bit value). Verify you get `onCharacteristicChanged` callbacks at ~1 Hz and that the CCCD write returned `GATT_SUCCESS`.

3. **Force a bonding path.** Point your client at a characteristic with `PERMISSION_READ_ENCRYPTED`, attempt the read without calling `createBond()`, and observe the pairing dialog plus the automatic retry. Then deliberately call `createBond()` first and watch the double-dialog bug — good motivation for the pattern above.

## Next Up

Tomorrow I flip to the other mobile platform: **iOS Core Bluetooth — Central Manager, Background Modes & State Restoration**. Apple's model differs sharply from Android's — no manual MTU negotiation, a different bonding story (Just Works vs. app-level pairing), and the `CBCentralManager` state restoration mechanism that lets your app be relaunched for a pending connection. I'll cover the delegate flow and the background-execution constraints that bite medical apps hardest.
