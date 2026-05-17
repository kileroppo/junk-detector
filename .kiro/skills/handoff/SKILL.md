# Skill: Handoff

## Description
Write a handoff document summarising the current conversation so a fresh agent can continue the work. Save it to a path produced by `mktemp -t handoff-XXXXXX.md` (read the file before you write to it).

Suggest the skills to be used, if any, by the next session.

Do not duplicate content already captured in other artifacts (PRDs, plans, ADRs, issues, commits, diffs). Reference them by path or URL instead.

If the user passed arguments, treat them as a description of what the next session will focus on and tailor the doc accordingly.

## Steps

1. Read the existing HANDOFF.md (if any) at the project root to understand what's already documented.
2. Summarise:
   - What was built this session (reference PRs/commits, not code)
   - Current project state (working? broken? blocked?)
   - Known issues / bugs discovered
   - What the next session should focus on
3. Generate a temp file path with `mktemp -t handoff-XXXXXX.md`
4. Read the generated file (it will be empty) to confirm the path
5. Write the handoff document to that path
6. Also update `HANDOFF.md` in the project root with the latest state
7. Suggest which skills (from `.kiro/skills/`) the next agent should activate

## Output Format

The handoff document should include:
- `## What was built` — bullet points referencing PRs/commits
- `## Current state` — is it working? any blockers?
- `## Known issues` — bugs, incomplete work
- `## Next session focus` — what to do next (from user args if provided)
- `## Suggested skills` — table of scenario → skill name
- `## Environment notes` — setup quirks, dependencies, etc.
