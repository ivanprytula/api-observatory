#!/usr/bin/env python3
"""Guardrails for service boundary enforcement.

Checks implemented:
1. No cross-service Python imports between workspace service boundaries.
2. Python modules under libs/ are shared namespaces — services may import
   them, but shared libraries must not import back into a service.

Test co-location:
Each service owns its tests under services/<name>/tests/. The boundary
scanner maps those files to the same service owner as the service code, so
imports from services/<name>/* inside services/<name>/tests/* are permitted
(owner == target). No special-casing is needed — detect_service_owner()
handles it by matching the owning workspace service root.
"""

from __future__ import annotations

import ast
import tomllib
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

EXCLUDED_DIRS = frozenset(
    {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache", "build", "dist"}
)


def workspace_service_roots() -> dict[str, Path]:
    """Load service directories from the root uv workspace declaration."""
    with (REPO_ROOT / "pyproject.toml").open("rb") as stream:
        manifest = tomllib.load(stream)

    members = manifest["tool"]["uv"]["workspace"]["members"]
    roots: dict[str, Path] = {}
    for member in members:
        path = REPO_ROOT / member
        if path.parent.name != "services":
            continue
        roots[path.name] = path
    return roots


SERVICE_ROOTS = workspace_service_roots()


@dataclass
class Violation:
    file: Path
    line: int
    code: str
    message: str


def detect_service_owner(file_path: Path) -> str | None:
    for service, root in SERVICE_ROOTS.items():
        try:
            file_path.relative_to(root)
            return service
        except ValueError:
            continue
    return None


def module_to_service(module: str) -> str | None:
    """Return the owning service name for a module string, or None.

    Returns None for:
    - stdlib / third-party modules
    - any module under libs (shared, always allowed)
    """
    if module == "libs" or module.startswith("libs."):
        return None

    if module == "services":
        return None
    if module.startswith("services."):
        parts = module.split(".")
        if len(parts) >= 2 and parts[1] in SERVICE_ROOTS:
            return parts[1]

    # Keep the historical top-level ingestor import form supported while the
    # service is still rooted at services/ingestor.
    for service in SERVICE_ROOTS:
        if module == service or module.startswith(service + "."):
            return service
    return None


def extract_import_modules(node: ast.AST) -> list[tuple[int, str]]:
    modules: list[tuple[int, str]] = []

    if isinstance(node, ast.Import):
        for alias in node.names:
            modules.append((node.lineno, alias.name))

    if isinstance(node, ast.ImportFrom):
        if node.level and node.level > 0:
            return modules
        if node.module:
            modules.append((node.lineno, node.module))

    return modules


def scan_file(file_path: Path) -> list[Violation]:
    service_owner = detect_service_owner(file_path)
    if service_owner is None:
        return []

    content = file_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(content, filename=str(file_path))
    except SyntaxError as error:
        return [
            Violation(
                file=file_path,
                line=error.lineno or 1,
                code="SVC000",
                message=f"Python syntax error: {error.msg}",
            )
        ]

    violations: list[Violation] = []

    for node in ast.walk(tree):
        for line, module in extract_import_modules(node):
            target_service = module_to_service(module)
            if not target_service:
                continue

            if target_service != service_owner:
                violations.append(
                    Violation(
                        file=file_path,
                        line=line,
                        code="SVC001",
                        message=(
                            f"Cross-service import is forbidden: '{module}' "
                            f"from service '{service_owner}' to '{target_service}'."
                        ),
                    )
                )

    return violations


def collect_service_python_files() -> list[Path]:
    files: list[Path] = []
    for root in SERVICE_ROOTS.values():
        if not root.exists():
            continue
        files.extend(
            p for p in root.rglob("*.py") if not EXCLUDED_DIRS.intersection(p.parts)
        )
    return sorted(files)


def collect_libs_python_files() -> list[Path]:
    libs_root = REPO_ROOT / "libs"
    if not libs_root.exists():
        return []
    return sorted(
        p for p in libs_root.rglob("*.py") if not EXCLUDED_DIRS.intersection(p.parts)
    )


def scan_libs_file(file_path: Path) -> list[Violation]:
    """Check that shared libs do not import back into any service (SVC002)."""
    content = file_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(content, filename=str(file_path))
    except SyntaxError as error:
        return [
            Violation(
                file=file_path,
                line=error.lineno or 1,
                code="SVC000",
                message=f"Python syntax error: {error.msg}",
            )
        ]

    violations: list[Violation] = []
    for node in ast.walk(tree):
        for line, module in extract_import_modules(node):
            target_service = module_to_service(module)
            if target_service is not None:
                violations.append(
                    Violation(
                        file=file_path,
                        line=line,
                        code="SVC002",
                        message=(
                            f"libs must not import from services: '{module}' "
                            f"(target: '{target_service}')."
                        ),
                    )
                )
    return violations


def main() -> int:
    violations: list[Violation] = []

    for file_path in collect_service_python_files():
        violations.extend(scan_file(file_path))

    for file_path in collect_libs_python_files():
        violations.extend(scan_libs_file(file_path))

    if not violations:
        print("Service boundary guardrails passed (phase 2).")
        return 0

    print("Service boundary guardrails failed:")
    for violation in violations:
        rel_path = violation.file.relative_to(REPO_ROOT)
        print(f"- {rel_path}:{violation.line} [{violation.code}] {violation.message}")

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
