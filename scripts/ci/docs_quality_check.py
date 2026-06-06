"""Quality checks for Markdown docs used in CI."""

from __future__ import annotations

import argparse
import re
import subprocess  # nosec B404
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

STRICT_MD_GLOBS = (
    "README.md",
    "docs/**/*.md",
    ".github/pull_request_template.md",
)

RELAXED_MD_GLOBS = (
    ".github/prompts/**/*.md",
    "learning_docs/**/*.md",
    "_archive/**/*.md",
    "CV.md",
)

LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
BOLD_HEADING_RE = re.compile(r"^\*\*[^*].*\*\*\s*$")
FENCE_RE = re.compile(r"^```([^\s`].*)?$")

CHECK_STRICT = "strict"
CHECK_RELAXED = "relaxed"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("ci", "precommit", "all"),
        default="ci",
        help="Select which markdown sets/check strictness are applied.",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Optional file list (used by pre-commit staged-file mode).",
    )
    return parser.parse_args()


def path_matches_any(path: Path, globs: tuple[str, ...]) -> bool:
    rel = path.relative_to(ROOT)
    return any(rel.match(pattern) for pattern in globs)


def classify_check_level(path: Path) -> str | None:
    if path_matches_any(path, STRICT_MD_GLOBS):
        return CHECK_STRICT
    if path_matches_any(path, RELAXED_MD_GLOBS):
        return CHECK_RELAXED
    return None


def get_staged_files_from_git() -> list[str]:
    result = subprocess.run(  # nosec
        ["git", "diff", "--name-only", "--cached"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def markdown_files(profile: str, file_args: list[str]) -> list[Path]:
    files: set[Path] = set()

    candidates = list(file_args)
    if profile == "precommit" and not candidates:
        candidates = get_staged_files_from_git()

    if candidates:
        for name in candidates:
            path = (ROOT / name).resolve()
            if path.is_file():
                if path.suffix.lower() != ".md":
                    continue
                files.add(path)
        return sorted(files)

    patterns = (
        STRICT_MD_GLOBS if profile == "ci" else STRICT_MD_GLOBS + RELAXED_MD_GLOBS
    )
    for pattern in patterns:
        for path in ROOT.glob(pattern):
            if path.is_file():
                files.add(path)
    return sorted(files)


def is_external_link(target: str) -> bool:
    return (
        target.startswith("http://")
        or target.startswith("https://")
        or target.startswith("mailto:")
        or target.startswith("#")
    )


def normalize_target(base: Path, target: str, root: Path) -> Path:
    no_anchor = target.split("#", 1)[0]
    # Root-relative paths: only .github/ and absolute paths / are repo-root-relative
    # Everything else (including ./ and ../) is relative to markdown file directory
    if no_anchor.startswith(".github/"):
        return (root / no_anchor).resolve()
    # Otherwise resolve relative to markdown file directory
    return (base / no_anchor).resolve()


def check_file(path: Path, check_level: str) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    rel_path = path.relative_to(ROOT)

    in_fence = False
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip("\n")

        if check_level == CHECK_STRICT and BOLD_HEADING_RE.match(line):
            errors.append(
                f"{rel_path}:{line_no}: bold-only heading detected (use markdown headings)."
            )

        if line.startswith("```"):
            if not in_fence:
                if check_level == CHECK_STRICT and (
                    not FENCE_RE.match(line) or line.strip() == "```"
                ):
                    errors.append(
                        f"{rel_path}:{line_no}: fenced code block missing language tag."
                    )
                in_fence = True
            else:
                in_fence = False

        if check_level != CHECK_STRICT:
            continue

        for match in LINK_RE.finditer(line):
            target = match.group(1).strip()
            if not target or is_external_link(target):
                continue
            if target.startswith("`"):
                continue

            resolved = normalize_target(path.parent, target, ROOT)
            if not resolved.exists():
                errors.append(
                    f"{rel_path}:{line_no}: broken local link target '{target}'."
                )

    if in_fence:
        errors.append(f"{rel_path}: unclosed fenced code block.")

    return errors


def main() -> int:
    args = parse_args()
    files = markdown_files(args.profile, args.files)
    if not files:
        print("No markdown files found for docs quality check.")
        return 0

    all_errors: list[str] = []
    for file_path in files:
        check_level = classify_check_level(file_path)
        if check_level is None:
            if args.profile == "ci":
                continue
            check_level = CHECK_RELAXED
        all_errors.extend(check_file(file_path, check_level))

    if all_errors:
        print("Docs quality check failed:")
        for err in all_errors:
            print(f"- {err}")
        return 1

    print(f"Docs quality check passed for {len(files)} markdown files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
