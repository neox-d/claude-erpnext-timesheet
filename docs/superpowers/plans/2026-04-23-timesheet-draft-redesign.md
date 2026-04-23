# Timesheet Draft Redesign + Submitter Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the timesheet draft to show two-line entries with ✓/⚠ status markers and always-visible project, add interactive AskUserQuestion resolution for unmatched entries (with clustering), and delegate post-approval submission to a dedicated subagent that outputs a live checklist.

**Architecture:** SKILL.md steps 2–4 are rewritten in place; a new `agents/timesheet-submitter.md` handles everything after draft approval. No MCP tool changes needed — all existing tools are sufficient.

**Tech Stack:** Claude Code SKILL.md prompt instructions, Claude Code agent frontmatter (markdown)

**Spec:** `docs/superpowers/specs/2026-04-23-timesheet-draft-redesign.md`

---

### Task 1: Create `agents/timesheet-submitter.md`

**Files:**
- Create: `agents/timesheet-submitter.md`

- [ ] **Step 1: Create the agents directory and write the file**

```bash
mkdir -p /home/neox/Work/erpnext-timesheet/agents
```

Write `agents/timesheet-submitter.md` with this exact content:

````markdown
---
name: timesheet-submitter
description: Submits an approved ERPNext timesheet. Creates task groups, child tasks, and root-level tasks as needed, then calls submitTimesheet. Dispatched by the timesheet skill after the user approves the final draft.
model: sonnet
effort: low
maxTurns: 20
disallowedTools: Write, Edit
---

You are submitting an approved timesheet to ERPNext. You will receive TARGET_DATE, STATUS, and ENTRIES in your prompt as JSON.

Begin your output with:
```
Submitting timesheet for {TARGET_DATE}...
```

Execute in this exact order, outputting one `- [x]` line as each action completes:

**1. Duplicate check**

Call `checkExisting` with `date=TARGET_DATE`.
- If `exists` is `true`: output `⚠ A timesheet already exists for {TARGET_DATE}. Stopping.` and stop.
- Otherwise output: `- [x] No duplicate found`

**2. Create new groups** (entries where `proposed_group` is set)

For each such entry in order:
- Call `createTask` with `subject=entry.proposed_group`, `description=entry.proposed_group`, `project=entry.project` (fall back to `STATUS.project` if not set), `hours=0`, `date=TARGET_DATE`, `is_group=True`
- Update `entry.parent_task` to the returned task name. Clear `entry.proposed_group`.
- Output: `- [x] Created group "{proposed_group}" → {returned_name}`

**3. Create child tasks** (entries where `parent_task` is set and `task` is not yet assigned)

For each such entry in order:
- Call `createTask` with `subject=entry.description`, `description=entry.description`, `project=entry.project` (fall back to `STATUS.project`), `hours=entry.hours`, `date=TARGET_DATE`, `parent_task=entry.parent_task`
- Set `entry.task` to the returned name.
- Output: `- [x] Created task "{description}" → {returned_name}`

**4. Create root-level tasks** (entries where neither `parent_task` nor `task` is set)

For each such entry in order:
- Call `createTask` with `subject=entry.description`, `description=entry.description`, `project=entry.project` (fall back to `STATUS.project`), `hours=entry.hours`, `date=TARGET_DATE`
- Set `entry.task` to the returned name.
- Output: `- [x] Created task "{description}" → {returned_name}`

**5. Submit**

Call `submitTimesheet` with `date=TARGET_DATE` and `entries` — each entry must include `description`, `hours`, `activity_type`; include `task` only if assigned.
- On success output: `- [x] Submitted → {name}`

Output `Done.` at the very end.

**On failure at any step:** output the error message and ask the user "Retry?" — max 3 attempts total across all steps. After 3 failures, tell the user to check their ERPNext connection.

**Auth failure:** if any MCP call returns `{"error": "auth_failed"}`, output:
> Your ERPNext session has expired. Run `/plugin config erpnext-timesheet` to update your credentials, then re-run `/timesheet`.

Then stop immediately.
````

- [ ] **Step 2: Verify against spec §4**

Check each item:
- [ ] Execution order: checkExisting → groups → child tasks → root tasks → submit
- [ ] Output format: `- [x]` per action, `Done.` at end
- [ ] `disallowedTools: Write, Edit` in frontmatter
- [ ] Auth failure message matches the wording in the existing SKILL.md Step 4
- [ ] Max 3 retry attempts mentioned

- [ ] **Step 3: Commit**

```bash
git add agents/timesheet-submitter.md
git commit -m "feat: add timesheet-submitter agent with live checklist output"
```

---

### Task 2: Update SKILL.md Narration Preamble

**Files:**
- Modify: `skills/timesheet/SKILL.md` line 13

The current preamble bans all narration, which conflicts with the new AskUserQuestion resolution in Step 3 and the agent checklist output in Step 4. Narrow the rule to cover only pre-draft output.

- [ ] **Step 1: Replace the narration rule**

In `skills/timesheet/SKILL.md`, find line 13:

```
When this skill is invoked, follow these steps exactly. Do not skip steps. Do not narrate which step you are on — no "Starting Step N", no "checking X", no intermediate announcements. The only output before the draft is the setup prompt or announce line.
```

Replace with:

```
When this skill is invoked, follow these steps exactly. Do not skip steps. Before the draft (Steps 0–2): no narration — no "Starting Step N", no "checking X", no intermediate announcements. The only output before the draft is the setup prompt or announce line. During Step 3: use AskUserQuestion as specified. During Step 4: display the agent's output verbatim.
```

- [ ] **Step 2: Commit**

```bash
git add skills/timesheet/SKILL.md
git commit -m "fix: narrow no-narration rule to pre-draft steps only"
```

---

### Task 3: Rewrite SKILL.md Step 2 — Auto-Match with ✓/⚠ Classification

**Files:**
- Modify: `skills/timesheet/SKILL.md` lines 67–97 (Step 2 section)

- [ ] **Step 1: Replace the entire Step 2 section**

In `skills/timesheet/SKILL.md`, find `## Step 2: Synthesize + Fetch Tasks` and replace the entire section (through the line before `## Step 3`) with:

```markdown
## Step 2: Synthesize + Fetch Tasks

From `MESSAGES`, identify distinct work themes. Create entries where:
- **description**: concise professional summary, max 80 chars, no filler phrases ("worked on", "helped with")
- **hours**: `STATUS.work_hours / number_of_tasks`, rounded to 1 decimal; last entry absorbs rounding remainder so total equals `work_hours` exactly
- **activity_type**: `STATUS.default_activity`
- **project**: `STATUS.project` (default; may be overridden per entry during Step 3)

Grouping rules:
- Merge closely related messages (e.g. "fix bug" + "write test for fix" = one entry)
- Ignore meta-conversation (greetings, off-topic chat)
- Focus on deliverables: what was built, fixed, reviewed, or designed
- 1–8 entries

Call `listTasks` with `project=STATUS.project` silently. Store as `TASKS`.

**Identify overdue tasks:** walk `TASKS` recursively; collect nodes where `exp_end_date` is non-empty and `exp_end_date < TARGET_DATE`. (Completed and Cancelled tasks are excluded at fetch time.)

**Auto-match and classify each entry:**

For each entry, search `TASKS` recursively by keyword overlap between the entry description and task subjects:

- **✓ resolved (existing task)** — exactly one task has clear keyword overlap. Set `entry.task = task.name`. If the matched task has a parent, set `entry.parent_task = task.parent_task`.
- **✓ resolved (new task, group known)** — zero tasks match AND exactly one group has clear keyword overlap with the description. Set `entry.parent_task = group.name`, leave `entry.task` unset. Set `entry.resolved = true`.
- **⚠ unresolved** — zero matches with no clear group fit, OR two or more tasks share similar keyword overlap (ambiguous). Set `entry.resolved = false`.

Entries that are ✓ resolved have `entry.resolved = true`.

**Cluster unresolved entries:**

After classifying all entries, group the ⚠ entries by shared topic keywords (e.g. entries mentioning "MCP", "plugin", "auth" form a cluster). Store each cluster as a list of entry indices. Assign each ⚠ entry a `cluster_id` (a short label like "mcp-work"); singletons get `cluster_id = null`.

Store synthesized entries as `ENTRIES`.
```

- [ ] **Step 2: Verify against spec §2**

Check:
- [ ] ✓ conditions: one clear match → task assigned; zero matches + one clear group → new task under group
- [ ] ⚠ conditions: zero with no group, or ambiguous
- [ ] `project` field added to entry shape
- [ ] `resolved` bool added to entry shape
- [ ] `cluster_id` field described

- [ ] **Step 3: Commit**

```bash
git add skills/timesheet/SKILL.md
git commit -m "feat: classify auto-match results as resolved/unresolved with clustering"
```

---

### Task 4: Rewrite SKILL.md Step 3 — New Draft Format + AskUserQuestion Resolution

**Files:**
- Modify: `skills/timesheet/SKILL.md` lines 99–156 (Step 3 section)

- [ ] **Step 1: Replace the entire Step 3 section**

In `skills/timesheet/SKILL.md`, find `## Step 3: Draft Review` and replace the entire section (through the line before `## Step 4`) with:

```markdown
## Step 3: Draft Review

If overdue tasks were identified in Step 2, list them before the draft:
> **Overdue tasks:** TASK-XXXX — subject (N days overdue), ...

**Display the draft:**

Each entry is two lines. Status marker at column 0 (`✓` resolved, `⚠` needs matching):

```
TARGET_DATE — Xh total
──────────────────────────────────────────────────────────────
✓ 1. [Xh] Description one
      Activity  ·  PROJ-XXXX / Group Name / TASK-XXXX

✓ 2. [Xh] Description two
      Deployment  ·  PROJ-XXXX / Infrastructure / new task

⚠ 3. [Xh] Description three
      Development  ·  PROJ-XXXX / ? needs matching
──────────────────────────────────────────────────────────────
N entries need matching — resolving below.
```

Rules:
- Project is **always shown** — never omitted, even on single-project days.
- Group shown if known; `/ ? needs matching` if not.
- Task field: `TASK-XXXX` (matched), `TASK-XXXX ⚠ Nd` (overdue matched), `new task` (will create), `? needs matching` (unresolved).
- Show the "N entries need matching" line only if N > 0. If all resolved, show `Submit, or let me know what to change.` instead.

**Interactive resolution (only if ⚠ entries exist):**

Process clusters before singletons.

**Cluster resolution** — for each cluster of 2+ ⚠ entries (same `cluster_id`):

Use `AskUserQuestion`:
- Question: `Entries {n1}, {n2}, ... seem related to {inferred topic} ({entry.project}). No matching group found — what should we do?`
- Options:
  1. `Create group "{suggested name}"` — set `entry.proposed_group` to the suggested name for all entries in the cluster; mark all resolved
  2. `Use existing group` — follow up with a second `AskUserQuestion` listing existing groups from `TASKS`; set `entry.parent_task` for all cluster entries; mark all resolved
  3. `No group (root-level tasks)` — clear `parent_task` and `proposed_group` on all cluster entries; mark all resolved
  4. `Split — handle each separately` — treat each cluster entry as a singleton below

**Per-entry resolution** — for singletons and entries split from clusters, in order:

**Q1 — Project** (skip if `entry.project` is already known and not flagged as off-topic):
Use `AskUserQuestion`:
- Question: `Entry N — "{description}" — which project?`
- Options: each item from `CONFIG._projects` (show `label`, value is `id`) + `Other (I'll type it)`
Set `entry.project` to the selected id.

**Q2 — Group** (skip if `entry.parent_task` or `entry.proposed_group` is already set):
Use `AskUserQuestion`:
- Question: `Entry N — "{description}" — which task group? ({entry.project})`
- Options: existing groups from `TASKS` (nodes where `is_group=1`) + `Create new group` + `No group (root-level task)`

If `Create new group` selected:
- Ask the user to name it via `AskUserQuestion` (free text).
- Set `entry.proposed_group` to the name.
- Immediately offer to pull in other ⚠ entries: use `AskUserQuestion` listing all remaining unresolved entry descriptions as a multi-select. For each entry selected, set `entry.proposed_group` to the same name and skip their Q2/Q3.

If an existing group selected: set `entry.parent_task = group.name`.
If `No group`: leave both unset; mark `entry.resolved = true`.

**Q3 — Task** (skip if `entry.task` is set, or if entry will create a new task under a known group):
Use `AskUserQuestion`:
- Question: `Entry N — "{description}" — assign to an existing task?`
- Options — overdue tasks first, then open tasks, then new:
  - Overdue: `TASK-XXXX — {subject} (⚠ Nd overdue)`
  - Open: `TASK-XXXX — {subject}`
  - Last option: `New task (create one under {group name or "root"})`

If an existing task selected: set `entry.task = task.name`. Mark `entry.resolved = true`.
If `New task`: leave `entry.task` unset. Mark `entry.resolved = true`.

**After all entries resolved:**

Re-render the full draft with `✓` on all entries:

```
TARGET_DATE — Xh total
──────────────────────────────────────────────────────────────
✓ 1. [Xh] Description one
      Activity  ·  PROJ-XXXX / Group Name / TASK-XXXX

✓ 2. [Xh] Description two
      Activity  ·  PROJ-XXXX / [new "Group Name"] / new task
──────────────────────────────────────────────────────────────
All resolved — submit, or let me know what to change.
```

**Conversational edits** (handle at any point):

- Edit description → update entry, re-render draft
- Delete entry → remove, recalculate hours, re-render draft
- Add entry → append, re-render draft
- Change activity → update `entry.activity_type`, re-render draft
- Reassign task → look up in `TASKS` recursively, assign, re-render draft
- Change project → set `entry.project`, re-fetch tasks if needed, re-run Q2/Q3 for that entry
- Redistribute hours → recalculate evenly, re-render draft
- Move to group → set `entry.parent_task`, clear `entry.proposed_group`, re-render draft
- Move to root → clear both `entry.parent_task` and `entry.proposed_group`, re-render draft
- "Submit" / "Looks good" / "Go ahead" → Step 4

**Hours mismatch:** if total ≠ `STATUS.work_hours` at approval, note it: "Total is Xh, default is Yh — proceed?" and wait.

**Empty entries:** if user tries to submit with no entries, ask them to add some first.
```

- [ ] **Step 2: Verify against spec §1 and §3**

Check:
- [ ] Two-line format, marker at column 0
- [ ] Project always shown
- [ ] All four task field states present in the rules
- [ ] Cluster: one AskUserQuestion, 4 options, handles all entries in cluster
- [ ] Per-entry Q1/Q2/Q3 skip conditions correct
- [ ] Q2 "create new group" triggers sibling pull-in offer
- [ ] Q3 overdue tasks appear first
- [ ] Post-resolution re-render shown
- [ ] Conversational edits complete

- [ ] **Step 3: Commit**

```bash
git add skills/timesheet/SKILL.md
git commit -m "feat: new two-line draft format with AskUserQuestion resolution flow"
```

---

### Task 5: Rewrite SKILL.md Step 4 — Dispatch to Submitter Agent

**Files:**
- Modify: `skills/timesheet/SKILL.md` lines 158–end (Step 4 section)

- [ ] **Step 1: Replace the entire Step 4 section**

In `skills/timesheet/SKILL.md`, find `## Step 4: Duplicate Check + Submit` and replace the entire section with:

```markdown
## Step 4: Submit

Call `checkExisting` with `date=TARGET_DATE` silently.

If `exists` is `true`: "A timesheet already exists for TARGET_DATE — submit anyway?" If no, return to Step 3.

Dispatch to the `timesheet-submitter` agent with this prompt (substitute actual values):

```
Submit timesheet for {TARGET_DATE}.

TARGET_DATE: {TARGET_DATE}
STATUS: {JSON — include username, project, work_hours}
ENTRIES: {JSON array — each entry with: description, hours, activity_type, project, task (if set), parent_task (if set), proposed_group (if set)}
```

Display the agent's output to the user verbatim as it arrives.

**If any MCP call returns `{"error": "auth_failed"}` at any step:** tell the user:
> Your ERPNext session has expired. Run `/plugin config erpnext-timesheet` to update your credentials, then re-run `/timesheet`.
```

- [ ] **Step 2: Verify against spec §4**

Check:
- [ ] `checkExisting` still called in the skill before dispatch (the agent also calls it — intentional double-check)
- [ ] Agent prompt passes TARGET_DATE, STATUS, ENTRIES as JSON with all required fields listed
- [ ] Auth failure handler still present
- [ ] Heading renamed from "Duplicate Check + Submit" to "Submit"

- [ ] **Step 3: Run full test suite to confirm no regressions**

```bash
cd /home/neox/Work/erpnext-timesheet
python -m pytest tests/ -q
```

Expected: `65 passed`

- [ ] **Step 4: Commit**

```bash
git add skills/timesheet/SKILL.md
git commit -m "feat: dispatch submission to timesheet-submitter agent"
```

---

### Task 6: Smoke Test

No automated tests cover SKILL.md or agent behavior. Verify manually after `/reload-plugins`.

- [ ] **Step 1: Reload plugins**

Run `/reload-plugins` in Claude Code. Confirm output shows `1 plugin MCP server` and agents count increased by 1.

- [ ] **Step 2: Verify draft format**

Run `/timesheet`. Confirm:
- [ ] Each entry is two lines with marker at column 0
- [ ] Project always appears on line 2
- [ ] Overdue matched tasks show `⚠ Nd` on line 2

- [ ] **Step 3: Verify AskUserQuestion fires for ⚠ entries**

If any entries are ⚠:
- [ ] Cluster question fires first for semantically similar entries (4 options)
- [ ] Per-entry Q2 (group) follows for singletons
- [ ] Q3 (task) shows overdue tasks at top
- [ ] Post-resolution draft re-renders with all ✓

- [ ] **Step 4: Verify submitter agent output**

After approving the draft:
- [ ] Agent outputs `Submitting timesheet for DATE...`
- [ ] One `- [x]` line per action
- [ ] Final `Done.` appears

- [ ] **Step 5: Push to remote**

```bash
git push origin master
```
