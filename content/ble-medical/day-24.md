---
title: "Day 24: iOS Core Bluetooth: Central Manager, Background Modes & State Restoration"
date: 2026-11-03
tags: ["til", "ble-medical", "ios", "core-bluetooth"]
---

# Day 24: iOS Core Bluetooth: Central Manager, Background Modes & State Restoration

## What I Explored Today

Today I went deep on the iOS side of our BLE medical stack — specifically how `CBCentralManager` behaves when the app is backgrounded or killed by the OS. For a continuous glucose monitor companion app, this is the difference between a working product and one that silently stops collecting data when the user locks their phone. I worked through the `bluetooth-central` background mode, the `CBCentralManagerOptionRestoreIdentifierKey` mechanism, and the delegate callback ordering that trips up almost everyone on their first implementation. The key insight: iOS will keep your app alive for BLE events, but only if you architect around state restoration from day one — retrofitting it later means rewriting your connection lifecycle.

## The Core Concept

Core Bluetooth's background behavior is governed by a simple but unforgiving rule: **the system, not your app, decides when your process runs.** When your app is backgrounded, iOS suspends it. But if you've declared the `bluetooth-central` background mode and have an active connection or pending scan, the OS will wake your app (or relaunch it) to deliver BLE events. The catch is that on relaunch, your in-memory state is gone — your `CBCentralManager` instance, your peripheral references, your characteristic handles, all of it.

State restoration solves this. When you initialize a `CBCentralManager` with a restore identifier, iOS persists the manager's state and, on relaunch, calls `centralManager(_:willRestoreState:)` **before** `centralManagerDidUpdateState`. That dictionary contains the peripherals you were connected to, the services you were scanning for, and pending characteristic notifications. Your job is to re-adopt those objects rather than re-discovering them — because re-scanning in the background is throttled and slow, and re-connecting to an already-connected peripheral fails.

The mental model: treat the `CBCentralManager` as a system-owned singleton keyed by your restore identifier. You don't own the connection; you're just a delegate that gets notified about it.

## Key Commands / Configuration / Code

First, the Info.plist entries. Both are required — the background mode alone won't survive termination:

```xml
<!-- Info.plist -->
<key>UIBackgroundModes</key>
<array>
    <string>bluetooth-central</string>
</array>
<!-- Required since iOS 13 for any BLE use -->
<key>NSBluetoothAlwaysUsageDescription</key>
<string>This app connects to your glucose sensor to record readings.</string>
```

Now the central manager with a stable restore identifier. This string must be constant across launches — use a reverse-DNS style constant, not a UUID you generate at runtime:

```swift
import CoreBluetooth

final class GlucoseCentral: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    // Stable identifier — same value every launch, or restoration won't fire
    private static let restoreID = "com.example.glucosemonitor.central"
    private var central: CBCentralManager!
    private var sensor: CBPeripheral?

    override init() {
        super.init()
        // queue: nil uses the main queue; pass a serial queue for production
        central = CBCentralManager(
            delegate: self,
            queue: nil,
            options: [CBCentralManagerOptionRestoreIdentifierKey: Self.restoreID]
        )
    }

    // Called BEFORE centralManagerDidUpdateState on relaunch
    func centralManager(_ central: CBCentralManager,
                        willRestoreState dict: [String: Any]) {
        // Re-adopt the peripheral the system kept alive for us
        if let restored = dict[CBCentralManagerRestoredStatePeripheralsKey]
            as? [CBPeripheral] {
            sensor = restored.first
            sensor?.delegate = self
        }
        // Re-adopt scan targets so we don't have to restart scanning
        if let services = dict[CBCentralManagerRestoredStateScanServicesKey]
            as? [CBUUID] {
            // store for later; do NOT call scanForPeripherals again here
            _ = services
        }
    }

    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        guard central.state == .poweredOn else { return }
        // Only scan if we don't already have a live peripheral from restoration
        if sensor == nil {
            central.scanForPeripherals(
                withServices: [CBUUID(string: "181F")], // Glucose service
                options: [CBCentralManagerScanOptionAllowDuplicatesKey: false]
            )
        }
    }

    func centralManager(_ central: CBCentralManager,
                        didDiscover peripheral: CBPeripheral,
                        advertisementData: [String: Any],
                        rssi RSSI: NSNumber) {
        sensor = peripheral
        peripheral.delegate = self
        central.stopScan()
        central.connect(peripheral, options: nil)
    }

    func centralManager(_ central: CBCentralManager,
                        didConnect peripheral: CBPeripheral) {
        // Re-discover services; handles are NOT preserved across relaunch
        peripheral.discoverServices([CBUUID(string: "181F")])
    }
}
```

The critical detail: **characteristic handles and service objects are not restored.** Only the `CBPeripheral` object identity survives. You must re-run `discoverServices` and `discoverCharacteristics` after restoration, then re-enable notifications.

## Common Pitfalls & Gotchas

**1. Calling `scanForPeripherals` inside `willRestoreState`.** This throws an exception or silently fails — the manager isn't in a valid state yet. Wait for `centralManagerDidUpdateState` and check whether restoration already gave you a peripheral before scanning.

**2. Using a per-launch restore identifier.** If you generate the identifier with `UUID().uuidString` at init, restoration never fires because iOS can't match the previous session. Hardcode it as a constant.

**3. Assuming `didConnect` fires after restoration.** It does not. If the peripheral was connected when the app was killed, restoration hands you the peripheral already in `.connected` state — you must call `discoverServices` directly from `willRestoreState` (or defer to `didUpdateState`), not wait for a connection callback that will never come.

## Try It Yourself

1. **Verify restoration fires.** Add a `print` in `willRestoreState` and `centralManagerDidUpdateState`. Connect to a peripheral, background the app, then trigger a characteristic notification from the peripheral side (or use a second device). Confirm the ordering: `willRestoreState` first, then `didUpdateState`.

2. **Force a relaunch.** With a connection active, swipe the app away in the app switcher (this *does* terminate it), then have the peripheral send a notification. Watch Console.app filtered by your process name — you should see the app relaunch and restoration fire.

3. **Break it deliberately.** Change the restore identifier to a runtime UUID and repeat task 2. Observe that restoration never fires and your app has no peripheral reference — this is the failure mode you're guarding against.

## Next Up

Tomorrow: **Cross-Platform BLE Apps: Flutter & React Native Libraries and Pitfalls** — we'll compare `flutter_blue_plus` and `react-native-ble-plx`, look at how each handles background connections on iOS vs. Android, and catalog the platform-specific bugs that bite you when you assume parity.
