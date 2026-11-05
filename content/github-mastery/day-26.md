---
title: "Day 26: Codespaces & Dev Containers for Reproducible Toolchains"
date: 2026-11-05
tags: ["til", "github-mastery", "codespaces", "devcontainers"]
---

## What I Explored Today

Today I dug into the intersection of GitHub Codespaces and the Dev Containers specification — specifically how a `.devcontainer/devcontainer.json` file becomes the single source of truth for a project's toolchain. The pitch is simple: instead of a README that says "install Node 20, Python 3.12, and Postgres 16, then run these five setup scripts," you commit a container definition and every contributor (and every CI job) gets the exact same environment. What surprised me is how much of this works *outside* Codespaces too — VS Code, JetBrains, and even plain `devcontainer` CLI all consume the same spec, so you're not locked into GitHub's cloud. I spent the afternoon converting a flaky "works on my machine" repo into one that boots in under 90 seconds on a fresh Codespace.

## The Core Concept

The problem Dev Containers solve is **environment drift**. A `Dockerfile` alone gives you a reproducible *image*, but it doesn't tell your editor how to attach to it, which extensions to install, which ports to forward, or which post-create commands to run (like `npm install` or `alembic upgrade head`). The `devcontainer.json` is the glue layer: it references an image or Dockerfile, then declares the *developer experience* on top of it.

Why this matters more than a Dockerfile in CI: CI runs your code once and throws the container away. A dev container is *long-lived and interactive* — it needs your shell history, your language server, your debugger, and your forwarded ports. The spec standardizes all of that. Codespaces is essentially a managed host that reads `devcontainer.json` and provisions a VM + container for you. The same file, run locally via the `devcontainer` CLI, gives you an identical environment offline. That symmetry is the whole value proposition: **one file, many hosts, zero drift.**

The other key insight: `devcontainer.json` supports **features** — composable installers (e.g., `ghcr.io/devcontainers/features/node:1`) that layer onto a base image without you writing Dockerfile `RUN` lines. Features are versioned OCI artifacts, so they're cacheable and shareable across repos.

## Key Commands / Configuration / Code

A minimal but realistic `devcontainer.json` for a Python + Node monorepo:

```jsonc
// .devcontainer/devcontainer.json
{
  "name": "monorepo-dev",
  // Use a prebuilt base image; swap for "build": { "dockerfile": "Dockerfile" } if you need custom layers
  "image": "mcr.microsoft.com/devcontainers/base:ubuntu-24.04",

  // Features layer toolchains on top of the base image without editing a Dockerfile
  "features": {
    "ghcr.io/devcontainers/features/python:1": { "version": "3.12" },
    "ghcr.io/devcontainers/features/node:1": { "version": "20" },
    "ghcr.io/devcontainers/features/docker-in-docker:2": {}
  },

  // Runs once when the container is created (not on every start) — good for installs
  "postCreateCommand": "pip install -e '.[dev]' && npm ci",

  // Runs on every container start — keep it fast
  "postStartCommand": "git fetch --all --prune",

  // Forward these ports to your host; label them so they're discoverable
  "forwardPorts": [3000, 8000, 5432],
  "portsAttributes": {
    "8000": { "label": "API", "onAutoForward": "notify" }
  },

  // Extensions installed automatically inside the container
  "customizations": {
    "vscode": {
      "extensions": ["ms-python.python", "dbaeumer.vscode-eslint", "esbenp.prettier-vscode"]
    }
  },

  // Run as a non-root user (the base image defines "vscode")
  "remoteUser": "vscode"
}
```

Running the same environment locally without Codespaces:

```bash
# Install the CLI (requires Docker running locally)
npm install -g @devcontainers/cli

# Build and start the container, then open a shell inside it
devcontainer up --workspace-folder .
devcontainer exec --workspace-folder . bash

# Validate your config before committing — catches schema errors early
devcontainer read-configuration --workspace-folder .
```

Pinning a Codespace machine type and prebuild via repo settings (`.github/codespaces/` isn't a thing — this lives in the UI or via the API), but you *can* commit a `devcontainer.json` that Codespaces honors automatically. Prebuilds are configured in **Settings → Codespaces → Prebuild configuration** and key off your `devcontainer.json` — change the file, and prebuilds re-run.

## Common Pitfalls & Gotchas

1. **`postCreateCommand` runs as `remoteUser`, not root.** If your install script needs `apt-get`, it will fail silently-ish (exit code non-zero, container still starts). Either move system packages into a `Dockerfile`/feature, or use `"postCreateCommand": "sudo apt-get update && sudo apt-get install -y ..."` — but prefer features, since they cache better.

2. **Port forwarding ≠ port binding.** `forwardPorts` makes a container port reachable from your host, but if your app binds to `127.0.0.1` *inside* the container, forwarding won't reach it. Bind to `0.0.0.0` in dev (e.g., `uvicorn app:main --host 0.0.0.0`). This bites everyone once.

3. **Volume mounts shadow your workspace.** If you mount a named volume over `node_modules` for performance, remember it persists across rebuilds — stale deps survive `postCreateCommand`. Use `"postCreateCommand": "npm ci"` (not `npm install`) and consider `devcontainer up --remove-existing-container` when things get weird.

## Try It Yourself

1. **Convert a repo.** Take any project with a multi-step setup README and write a `.devcontainer/devcontainer.json` using `image` + `features` (no Dockerfile). Verify with `devcontainer read-configuration --workspace-folder .` and boot it with `devcontainer up`.

2. **Prove reproducibility.** Open the same repo in a fresh Codespace and locally via the CLI. Run `python --version && node --version && git status` in both. They should match byte-for-byte on tool versions.

3. **Break it deliberately.** Set `"remoteUser": "root"`, add a `postCreateCommand` that runs `apt-get install -y jq`, then switch back to `vscode` and watch it fail. Fix it by moving `jq` into a feature or a `Dockerfile`. This is the fastest way to internalize the user/permission model.

## Next Up

Tomorrow: **GitHub Copilot — Chat, Code Review & Coding Agent.** We'll look at how Copilot's agent mode differs from inline suggestions, how to wire it into PR review, and where it still needs a human in the loop.
