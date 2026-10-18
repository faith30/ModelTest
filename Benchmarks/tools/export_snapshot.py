#!/usr/bin/env python3
"""Export tracked benchmark files into a new repository with one root commit."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


LFS_HEADER = b"version https://git-lfs.github.com/spec/v1"


class ExportError(Exception):
    """An export failure that leaves any created destination intact."""


def git_environment(*, isolated: bool) -> dict[str, str]:
    # Repository overrides must not redirect commands to the caller's repository.
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    if isolated:
        # Do not inherit remotes, hooks, templates, signing or shared LFS storage.
        env["GIT_CONFIG_NOSYSTEM"] = "1"
        env["GIT_CONFIG_GLOBAL"] = os.devnull
    return env


def run_git(
    root: Path,
    *arguments: str,
    isolated: bool = False,
    operation: str,
) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            env=git_environment(isolated=isolated),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise ExportError(f"Cannot run Git while {operation}: {exc}") from exc
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ExportError(f"Git failed while {operation} (exit {result.returncode}).\n{detail}")
    return result.stdout


def require_clean_tracked_files(source: Path) -> None:
    status = run_git(
        source,
        "status", "--porcelain=v1", "-z", "--untracked-files=no",
        operation="checking tracked source files",
    )
    if status:
        raise ExportError("Source has staged or unstaged tracked changes. Commit them before exporting.")


def tracked_files(source: Path) -> list[Path]:
    output = run_git(source, "ls-files", "-z", operation="listing tracked source files")
    paths = [Path(os.fsdecode(name)) for name in output.split(b"\0") if name]
    if not paths:
        raise ExportError("Source contains no tracked files.")
    for relative in paths:
        if relative.is_absolute() or ".." in relative.parts or any(part.lower() == ".git" for part in relative.parts):
            raise ExportError("The tracked file list contains an unsafe metadata path.")
        if relative.name.lower() in {".lfsconfig", ".gitmodules"}:
            raise ExportError(
                f"Tracked transport configuration requires separate review and cannot be exported: {relative}"
            )
        path = source / relative
        if path.is_symlink() or not path.resolve().is_relative_to(source):
            raise ExportError(f"Tracked symbolic links or paths outside the source are unsupported: {relative}")
        if not path.is_file():
            raise ExportError(f"Tracked path is not a materialized regular file: {relative}")
        with path.open("rb") as handle:
            header = handle.read(512).removeprefix(b"\xef\xbb\xbf")
        if header.startswith(LFS_HEADER):
            raise ExportError(f"Tracked file is an unmaterialized Git LFS pointer: {relative}")
    return paths


def export_snapshot(destination_argument: str) -> tuple[Path, int]:
    source = Path(__file__).resolve().parents[2]
    requested = Path(destination_argument).expanduser()
    if os.path.lexists(requested):
        raise ExportError("Destination already exists. Choose a new directory.")
    destination = requested.resolve()
    if destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ExportError("Destination must be outside the source directory and must not be a source ancestor.")

    repository_root = Path(os.fsdecode(run_git(
        source, "rev-parse", "--show-toplevel", operation="locating the source repository"
    )).strip()).resolve()
    if repository_root != source:
        raise ExportError("The script must be at Benchmarks/tools/export_snapshot.py inside the repository root.")

    require_clean_tracked_files(source)
    files = tracked_files(source)
    run_git(source, "lfs", "version", operation="checking Git LFS availability")

    # Nothing before this point creates or modifies the destination.
    destination.mkdir(parents=True, exist_ok=False)
    print(f"Copying {len(files)} tracked files into a new snapshot directory...", flush=True)
    for relative in files:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, target)
    require_clean_tracked_files(source)

    run_git(
        destination, "init", "-b", "main", "--template=", isolated=True,
        operation="initializing the snapshot repository",
    )
    run_git(
        destination, "lfs", "install", "--local", isolated=True,
        operation="installing local LFS support",
    )
    # Source-tracked files can match .gitignore; they still belong in the snapshot.
    run_git(
        destination, "add", "-A", "--force", isolated=True,
        operation="adding the snapshot files",
    )
    run_git(
        destination,
        "-c", "user.name=Benchmark Snapshot", "-c", "user.email=benchmark@local.invalid",
        "-c", "commit.gpgSign=false", "commit", "-m", "Benchmark starting snapshot",
        isolated=True, operation="creating the single starting commit",
    )

    count = run_git(
        destination, "rev-list", "--count", "HEAD", isolated=True,
        operation="checking snapshot commit count",
    ).strip()
    parents = run_git(
        destination, "rev-list", "--parents", "-n", "1", "HEAD", isolated=True,
        operation="checking the root commit",
    ).split()
    remotes = run_git(
        destination, "remote", isolated=True, operation="checking snapshot remotes"
    ).strip()
    copied_files = run_git(
        destination, "ls-files", "-z", isolated=True,
        operation="checking the exported file list",
    )
    expected_files = {os.fsencode(str(path).replace(os.sep, "/")) for path in files}
    actual_files = {name for name in copied_files.split(b"\0") if name}
    status = run_git(
        destination, "status", "--porcelain=v1", "-z", "--untracked-files=no", isolated=True,
        operation="checking snapshot cleanliness",
    )
    if count != b"1" or len(parents) != 1 or remotes or actual_files != expected_files or status:
        raise ExportError("The new snapshot failed its single-root, no-remote or tracked-file verification.")
    return destination, len(files)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, help="New directory outside the source repository")
    arguments = parser.parse_args()
    try:
        destination, count = export_snapshot(arguments.destination)
    except (ExportError, OSError, ValueError) as exc:
        print(f"Export failed: {exc}", file=sys.stderr)
        print("Any created destination has been left intact; nothing was deleted.", file=sys.stderr)
        return 1
    print(f"Snapshot ready: {destination}")
    print(f"Verified {count} tracked files, one root commit, branch main, and no configured remotes.")
    print("For evaluation, isolate the model from the original repository and other reference worktrees.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
