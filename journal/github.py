"""Import commits through the GitHub REST API.

Used when the app can't see the repo on disk (e.g. when it's hosted on Vercel).
Public repos work without a token; set GITHUB_TOKEN for private repos and a
much higher rate limit (5,000 requests/hour instead of 60).
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from django.conf import settings

API = "https://api.github.com"
PER_PAGE = 100
MAX_PAGES = 10  # up to 1,000 commits per import; run it again to continue further back

_REPO_URL = re.compile(r"github\.com[/:]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", re.I)


class GitHubError(Exception):
    pass


def parse_repo(url):
    """'https://github.com/elaiza-remo/Shelf' -> ('elaiza-remo', 'Shelf'), else None."""
    match = _REPO_URL.search((url or "").strip())
    return (match.group(1), match.group(2)) if match else None


def _get(path, params, timeout=15):
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "workbench-app",
    }
    if settings.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise GitHubError(
                "GitHub couldn't find that repo. Check the repo link, or set GITHUB_TOKEN if it's private."
            ) from e
        if e.code in (403, 429):
            raise GitHubError("GitHub's rate limit was hit. Set GITHUB_TOKEN, or try again in an hour.") from e
        if e.code == 409:
            return []  # empty repository
        raise GitHubError(f"GitHub returned an error ({e.code}).") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise GitHubError("Couldn't reach GitHub.") from e


def fetch_commits(repo_url, since=None):
    """Commits on the default branch, newest first, in the same shape as gitsync.read_log."""
    repo = parse_repo(repo_url)
    if repo is None:
        raise GitHubError("Set the project's repo link to a GitHub URL, like https://github.com/you/project.")
    owner, name = repo
    params = {"per_page": PER_PAGE}
    if since is not None:
        params["since"] = since.isoformat()

    rows = []
    for page in range(1, MAX_PAGES + 1):
        batch = _get(f"/repos/{owner}/{name}/commits", {**params, "page": page})
        for item in batch:
            commit = item.get("commit") or {}
            author = commit.get("author") or {}
            date = author.get("date") or (commit.get("committer") or {}).get("date")
            if not item.get("sha") or not date:
                continue
            rows.append({
                "sha": item["sha"],
                "author": (author.get("name") or (item.get("author") or {}).get("login") or "")[:200],
                "committed_at": datetime.fromisoformat(date.replace("Z", "+00:00")),
                "message": (commit.get("message") or "").strip() or "(no message)",
                # The list endpoint doesn't include line counts; those need one extra call per commit.
                "files_changed": 0,
                "insertions": 0,
                "deletions": 0,
            })
        if len(batch) < PER_PAGE:
            break
    return rows
