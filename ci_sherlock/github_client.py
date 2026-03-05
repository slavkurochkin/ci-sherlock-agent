import httpx
from ci_sherlock.models import ChangedFile

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
