---
title: "Day 02: Setting Up a Yocto Build Environment & kas"
date: 2026-06-14
tags: ["til", "yocto", "yocto", "setup", "kas"]
---

## What I Explored Today

Day 2 of my Yocto journey focused on getting a reliable, reproducible build environment off the ground. I set up the standard Yocto build prerequisites, cloned the `poky` reference distribution, and then—crucially—integrated `kas`, the Yocto build tool that eliminates the "works on my machine" problem. If you've ever spent a Monday morning debugging why a build that worked Friday now fails because someone updated a layer, `kas` is the antidote.

## The Core Concept

Yocto builds are notoriously stateful. The build directory (`build/`) accumulates configuration, downloaded sources (`downloads/`), shared state cache (`sstate-cache/`), and temporary files (`tmp/`). A single misconfigured `bblayers.conf` or `local.conf` can produce silent corruption or hours of wasted rebuilds.

The standard workflow—`source oe-init-build-env`, then `bitbake <target>`—works, but it's fragile. It assumes the developer has the correct host packages, the right Python version, and hasn't accidentally toggled a `MACHINE` variable between builds.

`kas` solves this by making the build configuration declarative. You write a YAML file that specifies exactly which layers, which branch, which machine, and which distro features to use. `kas` then:
1. Checks out the correct revisions of all layers.
2. Generates `bblayers.conf` and `local.conf` from your YAML.
3. Runs `bitbake` inside a controlled environment.

This means your build is version-controlled, auditable, and reproducible across CI, your laptop, and your colleague's workstation.

## Key Commands / Configuration / Code

### 1. Host Prerequisites (Ubuntu 22.04/24.04)

Yocto's `oe-init-build-env` script checks for these, but install them first:

```bash
sudo apt update && sudo apt install -y \
    gawk wget git diffstat unzip texinfo gcc build-essential \
    chrpath socat cpio python3 python3-pip python3-pexpect \
    xz-utils debianutils iputils-ping python3-git python3-jinja2 \
    libegl1-mesa libsdl1.2-dev pylint3 xterm python3-subunit \
    mesa-common-dev zstd liblz4-tool file locales libacl1
sudo locale-gen en_US.UTF-8
```

### 2. Clone Poky (Scarthgap LTS)

I'm using the latest LTS release for stability:

```bash
git clone --branch scarthgap git://git.yoctoproject.org/poky
cd poky
```

### 3. Install `kas` via pip

`kas` is a Python tool. Install it in a virtual environment to keep things clean:

```bash
python3 -m venv ~/yocto-venv
source ~/yocto-venv/bin/activate
pip install kas
```

### 4. Create a `kas` Project YAML

This is the heart of the setup. Save as `kas-project.yml` in your project root (outside `poky/`):

```yaml
# kas-project.yml
header:
  version: 14

machine: qemuarm64

distro: poky

target:
  - core-image-minimal

repos:
  poky:
    url: https://git.yoctoproject.org/poky
    refspec: scarthgap
    layers:
      meta:
      meta-poky:
      meta-yocto-bsp:

local_conf_header:
  standard: |
    CONF_VERSION = "2"
    PACKAGE_CLASSES = "package_ipk"
    DL_DIR = "${TOPDIR}/../downloads"
    SSTATE_DIR = "${TOPDIR}/../sstate-cache"
    TMPDIR = "${TOPDIR}/tmp"
  user: |
    # Add your custom overrides here
    INHERIT += "rm_work"
```

Key points:
- `header.version: 14` is required for kas 4.x.
- `repos` defines each layer and its exact revision.
- `local_conf_header` sections are merged in order; `user` is where you put your tweaks.
- Shared `DL_DIR` and `SSTATE_DIR` prevent re-downloading sources across projects.

### 5. Build with kas

```bash
# From the directory containing kas-project.yml
kas build kas-project.yml
```

That's it. `kas` will:
- Create a `build/` directory.
- Generate `bblayers.conf` and `local.conf` from the YAML.
- Run `bitbake core-image-minimal`.

First build will take 30-90 minutes depending on your machine. Subsequent builds reuse the sstate cache.

## Common Pitfalls & Gotchas

1. **Python version mismatch**  
   Yocto Scarthgap requires Python 3.8+. If your system Python is older (e.g., Ubuntu 20.04's 3.8 is fine, but CentOS 7's 2.7 is not), `kas` will fail silently or produce cryptic errors. Always run `python3 --version` first. Use `pyenv` or a container if needed.

2. **`kas` YAML indentation errors**  
   YAML is whitespace-sensitive. A single extra space in `local_conf_header` can cause `kas` to silently ignore your configuration, leading to builds that use default settings. Validate your YAML with `python3 -c "import yaml; yaml.safe_load(open('kas-project.yml'))"`.

3. **Shared `DL_DIR` race conditions**  
   If you run multiple `kas` builds concurrently pointing to the same `DL_DIR`, you can corrupt downloaded source archives. Either use separate download directories per project, or add `BB_NUMBER_THREADS = "1"` in your `local_conf_header` during development.

## Try It Yourself

1. **Create a minimal `kas` project** for `qemux86-64` targeting `core-image-base`. Build it and verify the image boots in QEMU with `runqemu qemux86-64`.

2. **Add a third-party layer** (e.g., `meta-openembedded` from `git://git.openembedded.org/meta-openembedded`) to your `kas` YAML. Add `meta-oe` and `meta-python` to the layers list, then build `core-image-minimal` again. Confirm the layer is loaded by checking `bitbake-layers show-layers`.

3. **Experiment with `local_conf_header` overrides**: Add `PACKAGE_CLASSES = "package_rpm"` in the `user` section and rebuild. Compare the output packages in `tmp/deploy/rpm/` vs the default `ipk` format.

## Next Up

Tomorrow, I'm diving into the engine room: **BitBake Fundamentals: Tasks, Recipes & Execution Model**. We'll dissect how a `.bb` recipe becomes a package, what `do_configure`, `do_compile`, and `do_install` actually do, and how BitBake's dependency graph prevents wasted work. If you've ever wondered why `bitbake -c listtasks` shows 50+ tasks for a simple recipe, that's our target.
