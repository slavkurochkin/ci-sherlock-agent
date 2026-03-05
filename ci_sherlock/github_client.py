import difflib
import re
import httpx
from ci_sherlock.models import ChangedFile

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", re.MULTILINE)


def find_original_in_patch(patch: str | None, original: str | None) -> int | None:
    """
    Search a unified diff patch for `original` and return its new-file line number.
    Matches against context lines (space-prefixed) and added lines (+).
    Tries exact match first, then fuzzy (handles quote/semicolon differences from LLM).
    Returns None if not found.
    """
    if not patch or not original:
        return None
    target = original.strip()
    m = _HUNK_RE.search(patch)
    if not m:
        return None
    candidates: list[tuple[str, int]] = []
    line_num = int(m.group(1))
    for raw_line in patch[m.end():].splitlines():
        if raw_line.startswith("+"):
            candidates.append((raw_line[1:].strip(), line_num))
            line_num += 1
        elif raw_line.startswith(" "):
            candidates.append((raw_line[1:].strip(), line_num))
            line_num += 1
        # "-" lines don't advance new-file counter; empty lines are hunk artefacts
    # Exact match first
    for content, ln in candidates:
        if content == target:
            return ln
    # Fuzzy match — handles LLM quote style / semicolon differences
    contents = [c for c, _ in candidates]
    matches = difflib.get_close_matches(target, contents, n=1, cutoff=0.8)
    if matches:
        for content, ln in candidates:
            if content == matches[0]:
                return ln
    return None


def first_added_line(patch: str | None) -> int:
    """Return the file line number of the first added line in a unified diff patch."""
    if not patch:
        return 1
    m = _HUNK_RE.search(patch)
    if not m:
        return 1
    line_num = int(m.group(1))
    for raw_line in patch[m.end():].splitlines():
        if raw_line.startswith("+"):
            return line_num
        if raw_line.startswith(" "):   # context line — advances new-file counter
            line_num += 1
        # "-" lines are deletions — don't advance new-file line counter
        # empty lines (hunk boundary artefact) — skip
    return int(m.group(1))

GITHUB_API = "https://api.github.com"
COMMENT_MARKER = "<!-- ci-sherlock -->"


class GitHubClient:
    def __init__(self, token: str, repo: str) -> None:
        self._repo = repo
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def get_pr_files(self, pr_number: int) -> list[ChangedFile]:
        files: list[ChangedFile] = []
        page = 1
        while True:
            resp = httpx.get(
                f"{GITHUB_API}/repos/{self._repo}/pulls/{pr_number}/files",
                headers=self._headers,
                params={"per_page": 100, "page": page},
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            for f in batch:
                files.append(ChangedFile(
                    filename=f["filename"],
                    status=f["status"],
                    additions=f.get("additions", 0),
                    deletions=f.get("deletions", 0),
                    patch=f.get("patch"),
                ))
            page += 1
        return files

    def get_existing_comment(self, pr_number: int) -> int | None:
        """Return the ID of an existing CI Sherlock comment, or None."""
        page = 1
        while True:
            resp = httpx.get(
                f"{GITHUB_API}/repos/{self._repo}/issues/{pr_number}/comments",
                headers=self._headers,
                params={"per_page": 100, "page": page},
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            for comment in batch:
                if COMMENT_MARKER in comment.get("body", ""):
                    return comment["id"]
            page += 1
        return None

    def create_comment(self, pr_number: int, body: str) -> str:
        resp = httpx.post(
            f"{GITHUB_API}/repos/{self._repo}/issues/{pr_number}/comments",
            headers=self._headers,
            json={"body": body},
        )
        resp.raise_for_status()
        return resp.json()["html_url"]

    def update_comment(self, comment_id: int, body: str) -> str:
        resp = httpx.patch(
            f"{GITHUB_API}/repos/{self._repo}/issues/comments/{comment_id}",
            headers=self._headers,
            json={"body": body},
        )
        resp.raise_for_status()
        return resp.json()["html_url"]

    def create_check_run(
        self,
        head_sha: str,
        conclusion: str,
        title: str,
        summary: str,
        name: str = "CI Sherlock",
    ) -> None:
        """
        Post a GitHub Check Run with pass/fail status.
        Requires `checks: write` permission. Fails silently on 403.
        conclusion: "success" | "failure" | "neutral"
        """
        resp = httpx.post(
            f"{GITHUB_API}/repos/{self._repo}/check-runs",
            headers=self._headers,
            json={
                "name": name,
                "head_sha": head_sha,
                "status": "completed",
                "conclusion": conclusion,
                "output": {"title": title, "summary": summary},
            },
            timeout=15,
        )
        if resp.status_code == 403:
            return  # missing checks:write permission — non-fatal
        resp.raise_for_status()

    def create_pull_review(
        self,
        pr_number: int,
        commit_sha: str,
        comments: list[dict],
    ) -> None:
        """
        Post inline review comments on the PR diff.
        Each comment: {"path": str, "line": int, "body": str}
        Fails silently on 403 or 422 (bad position).
        """
        if not comments:
            return
        # Convert to GitHub's review comment format
        github_comments = [
            {"path": c["path"], "line": c["line"], "side": "RIGHT", "body": c["body"]}
            for c in comments
        ]
        resp = httpx.post(
            f"{GITHUB_API}/repos/{self._repo}/pulls/{pr_number}/reviews",
            headers=self._headers,
            json={
                "commit_id": commit_sha,
                "event": "COMMENT",
                "comments": github_comments,
            },
            timeout=15,
        )
        if resp.status_code in (403, 422):
            return  # missing permission or bad position — non-fatal
        resp.raise_for_status()
