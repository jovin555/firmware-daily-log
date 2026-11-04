---
title: "Day 25: Cross-Platform BLE Apps: Flutter & React Native Libraries and Pitfalls"
date: 2026-11-04
tags: ["til", "ble-medical", "flutter", "react-native"]
---

## What I Explored Today

Today I moved from native BLE stacks to the cross-platform layer, because most medical IoT companion apps ship on both iOS and Android from a single codebase. I spent the day building the same GATT client in Flutter (`flutter_blue_plus`) and React Native (`react-native-ble-plx`), connecting to a heart-rate peripheral, and deliberately breaking things to see where the abstractions leak. The short version: both libraries are thin wrappers over CoreBluetooth and the Android Bluetooth stack, and they inherit every platform asymmetry. The library choice matters far less than understanding which platform you're on at any given moment.

## The Core Concept

Cross-platform BLE libraries do not unify BLE — they unify the *API surface*. Underneath, `flutter_blue_plus` calls CoreBluetooth on iOS and the Android Bluetooth GATT API on Android; `react-native-ble-plx` does the same via a native bridge. That means every behavioral difference between the two platforms survives the abstraction. The big ones you'll hit on day one:

- **Permissions are not symmetric.** Android 12+ (API 31) requires `BLUETOOTH_SCAN` and `BLUETOOTH_CONNECT` runtime permissions; older Android needs `ACCESS_FINE_LOCATION` for scanning. iOS uses `NSBluetoothAlwaysUsageDescription` in `Info.plist` and prompts automatically — no runtime permission call.
- **MTU negotiation is Android-only.** iOS negotiates MTU internally (effectively 185+ bytes for most peripherals) and exposes no API to request it. Android lets you call `requestMtu(512)`, and the result is whatever the peripheral agrees to (often 23–247).
- **The bridge is async and lossy under load.** Every notification crosses the JS/Dart bridge. At high notification rates (ECG at 250 Hz), you will drop packets unless you batch on the native side or throttle.

The practical takeaway: design your app around the *lowest common denominator* — assume a 20-byte payload until you've confirmed MTU, assume permissions are a platform-specific dance, and never assume notification delivery is lossless.

## Key Commands / Configuration / Code

**Flutter — `pubspec.yaml` and Android manifest:**

```yaml
dependencies:
  flutter_blue_plus: ^1.32.0
```

```xml
<!-- android/app/src/main/AndroidManifest.xml -->
<uses-permission android:name="android.permission.BLUETOOTH_SCAN"
    android:usesPermissionFlags="neverForLocation" />
<uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />
<!-- Legacy (API < 31) -->
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION"
    android:maxSdkVersion="30" />
```

```dart
import 'package:flutter_blue_plus/flutter_blue_plus.dart';

// Scan with a service filter — never scan unfiltered in production
await FlutterBluePlus.startScan(
  withServices: [Guid("180D")], // Heart Rate Service
  timeout: const Duration(seconds: 10),
);

final results = await FlutterBluePlus.scanResults.first;
final device = results.first.device;
await device.connect(timeout: const Duration(seconds: 15));

// MTU: Android only. On iOS this call is a no-op / throws.
try {
  final mtu = await device.requestMtu(247);
  print('Negotiated MTU: $mtu');
} catch (e) {
  print('MTU request unsupported (likely iOS): $e');
}

final services = await device.discoverServices();
final hrChar = services
    .firstWhere((s) => s.uuid == Guid("180D"))
    .characteristics
    .firstWhere((c) => c.uuid == Guid("2A37"));

await hrChar.setNotifyValue(true);
hrChar.onValueReceived.listen((value) {
  // value[0] = flags, value[1] = BPM (uint8) for the standard HR measurement
  print('HR: ${value[1]} bpm');
});
```

**React Native — `react-native-ble-plx`:**

```bash
npm install react-native-ble-plx
cd ios && pod install
```

```tsx
import { BleManager } from 'react-native-ble-plx';

const manager = new BleManager();

// Android 12+ runtime permission must be requested before scanning
// (use react-native-permissions or PermissionsAndroid)
const device = await manager.startDeviceScan(
  ['0000180d-0000-1000-8000-00805f9b34fb'],
  { allowDuplicates: false },
  (error, scanned) => {
    if (error) { console.warn(error); return; }
    if (scanned?.localName === 'HRM-01') {
      manager.stopDeviceScan();
      connect(scanned.id);
    }
  },
);

async function connect(id: string) {
  const dev = await manager.connectToDevice(id, { timeout: 15000 });
  await dev.discoverAllServicesAndCharacteristics();

  // Android: request larger MTU. iOS ignores this.
  await dev.requestMTU(247).catch(() => {});

  dev.monitorCharacteristicForService(
    '0000180d-0000-1000-8000-00805f9b34fb',
    '00002a37-0000-1000-8000-00805f9b34fb',
    (err, char) => {
      if (err || !char?.value) return;
      // Base64-encoded payload — decode before parsing
      const buf = Buffer.from(char.value, 'base64');
      console.log('HR:', buf.readUInt8(1), 'bpm');
    },
  );
}
```

## Common Pitfalls & Gotchas

1. **Base64 decoding in React Native.** `react-native-ble-plx` returns characteristic values as base64 strings, not `Uint8Array`. If you parse `char.value` directly as bytes you'll get garbage. Always `Buffer.from(value, 'base64')` (or `atob` + manual conversion) before reading offsets. Flutter's `flutter_blue_plus` returns `List<int>` directly, so code ported between the two silently breaks.

2. **iOS state restoration vs. Android background limits.** iOS supports CoreBluetooth *state restoration* (relaunch your app when a peripheral connects while backgrounded) via `CBCentralManagerOptionRestoreIdentifierKey` — but neither `flutter_blue_plus` nor `ble-plx` exposes it cleanly, so background reconnection on iOS usually requires a small native module. On Android, background scanning is throttled and `BLUETOOTH_SCAN` with `neverForLocation` still gets killed by Doze. Plan for foreground-only unless you write native code.

3. **The bridge drops notifications under load.** At 100+ notifications/sec, the JS/Dart bridge becomes the bottleneck and you'll see gaps in ECG/PPG streams. Mitigation: batch on the native side, or reduce the peripheral's notification rate. Don't debug this as a BLE problem — it's a bridge problem.

## Try It Yourself

1. Build the heart-rate client above in both Flutter and React Native against the same peripheral (a Polar H10 or an nRF52 dev kit works). Log the negotiated MTU on each platform and compare — confirm iOS returns nothing useful.
2. Deliberately request `MTU 512` on Android and log the actual granted value across three different peripherals. Note which ones cap at 23.
3. Add a notification counter to the HR characteristic and run for 60 seconds on each platform. Compare packet counts against the peripheral's advertised rate to quantify bridge drops.

## Next Up

Tomorrow: **Reliable Data Transfer: Buffering, Reconnection & Data Integrity** — because a BLE link that drops mid-ECG is a clinical liability, not an inconvenience. We'll cover write-with-response vs. write-without-response, ring buffers on the native side, and how to detect and recover from silent data loss.
