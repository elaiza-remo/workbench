"""Import commits from a local git repo by running `git log`.

The app runs on your own computer, so it can read your repos directly:
no GitHub token, works offline, and private repos are fine.
"""
import re
import subprocess
from datetime import datetime
from pathlib import Path

RECORD, FIELD = "\x1e", "\x1f"
LOG_FORMAT = f"{RECORD}%H{FIELD}%an{FIELD}%aI{FIELD}%B{FIELD}"
SHORTSTAT = re.compile(
    r"(\d+) files? changed(?:, (\d+) insertions?\(\+\))?(?:, (\d+) deletions?\(-\))?"
)


class GitError(Exception):
    pass


def resolve_repo(path_text):
    path = Path(path_text.strip()).expanduser()
    if not path.is_dir():
        raise GitError(f"Couldn't find the folder {path}. Check the repo folder on the project.")
    return path


def read_log(path_text, timeout=60):
    """Return every commit reachable from the repo's current branch, newest first."""
    path = resolve_repo(path_text)
    cmd = ["git", "-C", str(path), "log", f"--pretty=format:{LOG_FORMAT}", "--shortstat"]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, check=False,
        )
    except FileNotFoundError as e:
        raise GitError("git isn't installed, or isn't on your PATH.") from e
    except subprocess.TimeoutExpired as e:
        raise GitError("git took too long to respond.") from e

    if proc.returncode != 0:
        err = proc.stderr.strip()
        if "does not have any commits" in err:
            return []
        if "not a git repository" in err:
            raise GitError(f"{path} isn't a git repo. Point it at the folder that contains .git.")
        raise GitError(err.splitlines()[-1] if err else "git log failed.")

    return parse_log(proc.stdout)


def parse_log(output):
    commits = []
    for chunk in output.split(RECORD):
        parts = chunk.split(FIELD)
        if len(parts) < 5 or not parts[0].strip():
            continue
        sha, author, date, message = parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip()
        stat = SHORTSTAT.search(FIELD.join(parts[4:]))
        commits.append({
            "sha": sha,
            "author": author[:200],
            "committed_at": datetime.fromisoformat(date),
            "message": message or "(no message)",
            "files_changed": int(stat.group(1)) if stat else 0,
            "insertions": int(stat.group(2) or 0) if stat else 0,
            "deletions": int(stat.group(3) or 0) if stat else 0,
        })
    return commits


def _has_local_repo(project):
    if not project.repo_path:
        return False
    try:
        return resolve_repo(project.repo_path).joinpath(".git").exists()
    except GitError:
        return False


def source_for(project):
    """'local' if the repo folder exists on this machine, 'github' if there's a GitHub link, else None."""
    from .github import parse_repo

    if _has_local_repo(project):
        return "local"
    if parse_repo(project.repo_url):
        return "github"
    return None


def can_sync(project, user):
    """Whether to show the Import button. The demo account's commits are sample data."""
    from django.conf import settings

    if getattr(user, "username", None) == settings.DEMO_USERNAME:
        return False
    return source_for(project) is not None


def sync_project(project):
    """Import any commits not already saved. Returns (new_count, total_seen).

    Reads the local repo folder when it exists on this machine (running on your
    Mac); otherwise uses the GitHub API with the project's repo link (on Vercel).
    """
    from .github import GitHubError, fetch_commits
    from .models import Commit

    source = source_for(project)
    if source == "local":
        rows = read_log(project.repo_path)
    elif source == "github":
        latest = project.commits.order_by("-committed_at").values_list("committed_at", flat=True).first()
        try:
            rows = fetch_commits(project.repo_url, since=latest)
        except GitHubError as e:
            raise GitError(str(e)) from e
    elif project.repo_path:
        raise GitError(
            f"Couldn't find a git repo at {project.repo_path} on this computer. "
            "To import on the hosted site, set the project's GitHub repo link."
        )
    else:
        raise GitError("Set this project's GitHub repo link (or a local repo folder) first.")

    existing = set(project.commits.values_list("sha", flat=True))
    new = [Commit(project=project, **row) for row in rows if row["sha"] not in existing]
    Commit.objects.bulk_create(new, batch_size=500, ignore_conflicts=True)
    return len(new), len(rows)
