---
title: "Day 18: devtool: Modify, Build & Deploy Workflows"
date: 2026-06-30
tags: ["til", "yocto", "devtool", "workflow"]
---

## What I Explored Today

Today I went deep into `devtool`, the Yocto Project's Swiss Army knife for iterative development. After weeks of full image rebuilds and manual recipe patching, I finally dedicated time to mastering `devtool modify`, `devtool build`, and `devtool deploy-target`. The workflow is transformative: you extract a source tree, hack on it in your familiar editor, rebuild just that component, and push the binary to a running target—all without touching the rest of the build system. This is the difference between waiting 45 minutes for a kernel rebuild and iterating in under 30 seconds.

## The Core Concept

The fundamental problem `devtool` solves is the edit-compile-deploy cycle inside a Yocto build. Without it, every change requires: edit the recipe, run `bitbake -c clean <recipe>`, rebuild the entire recipe (including do_fetch, do_patch, do_configure, do_compile, do_install, do_package), then either rebuild the image or manually copy files. That's slow and error-prone.

`devtool` works by creating a "workspace" layer—a special overlay that takes precedence over all other layers. When you run `devtool modify <recipe>`, it:
1. Unpacks the source to a workspace directory (default: `build/workspace/sources/<recipe>`)
2. Creates a symlink-based recipe in the workspace layer that points to that source tree
3. Sets up a `git` repository in the source tree (even if upstream isn't git-based) so you can track changes

The key insight: `devtool` doesn't change how BitBake works. It just manipulates the layer priority and source fetching to give you a writable, version-controlled source tree that BitBake treats as the canonical source. When you run `devtool build`, it invokes `bitbake` under the hood but skips fetch and patch steps because the source is already there and unmodified from the workspace's perspective.

## Key Commands / Configuration / Code

### Setting Up the Workspace
```bash
# Initialize the workspace layer (only needed once per build directory)
devtool create-workspace

# Verify the workspace layer is in bblayers.conf
bitbake-layers show-layers | grep workspace
# Expected: /path/to/build/workspace, priority 99 (highest)
```

### The Core Workflow: Modify, Build, Deploy
```bash
# Step 1: Extract a recipe's source into workspace
devtool modify openssh

# Step 2: Navigate to the extracted source
cd build/workspace/sources/openssh

# Step 3: Make your changes (example: enable X11 forwarding by default)
sed -i 's/#X11Forwarding yes/X11Forwarding yes/' sshd_config

# Step 4: Build just the modified recipe (fast!)
devtool build openssh

# Step 5: Deploy to a running target (requires SSH access)
devtool deploy-target openssh root@192.168.1.100
# This copies the built binaries to /usr/bin/ on the target
```

### Advanced: Resetting and Finishing
```bash
# If you mess up, reset the source to original state
devtool reset openssh

# When done, create a proper patch and clean up
devtool finish openssh meta-custom-layer
# This generates patches from your git commits and adds them to the recipe
```

### Deploying Specific Files
```bash
# Sometimes you only need one binary, not the whole package
devtool deploy-target --strip openssh root@192.168.1.100
# --strip removes debug symbols, reducing transfer size
```

## Common Pitfalls & Gotchas

1. **Workspace Layer Persistence**: If you run `bitbake -c clean <recipe>` while `devtool modify` is active, it will delete the source in the workspace directory. Always use `devtool build` instead of direct `bitbake` commands for modified recipes. The clean command in devtool's context is `devtool reset`.

2. **Deploy-Target Dependencies**: `devtool deploy-target` only copies the recipe's output files, not its runtime dependencies. If your modified binary links against a new shared library you also modified, you need to deploy that library separately or rebuild the image. I wasted an hour debugging a segfault because I deployed a new `libssl` but not the updated `openssl` binary that depended on it.

3. **Source Tree Git State**: `devtool modify` initializes a git repo in the source directory, but it doesn't commit the initial state. If you run `git checkout -- .` to revert changes, you'll lose everything. Always commit the initial state immediately: `git add -A && git commit -m "initial state"`. This gives you a clean baseline to diff against.

## Try It Yourself

1. **Modify and Deploy a System Service**: Pick `lighttpd` or `dropbear` from your image. Use `devtool modify` to change a configuration default (e.g., enable a debug log). Build and deploy to your target. Verify the change took effect by checking the running process's command line or config file.

2. **Two-Recipe Dependency Chain**: Modify both `openssl` and `openssh` simultaneously. Change a cipher default in openssl's config, then rebuild openssh against the modified openssl. Deploy both to target and verify SSH still works with `ssh -v`. This exercises the dependency tracking in devtool's build.

3. **Finish with Patch Generation**: After making changes to a recipe, use `devtool finish` to move your modifications into a custom layer. Verify the generated patches apply cleanly with `devtool modify` on a fresh build directory. This simulates the handoff from development to integration.

## Next Up

Tomorrow, I'll explore the Standard SDK workflow with `populate_sdk` and cross-development. We'll build a standalone SDK, understand the environment setup script, and compile a userspace program outside of BitBake using the cross-toolchain—essential for teams that need to develop without a full Yocto build setup.
