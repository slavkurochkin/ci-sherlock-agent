# Proposed Fixes — Human-in-the-Loop Repair

CI Sherlock can propose code fixes for failures it detects. A human reviews and accepts or declines. Two options exist; Option A is implemented.

---

## Option A — GitHub Suggested Changes (implemented)

When CI Sherlock identifies a failure with high confidence (> 0.7) and a `direct_match` correlation, the LLM also generates a one-to-five-line replacement. This is posted as a GitHub **suggested change** on the PR diff.

### How it works

1. The LLM returns three extra fields alongside `root_cause`:
   - `suggested_fix` — replacement lines (no surrounding context, no diff markers)
   - `suggested_fix_file` — must be one of the PR's changed files
   - `suggested_fix_original` — the exact original line(s) being replaced

2. CI Sherlock finds the line in the patch where `suggested_fix_original` appears.

3. It posts an inline PR review comment on that line using the `\`\`\`suggestion` block syntax:

   ````markdown
   **CI Sherlock proposed fix** — test `should submit form` failed here.

   ```suggestion
   await page.getByRole('button', { name: 'Submit' }).click();
   ```
   ````

4. GitHub renders this as a diff with a **"Commit suggestion"** button.
   - Click **Commit suggestion** → the fix is committed to the branch. ✅
   - Leave or dismiss the comment → fix is declined. ❌

5. The same fix is also shown in the main PR comment as a plain diff for visibility.

### Constraints

- The fix must target a file already in the PR diff. GitHub can only render suggestions on lines visible in the diff.
- Best suited for small, targeted changes (selector renames, API renames, single-line logic errors).
- The LLM is conservative: if it cannot produce a reliable fix, all three fields are null and no suggestion is posted.

### Configuration

No configuration required. The behaviour is automatic when:
- `OPENAI_API_KEY` is set
- A `direct_match` correlation is found
- LLM confidence exceeds 0.7

---

## Option B — Draft PR (not yet implemented)

For fixes that span multiple files, or target files not in the PR diff (e.g., updating a test file while the source file changed), the Draft PR approach is more appropriate.

### Proposed design

1. **Trigger:** same as Option A — high confidence, but fix spans > 1 file or fix file is not in the diff.

2. **Branch creation:** CI Sherlock calls the [GitHub Contents API](https://docs.github.com/en/rest/repos/contents) to create a new branch `sherlock/fix-pr-{pr_number}-{run_id}` based on the PR's head SHA.

3. **File patching:** For each file in the fix, the LLM returns a full replacement (or a unified diff). CI Sherlock applies it via `PUT /repos/{owner}/{repo}/contents/{path}` (base64-encoded content + commit message).

4. **Draft PR:** `POST /repos/{owner}/{repo}/pulls` with `draft: true`, targeting the original PR's base branch, or the PR's head branch if fixing the PR's own code.

5. **Link in comment:** The main PR comment is updated with:
   ```
   🔧 Proposed fix: #456 (draft PR) — merge to apply · close to decline
   ```

6. **Cleanup:** If the draft PR is closed without merging, a GitHub Actions workflow on `pull_request: [closed]` can delete the `sherlock/fix-*` branch automatically.

### Why not implemented yet

- Requires the LLM to generate full-file diffs reliably, which needs evals before shipping.
- Branch + commit management adds surface area that can go wrong (merge conflicts, invalid patches).
- Option A covers the majority of actionable cases (single-line renames, selector changes) without this complexity.
- Good candidate for a future sprint once Option A has been validated in production.

### Permissions required (for future implementation)

Add to the GitHub Actions workflow:

```yaml
permissions:
  pull-requests: write
  contents: write   # needed to create branches and commit files
  checks: write
```

---

## Decision matrix

| Situation | Option |
|---|---|
| Single-line fix in a changed file | **A** — Suggested Change |
| Multi-line fix in a changed file | **A** — multi-line suggestion block |
| Fix is in a file NOT changed by the PR | **B** — Draft PR |
| Fix spans multiple files | **B** — Draft PR |
| LLM confidence < 0.7 | Neither — post root cause only |
