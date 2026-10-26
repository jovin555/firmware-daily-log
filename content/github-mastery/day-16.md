---
title: "Day 16: Writing Custom Actions: JavaScript & Docker Actions"
date: 2026-10-26
tags: ["til", "github-mastery", "custom-actions", "docker"]
---

## What I Explored Today

Today I moved past consuming marketplace actions and started authoring my own. The trigger was a recurring annoyance: every firmware repo I maintain has the same three-step dance to compute a build version from `git describe`, inject it into a header, and post a summary to the job output. Copy-pasting that YAML across repos is exactly the kind of drift that bites you six months later. So I built it once as a composite-free, self-contained action — first as a JavaScript action, then as a Docker action — and compared the tradeoffs. This post is the distilled version of what actually matters when you ship an action that other workflows (and other people) will depend on.

## The Core Concept

A GitHub Action is just a repository with an `action.yml` metadata file and an entrypoint. There are three flavors: **composite** (shell steps glued together), **JavaScript** (Node runs your code directly on the runner), and **Docker** (your code runs inside a container you build). The "why" behind choosing between the last two is about the execution environment contract.

JavaScript actions run *on the runner itself*, using the Node runtime GitHub pre-installs. That means no build step at invocation time, fast startup, and access to the runner's filesystem and pre-installed toolchains. The cost: you must commit your `node_modules` (or bundle with `ncc`) because the runner won't `npm install` for you, and you're pinned to whatever Node major the runner ships.

Docker actions run *in a container you define*, so you control the OS, the language version, and every dependency. That's the right call when your action needs a specific toolchain (a particular GCC, a Python version, a binary that isn't on the runner). The cost is a container build/pull on every run and a Linux-only constraint — Docker actions don't run on Windows or macOS runners.

The unifying contract is the **toolkit**: inputs arrive as `INPUT_*` environment variables, outputs are written to `$GITHUB_OUTPUT`, and logs/annotations go through the runner's command protocol. Get that contract right and the action is portable regardless of flavor.

## Key Commands / Configuration / Code

**`action.yml` — the metadata contract.** This is the file that makes a repo an action.

```yaml
name: 'Compute Build Version'
description: 'Derives a semver-ish build version from git describe and writes a header'
inputs:
  header-path:
    description: 'Path to the generated version header'
    required: false
    default: 'include/version.h'
outputs:
  version:
    description: 'The computed version string'
    value: ${{ steps.compute.outputs.version }}
runs:
  using: 'node20'          # JavaScript action; use 'docker' for a container action
  main: 'dist/index.js'    # MUST be the bundled output, not src/index.js
```

**JavaScript action entrypoint.** Inputs come in via `INPUT_*` (uppercased, spaces→underscores). Outputs go to the `GITHUB_OUTPUT` file, never `::set-output` (deprecated).

```js
// src/index.js — bundled to dist/index.js with @vercel/ncc
const core = require('@actions/core');
const exec = require('@actions/exec');

async function run() {
  try {
    // Capture stdout from git describe into a variable
    let version = '';
    await exec.exec('git', ['describe', '--tags', '--always'], {
      listeners: { stdout: (d) => (version += d.toString()) },
    });
    version = version.trim();

    // Write the header file the build will include
    const headerPath = core.getInput('header-path') || 'include/version.h';
    require('fs').writeFileSync(
      headerPath,
      `#define FW_VERSION "${version}"\n`
    );

    // Set the step output — read by downstream steps via steps.<id>.outputs.version
    core.setOutput('version', version);
    core.info(`Computed version: ${version}`);
  } catch (err) {
    core.setFailed(err.message); // marks the step failed and surfaces the message
  }
}
run();
```

Bundle it so the runner has everything it needs:

```bash
npm install @actions/core @actions/exec
npx @vercel/ncc build src/index.js -o dist   # produces dist/index.js + vendored deps
git add dist && git commit -m "build: bundle action"
```

**Docker action variant.** Same `action.yml` shape, different `runs` block:

```yaml
runs:
  using: 'docker'
  image: 'Dockerfile'      # or 'docker://ghcr.io/you/action:tag' for a prebuilt image
  args:
    - ${{ inputs.header-path }}
```

```dockerfile
FROM alpine:3.20
RUN apk add --no-cache git
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
```

```bash
#!/bin/sh
# entrypoint.sh — inputs arrive as INPUT_<NAME> env vars, args as $1, $2...
set -e
VERSION=$(git describe --tags --always)
printf '#define FW_VERSION "%s"\n' "$VERSION" > "${INPUT_HEADER_PATH:-include/version.h}"
echo "version=$VERSION" >> "$GITHUB_OUTPUT"
```

**Consuming it from a workflow** (local path during development, tag once published):

```yaml
- uses: actions/checkout@v4
  with: { fetch-depth: 0 }   # git describe needs full history + tags
- id: compute
  uses: ./.github/actions/compute-version   # local action, resolved from the checkout
- run: echo "Built ${{ steps.compute.outputs.version }}"
```

## Common Pitfalls & Gotchas

**Forgetting `fetch-depth: 0`.** `actions/checkout` does a shallow clone by default, so `git describe --tags` fails or returns garbage because tags and history are missing. Any action that inspects git history needs the full clone — this is the single most common bug in version-computing actions.

**Committing `src/` but not `dist/`.** The runner executes `main:` exactly as written and never runs your build. If you point `main` at `dist/index.js` but forget to commit the bundle, the action fails with a module-not-found error that's confusing because it works locally. Either commit `dist/` or wire a CI job that builds and commits it on tag.

**Docker actions and the workspace path.** Inside a Docker action, `$GITHUB_WORKSPACE` is mounted, but your `ENTRYPOINT` runs with a working directory that isn't necessarily the repo root, and the container user may not match the runner user — files you write can end up root-owned and break later steps. Always `cd "$GITHUB_WORKSPACE"` explicitly and be deliberate about `USER` in the Dockerfile.

## Try It Yourself

1. **Build the JS action end-to-end.** Create `.github/actions/compute-version/` with the `action.yml` and bundled `dist/index.js` above, wire it into a workflow with `fetch-depth: 0`, and confirm `steps.compute.outputs.version` prints a real tag in a downstream step.
2. **Port it to Docker.** Reimplement the same logic as a Docker action in a sibling directory, run both in one workflow, and time them — note the container pull/build overhead versus the JS startup.
3. **Break it on purpose.** Remove `fetch-depth: 0` and observe the failure mode, then add `core.setFailed` handling so the step fails cleanly with a readable message instead of a stack trace.

## Next up

Tomorrow: **Self-Hosted Runners for Embedded & Hardware-in-the-Loop Builds** — why cloud runners can't flash a board, how to register a runner on a bench machine with the target hardware attached, and the isolation and security tradeoffs that come with letting workflows touch real silicon.
