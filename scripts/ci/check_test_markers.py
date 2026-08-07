"""Reject service tests that cannot be selected by lane and capability profile."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = PROJECT_ROOT / "services" / "ingestor" / "tests"
CAPABILITY_MARKERS = (
    "core",
    "capability_rls",
    "capability_broker",
    "capability_ai",
    "full_optional",
)


def _has_any_marker(source: str, markers: tuple[str, ...]) -> bool:
    return any(f"pytest.mark.{marker}" in source for marker in markers)


def _capability_markers(source: str) -> list[str]:
    return [
        marker for marker in CAPABILITY_MARKERS if f"pytest.mark.{marker}" in source
    ]


def main() -> None:
    failures: list[str] = []
    lane_markers = {
        "unit": ("unit", "integration"),
        "integration": ("integration", "e2e", "demo"),
    }
    for lane, accepted_markers in lane_markers.items():
        for path in sorted((TEST_ROOT / lane).rglob("test_*.py")):
            source = path.read_text()
            if not _has_any_marker(source, accepted_markers):
                failures.append(path.relative_to(PROJECT_ROOT).as_posix())
                continue
            profiles = _capability_markers(source)
            if len(profiles) > 1:
                failures.append(
                    f"{path.relative_to(PROJECT_ROOT).as_posix()} "
                    f"(multiple capability profiles: {', '.join(profiles)})"
                )

    if failures:
        joined = "\n".join(f"- {path}" for path in failures)
        raise SystemExit(
            "Service tests must declare one selectable lane and at most one "
            f"capability profile:\n{joined}"
        )


if __name__ == "__main__":
    main()
