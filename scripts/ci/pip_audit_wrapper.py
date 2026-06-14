"""
pip-audit wrapper for pre-commit (Python >= 3.12).

Runs `pip-audit -r requirements-audit.txt --no-deps`. If pip cannot resolve the
requirements (ResolutionImpossible / Cannot install), falls back to auditing only
top-level dependencies declared in `pyproject.toml` (PEP 621 or Poetry sections).

This script requires Python 3.12+ and uses modern typing (PEP 585+).
"""

import contextlib
import re
import subprocess  # nosec B404
import sys
import tempfile
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def generate_requirements(path: Path) -> Path:
    if path.exists():
        return path
    cmd = [
        "uv",
        "export",
        "--frozen",
        "--all-groups",
        "--no-hashes",
        "--format",
        "requirements-txt",
    ]
    try:
        out = subprocess.check_output(  # nosec B603
            cmd, cwd=ROOT, text=True, stderr=subprocess.STDOUT
        )
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(f"ERROR: failed to run {' '.join(cmd)}: {exc}\n")
        sys.exit(2)
    path.write_text(out)
    return path


def run_pip_audit(req_path: Path) -> tuple[int, str]:
    proc = subprocess.run(  # nosec
        ["pip-audit", "-r", str(req_path), "--no-deps"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def get_top_level_packages() -> set[str]:
    pyproject = ROOT / "pyproject.toml"
    packages: set[str] = set()
    if not pyproject.exists():
        return packages
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except Exception:
        return packages
    proj = data.get("project")
    if isinstance(proj, dict):
        deps = proj.get("dependencies", []) or []
        for item in deps:
            if isinstance(item, str):
                m = re.match(r"^\s*([A-Za-z0-9_.+\-]+)", item)
                if m:
                    packages.add(m.group(1).lower())
    tool = data.get("tool", {})
    poetry = tool.get("poetry") if isinstance(tool, dict) else None
    if isinstance(poetry, dict):
        deps = poetry.get("dependencies", {}) or {}
        for k in deps:
            if k != "python":
                packages.add(k.lower())
    return packages


def filter_requirements_for_top_level(
    req_path: Path, top_names: set[str]
) -> Path | None:
    text = req_path.read_text(encoding="utf-8")
    out_lines: list[str] = []
    re_req = re.compile(r"^\s*([A-Za-z0-9_.+\-]+)==([^\s;]+)")
    for line in text.splitlines():
        m = re_req.match(line)
        if m and m.group(1).lower() in top_names:
            out_lines.append(line)
    if not out_lines:
        return None
    fd, tmp_path = tempfile.mkstemp(
        prefix="reqs-top-", suffix=".txt", dir=str(Path.cwd())
    )
    Path(tmp_path).write_text("\n".join(out_lines) + "\n")
    return Path(tmp_path)


def main() -> None:
    req_file = ROOT / "requirements-audit.txt"
    req_file = generate_requirements(req_file)

    rc, out = run_pip_audit(req_file)
    sys.stderr.write(out)
    if rc == 0:
        print("pip-audit: OK", file=sys.stderr)
        sys.exit(0)

    if "ResolutionImpossible" in out or "Cannot install" in out:
        sys.stderr.write(
            "pip-audit: dependency resolution failed; falling back to top-level dependencies\n"
        )
        top = get_top_level_packages()
        if not top:
            sys.stderr.write(
                "ERROR: no top-level dependencies found in pyproject.toml; cannot fallback\n"
            )
            sys.exit(2)
        filtered = filter_requirements_for_top_level(req_file, top)
        if not filtered:
            sys.stderr.write("ERROR: filtered requirements is empty; cannot fallback\n")
            sys.exit(2)
        try:
            rc2, out2 = run_pip_audit(filtered)
            sys.stderr.write(out2)
            sys.exit(rc2)
        finally:
            with contextlib.suppress(Exception):
                filtered.unlink()

    sys.stderr.write("pip-audit failed\n")
    sys.exit(rc)


if __name__ == "__main__":
    main()
