---
title: "Day 20: GitHub Pages: Deploying Static Sites from Actions"
date: 2026-10-30
tags: ["til", "github-mastery", "github-pages", "deployment"]
---

## What I Explored Today

Today I wired up GitHub Pages to deploy from a GitHub Actions workflow instead of the legacy "deploy from a branch" mode. The branch-based approach is fine for a plain Jekyll site, but the moment you need a build step — Hugo, Astro, Vite, a custom static generator, or even just a `npm run build` — you want Actions to own the pipeline. I spent the afternoon converting a Vite site to deploy via `actions/upload-pages-artifact` and `actions/deploy-pages`, and I hit enough permission and artifact gotchas that it's worth writing down.

## The Core Concept

GitHub Pages has two deployment sources: a branch (Pages builds or serves files directly from a ref) and GitHub Actions. The branch mode is convenient but opaque — you don't control the build environment, and you can't easily inject a build step. The Actions mode flips the model: your workflow produces a directory of static files, uploads it as a *Pages artifact*, and a dedicated deploy job hands that artifact to the Pages service.

The reason this matters is the separation of concerns. The build job runs on a normal runner with whatever toolchain you need. The deploy job runs in a special environment (`github-pages`) that has the `pages: write` and `id-token: write` permissions required to publish. The `id-token: write` permission is the part people miss — Pages uses an OIDC token to verify the deployment came from your workflow, not from a random actor. Without it, the deploy step fails with a permissions error that doesn't obviously point at OIDC.

The artifact itself must be a single tarball of the *final* static output — the directory that would sit at the web root. If your build emits `dist/`, you upload `dist/`, not the repo root. Pages serves exactly what's in the artifact, so a stray `node_modules` or source file in the artifact is a bug, not a convenience.

## Key Commands / Configuration / Code

The canonical workflow. Note the two-job split and the `environment` block:

```yaml
# .github/workflows/pages.yml
name: Deploy to GitHub Pages

on:
  push:
    branches: [main]
  workflow_dispatch:        # allow manual runs

permissions:
  contents: read            # checkout needs this
  pages: write              # publish to Pages
  id-token: write           # OIDC token for deploy verification

# Only one deploy at a time; don't cancel in-progress deploys
concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm

      - run: npm ci
      - run: npm run build          # emits ./dist

      # Configure Pages metadata (base path, etc.)
      - uses: actions/configure-pages@v5

      # Package ./dist into the Pages artifact
      - uses: actions/upload-pages-artifact@v3
        with:
          path: ./dist

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

Enable the source once in the repo settings, or via the API:

```bash
# Point Pages at Actions instead of a branch
gh api -X POST repos/OWNER/REPO/pages \
  -f build_type=workflow
```

If your site lives under a subpath (project pages at `https://user.github.io/repo/`), set the base path so asset URLs resolve:

```js
// vite.config.js
export default {
  base: '/repo/',   // trailing slash matters
}
```

`actions/configure-pages@v5` exposes `base_path` and `base_url` outputs you can feed into your build if you'd rather not hardcode it.

## Common Pitfalls & Gotchas

**Missing `id-token: write`.** The deploy job fails with a vague "not authorized" or OIDC error. The permission must be at the workflow level (or on the deploy job) — `pages: write` alone is not enough.

**Uploading the wrong directory.** `upload-pages-artifact` tars whatever `path` points at. If you point it at the repo root, you ship `.git`, source files, and `node_modules`. Point it at your build output. Also: the action expects a directory, not a glob — `path: ./dist` works, `path: ./dist/*` does not.

**`concurrency` with `cancel-in-progress: true`.** Cancelling a deploy mid-flight can leave the Pages environment in a half-published state. Use `cancel-in-progress: false` and let deploys queue. The `group: pages` name is conventional and keeps all Pages workflows serialized.

**Custom domains and CNAME.** If you use a custom domain, the `CNAME` file must be in the artifact root. With a build step, that means copying it into `dist/` during the build — it won't survive otherwise, and Pages will drop your domain on the next deploy.

## Try It Yourself

1. Convert an existing branch-deployed Pages site to Actions: add the workflow above, flip `build_type` to `workflow` via `gh api`, and confirm the deploy job's `page_url` output matches your live URL.

2. Add a `CNAME` copy step to the build job (`cp CNAME dist/`) and verify a custom domain survives a redeploy — check the Pages settings page after the run.

3. Break it on purpose: remove `id-token: write` from the permissions block and read the actual failure message. Then restore it. Knowing the error signature saves an hour next time.

## Next Up

Tomorrow: **Dependabot: Version Updates, Security Alerts & Auto-Merge** — configuring `dependabot.yml`, triaging security advisories, and wiring auto-merge so patch bumps land without a human in the loop.
