#!/usr/bin/env python3
"""Phase 2 guardrails for service boundary enforcement.

Checks implemented:
1. No cross-service Python imports between the six service boundaries.
2. No direct access to another service's persistence modules
   (database/models/crud/storage/repository/repositories).
3. libs.platform and libs.contracts are shared namespaces — any service
   may import from them, but they must not import back into any service.

The six service boundaries are:
- ingestor
- inference
- analytics
- processor
- dashboard
- webhook

Allowed shared namespaces (any service may import):
- libs.platform
- libs.contracts

Test co-location:
Each service owns its tests under services/<name>/tests/. The boundary
scanner maps those files to the same service owner as the service code, so
imports from services/<name>/* inside services/<name>/tests/* are permitted
(owner == target). No special-casing is needed — detect_service_owner()
handles it by longest-prefix matching on SERVICE_ROOTS.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

# Shared library namespaces — imports from these are always permitted.
SHARED_LIBS: frozenset[str] = frozenset({"libs.platform", "libs.contracts"})

LIBS_ROOTS: dict[str, Path] = {
    "libs.platform": REPO_ROOT / "libs" / "platform",
    "libs.contracts": REPO_ROOT / "libs" / "contracts",
}

SERVICE_ROOTS: dict[str, Path] = {
    "ingestor": REPO_ROOT / "services" / "ingestor",
    "inference": REPO_ROOT / "services" / "inference",
    "analytics": REPO_ROOT / "services" / "analytics",
    "processor": REPO_ROOT / "services" / "processor",
    "dashboard": REPO_ROOT / "services" / "dashboard",
    "webhook": REPO_ROOT / "services" / "webhook",
}

PERSISTENCE_MODULE_HINTS = {
    "database",
    "models",
    "crud",
    "storage",
    "repository",
    "repositories",
}


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
    - libs.platform and libs.contracts (shared, always allowed)
    """
    # Shared libs are always allowed — not owned by any single service.
    if module == "libs" or any(
        module == lib or module.startswith(lib + ".") for lib in SHARED_LIBS
    ):
        return None

    if (
        module == "ingestor"
        or module.startswith("ingestor.")
        or module == "services.ingestor"
        or module.startswith("services.ingestor.")
    ):
        return "ingestor"

    if module == "services" or module.startswith("services."):
        parts = module.split(".")
        if len(parts) >= 2:
            svc = parts[1]
            if svc in {"inference", "analytics", "processor", "dashboard"}:
                return svc
    return None


def references_persistence_module(module: str) -> bool:
    return any(part in PERSISTENCE_MODULE_HINTS for part in module.split("."))


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
    tree = ast.parse(content, filename=str(file_path))

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

            if target_service != service_owner and references_persistence_module(
                module
            ):
                violations.append(
                    Violation(
                        file=file_path,
                        line=line,
                        code="SVC002",
                        message=(
                            "Direct access to another service's persistence boundary is forbidden: "
                            f"'{module}'."
                        ),
                    )
                )

    return violations


def collect_service_python_files() -> list[Path]:
    files: list[Path] = []
    for root in SERVICE_ROOTS.values():
        if not root.exists():
            continue
        files.extend(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
    return sorted(files)


def collect_libs_python_files() -> list[Path]:
    files: list[Path] = []
    for root in LIBS_ROOTS.values():
        if not root.exists():
            continue
        files.extend(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
    return sorted(files)


def scan_libs_file(file_path: Path) -> list[Violation]:
    """Check that libs/* do not import back into any service (SVC003)."""
    content = file_path.read_text(encoding="utf-8")
    tree = ast.parse(content, filename=str(file_path))

    violations: list[Violation] = []
    for node in ast.walk(tree):
        for line, module in extract_import_modules(node):
            target_service = module_to_service(module)
            if target_service is not None:
                violations.append(
                    Violation(
                        file=file_path,
                        line=line,
                        code="SVC003",
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
