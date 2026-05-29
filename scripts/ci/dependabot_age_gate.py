#!/usr/bin/env python3
"""
Minimal dependabot PR age gate.

When a Dependabot PR is opened/synchronized/reopened, this script attempts to detect
the updated package and target version, queries PyPI for the release upload time,
and if the release is younger than 7 days the PR is commented and closed.

This is a best-effort guard designed to emulate the repo `uv` policy: don't install
packages that are younger than N days on PyPI.
"""

import datetime
import json
import os
import re
import sys

import requests


GITHUB_API = "https://api.github.com"
MIN_DAYS = 7
REQUEST_TIMEOUT = 15


def gh_headers(token: str):
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }


def parse_from_title(title: str) -> tuple[str, str] | None:
    # Dependabot pip PR titles are typically: "Bump fastapi from 0.136.0 to 0.136.1"
    m = re.match(
        r"Bump[ ]+(?P<name>[A-Za-z0-9_.\-]+)[ ]+from[ ]+(?P<old>[^ ]+)[ ]+to[ ]+(?P<new>[^ ]+)",
        title,
    )
    if m:
        return m.group("name"), m.group("new")
    return None


def find_in_files(
    owner: str, repo: str, pr_number: int, token: str
) -> tuple[str, str] | None:
    url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/files"
    headers = gh_headers(token)
    results = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    if results.status_code != 200:
        print("Failed to list PR files", results.status_code, results.text)
        return None
    for f in results.json():
        patch = f.get("patch") or ""
        # look for added lines that include a package + version
        for line in patch.splitlines():
            if not line.startswith("+"):
                continue
            # Best-effort parsing for common formats, avoid complex quoted regex
            line_str = line[1:].strip()  # remove leading '+' and surrounding whitespace
            for sep in ("==", "=", ":"):
                if sep not in line_str:
                    continue
                parts = re.split(r"\s*" + re.escape(sep) + r"\s*", line_str, maxsplit=1)
                if len(parts) != 2:
                    continue
                name = parts[0].strip().strip("\"'")
                ver_raw = parts[1].strip().strip(",")
                # strip surrounding quotes if present
                ver = ver_raw.strip("\"'")
                mv = re.match(r"([0-9a-zA-Z\.\-\+]+)", ver)
                if mv:
                    return name, mv.group(1)
    return None


def pypi_release_time(package: str, version: str) -> datetime.datetime | None:
    url = f"https://pypi.org/pypi/{package}/json"
    r = requests.get(url, timeout=REQUEST_TIMEOUT)
    if r.status_code != 200:
        print(f"PyPI lookup failed for {package}: {r.status_code}")
        return None
    data = r.json()
    releases = data.get("releases", {})
    if version not in releases:
        print(f"Version {version} not found in PyPI releases for {package}")
        return None
    files = releases[version]
    if not files:
        return None
    # pick earliest upload_time_iso_8601 if available
    times = []
    for f in files:
        t = f.get("upload_time_iso_8601") or f.get("upload_time")
        if not t:
            continue
        # ensure timezone-aware
        if t.endswith("Z"):
            t = t.replace("Z", "+00:00")
        try:
            dt = datetime.datetime.fromisoformat(t)
            times.append(dt)
        except ValueError:
            continue
    if not times:
        return None
    return min(times)


def comment_and_close(
    owner: str,
    repo: str,
    pr_number: int,
    token: str,
    package: str,
    version: str,
    age_days: float,
):
    issue_url = f"{GITHUB_API}/repos/{owner}/{repo}/issues/{pr_number}/comments"
    body = (
        f"Note: the requested release {package}=={version} is only {age_days:.1f} "
        f"days old and is within the repository's {MIN_DAYS}-day cooldown window.\n\n"
        f"This repository prefers waiting {MIN_DAYS} days before automatic adoption. "
        f"You can test the release locally (see README) and merge when you're satisfied."
    )
    r = requests.post(
        issue_url,
        headers=gh_headers(token),
        json={"body": body},
        timeout=REQUEST_TIMEOUT,
    )
    if r.status_code not in (200, 201):
        print("Failed to post comment", r.status_code, r.text)
    # Add an informative label instead of closing the PR so maintainers can test locally.
    label = "early-dependency"
    # Ensure label exists (create if necessary)
    labels_url = f"{GITHUB_API}/repos/{owner}/{repo}/labels"
    label_payload = {
        "name": label,
        "color": "f29513",
        "description": "Dependabot: release is under cooldown/maturation",
    }
    rlbl = requests.post(
        labels_url,
        headers=gh_headers(token),
        json=label_payload,
        timeout=REQUEST_TIMEOUT,
    )
    if rlbl.status_code not in (200, 201, 422):
        print("Failed to ensure label exists", rlbl.status_code, rlbl.text)
    # Add the label to the PR (issues endpoint)
    add_label_url = f"{GITHUB_API}/repos/{owner}/{repo}/issues/{pr_number}/labels"
    rlab = requests.post(
        add_label_url,
        headers=gh_headers(token),
        json={"labels": [label]},
        timeout=REQUEST_TIMEOUT,
    )
    if rlab.status_code not in (200, 201):
        print("Failed to add label to PR", rlab.status_code, rlab.text)


def main():
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    token = os.environ.get("GITHUB_TOKEN")
    if not event_path or not os.path.exists(event_path):
        print("Missing GITHUB_EVENT_PATH")
        sys.exit(0)
    with open(event_path, encoding="utf-8") as fh:
        ev = json.load(fh)

    pr = ev.get("pull_request")
    repo = ev.get("repository", {}).get("name")
    owner = ev.get("repository", {}).get("owner", {}).get("login")
    if not pr or not repo or not owner:
        print("No PR or repo info in event payload; exiting")
        sys.exit(0)

    pr_number = pr.get("number")
    author = pr.get("user", {}).get("login", "")
    title = pr.get("title", "")

    # Only act on Dependabot authored PRs
    if not author.lower().startswith("dependabot"):
        print(f"PR author is {author}; skipping (not Dependabot)")
        sys.exit(0)

    found = parse_from_title(title)
    if not found:
        found = find_in_files(owner, repo, pr_number, token)  # type: ignore

    if not found:
        print("Could not detect package+version from PR title/files; skipping")
        sys.exit(0)

    package, version = found
    print(f"Detected package {package} new version {version}")

    release_time = pypi_release_time(package, version)
    if not release_time:
        print("Could not determine release time from PyPI; skipping")
        sys.exit(0)

    now = datetime.datetime.now(datetime.UTC)
    if release_time.tzinfo is None:
        release_time = release_time.replace(tzinfo=datetime.UTC)
    age = (now - release_time).total_seconds() / 86400.0
    print(f"Release age (days): {age:.2f}")

    if age < MIN_DAYS:
        print(
            f"Release too new ({age:.2f} days) — commenting and labeling PR {pr_number}"
        )
        comment_and_close(owner, repo, pr_number, token, package, version, age)  # type: ignore
        sys.exit(0)

    print("Release is old enough; no action taken.")


if __name__ == "__main__":
    main()
