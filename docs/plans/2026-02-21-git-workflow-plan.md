# Git Workflow Plan for PrismataAI

**Status:** DONE (Phases 1-3 implemented, Phase 4 pending user cleanup session, Phase 5 done via CLAUDE.md)
**Author:** Claude Code session, Feb 21 2026
**Context:** User is solo developer, self-described git noob, wants simple discipline without overhead

## The Honest Assessment: Do You Need This?

**Short answer: Yes, but keep it lightweight.**

You're a solo dev on a fork. You don't need GitHub Flow, Gitflow, or trunk-based development. But you DO benefit from:

1. **Independent mergeability** — Right now, the GUI `activateWorkers` fix is tangled with watcher enhancements, commentary knowledge, replay ingestion, and training fixes on one branch. You can't merge just the bugfix without everything else.

2. **Clean rollback** — If a change breaks something, `git revert <commit>` works cleanly when each branch has one purpose. With everything mixed, reverting is surgery.

3. **Context for future sessions** — Branch names tell Claude Code what you're working on. `fix/gui-activateWorkers` is instantly clear; `feature/watcher-enhancements-v2` with 149 files is not.

**What you DON'T need:** PR reviews, branch protection rules, CI gates, release branches, or any ceremony. Just: name it, work on it, merge it when done.

## Phase 1: Add CLAUDE.md Guidelines (5 minutes)

Add a "Git Workflow" section to CLAUDE.md with simple rules all future Claude sessions follow.

### Rules:

```markdown
## Git Workflow

**Branch naming:** `{type}/{short-description}` where type is:
- `fix/` — bug fixes (e.g., `fix/gui-activateWorkers-precedence`)
- `feature/` — new features (e.g., `feature/replay-ingestion`)
- `docs/` — documentation only (e.g., `docs/commentary-knowledge`)
- `training/` — training pipeline changes (e.g., `training/streaming-loader-fix`)

**When to branch:** Create a new branch from `master` when starting work that is logically independent from other in-progress work. Small fixes (typos, one-line changes) can go directly on the current branch if it's related.

**Branch lifecycle:**
1. `git checkout master && git pull PrismatAlpha master` — start from latest
2. `git checkout -b fix/description` — create branch
3. Work, commit as you go
4. When done: push and optionally PR, or merge locally with `git checkout master && git merge fix/description`
5. Delete branch after merge: `git branch -d fix/description`

**Push target:** Always push to `PrismatAlpha` (never `origin`).

**Commit style:** Imperative mood, focus on "why" not "what". One logical change per commit.

**Don't worry about:**
- Squashing commits (your history is fine as-is)
- Rebasing (merge commits are fine for solo dev)
- PR descriptions (optional — use `/commit-push-pr` if you want one)
```

### Why CLAUDE.md, not hooks:
- Hooks that BLOCK you from committing on the wrong branch would be annoying
- Guidelines in CLAUDE.md mean every Claude session follows them naturally
- You can override anytime by just telling Claude "commit here, I don't want a new branch"

## Phase 2: Create `/start-work` Command (10 minutes)

A simple slash command that automates the "start new work" flow.

**File:** `.claude/commands/start-work.md`

```markdown
---
description: Start a new piece of work on a clean branch from master
allowed-tools: Bash(git:*)
argument-hint: <type/description> e.g. fix/gui-blocking-bug or feature/replay-mode
---

Start a new branch for the user's work. Steps:

1. Check current git status for uncommitted changes. If any exist, warn the user and ask what to do (stash, commit first, or abort).
2. Fetch latest from PrismatAlpha: `git fetch PrismatAlpha`
3. Create new branch from PrismatAlpha/master: `git checkout -b {argument} PrismatAlpha/master`
4. Confirm the branch was created and show `git log --oneline -1` to verify starting point.
5. Tell the user they're ready to work and remind them to use `/commit` when they want to save progress.
```

**Usage:** `/start-work fix/gui-activateWorkers`

## Phase 3: Create `/audit` Command (10 minutes)

A repo health check command the user can run anytime.

**File:** `.claude/commands/audit.md`

```markdown
---
description: Audit repository health - branches, uncommitted changes, stale files
allowed-tools: Bash(git:*), Bash(ls:*), Bash(wc:*), Read
---

Run a repository health audit. Check ALL of the following and report a summary:

1. **Branch status:**
   - Current branch name
   - How many commits ahead/behind master
   - List all local branches with their tracking status
   - Flag any branches that have been merged to master but not deleted

2. **Working tree:**
   - Count of modified tracked files
   - Count of untracked files
   - List modified tracked files (these are likely in-progress work)
   - Flag any large untracked files (>10MB) that might need .gitignore

3. **Remote sync:**
   - Whether current branch has been pushed
   - Whether master is up to date with PrismatAlpha/master
   - Any unpushed commits on any branch

4. **Stale branches:**
   - Branches with no commits in the last 30 days
   - Branches that diverge significantly from master (>20 commits)

5. **Recommendations:**
   - Suggest cleanup actions (delete merged branches, push unpushed work, gitignore large files)
   - Flag any risky state (uncommitted changes to critical files like train.py, NeuralNet.cpp)

Format output as a clean dashboard with emoji indicators:
- OK items
- WARN items that need attention
- CRITICAL items that need immediate action
```

## Phase 4: Clean Up Current State (15 minutes, with user)

The current repo has accumulated work across branches. A one-time cleanup:

1. **Inventory what's on each branch:**
   - `feature/watcher-enhancements-v2` — watcher cost tracking, idle detection, Azure cleanup (NOT merged to master)
   - `feature/cpp-replay-stepper` — replay ingestion + various other work (8 commits ahead)
   - `master` — last clean state

2. **Decide what to do with each:**
   - The watcher enhancements branch: merge to master if ready, or keep as-is
   - The replay stepper branch: merge completed work, keep WIP separate
   - The 142 untracked files: most are dev artifacts — add to `.gitignore` or delete

3. **Get to a clean `master`** so future `/start-work` commands have a good base.

This phase needs user input — Claude should present options, not act unilaterally.

## Phase 5: Optional — Add Pre-Planning Hook

If the user wants Claude to automatically suggest branching when starting new work:

**Option A: CLAUDE.md guideline (recommended)**
Add to the planning instructions: "Before starting implementation, check if the work should be on a new branch. If current branch has unrelated uncommitted work, suggest `/start-work`."

**Option B: Hook on EnterPlanMode**
Not currently supported by Claude Code's hook system (hooks only fire on tool use, not on planning mode entry). So Option A is the practical choice.

## What We're NOT Doing (and why)

| Approach | Why Not |
|----------|---------|
| Branch protection rules | Solo dev, no team to enforce against |
| PR templates | Overhead without reviewers |
| Pre-commit hooks (husky/lint-staged) | No linter/formatter in C++ workflow |
| Git hooks (`.git/hooks/`) | Too rigid for exploratory dev style |
| Conventional Commits | Overkill for this project size |
| GitFlow (develop/release/hotfix) | Enterprise pattern, wrong for solo |
| Trunk-based development | Requires CI/CD maturity you don't have |

## Summary

| Phase | What | Time | Complexity |
|-------|------|------|------------|
| 1 | CLAUDE.md guidelines | 5 min | Add text |
| 2 | `/start-work` command | 10 min | Create 1 file |
| 3 | `/audit` command | 10 min | Create 1 file |
| 4 | Clean up current state | 15 min | Interactive |
| 5 | Planning guideline | 2 min | Add 1 line to CLAUDE.md |

Total: ~40 minutes for a system that every future session will follow automatically.
