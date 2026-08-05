from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Callable, Sequence


CommandRunner = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]


class RestoreVerificationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RestoreVerificationResult:
    version: str
    commit: str
    bundle: Path
    restored_repository: Path
    validation_output: str


def default_runner(
    command: Sequence[str],
    working_directory: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=working_directory,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


class RecoveryRestoreVerifier:
    def __init__(
        self,
        source_repository: Path,
        *,
        runner: CommandRunner = default_runner,
    ) -> None:
        self._source_repository = source_repository.resolve()
        self._runner = runner

    def verify(
        self,
        package_directory: Path,
        *,
        workspace_root: Path | None = None,
        retain_workspace: bool = False,
    ) -> RestoreVerificationResult:
        package_directory = package_directory.expanduser().resolve()
        manifest_path = package_directory / "release-manifest.json"
        if not manifest_path.is_file():
            raise RestoreVerificationError("release-manifest.json is missing")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        version = str(manifest["version"])
        commit = str(manifest["commit"])
        bundle = package_directory / f"Jason-{version}.bundle"
        if not bundle.is_file():
            raise RestoreVerificationError(f"Git bundle is missing: {bundle}")

        if workspace_root is None:
            workspace = Path(tempfile.mkdtemp(prefix="jason-restore-"))
        else:
            workspace = workspace_root.expanduser().resolve()
            if workspace.exists():
                raise RestoreVerificationError(
                    f"Restore workspace already exists: {workspace}"
                )
            workspace.mkdir(parents=True)

        restored = workspace / "jason-restored"
        try:
            self._run_required(
                ("git", "clone", "--quiet", str(bundle), str(restored)),
                workspace,
            )
            self._run_required(("git", "checkout", "--quiet", commit), restored)
            actual_commit = self._run_required(
                ("git", "rev-parse", "HEAD"), restored
            ).stdout.strip()
            if actual_commit != commit:
                raise RestoreVerificationError(
                    f"Restored commit differs: expected {commit}, got {actual_commit}"
                )

            self._attach_validation_environments(restored)
            validation = self._run_required(
                (
                    str(self._validation_python()),
                    str(restored / "tools" / "validate_release.py"),
                ),
                restored,
            )

            return RestoreVerificationResult(
                version=version,
                commit=commit,
                bundle=bundle,
                restored_repository=restored,
                validation_output=validation.stdout or "",
            )
        finally:
            if not retain_workspace:
                shutil.rmtree(workspace, ignore_errors=True)

    def _validation_python(self) -> Path | str:
        candidate = self._source_repository / ".venv-test" / "bin" / "python"
        if candidate.is_file():
            return candidate
        return "python3"

    def _attach_validation_environments(self, restored: Path) -> None:
        exclude = restored / ".git" / "info" / "exclude"
        with exclude.open("a", encoding="utf-8") as handle:
            for name in (".venv-test", ".venv-docs"):
                source = self._source_repository / name
                if not source.is_dir():
                    continue
                (restored / name).symlink_to(source, target_is_directory=True)
                handle.write(f"/{name}\n")

    def _run_required(
        self,
        command: Sequence[str],
        working_directory: Path,
    ) -> subprocess.CompletedProcess[str]:
        completed = self._runner(command, working_directory)
        if completed.returncode != 0:
            raise RestoreVerificationError(
                "Command failed: "
                + " ".join(str(item) for item in command)
                + "\n"
                + (completed.stdout or "")
            )
        return completed
