#!/usr/bin/env python3
"""Bump or validate libs/contracts VERSION and CHANGELOG.md.

Usage examples:
Check-mode (CI or pre-commit): exit non-0 if contracts changed but VERSION/CHANGELOG not updated
python scripts/bump_contracts_version.py --check

# Apply a patch bump and prepend changelog entry
python scripts/bump_contracts_version.py --apply --strategy patch --changelog-entry "Auto bump CI"

This script is intentionally dependency-free (stdlib only).
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess  # nosec B404 - subprocess used safely with path resolution
import sys
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = PROJECT_ROOT / "libs" / "contracts" / "VERSION"
CHANGELOG_FILE = PROJECT_ROOT / "libs" / "contracts" / "CHANGELOG.md"

SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


# Resolve git executable (prefer full path to satisfy security checks)
GIT = shutil.which("git") or "git"


def _git_run(args: list[str], **kwargs) -> subprocess.CompletedProcess[bytes]:  # type: ignore[no-untyped-def]
    """Run a git subcommand using the resolved `GIT` path.

    Uses `PROJECT_ROOT` as the working directory. Marked `# nosec` because the
    arguments are controlled within this script (no shell execution).
    """
    return subprocess.run([GIT, *args], cwd=PROJECT_ROOT, **kwargs)  # nosec B603


def _git_check_output(args: list[str], **kwargs) -> bytes:  # type: ignore[no-untyped-def]
    """Return stdout bytes for the given git subcommand.

    Wrapper centralises cwd handling and is marked `# nosec` for bandit.
    """
    return subprocess.check_output([GIT, *args], cwd=PROJECT_ROOT, **kwargs)  # nosec B603


def read_version() -> str:
    if not VERSION_FILE.exists():
        raise SystemExit(f"Missing VERSION file: {VERSION_FILE}")
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def write_version(new: str) -> None:
    VERSION_FILE.write_text(new + "\n", encoding="utf-8")


def bump_semver(current: str, strategy: str) -> str:
    m = SEMVER_RE.match(current.strip())
    if not m:
        raise SystemExit(f"Unrecognized semver in VERSION: {current!r}")
    major, minor, patch = map(int, m.groups())
    if strategy == "patch":
        patch += 1
    elif strategy == "minor":
        minor += 1
        patch = 0
    elif strategy == "major":
        major += 1
        minor = 0
        patch = 0
    else:
        raise SystemExit(f"Unknown bump strategy: {strategy}")
    return f"{major}.{minor}.{patch}"


def _is_single_step_bump(old: str, new: str) -> bool:
    """Return True if `new` is a single semver step bump from `old`.

    Allowed single-step bumps:
    - patch: major/minor unchanged, patch +1
    - minor: major unchanged, minor +1, patch == 0
    - major: major +1, minor == 0, patch == 0
    """
    if not old or not new:
        return False
    mo = SEMVER_RE.match(old.strip())
    mn = SEMVER_RE.match(new.strip())
    if not mo or not mn:
        return False
    o_major, o_minor, o_patch = map(int, mo.groups())
    n_major, n_minor, n_patch = map(int, mn.groups())
    if n_major == o_major and n_minor == o_minor and n_patch == o_patch + 1:
        return True
    if n_major == o_major and n_minor == o_minor + 1 and n_patch == 0:
        return True
    return bool(n_major == o_major + 1 and n_minor == 0 and n_patch == 0)


def prepend_changelog(new_version: str, entry_text: str) -> None:
    today = date.today().isoformat()
    header = f"## [{new_version}] - {today}\n\n### Changed\n\n- {entry_text}\n\n"

    # Read existing changelog or use a default H1
    if CHANGELOG_FILE.exists():
        old = CHANGELOG_FILE.read_text(encoding="utf-8")
    else:
        old = "# Contracts Changelog\n\n"

    # Avoid inserting the same release twice
    if re.search(rf"^## \[{re.escape(new_version)}\]", old, flags=re.M):
        return

    # Normalize newlines and ensure trailing newline for robust splitting
    old = old.replace("\r\n", "\n")
    if not old.endswith("\n"):
        old = old + "\n"

    lines = old.split("\n")

    # Find first non-blank line
    first_non_blank = 0
    while first_non_blank < len(lines) and lines[first_non_blank].strip() == "":
        first_non_blank += 1

    # Find top-level H1 starting at first non-blank
    h1_index = None
    for i in range(first_non_blank, len(lines)):
        if re.match(r"^#\s+", lines[i]):
            h1_index = i
            break

    # If no H1 present, create a standard one and prepend header
    if h1_index is None:
        new_content = "# Contracts Changelog\n\n" + header + old
        CHANGELOG_FILE.write_text(new_content, encoding="utf-8")
        return

    # Find first release header ("## [") after the H1. If none, releases start at end.
    first_release_after_h1 = None
    for j in range(h1_index + 1, len(lines)):
        if re.match(r"^##\s+\[", lines[j]):
            first_release_after_h1 = j
            break
    if first_release_after_h1 is None:
        first_release_after_h1 = len(lines)

    # top_block is H1 and any intro text before the first release
    top_block = lines[h1_index:first_release_after_h1]
    releases_above = lines[:h1_index]
    releases_below = lines[first_release_after_h1:]

    # Rebuild file: top_block (H1 + intro), header, then existing releases (preserving order)
    new_lines: list[str] = []
    new_lines.extend(top_block)
    # ensure a single blank line before header
    if not new_lines or new_lines[-1].strip() != "":
        new_lines.append("")
    new_lines.extend(header.rstrip("\n").split("\n"))
    # single blank line after header
    new_lines.append("")
    # append releases that were above the H1 (they were pushed there by the old bug),
    # then the releases that followed the H1. This preserves newest-first ordering.
    if releases_above:
        new_lines.extend(releases_above)
    if releases_below:
        new_lines.extend(releases_below)

    new_content = "\n".join(new_lines)
    if not new_content.endswith("\n"):
        new_content += "\n"
    CHANGELOG_FILE.write_text(new_content, encoding="utf-8")


def git_has_origin_main() -> bool:
    try:
        _git_run(
            ["rev-parse", "--verify", "--quiet", "origin/main"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def get_changed_contract_files_via_merge_base() -> tuple[list[str], str]:
    merge_base = (
        _git_check_output(["merge-base", "HEAD", "origin/main"]).decode().strip()
    )
    out = _git_check_output(
        ["diff", "--name-only", f"{merge_base}...HEAD", "--", "libs/contracts"]
    ).decode()
    files = [line for line in out.splitlines() if line.strip()]
    return files, merge_base


def get_staged_changed_contract_files() -> list[str]:
    out = _git_check_output(
        ["diff", "--name-only", "--cached", "--", "libs/contracts"]
    ).decode()
    return [line for line in out.splitlines() if line.strip()]


def check_mode() -> int:
    """Return 0 if OK, non-zero if a contracts change is present without VERSION/CHANGELOG update.

    Behavior:
    - If there are staged changes (pre-commit / committing locally), validate against the staged
      files to ensure `libs/contracts/VERSION` or `libs/contracts/CHANGELOG.md` are staged.
    - Otherwise (no staged files), fall back to comparing committed changes relative to
      `origin/main` (merge-base) for CI runs.
    """
    try:
        # Prefer staged-file checks first (pre-commit / local commits)
        staged = get_staged_changed_contract_files()
        if staged:
            contracts_changed = any(f.endswith(".py") for f in staged)
            if not contracts_changed:
                print("No staged contracts python changes detected.")
                return 0
            staged_version = _git_check_output(
                [
                    "diff",
                    "--name-only",
                    "--cached",
                    "--",
                    "libs/contracts/VERSION",
                    "libs/contracts/CHANGELOG.md",
                ]
            ).decode()
            if not staged_version.strip():
                print(
                    "Contracts changed but libs/contracts/VERSION or CHANGELOG.md not staged/updated.",  # noqa: E501
                    file=sys.stderr,
                )
                return 2
            # Validate staged VERSION is a single-step semver bump from HEAD
            try:
                head_version = (
                    _git_check_output(["show", "HEAD:libs/contracts/VERSION"])
                    .decode()
                    .strip()
                )
            except subprocess.CalledProcessError:
                head_version = None
            try:
                staged_version_value = (
                    _git_check_output(["show", ":libs/contracts/VERSION"])
                    .decode()
                    .strip()
                )
            except subprocess.CalledProcessError:
                staged_version_value = None
            if (
                head_version
                and staged_version_value
                and not _is_single_step_bump(head_version, staged_version_value)
            ):
                print(
                    "libs/contracts/VERSION must be a single-step semver bump relative to HEAD (patch/minor/major).",  # noqa: E501
                    file=sys.stderr,
                )
                return 2
            print("Staged contracts and VERSION/CHANGELOG updates present.")
            return 0

        # No staged files: fall back to merge-base/origin/main path (CI)
        if git_has_origin_main():
            files, merge_base = get_changed_contract_files_via_merge_base()
            contracts_changed = any(f.endswith(".py") for f in files)
            if not contracts_changed:
                print("No contracts python changes detected relative to origin/main.")
                return 0
            version_changed_out = _git_check_output(
                [
                    "diff",
                    "--name-only",
                    f"{merge_base}...HEAD",
                    "--",
                    "libs/contracts/VERSION",
                    "libs/contracts/CHANGELOG.md",
                ]
            ).decode()
            version_changed = bool(version_changed_out.strip())
            if not version_changed:
                print(
                    "Contracts changed but libs/contracts/VERSION or CHANGELOG.md not updated.",
                    file=sys.stderr,
                )
                return 2
            # Validate committed VERSION is a single-step semver bump from merge_base -> HEAD
            try:
                prev_version = (
                    _git_check_output(["show", f"{merge_base}:libs/contracts/VERSION"])
                    .decode()
                    .strip()
                )
            except subprocess.CalledProcessError:
                prev_version = None
            try:
                new_version = (
                    _git_check_output(["show", "HEAD:libs/contracts/VERSION"])
                    .decode()
                    .strip()
                )
            except subprocess.CalledProcessError:
                new_version = None
            if (
                prev_version
                and new_version
                and not _is_single_step_bump(prev_version, new_version)
            ):
                print(
                    "libs/contracts/VERSION in the commit must be a single-step semver bump "
                    "relative to the merge-base.",
                    file=sys.stderr,
                )
                return 2
            print("Contracts and VERSION/CHANGELOG updates present.")
            return 0

        # Fallback: no origin/main and no staged files — nothing to validate
        print("No staged contracts python changes detected.")
        return 0
    except subprocess.CalledProcessError as exc:
        print(f"git command failed: {exc}", file=sys.stderr)
        return 3


def apply_bump(strategy: str, changelog_entry: str | None, force: bool = False) -> int:
    """Apply a semver bump and update CHANGELOG.
    Simplified policy: require both staged and committed `libs/contracts/*.py` changes
    to allow `--apply`. Use `--force` to override when a manual bump is intended.
    """
    try:
        staged = get_staged_changed_contract_files()
    except subprocess.CalledProcessError:
        staged = []

    staged_changed = any(f.endswith(".py") for f in staged)

    # Determine whether committed changes exist relative to origin/main (merge-base).
    committed_changed = False
    try:
        if git_has_origin_main():
            files, _ = get_changed_contract_files_via_merge_base()
            committed_changed = any(f.endswith(".py") for f in files)
        else:
            # No origin/main available: check the last commit for contract changes
            try:
                out = _git_check_output(
                    [
                        "diff",
                        "--name-only",
                        "HEAD^",
                        "HEAD",
                        "--",
                        "libs/contracts",
                    ]
                ).decode()
                files = [line for line in out.splitlines() if line.strip()]
                committed_changed = any(f.endswith(".py") for f in files)
            except subprocess.CalledProcessError:
                committed_changed = False
    except subprocess.CalledProcessError:
        committed_changed = False

    if not (staged_changed and committed_changed) and not force:
        msg = (
            "Require both staged and committed libs/contracts/*.py changes to apply bump; "
            "use --force to override."
        )
        print(msg, file=sys.stderr)
        return 2

    current = read_version()
    new = bump_semver(current, strategy)
    if new == current:
        print(f"Version unchanged: {current}")
        return 0
    write_version(new)
    entry = changelog_entry or "Automated bump from scripts/bump_contracts_version.py"
    prepend_changelog(new, entry)
    # Print NEW_VERSION for CI consumption
    print(f"NEW_VERSION={new}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--strategy", choices=("patch", "minor", "major"), default="patch")
    p.add_argument(
        "--check",
        action="store_true",
        help="Validate contract-change -> VERSION/CHANGELOG updates",
    )
    p.add_argument(
        "--apply", action="store_true", help="Apply bump to VERSION and CHANGELOG"
    )
    p.add_argument(
        "--changelog-entry", default=None, help="Custom changelog entry text"
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Force apply bump even when no contract .py changes are detected",
    )
    # Accept and ignore extra filenames passed by pre-commit
    p.add_argument("filenames", nargs="*", help=argparse.SUPPRESS)
    args = p.parse_args(argv)

    if args.check:
        return check_mode()

    if args.apply:
        return apply_bump(args.strategy, args.changelog_entry, args.force)

    p.print_usage()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
