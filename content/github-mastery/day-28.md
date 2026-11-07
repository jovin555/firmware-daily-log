---
title: "Day 28: Organization Admin: Teams, Org Rulesets, Audit Log & Insights"
date: 2026-11-07
tags: ["til", "github-mastery", "organizations", "audit-log"]
---

# Day 28: Organization Admin: Teams, Org Rulesets, Audit Log & Insights

## What I Explored Today

Today I moved past per-repo settings and into the org-level control plane. The difference is significant: instead of configuring branch protection on each repository, I explored **organization rulesets** that apply across many repos at once, **teams** as the unit of access rather than individual collaborators, the **audit log** as the forensic record of everything that happens in the org, and **Insights** for spotting trends across the whole estate. This is the layer where a platform team actually governs a fleet of repositories instead of babysitting them one at a time.

## The Core Concept

The mental shift is from **repository administration** to **organization governance**. When you have five repos, you click through settings. When you have fifty, clicking is a liability — it drifts, it's unauditable, and nobody remembers which repo has which protection.

Three primitives solve this:

1. **Teams** decouple *who* from *what*. You grant a team access to a repo once; membership changes happen in the team, not in fifty repo settings. Teams also nest, so `@org/platform` can contain `@org/platform-infra` and `@org/platform-security`.

2. **Organization rulesets** are the fleet-wide version of branch protection. A single ruleset can target repos by name pattern or by custom property, and enforce required reviews, required status checks, signed commits, and push restrictions everywhere at once. They're evaluated *in addition to* repo-level rules — the most restrictive wins.

3. **The audit log** is the ground truth. Every settings change, membership edit, token creation, and ruleset bypass is recorded with actor, IP, and timestamp. It's the only reliable way to answer "who turned off the required checks on the firmware repo at 2am?"

Insights ties it together with aggregate views — traffic, dependency graph, code scanning, and Actions usage — so you can see the org as a system rather than a list.

## Key Commands / Configuration

**Create a team and grant repo access via `gh`:**

```bash
# Create a nested team under the platform parent team
gh api -X POST /orgs/acme/teams \
  -f name="platform-infra" \
  -f description="Infra & build tooling" \
  -f parent_team_id=1234567 \
  -f privacy=closed

# Grant the team push access to a specific repo
gh api -X PUT /orgs/acme/teams/platform-infra/repos/acme/firmware \
  -f permission=push
```

**An organization ruleset targeting repos by custom property** (this is the powerful part — no repo list to maintain):

```json
{
  "name": "org-baseline-protection",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] },
    "repository_property": {
      "include": [{ "name": "tier", "values": ["production"] }],
      "exclude": []
    }
  },
  "rules": [
    { "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 2,
        "dismiss_stale_reviews_on_push": true,
        "require_code_owner_review": true
      }
    },
    { "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [{ "context": "ci/build" }]
      }
    },
    { "type": "non_fast_forward" }
  ]
}
```

Apply it:

```bash
gh api -X POST /orgs/acme/rulesets --input ruleset.json
```

**Query the audit log** (org owners only; `--include all` pulls git and web events):

```bash
# Who changed rulesets in the last week?
gh api "/orgs/acme/audit-log?phrase=action:rulesets.update&per_page=50" \
  --jq '.[] | {actor: .actor, action: .action, repo: .repo, when: ."@timestamp"}'

# All PAT creations — useful for spotting leaked tokens
gh api "/orgs/acme/audit-log?phrase=action:personal_access_token.create" \
  --jq '.[] | {actor: .actor, when: ."@timestamp"}'
```

**Set a custom property** so the ruleset above actually matches something:

```bash
gh api -X PUT /orgs/acme/properties/schema/tier \
  -f value_type=string \
  -f 'allowed_values[]=production' \
  -f 'allowed_values[]=internal'

gh api -X PATCH /repos/acme/firmware \
  -f 'properties[tier]=production'
```

## Common Pitfalls & Gotchas

- **Rulesets stack, they don't override.** A repo-level ruleset that "allows" something doesn't loosen an org ruleset that forbids it. The union of all active rulesets applies, and the strictest constraint wins. If a push is blocked and you can't find the rule in the repo settings, check the org rulesets tab.

- **Bypass lists are the silent hole.** Org rulesets support `bypass_actors` (teams, apps, or the org admin role). It's easy to add `OrganizationAdmin` "just in case" and then discover every admin has been quietly pushing to `main`. Audit bypasses explicitly — they show up in the audit log as `rulesets.bypass`.

- **The audit log has a retention window.** On GitHub Enterprise Cloud it's 180 days via the API; on Free/Team it's 90 days for the UI and shorter via API. If you need longer retention for compliance (medical firmware, anyone?), stream it to an external sink with the audit log streaming feature — don't assume it'll be there next quarter.

## Try It Yourself

1. **Build a team hierarchy.** Create a parent team `platform` and a child team `platform-security`. Add yourself to the child, then verify you inherit the parent's repo access with `gh api /orgs/<org>/teams/platform-security/members`.

2. **Write an org ruleset gated on a custom property.** Define a `tier` property with values `production`/`internal`, tag one repo as `production`, and create a ruleset that requires two approvals only for `tier=production`. Confirm a PR on the tagged repo now demands two reviews.

3. **Hunt a settings change.** Use the audit log API to list every `repo.access` or `protected_branch` change in the last 30 days, and pipe it through `--jq` to print actor + timestamp. Bonus: find the most recent `personal_access_token.create` event.

## Next Up

Tomorrow is the capstone: **Full Review & Project — Set Up a Medical Firmware Repo with Templates, CI, Projects & Releases.** We'll take everything from the last 28 days and assemble it into a single, compliance-minded repository: issue/PR templates, a CI pipeline with required checks, a Projects board wired to automation, and a signed release workflow. Bring your notes — it's a build day.
