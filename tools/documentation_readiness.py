from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


class DocumentationReadinessError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DocumentationReadinessResult:
    version: str
    release_name: str
    status: str
    record_path: Path


class DocumentationReadinessGate:
    """Require an approved release record before release artifacts are created."""

    _FIELD_PATTERN = re.compile(
        r"^\*\*(?P<name>[^*]+):\*\*\s*(?P<value>.+?)\s*$",
        re.MULTILINE,
    )

    def __init__(self, repository_root: Path) -> None:
        self._repository_root = repository_root.resolve()

    def verify(
        self,
        version: str,
        *,
        release_name: str,
    ) -> DocumentationReadinessResult:
        normalized_version = version if version.startswith("v") else f"v{version}"
        expected_version = normalized_version.removeprefix("v")
        expected_name = release_name.strip()
        if not expected_name:
            raise DocumentationReadinessError("Release name must not be empty.")

        matches: list[DocumentationReadinessResult] = []
        milestone_root = self._repository_root / "docs" / "milestones"
        for record_path in sorted(milestone_root.glob("*.md")):
            content = record_path.read_text(encoding="utf-8")
            fields = {
                match.group("name").strip().lower(): match.group("value").strip()
                for match in self._FIELD_PATTERN.finditer(content)
            }
            if fields.get("version") != expected_version:
                continue
            if fields.get("release name") != expected_name:
                continue
            status = fields.get("status", "")
            if status.lower() not in {"complete", "approved"}:
                raise DocumentationReadinessError(
                    f"Release record status must be Complete or Approved: {record_path}"
                )
            relative_path = record_path.relative_to(self._repository_root)
            self._verify_navigation(relative_path)
            matches.append(
                DocumentationReadinessResult(
                    version=normalized_version,
                    release_name=expected_name,
                    status=status,
                    record_path=relative_path,
                )
            )

        if not matches:
            raise DocumentationReadinessError(
                "No approved milestone record matches release version "
                f"{normalized_version} and release name {expected_name!r}."
            )
        if len(matches) > 1:
            raise DocumentationReadinessError(
                f"Multiple release records match {normalized_version}: "
                + ", ".join(str(item.record_path) for item in matches)
            )
        return matches[0]

    def _verify_navigation(self, relative_path: Path) -> None:
        navigation = self._repository_root / "mkdocs.yml"
        if not navigation.is_file():
            raise DocumentationReadinessError("mkdocs.yml is missing.")
        content = navigation.read_text(encoding="utf-8")
        nav_path = relative_path.as_posix().removeprefix("docs/")
        if nav_path not in content:
            raise DocumentationReadinessError(
                f"Release record is not included in MkDocs navigation: {relative_path}"
            )
