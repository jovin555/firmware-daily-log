---
title: Secure OTA Update Architecture Daily Log
---

# Secure OTA Update Architecture Daily Log

Dual-slot partitioning, anti-rollback counters, delta updates and fleet rollout strategy.

## Posts

| Day | Topic | Module | Tags |
|-----|-------|--------|------|

| [[secure-ota/day-01\|Day 01]] | Why OTA Matters: Field Update Economics & Failure Modes | Foundations | `#ota` `#field-updates` |

| [[secure-ota/day-02\|Day 02]] | A/B (Dual-Slot) Partitioning: Design & Tradeoffs | Update Architectures | `#ab-update` `#partitioning` |

| [[secure-ota/day-03\|Day 03]] | Single-Slot vs Recovery-Partition Update Schemes | Update Architectures | `#recovery-partition` |

| [[secure-ota/day-04\|Day 04]] | Image Metadata & Manifests: Versioning, Hashes & Signatures | Image & Metadata | `#manifest` `#versioning` |

| [[secure-ota/day-05\|Day 05]] | Anti-Rollback Policies: Manifest Versioning & Fleet-Wide Enforcement | Rollback & Recovery | `#anti-rollback` `#versioning` |

| [[secure-ota/day-06\|Day 06]] | A/B Slot Swap Algorithms: Bank Swap vs Scratch-Area Swap | Update Architectures | `#swap-algorithm` |

| [[secure-ota/day-07\|Day 07]] | Delta/Differential Updates: bsdiff, Courgette & Binary Patching | Delta Updates | `#delta-update` `#bsdiff` |

| [[secure-ota/day-08\|Day 08]] | Compressing Firmware Images: LZ4, zlib & Constrained Flash | Delta Updates | `#compression` |

| [[secure-ota/day-09\|Day 09]] | Update Verification: Signature Checks Before Boot Commit | Image & Metadata | `#signature-verification` |

| [[secure-ota/day-10\|Day 10]] | Boot Confirmation & Health Checks: Marking an Update "Good" | Rollback & Recovery | `#boot-confirmation` `#health-check` |

| [[secure-ota/day-11\|Day 11]] | Automatic Rollback on Boot Failure & Watchdog-Triggered Recovery | Rollback & Recovery | `#rollback` `#watchdog` |

| [[secure-ota/day-12\|Day 12]] | mender.io & RAUC: Open-Source OTA Framework Internals | Update Architectures | `#mender` `#rauc` |

| [[secure-ota/day-13\|Day 13]] | AWS IoT & Azure Device Update Fleet OTA Pipelines | Fleet Management | `#aws-iot` `#azure-adu` |

| [[secure-ota/day-14\|Day 14]] | Staged Rollouts: Canary Groups & Percentage-Based Deployment | Fleet Management | `#staged-rollout` `#canary` |

| [[secure-ota/day-15\|Day 15]] | Update Scheduling: Bandwidth, Power & Maintenance Windows | Fleet Management | `#scheduling` `#power-budget` |

| [[secure-ota/day-16\|Day 16]] | Resuming Interrupted Downloads: Chunked Transfer & Integrity | Delta Updates | `#chunked-transfer` `#resumability` |

| [[secure-ota/day-17\|Day 17]] | Multi-Image Updates: Bootloader, App & Peripheral Firmware Together | Image & Metadata | `#multi-image` |

| [[secure-ota/day-18\|Day 18]] | OTA Over BLE: GATT-Based DFU & Throughput Constraints | Update Architectures | `#ble-dfu` |

| [[secure-ota/day-19\|Day 19]] | OTA Over Cellular: NB-IoT/LTE-M Bandwidth & Cost Considerations | Update Architectures | `#cellular-ota` |

| [[secure-ota/day-20\|Day 20]] | Bricking Prevention: Failsafe Bootloaders & Golden Images | Rollback & Recovery | `#failsafe` `#golden-image` |

| [[secure-ota/day-21\|Day 21]] | Update Telemetry: Success/Failure Reporting Back to the Fleet | Fleet Management | `#telemetry` `#reporting` |

| [[secure-ota/day-22\|Day 22]] | Compliance: EU Cyber Resilience Act Update Requirements | Foundations | `#cra` `#compliance` |

| [[secure-ota/day-23\|Day 23]] | Testing OTA Pipelines: Fault Injection & Power-Loss Simulation | Fleet Management | `#fault-injection` `#testing` |

---

> *New post every day at 6:00 AM UTC.*
