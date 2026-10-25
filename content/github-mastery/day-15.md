---
title: "Day 15: Reusable Workflows & Composite Actions"
date: 2026-10-25
tags: ["til", "github-mastery", "reusable-workflows", "composite-actions"]
---

## What I Explored Today

Today I dug into the two mechanisms GitHub Actions gives you for DRY-ing up your pipelines: **reusable workflows** (`workflow_call`) and **composite actions**. They solve overlapping but distinct problems, and I spent the day figuring out where the boundary actually sits. The short version: reusable workflows are for orchestrating *jobs* across repos, composite actions are for packaging *steps* within a job. Getting that distinction wrong is the source of most of the confusion I hit, so I want to write down the mental model while it's fresh.

## The Core Concept

Before `workflow_call` and composite actions, the only way to share CI logic was copy-paste or a third-party action. Copy-paste rots. Third-party actions are fine for generic tooling but awkward for your own org-specific logic — you'd need to publish and version an action repo just to share a 15-line build script.

The two features split the problem along the job boundary:

- **Reusable workflows** are invoked at the *job* level with `uses: org/repo/.github/workflows/file.yml@ref`. They get their own runner, their own `jobs:` block, and their own `secrets`/`inputs` contract. You use them when the reusable unit needs a fresh runner, needs to run jobs in parallel, or needs to be called from another repository entirely.
- **Composite actions** are invoked at the *step* level with `uses: ./.github/actions/name` (or `org/repo/path@ref`). They run inside the caller's job, on the caller's runner, sharing the caller's workspace and environment. You use them when you want to bundle a sequence of `run:` steps — checkout, setup, cache, build — into one logical step without spinning up a new job.

The "why" is about **blast radius and cost**. A reusable workflow is a black box: the caller can't see intermediate steps, can't `cd` into its workspace afterward, and pays for a runner. A composite action is transparent: it's just steps, inlined into your job, and you can inspect every command. Reach for composite actions first; escalate to reusable workflows only when you genuinely need job-level isolation or cross-repo invocation.

## Key Commands / Configuration / Code

### A reusable workflow

```yaml
# .github/workflows/reusable-build.yml
name: Reusable Build
on:
  workflow_call:                    # the trigger that makes it callable
    inputs:
      node-version:
        type: string
        default: '20'
    secrets:
      NPM_TOKEN:
        required: true
    outputs:
      artifact-name:
        description: "Name of the uploaded artifact"
        value: ${{ jobs.build.outputs.artifact-name }}

jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      artifact-name: ${{ steps.upload.outputs.name }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ inputs.node-version }}
          cache: npm
      - run: npm ci
        env:
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
      - run: npm run build
      - id: upload
        run: echo "name=dist-${{ github.sha }}" >> "$GITHUB_OUTPUT"
      - uses: actions/upload-artifact@v4
        with:
          name: ${{ steps.upload.outputs.name }}
          path: dist/
```

### Calling it from another workflow

```yaml
# .github/workflows/ci.yml
jobs:
  build:
    uses: my-org/shared-workflows/.github/workflows/reusable-build.yml@v1
    with:
      node-version: '20'
    secrets:
      NPM_TOKEN: ${{ secrets.NPM_TOKEN }}   # must be passed explicitly
```

### A composite action

```yaml
# .github/actions/setup-and-build/action.yml
name: Setup and Build
description: Checkout, install, and build with caching
inputs:
  node-version:
    description: Node version
    default: '20'
runs:
  using: composite
  steps:
    - uses: actions/setup-node@v4
      with:
        node-version: ${{ inputs.node-version }}
        cache: npm
    - run: npm ci
      shell: bash                        # REQUIRED on every run step
    - run: npm run build
      shell: bash
```

### Using it in a job

```yaml
steps:
  - uses: actions/checkout@v4          # composite can't checkout for you
  - uses: ./.github/actions/setup-and-build
    with:
      node-version: '20'
```

Note the asymmetry: the reusable workflow does its own `checkout` because it owns its job; the composite action does not, because it inherits the caller's workspace.

## Common Pitfalls & Gotchas

**1. `shell:` is mandatory in composite `run:` steps.** Unlike workflow steps, composite actions have no default shell. Omit it and you get a validation error at parse time, not runtime — easy to miss if you're iterating locally with `act`.

**2. Secrets don't flow implicitly into reusable workflows.** Even if the caller has `NPM_TOKEN` in its environment, the callee sees nothing unless you pass it under `secrets:`. Use `secrets: inherit` to forward everything, but be aware that's a blunt instrument — it leaks every secret to the callee, including ones it has no business seeing.

**3. `uses:` refs in reusable workflows must be a full path with a ref.** `uses: my-org/shared-workflows/.github/workflows/build.yml` fails; you need `@v1` (or `@main`, or a SHA). And the called workflow must live in `.github/workflows/` — you can't call a workflow from an arbitrary path in the repo.

**4. Composite action `uses:` paths are relative to the *repo root*, not the action directory.** Inside `./.github/actions/foo/action.yml`, `uses: ./bar` resolves to `<repo>/bar`, not `<repo>/.github/actions/foo/bar`. This trips people up constantly when they try to nest composite actions.

## Try It Yourself

1. **Extract a composite action.** Take an existing job that does checkout → setup-node → `npm ci` → `npm test` and pull the last three steps into `.github/actions/test/action.yml`. Verify the caller still passes, then delete the now-duplicated steps from a second job and point it at the same action.

2. **Build a reusable workflow with an output.** Create a `workflow_call` workflow that builds an artifact and exposes its name as an output. Call it from a second workflow and consume the output in a downstream job via `needs.build.outputs.artifact-name`.

3. **Break it on purpose.** Remove the `shell: bash` from a composite `run:` step and observe the validation error. Then try calling a reusable workflow without passing a required secret and read the error message — knowing what these look like saves you a debugging session later.

## Next Up

Tomorrow: **Writing Custom Actions: JavaScript & Docker Actions** — moving past composite actions into the two "real" action types, where you get a `main` entrypoint, `@actions/core` for inputs and outputs, and the tradeoffs between shipping a Node bundle versus a Docker image.
