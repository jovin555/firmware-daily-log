#!/usr/bin/env python3
"""
Firmware Daily Log — unified post generator for all 15 topics.

Usage:
  python3 generate_post.py                      # next post for ALL topics (15/day)
  python3 generate_post.py --topic lfcs         # one topic only
  python3 generate_post.py --topic lfcs --day 5
  python3 generate_post.py --dry-run
  python3 generate_post.py --list
"""

import os, sys, argparse
from pathlib import Path
from datetime import date
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

try:
    from openai import OpenAI
except ImportError:
    print("pip install openai python-dotenv"); sys.exit(1)

CONTENT_DIR = Path(__file__).parent / "content"
API_KEY  = os.getenv("LLM_API_KEY")
MODEL    = os.getenv("LLM_MODEL", "deepseek-chat")
if not API_KEY:
    print("Error: LLM_API_KEY not found in .env"); sys.exit(1)

client = OpenAI(api_key=API_KEY, base_url="https://api.deepseek.com")

# ─────────────────────────────────────────────────────────────────────────────
TOPICS = {
 "lfcs": {
  "title": "LFCS Daily Log",
  "curriculum": [
   ("Essential File Operations & Permissions","Essential Commands",["files","permissions"]),
   ("Hard Links, Symbolic Links & readlink","Essential Commands",["links","inodes"]),
   ("Finding Files: find, locate, which, whereis","Essential Commands",["find","search"]),
   ("grep Deep Dive: BRE, ERE & Practical Patterns","Essential Commands",["grep","regex"]),
   ("sed: Stream Editing & In-Place Config Modification","Essential Commands",["sed","text-processing"]),
   ("awk: Field Parsing, Conditions & Log Analysis","Essential Commands",["awk","text-processing"]),
   ("sort, uniq, cut, wc & Text Pipeline Patterns","Essential Commands",["pipelines","text-processing"]),
   ("Archiving with tar: Creation, Extraction & Compression","Essential Commands",["tar","compression"]),
   ("I/O Redirection, Pipes, tee & xargs","Essential Commands",["redirection","pipes"]),
   ("Regular Expressions for the LFCS Exam","Essential Commands",["regex","grep"]),
   ("Shell Variables, Environment & Startup Files","Essential Commands",["shell","environment"]),
   ("Process Management: ps, kill, nice, jobs, nohup","Essential Commands",["processes","jobs"]),
   ("System Information: uname, dmesg, lsblk, /proc","Essential Commands",["system-info","proc"]),
   ("Permissions Deep Dive: SUID, SGID, Sticky Bit","Essential Commands",["permissions","security"]),
   ("Shell Scripting Basics: Loops, Conditions, Functions","Essential Commands",["scripting","bash"]),
   ("Disk Usage: df, du & Finding Space Hogs","Essential Commands",["disk","storage"]),
   ("Command Sequencing: &&, ||, ; and subshells","Essential Commands",["shell","scripting"]),
   ("Essential Commands Review & Mock Lab","Essential Commands",["review","mock-exam"]),
   ("User Accounts: useradd, usermod, userdel","User and Group Management",["users","accounts"]),
   ("Group Management: groupadd, gpasswd & /etc/group","User and Group Management",["groups"]),
   ("Passwords & PAM: passwd, chage, /etc/shadow","User and Group Management",["passwords","pam"]),
   ("sudo & /etc/sudoers: Privilege Escalation","User and Group Management",["sudo","security"]),
   ("File Ownership & ACLs: setfacl, getfacl","User and Group Management",["acl","permissions"]),
   ("The Linux Boot Process: BIOS to GRUB to Kernel","Operation of Running Systems",["boot","kernel"]),
   ("systemd: Units, Targets & Dependency Graph","Operation of Running Systems",["systemd","services"]),
   ("systemctl & journalctl: Services & Logs","Operation of Running Systems",["systemctl","logging"]),
   ("Scheduling Tasks: cron, crontab, at","Operation of Running Systems",["cron","scheduling"]),
   ("Kernel Modules: lsmod, modprobe, insmod","Operation of Running Systems",["kernel","modules"]),
   ("System Performance: top, vmstat, iostat, sar","Operation of Running Systems",["performance","monitoring"]),
   ("GRUB2 Configuration & Boot Recovery","Operation of Running Systems",["grub","boot-recovery"]),
   ("Package Management: apt, dpkg, rpm, dnf","Operation of Running Systems",["packages","apt"]),
   ("Disk Partitioning: fdisk, gdisk","Storage Management",["partitions","disks"]),
   ("Filesystems: mkfs, fsck & Filesystem Types","Storage Management",["filesystems","mkfs"]),
   ("Mounting: mount, umount & /etc/fstab","Storage Management",["mount","fstab"]),
   ("LVM: PVs, VGs, LVs & Snapshots","Storage Management",["lvm","storage"]),
   ("Swap, RAID Basics & NFS Client Mounts","Storage Management",["swap","raid","nfs"]),
   ("Network Interfaces: ip, ifconfig & Link Management","Networking",["networking","interfaces"]),
   ("DNS, SSH & Port Forwarding","Networking",["dns","ssh","security"]),
   ("Firewall: iptables, nftables, ufw & firewalld","Networking",["firewall","iptables"]),
   ("Network Troubleshooting: ss, netstat, tcpdump","Networking",["troubleshooting","networking"]),
   ("HTTP Servers: Apache & nginx","Service Configuration",["apache","nginx","http"]),
   ("NFS Server, Samba & FTP","Service Configuration",["nfs","samba","ftp"]),
   ("Postfix, DHCP & BIND9 Basics","Service Configuration",["postfix","dhcp","dns"]),
   ("System Security: SELinux & AppArmor","Service Configuration",["selinux","security"]),
   ("Full Mock Exam — All Domains","All Domains",["mock-exam","review","exam-prep"]),
  ],
 },
 "zephyr": {
  "title": "Zephyr RTOS Daily Log",
  "curriculum": [
   ("Introduction to Zephyr: Architecture & the West Build System","Foundations",["zephyr","rtos","west"]),
   ("Project Structure: CMakeLists, prj.conf & Kconfig","Foundations",["kconfig","cmake"]),
   ("Devicetree in Zephyr: DTS, DTSI & Overlays","Foundations",["devicetree","dts"]),
   ("Kconfig Deep Dive: Symbols, Dependencies & Menuconfig","Foundations",["kconfig","configuration"]),
   ("Building & Flashing: west build, flash, debug","Foundations",["west","build","flashing"]),
   ("Threads: k_thread_create, Priorities & Scheduling","Threading",["threads","scheduling"]),
   ("Semaphores & Mutexes: Producer-Consumer Patterns","Threading",["semaphore","mutex"]),
   ("Message Queues & Mailboxes: Thread Communication","Threading",["msgq","ipc"]),
   ("FIFOs, LIFOs & Ring Buffers","Threading",["fifo","lifo","buffers"]),
   ("Timers & Delayed Work: k_timer, k_work","Threading",["timers","work-queue"]),
   ("GPIO Driver API: Input, Output, Interrupts","HAL & Drivers",["gpio","drivers"]),
   ("I2C Driver API: Controller & Target Mode","HAL & Drivers",["i2c","drivers"]),
   ("SPI Driver API: Full-Duplex & DMA Transfers","HAL & Drivers",["spi","dma"]),
   ("UART Driver API: Async, Interrupt & Polling Modes","HAL & Drivers",["uart","serial"]),
   ("Sensor API: Generic Sensor Framework & SENSOR_CHAN","HAL & Drivers",["sensors","api"]),
   ("Flash & NVS: Non-Volatile Storage in Zephyr","HAL & Drivers",["flash","nvs"]),
   ("Networking Stack: BSD Sockets & TCP/IP","Networking",["networking","tcp-ip"]),
   ("Bluetooth LE: Advertising, Scanning & GATT","Networking",["ble","bluetooth"]),
   ("BLE GATT: Custom Service & Characteristic","Networking",["ble","gatt"]),
   ("OpenThread: 802.15.4 & Thread Network","Networking",["openthread","thread"]),
   ("LTE-M & NB-IoT with nRF9160","Networking",["lte","nrf9160"]),
   ("Power Management: PM States & Hooks","Power Management",["power","pm"]),
   ("Optimizing for Ultra-Low Power: Tickless Idle","Power Management",["low-power","optimization"]),
   ("Logging Subsystem: LOG_MODULE_REGISTER","Debugging & Testing",["logging","debug"]),
   ("Ztest Framework & Unit Tests","Debugging & Testing",["ztest","testing"]),
   ("Twister: Automated Test Execution","Debugging & Testing",["twister","ci"]),
   ("GDB + OpenOCD: JTAG Debug on Real Hardware","Debugging & Testing",["gdb","jtag"]),
   ("Custom Board Support: DTS & Kconfig","Advanced",["bsp","board"]),
   ("Writing a Custom Zephyr Driver","Advanced",["drivers","custom"]),
   ("MCUboot: Secure Bootloader & DFU","Advanced",["mcuboot","bootloader"]),
   ("TF-M: Trusted Firmware-M & Secure Services","Advanced",["tfm","security"]),
   ("Full Review & Project: BLE Sensor Node","Review",["review","project"]),
  ],
 },
 "embedded-linux": {
  "title": "Embedded Linux Daily Log",
  "curriculum": [
   ("Embedded Linux Architecture: Components & Boot Flow","Foundations",["embedded-linux","architecture"]),
   ("Cross-Compilation Toolchain: crosstool-NG & Linaro","Toolchain",["cross-compilation","toolchain"]),
   ("U-Boot Bootloader: Build, Configure & Boot Scripts","Bootloader",["uboot","bootloader"]),
   ("U-Boot Environment: Variables, Commands & Scripting","Bootloader",["uboot","environment"]),
   ("Kernel Configuration: menuconfig, defconfig & Fragments","Kernel",["kernel","kconfig"]),
   ("Building the Linux Kernel for Embedded Targets","Kernel",["kernel","build"]),
   ("Device Tree: Syntax, Bindings & Overlays","Device Tree",["devicetree","dts"]),
   ("Root Filesystem: BusyBox, initramfs & Filesystem Layout","Root Filesystem",["rootfs","busybox"]),
   ("Linux Kernel Module: Hello World to Real Device","Kernel Modules",["kernel-module","lkm"]),
   ("Character Device Drivers: cdev, file_operations & ioctl","Device Drivers",["char-driver","ioctl"]),
   ("Platform Drivers & Device Tree Binding","Device Drivers",["platform-driver","dt-binding"]),
   ("I2C Client Drivers: i2c_driver & Adapter API","Device Drivers",["i2c","driver"]),
   ("SPI Client Drivers: spi_driver & Transfer API","Device Drivers",["spi","driver"]),
   ("GPIO & Interrupt Handling in Kernel Drivers","Device Drivers",["gpio","interrupts"]),
   ("DMA Engine API: Scatter-Gather & Cyclic Transfers","Device Drivers",["dma","transfers"]),
   ("Linux Memory Management: Virtual Memory & MMU","Memory",["memory","mmu"]),
   ("Memory Allocation: kmalloc, vmalloc, DMA Memory","Memory",["kmalloc","vmalloc"]),
   ("MTD Subsystem: NAND, NOR & Flash Layers","Storage",["mtd","nand","flash"]),
   ("Embedded Filesystems: JFFS2, UBIFS, SquashFS","Storage",["filesystem","ubifs"]),
   ("Sysfs & Debugfs: Kernel-Userspace Interface","Userspace",["sysfs","debugfs"]),
   ("GDB Cross-Debug: JTAG, gdbserver & Remote Debug","Debugging",["gdb","jtag"]),
   ("ftrace & trace-cmd: Function & Latency Tracing","Debugging",["ftrace","tracing"]),
   ("perf: Profiling on Embedded","Debugging",["perf","profiling"]),
   ("Secure Boot: Verified Boot Chain on Embedded Linux","Security",["secure-boot","signing"]),
   ("OTA Updates: SWUpdate, RAUC & A/B Partitions","Production",["ota","swupdate"]),
   ("Full Review & Bring-up Checklist","Review",["review","bringup"]),
  ],
 },
 "yocto": {
  "title": "Yocto Project Daily Log",
  "curriculum": [
   ("Yocto Overview: OpenEmbedded, Poky & BitBake","Foundations",["yocto","openembedded","poky"]),
   ("Setting Up a Yocto Build Environment & kas","Foundations",["yocto","setup","kas"]),
   ("BitBake Fundamentals: Tasks, Recipes & Execution Model","BitBake",["bitbake","tasks","recipes"]),
   ("Layers: Architecture, Priority & bblayers.conf","Layers",["layers","bblayers"]),
   ("Your First Image: core-image-minimal from Scratch","Foundations",["image","core-image"]),
   ("Writing a Recipe: .bb File Anatomy & Variables","Recipes",["recipe","bb-file"]),
   ("Fetchers: SRC_URI for Git, HTTP, Local & Patches","Recipes",["src-uri","fetcher","patches"]),
   ("do_compile & do_install: Build & Stage Tasks","Recipes",["do-compile","do-install"]),
   ("Package Groups & RDEPENDS: Runtime Dependencies","Recipes",["package-groups","rdepends"]),
   ("BitBake Classes: inherit, autotools, cmake, systemd","BitBake",["inherit","classes"]),
   ("Machine Configuration: MACHINE, TUNE & BSP Layers","Machine & Distro",["machine","bsp"]),
   ("Distro Configuration: DISTRO_FEATURES & Policies","Machine & Distro",["distro","policies"]),
   ("Image Configuration: IMAGE_FEATURES & Packages","Machine & Distro",["image","image-features"]),
   ("Kernel Recipe: linux-yocto & KBRANCH","Kernel & Boot",["kernel","linux-yocto"]),
   ("Kernel Config Fragments & defconfig in Yocto","Kernel & Boot",["kernel-config","cfg-fragment"]),
   ("Device Tree in Yocto: KERNEL_DEVICETREE","Kernel & Boot",["devicetree","kernel"]),
   ("U-Boot Recipe: UBOOT_MACHINE & Integration","Kernel & Boot",["uboot","bootloader"]),
   ("devtool: Modify, Build & Deploy Workflows","SDK & Workflow",["devtool","workflow"]),
   ("Standard SDK: populate_sdk & Cross-Development","SDK & Workflow",["sdk","populate-sdk"]),
   ("Shared State Cache (sstate): Speed Up Builds","SDK & Workflow",["sstate","cache"]),
   ("BitBake Debugging: -DDD, buildhistory & dep graphs","Debugging",["debugging","bitbake"]),
   ("Image Size Optimization & Stripping","Optimization",["image-size","optimization"]),
   ("Reproducible Builds & SOURCE_DATE_EPOCH","Security & Production",["reproducible-builds"]),
   ("OTA with Yocto: SWUpdate & A/B Image Strategy","Security & Production",["ota","swupdate"]),
   ("Creating a Custom BSP Layer: meta-mybsp","Advanced",["bsp","custom-layer"]),
   ("CI/CD for Yocto: KAS, Docker & GitHub Actions","Advanced",["ci-cd","kas","docker"]),
   ("Full Review: Build a Complete Embedded Image","Review",["review","project"]),
  ],
 },
 "iec62304": {
  "title": "IEC 62304 Daily Log",
  "curriculum": [
   ("Medical Device Software Regulation: FDA, CE & MDR","Regulatory Landscape",["regulation","fda","ce-mark"]),
   ("IEC 62304 Structure: Clauses, Scope & ISO 14971","Regulatory Landscape",["iec62304","overview"]),
   ("Software Safety Classification: Class A, B & C","Regulatory Landscape",["safety-class","classification"]),
   ("Risk Management Primer: ISO 14971 & FMEA","Regulatory Landscape",["iso14971","fmea","risk"]),
   ("Regulatory Submissions: 510(k), PMA & Technical Files","Regulatory Landscape",["510k","submissions"]),
   ("Software Development Plan (SDP): What It Must Contain","Development Planning",["sdp","planning"]),
   ("Software Configuration Management Plan","Development Planning",["scm","versioning"]),
   ("Traceability Matrix: Requirements to Design to Test","Development Planning",["traceability","requirements"]),
   ("Software Requirements Specification (SRS)","Requirements",["srs","requirements"]),
   ("Documenting Safety Requirements from Risk Analysis","Requirements",["safety-requirements","risk"]),
   ("Software Architectural Design: Decomposition","Architecture",["architecture","design"]),
   ("Architectural Design for Safety: Fault Isolation","Architecture",["safety-architecture"]),
   ("MISRA C for Medical: Compliant Coding Guidelines","Design & Implementation",["misra","coding-standards"]),
   ("Unit Verification: Code Reviews & Static Analysis","Design & Implementation",["unit-verification","static-analysis"]),
   ("Software Integration & Integration Testing","Integration & Testing",["integration","build"]),
   ("Software System Testing: Plans, Cases & Reports","Integration & Testing",["system-testing","class-c"]),
   ("Regression Testing & Change Control","Integration & Testing",["regression","change-control"]),
   ("Verification vs Validation: The V&V Distinction","V&V",["verification","validation"]),
   ("Usability Engineering: IEC 62366 Integration","V&V",["usability","iec62366"]),
   ("Software Release: Notes, Version Labels & Archiving","Release & Maintenance",["release","versioning"]),
   ("Cybersecurity for Medical Devices: IEC 81001-5-1","Release & Maintenance",["cybersecurity","iec81001"]),
   ("Agile & IEC 62304: Making Iterative Dev Compliant","Release & Maintenance",["agile","compliance"]),
   ("Audit Preparation: DHF, DMR & Device History Records","Release & Maintenance",["audit","dhf","dmr"]),
   ("Full Review: Compliance Checklist & Mock Audit","Review",["review","checklist"]),
  ],
 },
 "ebpf": {
  "title": "eBPF & Kernel Debugging Daily Log",
  "curriculum": [
   ("Linux Tracing Overview: ftrace, perf, eBPF & the Stack","Foundations",["tracing","ftrace","ebpf"]),
   ("ftrace: Function Tracer & trace_printk Setup","ftrace",["ftrace","tracing","kernel"]),
   ("ftrace: Function Graph Tracer & Latency Tracing","ftrace",["ftrace","latency","graph"]),
   ("trace-cmd: Front-End for ftrace in Practice","ftrace",["trace-cmd","ftrace"]),
   ("perf: Performance Counters & Hardware PMU Events","perf",["perf","pmu","counters"]),
   ("perf record & report: Profiling a Running System","perf",["perf","profiling","flamegraph"]),
   ("perf stat: Cycle Counting & CPI Analysis","perf",["perf","stat","cpi"]),
   ("Flame Graphs: Visualizing perf Stack Traces","perf",["flamegraph","perf","visualization"]),
   ("perf sched: Scheduling Latency Analysis","perf",["perf","scheduling","latency"]),
   ("eBPF Architecture: BPF VM, Maps & Helper Functions","eBPF Foundations",["ebpf","bpf-vm","maps"]),
   ("BCC: Writing eBPF Programs in Python","eBPF BCC",["bcc","ebpf","python"]),
   ("bpftrace: One-Liners for Kernel Tracing","eBPF bpftrace",["bpftrace","ebpf","tracing"]),
   ("eBPF kprobes & kretprobes: Dynamic Instrumentation","eBPF Advanced",["kprobes","ebpf"]),
   ("eBPF uprobes: Tracing Userspace from Kernel","eBPF Advanced",["uprobes","ebpf"]),
   ("eBPF Maps: Hash, Array, Ring Buffer & Perf Events","eBPF Advanced",["maps","ring-buffer"]),
   ("libbpf & CO-RE: Portable eBPF Programs in C","eBPF libbpf",["libbpf","co-re","portability"]),
   ("eBPF for Network Observability: XDP & TC Programs","eBPF Networking",["xdp","tc","networking"]),
   ("eBPF Security: LSM Hooks & Seccomp Filters","eBPF Security",["lsm","seccomp","security"]),
   ("Debugging Driver Latency with eBPF: End-to-End","eBPF Applied",["driver","latency","example"]),
   ("Dynamic Tracing a Custom Kernel Module","eBPF Applied",["kernel-module","tracing","debug"]),
   ("Full Review & Project: Kernel Latency Monitor","Review",["review","project","latency"]),
  ],
 },
 "hil-testing": {
  "title": "HIL Testing & Embedded CI/CD Daily Log",
  "curriculum": [
   ("Why HIL Testing: Firmware Testing Pyramid & Hardware Gap","Foundations",["hil","testing","strategy"]),
   ("Test Frameworks for Embedded: Unity, CppUTest, Ztest","Unit Testing",["unity","cpputest","unit-tests"]),
   ("Mocking Hardware in Unit Tests: CMock & FFF","Unit Testing",["cmock","fff","mocking"]),
   ("Host-Based Testing: Running Firmware Tests on Linux","Unit Testing",["host-testing","posix"]),
   ("pytest-embedded: Python Test Runner for Embedded","Integration Testing",["pytest","embedded","python"]),
   ("Twister: Zephyr CI Test Runner for Multiple Boards","Integration Testing",["twister","zephyr","ci"]),
   ("OpenOCD & pyOCD: Programmatic Flash & Debug","HIL Infrastructure",["openocd","pyocd","flashing"]),
   ("Serial Console Automation: pexpect & miniterm","HIL Infrastructure",["serial","automation"]),
   ("GPIO Control from Host: Controlling DUT via Relay","HIL Infrastructure",["gpio","relay","dut"]),
   ("Power Cycling the DUT: Automated Reset & Fault Injection","HIL Infrastructure",["power-cycling","fault-injection"]),
   ("GitHub Actions for Embedded: Self-Hosted Runners","CI/CD",["github-actions","self-hosted","ci"]),
   ("Docker for Embedded Build Environments","CI/CD",["docker","build-environment"]),
   ("CMake & CTest: Unified Build & Test System","Build Systems",["cmake","ctest"]),
   ("Code Coverage for Embedded: gcov, lcov & Gcovr","Quality Gates",["gcov","coverage","lcov"]),
   ("Static Analysis in CI: cppcheck, clang-tidy, MISRA","Quality Gates",["cppcheck","clang-tidy"]),
   ("IEC 62304-Compliant Test Documentation from CI","Compliance",["iec62304","documentation"]),
   ("HIL for Zephyr BLE: Testing BLE Advertisements","HIL Applied",["ble","zephyr","automation"]),
   ("HIL Power Measurement: Automated Current Profiling","HIL Applied",["power","measurement"]),
   ("Full Review & Project: Complete HIL Pipeline","Review",["review","project","pipeline"]),
  ],
 },
 "trustzone": {
  "title": "TrustZone & Secure Boot Daily Log",
  "curriculum": [
   ("ARM Security Architecture: TrustZone for Cortex-A & Cortex-M","Foundations",["trustzone","arm","security"]),
   ("Secure Boot Concepts: Chain of Trust, Keys & Attestation","Foundations",["secure-boot","chain-of-trust"]),
   ("ARM Cortex-M Security: SAU, IDAU & TrustZone-M","Cortex-M Security",["trustzone-m","sau","idau"]),
   ("TF-M: Trusted Firmware-M Architecture & Secure Services","TF-M",["tfm","secure-services"]),
   ("TF-M PSA Crypto API: Key Management & Crypto Ops","TF-M",["psa-crypto","keys","tfm"]),
   ("TF-M Secure Storage & Attestation Services","TF-M",["secure-storage","attestation"]),
   ("MCUboot: Bootloader Architecture & Image Slots","MCUboot",["mcuboot","bootloader","slots"]),
   ("MCUboot Image Signing: Keys, imgtool & Verification","MCUboot",["mcuboot","signing","imgtool"]),
   ("MCUboot DFU: USB, BLE & Serial Upgrade Modes","MCUboot",["dfu","ble","usb"]),
   ("MCUboot Rollback Protection & Anti-Rollback Counters","MCUboot",["rollback","security"]),
   ("Trusted Firmware-A (TF-A): Architecture & Boot Stages","TF-A",["tfa","boot-stages","arm64"]),
   ("TF-A BL1, BL2, BL3: Each Stage Explained","TF-A",["bl1","bl2","bl3"]),
   ("OP-TEE: Trusted Execution Environment Architecture","OP-TEE",["optee","tee"]),
   ("OP-TEE Trusted Application: Writing a TA from Scratch","OP-TEE",["trusted-application","optee"]),
   ("OP-TEE Client API: Calling TAs from Normal World","OP-TEE",["client-api","optee"]),
   ("Secure Boot on Embedded Linux: U-Boot Verified Boot","Embedded Linux Secure Boot",["uboot","verified-boot"]),
   ("FIT Images: Kernel + DTB + Initramfs Signing","Embedded Linux Secure Boot",["fit-image","signing"]),
   ("Key Management Infrastructure: HSM & PKCS#11","Key Management",["hsm","pkcs11","provisioning"]),
   ("Firmware Encryption: Confidentiality for IP Protection","Advanced",["encryption","ip-protection"]),
   ("Side-Channel Attacks: Timing & Power Analysis Basics","Advanced",["side-channel","power-analysis"]),
   ("Full Review & Project: Secure Boot Chain on nRF9160","Review",["review","project","secure-boot"]),
  ],
 },
 "preempt-rt": {
  "title": "PREEMPT_RT & Real-Time Linux Daily Log",
  "curriculum": [
   ("What Makes a System Real-Time? WCET, Jitter & Latency","Foundations",["real-time","wcet","latency"]),
   ("Linux Scheduling: CFS, FIFO, RR & Deadline Policies","Linux Scheduler",["cfs","sched-fifo","scheduling"]),
   ("PREEMPT_RT Patch: What It Changes & How to Apply It","PREEMPT_RT",["preempt-rt","patch","kernel"]),
   ("Building a PREEMPT_RT Kernel for Your Target","PREEMPT_RT",["preempt-rt","build","kernel"]),
   ("cyclictest: Measuring Worst-Case Latency","Measurement",["cyclictest","latency","measurement"]),
   ("hackbench & stress-ng: Generating Realistic Load","Measurement",["hackbench","stress","load"]),
   ("Latency Histograms: Interpreting cyclictest Output","Measurement",["histogram","latency","analysis"]),
   ("CPU Isolation: isolcpus, nohz_full & rcu_nocbs","Tuning",["isolcpus","nohz","rcu"]),
   ("IRQ Affinity: Binding Interrupts to Specific CPUs","Tuning",["irq-affinity","smp","cpus"]),
   ("CPU Frequency Scaling: cpufreq & performance Mode","Tuning",["cpufreq","governors","performance"]),
   ("Memory: Huge Pages, mlockall & Page Faults in RT","Tuning",["hugepages","mlockall","page-faults"]),
   ("Priority Inversion & Priority Inheritance Mutexes","RT Programming",["priority-inversion","mutex","pthread"]),
   ("pthread Real-Time API: SCHED_FIFO & CPU Affinity","RT Programming",["pthread","sched-fifo","affinity"]),
   ("Lock-Free Data Structures for RT Code","RT Programming",["lock-free","atomic","wait-free"]),
   ("SCHED_DEADLINE: Sporadic Task Scheduling","Advanced Scheduling",["sched-deadline","sporadic","edf"]),
   ("RT Linux for Industrial Control: EtherCAT & Fieldbus","Industrial",["ethercat","fieldbus","industrial"]),
   ("Benchmarking Zephyr vs PREEMPT_RT Linux","Comparison",["zephyr","comparison","benchmark"]),
   ("Full Review & Project: Certifiable Latency Report","Review",["review","project","report"]),
  ],
 },
 "cpp-embedded": {
  "title": "C++ for Embedded Daily Log",
  "curriculum": [
   ("Why C++ in Embedded? Myths, Tradeoffs & Modern Approach","Foundations",["cpp","embedded","tradeoffs"]),
   ("RAII: Resource Acquisition Is Initialization for Hardware","Core Patterns",["raii","resources","ownership"]),
   ("Smart Pointers in Embedded: unique_ptr Without Heap","Core Patterns",["unique-ptr","ownership","stack"]),
   ("constexpr & consteval: Compile-Time Computation","Modern C++",["constexpr","compile-time"]),
   ("std::array, std::span & Fixed-Size Containers","Modern C++",["array","span","containers"]),
   ("Templates for Zero-Cost Abstraction in Drivers","Templates",["templates","zero-cost","drivers"]),
   ("Type Traits & SFINAE for Hardware-Specific Code","Templates",["type-traits","sfinae"]),
   ("std::variant & std::optional for Error Handling","Modern C++",["variant","optional","error"]),
   ("Lambda Expressions & Callbacks in Firmware","Modern C++",["lambda","callbacks"]),
   ("Operator Overloading for Register Bitfields","Patterns",["operator-overloading","bitfields","registers"]),
   ("Interrupt Handlers in C++: Class Methods as Callbacks","Embedded Patterns",["interrupts","callbacks","isr"]),
   ("State Machines in C++: enum class & std::variant FSMs","Embedded Patterns",["state-machine","fsm"]),
   ("Ring Buffer Implementation in Modern C++","Data Structures",["ring-buffer","template"]),
   ("Memory Management: Placement new & Static Pools","Memory",["placement-new","pool","static"]),
   ("C++ in Zephyr: Enabling & Writing C++ Drivers","Zephyr C++",["zephyr","cpp","drivers"]),
   ("MISRA C++ 2023: Key Rules & Enforcement with clang-tidy","Safety",["misra-cpp","clang-tidy","safety"]),
   ("AUTOSAR C++14: Subset for Safety-Critical Systems","Safety",["autosar","cpp14","safety"]),
   ("Undefined Behavior: UBSan & Catching UB in Firmware","Safety",["ubsan","undefined-behavior"]),
   ("Compiler Optimizations: What -O2 Does to Your Driver","Advanced",["optimization","compiler","asm"]),
   ("Full Review & Project: C++ HAL for a Sensor Driver","Review",["review","project","hal"]),
  ],
 },
 "devicetree": {
  "title": "Device Tree & Overlays Daily Log",
  "curriculum": [
   ("Device Tree Origins: Why It Exists & What Problem It Solves","Foundations",["devicetree","origins"]),
   ("DTS Syntax: Nodes, Properties, Cells & Phandles","DTS Syntax",["dts","nodes","properties"]),
   ("Data Types in Device Tree: u32, string, bytearray","DTS Syntax",["dtypes","cells","arrays"]),
   ("Address Cells & Size Cells: Memory Maps in DT","DTS Syntax",["address-cells","size-cells"]),
   ("Phandles & References: Linking Nodes Together","DTS Syntax",["phandles","references","labels"]),
   ("Binding Documentation: Writing & Reading DT Bindings","Bindings",["bindings","documentation","yaml"]),
   ("Common Bindings: GPIO, I2C, SPI, UART & Regulators","Bindings",["gpio","i2c","spi"]),
   ("The compatible Property: How Drivers Match DT Nodes","Kernel Integration",["compatible","probe","matching"]),
   ("of_* API: Reading Device Tree from Kernel Drivers","Kernel Integration",["of-api","driver","kernel"]),
   ("devm_* Functions: Managed Resources from DT","Kernel Integration",["devm","managed","resources"]),
   ("Device Tree Overlays (DTBO): Syntax & Structure","Overlays",["dtbo","overlay","syntax"]),
   ("Applying Overlays at Boot: U-Boot & overlays.txt","Overlays",["uboot","overlay","boot"]),
   ("Runtime Overlays: configfs & dtoverlay","Overlays",["configfs","dtoverlay","runtime"]),
   ("Pinmux & Pincontrol: Configuring Pin Functions via DT","Pincontrol",["pinmux","pincontrol","iomux"]),
   ("Clock Tree in Device Tree: clock-names & clkspec","Clocks",["clocks","clkspec","pll"]),
   ("Interrupt Routing in Device Tree: interrupt-parent","Interrupts",["interrupts","gic","routing"]),
   ("Device Tree in Yocto: KERNEL_DEVICETREE & DTBO","Yocto & DT",["yocto","kernel","dtbo"]),
   ("Device Tree in Zephyr vs Linux: Key Differences","Comparison",["zephyr","linux","comparison"]),
   ("dtc & fdtdump: Compiling & Inspecting DTBs","Tools",["dtc","fdtdump","tools"]),
   ("Common Device Tree Bugs & How to Debug Them","Debugging",["debug","bugs","dtc"]),
   ("Full Review & Project: DT Overlay for a Custom Sensor","Review",["review","project","overlay"]),
  ],
 },
 "formal-verification": {
  "title": "Formal Verification & Static Analysis Daily Log",
  "curriculum": [
   ("Why Formal Verification? Safety Standards & Cost of Bugs","Foundations",["formal-verification","safety"]),
   ("Static vs Dynamic Analysis: The Verification Spectrum","Foundations",["static-analysis","dynamic"]),
   ("Cppcheck: Fast Open-Source Static Analysis","Static Analysis",["cppcheck","static","bugs"]),
   ("clang-tidy: Linting & Refactoring C/C++ Code","Static Analysis",["clang-tidy","linting"]),
   ("Clang Static Analyzer: Path-Sensitive Bug Detection","Static Analysis",["clang-analyzer","path-sensitive"]),
   ("MISRA C 2012: Rules, Deviations & Compliance Reports","MISRA",["misra-c","rules","deviations"]),
   ("Frama-C Architecture: Plugins, ACSL & Value Analysis","Frama-C",["frama-c","acsl","value-analysis"]),
   ("ACSL Annotations: Preconditions, Postconditions & Invariants","Frama-C",["acsl","contracts","annotations"]),
   ("Frama-C WP Plugin: Deductive Verification","Frama-C",["wp","deductive","coq"]),
   ("Frama-C Eva Plugin: Abstract Interpretation for C","Frama-C",["eva","abstract-interpretation"]),
   ("Proving a Zephyr Driver with Frama-C WP","Frama-C Applied",["frama-c","zephyr","driver"]),
   ("CBMC: Bounded Model Checking for C Programs","Model Checking",["cbmc","model-checking","bounded"]),
   ("CBMC: Writing Harnesses & Checking Loop Bounds","Model Checking",["cbmc","harness","bounds"]),
   ("AFL++: Coverage-Guided Fuzzing for Firmware","Fuzzing",["afl","fuzzing","coverage"]),
   ("AddressSanitizer & UBSan: Runtime Bug Detection","Sanitizers",["asan","ubsan","sanitizers"]),
   ("Integrating Static Analysis in CI: Fail on Warnings","CI Integration",["ci","static-analysis","gates"]),
   ("Safety Case Documentation: GSN & CAE Notation","Documentation",["safety-case","gsn","cae"]),
   ("Full Review & Project: Verify a State Machine with CBMC","Review",["review","project","cbmc"]),
  ],
 },
 "power-management": {
  "title": "Power Management & Energy Profiling Daily Log",
  "curriculum": [
   ("Embedded Power Management: Goals, Trade-offs & Standards","Foundations",["power","standards"]),
   ("Linux PM Stack: PM Core, Drivers & Governors","Linux PM",["linux-pm","pm-core","drivers"]),
   ("suspend/resume: System Sleep States in Linux","System Sleep",["suspend","resume","sleep-states"]),
   ("Runtime PM: dev_pm_ops & rpm_suspend/resume","Runtime PM",["runtime-pm","dev-pm-ops"]),
   ("Wakeup Sources: Configuring & Debugging Wakeup Events","System Sleep",["wakeup","wakelock"]),
   ("cpufreq: Governors, Policies & DVFS on Embedded","CPU Power",["cpufreq","dvfs","governors"]),
   ("cpuidle: C-States, Latency Tolerance & Residency","CPU Power",["cpuidle","c-states","residency"]),
   ("devfreq: Dynamic Voltage & Frequency Scaling","Peripheral Power",["devfreq","dvfs","peripherals"]),
   ("Regulator Framework: Managing Power Rails in Drivers","Regulator",["regulator","rails","framework"]),
   ("Clock Gating & Power Domains","Clock & Domain",["clock-gating","power-domains"]),
   ("powertop: Finding Power Hogs on Linux","Measurement Tools",["powertop","measurement","tuning"]),
   ("Nordic PPK2: Per-Microsecond Current Profiling","Hardware Tools",["ppk2","nordic","current"]),
   ("Zephyr Power Management: pm_state & Device PM","Zephyr PM",["zephyr","pm-state","device-pm"]),
   ("Zephyr Tickless Idle & Wake-Up Sources","Zephyr PM",["tickless","idle","wakeup"]),
   ("Optimizing a Zephyr BLE Beacon for Sub-10uA Sleep","Zephyr PM Applied",["ble","beacon","optimization"]),
   ("Yocto Image Power Optimization: Stripping Daemons","Yocto PM",["yocto","daemons","optimization"]),
   ("Power Budget Spreadsheet: From Spec to Schematic","Design",["power-budget","design"]),
   ("Full Review & Project: Power Profile an Embedded System","Review",["review","project","profiling"]),
  ],
 },
 "rust-embedded": {
  "title": "Rust for Embedded Daily Log",
  "curriculum": [
   ("Why Rust for Embedded? Memory Safety Without GC","Foundations",["rust","memory-safety","embedded"]),
   ("Rust Toolchain for Embedded: rustup, targets & cargo","Foundations",["rustup","cargo","targets"]),
   ("no_std: Writing Embedded Rust Without the Standard Library","no_std",["no-std","bare-metal"]),
   ("Ownership & Borrowing: How It Prevents Embedded Bugs","Rust Core",["ownership","borrowing","safety"]),
   ("Lifetimes in Embedded: Static References & Peripherals","Rust Core",["lifetimes","static","peripherals"]),
   ("Peripheral Access Crates (PAC): Register-Level Access","HAL",["pac","registers","svd2rust"]),
   ("Embedded HAL: The Hardware Abstraction Layer Traits","HAL",["embedded-hal","traits","abstraction"]),
   ("GPIO, SPI & I2C with embedded-hal Traits","HAL",["gpio","spi","i2c"]),
   ("Interrupt Handlers in Rust: cortex-m & RTIC","Interrupts",["interrupts","cortex-m","rtic"]),
   ("RTIC Framework: Real-Time Interrupt-Driven Concurrency","RTIC",["rtic","concurrency","tasks"]),
   ("Embassy: Async/Await for Embedded Rust","Embassy",["embassy","async","await"]),
   ("Embassy Executor & Tasks: Cooperative Multitasking","Embassy",["executor","tasks","embassy"]),
   ("Embassy Peripherals: GPIO, UART, SPI, I2C Async APIs","Embassy",["peripherals","async","drivers"]),
   ("Embassy Networking: TCP/IP & BLE with nrf-softdevice","Embassy",["networking","ble","nrf"]),
   ("defmt: Efficient Logging for Embedded Rust","Debugging",["defmt","logging","rtt"]),
   ("probe-rs: Flash, Debug & RTT for Embedded Rust","Debugging",["probe-rs","flash","rtt"]),
   ("Testing Embedded Rust: Unit Tests on Host & QEMU","Testing",["testing","qemu","hil"]),
   ("Rust in the Linux Kernel: rust_module! Basics (v6.1+)","Linux Kernel Rust",["kernel","rust","module"]),
   ("Writing a Linux Kernel Driver in Rust: CharDev Example","Linux Kernel Rust",["chardev","driver","kernel"]),
   ("Comparing C vs Rust Driver: Safety Wins & Trade-offs","Comparison",["comparison","c","rust"]),
   ("Full Review & Project: Embassy BLE Thermometer","Review",["review","project","embassy"]),
  ],
 },
 "cfse": {
  "title": "Functional Safety Engineering Daily Log",
  "curriculum": [
   ("Functional Safety Overview: What It Is & Why It Matters","Foundations",["functional-safety","iec61508"]),
   ("IEC 61508: Structure, SIL Levels & Scope","IEC 61508",["iec61508","sil","e-e-e"]),
   ("Safety Integrity Levels (SIL): Determination & Verification","IEC 61508",["sil","determination"]),
   ("FMEA: Failure Mode & Effects Analysis for Firmware","Hazard Analysis",["fmea","failure-modes"]),
   ("FTA: Fault Tree Analysis - Top-Down Hazard Decomposition","Hazard Analysis",["fta","fault-tree"]),
   ("HAZOP: Hazard & Operability Study for Embedded Systems","Hazard Analysis",["hazop","hazard"]),
   ("ISO 26262: Automotive Functional Safety & ASIL Levels","ISO 26262",["iso26262","asil","automotive"]),
   ("ASIL Decomposition: Splitting Safety Requirements","ISO 26262",["asil","decomposition"]),
   ("ISO 26262 Part 6: Product Development at SW Level","ISO 26262",["iso26262","part6","software"]),
   ("Safety Case: Goal Structuring Notation (GSN)","Safety Case",["safety-case","gsn","goals"]),
   ("Software Safety Requirements: Deriving from Hazards","Requirements",["safety-requirements","hazards"]),
   ("Defensive Programming for Safety: MISRA & Coding Rules","Implementation",["misra","defensive","coding"]),
   ("Safe State & Fail-Safe Design Patterns for Firmware","Design Patterns",["fail-safe","safe-state"]),
   ("Diversity & Redundancy: Hardware & Software Strategies","Architecture",["redundancy","diversity"]),
   ("Watchdog Timers: Hardware & Software WDT Strategies","Implementation",["watchdog","wdt","safety"]),
   ("Memory Protection Unit (MPU): Spatial Isolation","Implementation",["mpu","spatial","isolation"]),
   ("Testing for Functional Safety: Coverage & Independence","Testing",["testing","coverage","independence"]),
   ("IEC 62443: Industrial Cybersecurity & Safety Convergence","Security & Safety",["iec62443","cybersecurity"]),
   ("CFSE Exam Prep: Key Topics, Structure & Mock Questions","Certification",["cfse","exam-prep"]),
   ("Full Review: Safety Case for a Zephyr-Based Medical Device","Review",["review","project","safety-case"]),
  ],
 },
}

POST_PROMPT = """You are an expert embedded systems engineer writing a daily technical blog post.

Blog series: {blog_title}
Day {day_num} topic: **{topic_title}**
Module/Domain: {domain}

Requirements:
1. Correct frontmatter (title, date, tags)
2. Technically precise — every command, config, or code example must be real and correct
3. Practical — focus on what engineers actually do
4. Intermediate level — reader has engineering experience but is learning this topic
5. 600-900 words of content (not counting code blocks)
6. End with "Try It Yourself" section (2-3 concrete tasks)
7. End with a teaser for the next day: {next_title}

Required Sections:
- What I Explored Today (1 paragraph)
- The Core Concept (explain the why, not just the what)
- Key Commands / Configuration / Code (with inline comments)
- Common Pitfalls & Gotchas (2-3 items)
- Try It Yourself (2-3 tasks)
- Next up teaser

Frontmatter format:
---
title: "Day {day_num:02d}: {topic_title}"
date: {today}
tags: [{tags}]
---

Write ONLY the post. No meta-commentary.
"""


def get_next_day(topic_dir: Path) -> int:
    existing = sorted(topic_dir.glob("day-*.md"))
    return 1 if not existing else int(existing[-1].stem.split("-")[1]) + 1


def update_index(topic_dir: Path, day: int, title: str, domain: str, tags: list) -> None:
    idx = topic_dir / "index.md"
    if not idx.exists():
        return
    content = idx.read_text()
    if f"day-{day:02d}" in content:
        return
    tag_str = " ".join(f"`#{t}`" for t in tags[:3])
    row = f"| [[{topic_dir.name}/day-{day:02d}\\|Day {day:02d}]] | {title} | {domain} | {tag_str} |"
    # Append row before the closing --- separator
    content = content.replace("\n---\n\n> *New post", f"\n{row}\n\n---\n\n> *New post", 1)
    idx.write_text(content)


def generate_post(topic_key: str, day: int = None, dry_run: bool = False) -> None:
    config = TOPICS[topic_key]
    curriculum = config["curriculum"]
    topic_dir = CONTENT_DIR / topic_key

    if day is None:
        day = get_next_day(topic_dir)

    idx = (day - 1) % len(curriculum)
    topic_title, domain, tags = curriculum[idx]
    next_title = curriculum[idx + 1][0] if idx + 1 < len(curriculum) else "Full Review"
    today = date.today().isoformat()
    tags_str = ", ".join(f'"{t}"' for t in ["til", topic_key] + tags[:3])

    print(f"  [{topic_key}] Day {day:02d}: {topic_title}")

    prompt = POST_PROMPT.format(
        blog_title=config["title"], day_num=day, topic_title=topic_title,
        domain=domain, next_title=next_title, today=today, tags=tags_str,
    )
    resp = client.chat.completions.create(
        model=MODEL, messages=[{"role": "user", "content": prompt}],
        temperature=0.4, max_tokens=4096,
    )
    content = resp.choices[0].message.content.strip()

    if dry_run:
        print(content[:400]); return

    out = topic_dir / f"day-{day:02d}.md"
    out.write_text(content + "\n")
    update_index(topic_dir, day, topic_title, domain, tags)
    print(f"  Written: content/{topic_key}/day-{day:02d}.md")


def generate_all(day: int = None, dry_run: bool = False) -> None:
    print(f"Generating next post for all {len(TOPICS)} topics...")
    for topic_key in TOPICS:
        generate_post(topic_key, day, dry_run)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Firmware Daily Log — post generator")
    p.add_argument("--topic", choices=list(TOPICS.keys()), help="Topic slug")
    p.add_argument("--day", type=int, help="Day number (default: next)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--list", action="store_true", help="List all topics and curriculum size")
    args = p.parse_args()

    if args.list:
        print(f"\n{'Slug':<22} {'Title':<42} Days")
        print("-" * 72)
        for k, v in TOPICS.items():
            print(f"  {k:<22} {v['title']:<42} {len(v['curriculum'])}")
        sys.exit(0)

    if args.topic:
        generate_post(args.topic, args.day, args.dry_run)
    else:
        generate_all(args.day, args.dry_run)
