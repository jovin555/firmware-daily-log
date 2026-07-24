---
title: HAL & Firmware Design Patterns Daily Log
---

# HAL & Firmware Design Patterns Daily Log

Hardware abstraction layers, C/C++ driver design patterns, and multi-vendor portability.

## Posts

| Day | Topic | Module | Tags |
|-----|-------|--------|------|

| [[hal-patterns/day-01\|Day 01]] | Why Hardware Abstraction Matters: Coupling & Portability | Foundations | `#hal` `#portability` |

| [[hal-patterns/day-02\|Day 02]] | Layered Firmware Architecture: BSP, HAL, Middleware & App Layers | Layered Architecture | `#layered-architecture` |

| [[hal-patterns/day-03\|Day 03]] | Register Abstraction: Memory-Mapped I/O & volatile Correctness | Layered Architecture | `#mmio` `#volatile` |

| [[hal-patterns/day-04\|Day 04]] | Designing a Clean HAL API: Function Pointers vs Structs | C Patterns | `#hal-api` `#function-pointers` |

| [[hal-patterns/day-05\|Day 05]] | The vtable Pattern in C: Simulating Polymorphism for Drivers | C Patterns | `#vtable` `#polymorphism` |

| [[hal-patterns/day-06\|Day 06]] | Opaque Handles & Pimpl-Style Encapsulation in C | C Patterns | `#opaque-handle` `#encapsulation` |

| [[hal-patterns/day-07\|Day 07]] | Dependency Injection in Embedded C: Decoupling Drivers from Logic | C Patterns | `#dependency-injection` |

| [[hal-patterns/day-08\|Day 08]] | State Machines for Driver Design: Table-Driven vs Switch-Based | Driver Design | `#state-machine` |

| [[hal-patterns/day-09\|Day 09]] | Observer Pattern for Sensor Data & Event Callbacks | Driver Design | `#observer-pattern` `#callbacks` |

| [[hal-patterns/day-10\|Day 10]] | HAL Design in C++: Templates & Zero-Cost Abstraction | C++ Patterns | `#cpp-templates` `#zero-cost` |

| [[hal-patterns/day-11\|Day 11]] | CRTP for Compile-Time Polymorphic Drivers | C++ Patterns | `#crtp` |

| [[hal-patterns/day-12\|Day 12]] | Strategy Pattern: Swappable Communication Backends (SPI/I2C/UART) | Driver Design | `#strategy-pattern` |

| [[hal-patterns/day-13\|Day 13]] | Factory Pattern for Peripheral Driver Instantiation | C++ Patterns | `#factory-pattern` |

| [[hal-patterns/day-14\|Day 14]] | Device Driver Model: Init, Configure, Read/Write, Deinit Contracts | Driver Design | `#driver-model` |

| [[hal-patterns/day-15\|Day 15]] | Porting a HAL Across Vendors: STM32 HAL vs MCUXpresso vs nRFx | Portability | `#multi-vendor` `#porting` |

| [[hal-patterns/day-16\|Day 16]] | Zephyr Device Driver Model: device_api & DEVICE_DT_DEFINE | Portability | `#zephyr` `#device-model` |

| [[hal-patterns/day-17\|Day 17]] | Board Support Packages: Structuring Board-Specific Code | Layered Architecture | `#bsp` |

| [[hal-patterns/day-18\|Day 18]] | Peripheral Drivers as Reusable Components: Versioning & APIs | Driver Design | `#reusability` `#api-versioning` |

| [[hal-patterns/day-19\|Day 19]] | Error Handling Patterns Across HAL Layers: Codes vs Exceptions | Driver Design | `#error-handling` |

| [[hal-patterns/day-20\|Day 20]] | Testing HALs: Mocking Hardware with Fakes & Hardware-in-the-Loop | Portability | `#hal-testing` `#mocking` |

| [[hal-patterns/day-21\|Day 21]] | Interrupt Abstraction: ISR Registration Patterns Across Vendors | Layered Architecture | `#isr` `#interrupts` |

| [[hal-patterns/day-22\|Day 22]] | Migrating a Product Line to a New MCU: A HAL Case Study | Portability | `#migration` `#case-study` |

| [[hal-patterns/day-23\|Day 23]] | Anti-Patterns: God Objects, Leaky Abstractions & Over-Engineering | Driver Design | `#anti-patterns` |

| [[hal-patterns/day-24\|Day 24]] | Full Review & Project: Vendor-Agnostic SPI Sensor Driver | Review | `#review` `#project` |

---

> *New post every day at 6:00 AM UTC.*
