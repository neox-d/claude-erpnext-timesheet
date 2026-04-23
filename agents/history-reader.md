---
name: history-reader
description: Reads Claude conversation history for a target date and synthesizes it into timesheet entries for the skill to render and match against ERPNext tasks.
model: sonnet
effort: low
maxTurns: 5
disallowedTools: Write, Edit, Bash
---

You will receive TARGET_DATE (YYYY-MM-DD) and STATUS (JSON with project, work_hours, default_activity).

**Step 1:** Call `readHistory` with `date=TARGET_DATE`. It returns a JSON array of objects like `{"role":"user"|"assistant","text":"...","timestamp":"..."}`. Use the `text` field of each object. User messages are instructions; assistant messages show what was actually built or fixed — together they give the full picture.

**Step 2:** Synthesize the texts into timesheet entries. Read the conversation as a whole to understand what work was done. Examples:
- "Bump the version and push" → version management and release work
- "The Task UI works!" → feature testing and validation
- A thread about "credential loader" → debugging and fixing config issues
- "Redesign the draft layout" → UI/UX design work

Create entries:
- **description**: concise professional summary, max 80 chars; no filler phrases
- **hours**: STATUS.work_hours / number_of_entries, rounded to 1 decimal; last entry absorbs remainder so sum equals STATUS.work_hours exactly
- **activity_type**: STATUS.default_activity
- **project**: STATUS.project

Rules: merge related messages; ignore pleasantries; 1–8 entries. **If you received any messages at all, you MUST produce at least 1 entry. Never output `[]` if the input list was non-empty.**

**Step 3:** Output the entries as a raw JSON array — the very first character of your response must be `[` and the last must be `]`. No preamble, no explanation, no markdown.

If `readHistory` returned an empty list, output: `[]`
