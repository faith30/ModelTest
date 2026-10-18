#!/usr/bin/env python3
"""Prepare a source-only candidate task for subsequent real UE Linux evaluation."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


TASK_ID = "lyra-death-v1"
COMPONENT_CPP = "Source/LyraGame/Character/LyraHealthComponent.cpp"
SOURCE_PATHS = (
    COMPONENT_CPP,
    "Source/LyraGame/Character/LyraHealthComponent.h",
    "Source/LyraGame/AbilitySystem/Attributes/LyraHealthSet.cpp",
)
MUTATIONS = (
    (
        "replication_skips_start", "OnRep_DeathState",
        "\t\telse if (NewDeathState == ELyraDeathState::DeathFinished)\n"
        "\t\t{\n\t\t\tStartDeath();\n\t\t\tFinishDeath();\n\t\t}",
        "\t\telse if (NewDeathState == ELyraDeathState::DeathFinished)\n"
        "\t\t{\n\t\t\tFinishDeath();\n\t\t}",
    ),
    (
        "start_allows_duplicate", "StartDeath",
        "if (DeathState != ELyraDeathState::NotDead)",
        "if (DeathState == ELyraDeathState::DeathFinished)",
    ),
    (
        "finish_clears_dead", "FinishDeath",
        "SetLooseGameplayTagCount(LyraGameplayTags::Status_Death_Dead, 1)",
        "SetLooseGameplayTagCount(LyraGameplayTags::Status_Death_Dead, 0)",
    ),
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(*args, cwd=None):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=30)
    if result.returncode:
        raise ValueError("Git command failed: " + (result.stderr.strip() or result.stdout.strip()))
    return result.stdout.strip()


def function_span(text, name):
    """Match this upstream file's column-zero method closing brace, fail closed."""
    signature = "void ULyraHealthComponent::" + name + "("
    if text.count(signature) != 1:
        raise ValueError(f"Expected exactly one {name} definition")
    start = text.index(signature)
    closing = re.search(r"^}\s*$", text[start:], re.MULTILINE)
    if closing is None:
        raise ValueError(f"Cannot locate the closing brace for {name}")
    return start, start + closing.end()


def seed_component(original):
    text = original.decode("utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    original_text = text.replace("\r\n", "\n")
    text = original_text
    checks = []
    for mutation_id, name, before, after in MUTATIONS:
        start, end = function_span(text, name)
        body = text[start:end]
        if body.count(before) != 1 or body.count(after) != 0:
            raise ValueError(f"Source does not uniquely match mutation {mutation_id}; no destination created")
        seeded_body = body.replace(before, after, 1)
        if seeded_body.count(after) != 1 or seeded_body.count(before) != 0:
            raise ValueError(f"Failed unique mutation verification: {mutation_id}")
        text = text[:start] + seeded_body + text[end:]
        checks.append({"id": mutation_id, "function": name,
                       "original_matches": 1, "seeded_matches": 1})
    restored = text
    for _, name, before, after in reversed(MUTATIONS):
        start, end = function_span(restored, name)
        restored = restored[:start] + restored[start:end].replace(after, before, 1) + restored[end:]
    if restored != original_text:
        raise ValueError("Mutation round-trip changed content beyond the three intended replacements")
    return text.replace("\n", newline).encode("utf-8"), checks


def prepare(source_root, destination):
    source_root = source_root.resolve()
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"Destination already exists; refusing to overwrite: {destination}")
    if not shutil.which("git"):
        raise ValueError("Git is required to create the independent task repository")
    source_commit = git("rev-parse", "--verify", "HEAD", cwd=source_root)
    source_data = {path: (source_root / path).read_bytes() for path in SOURCE_PATHS}
    seeded_cpp, mutation_checks = seed_component(source_data[COMPONENT_CPP])
    seeded_data = dict(source_data)
    seeded_data[COMPONENT_CPP] = seeded_cpp
    task_text = (Path(__file__).resolve().parent / "task" / "TASK.md").read_bytes()
    dirty = git("status", "--porcelain", "--", *SOURCE_PATHS, cwd=source_root)
    metadata = {
        "task_id": TASK_ID,
        "artificial_defects": True,
        "source_commit": source_commit,
        "source_worktree_modified": bool(dirty),
        "source_hashes": {path: digest(data) for path, data in source_data.items()},
        "seeded_hashes": {path: digest(data) for path, data in seeded_data.items()},
        "mutation_checks": mutation_checks,
        "evaluation_boundary": "Candidate changes are applied to the complete Lyra project, built with Unreal Engine, and evaluated by real UE automation on Linux. This preparation step does not build or run UE.",
    }
    destination.mkdir(parents=True, exist_ok=False)
    for relative_path, data in seeded_data.items():
        output = destination / relative_path
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)
    (destination / "TASK.md").write_bytes(task_text)
    (destination / "task_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    git("init", "--initial-branch=codex/lyra-death-v1", cwd=destination)
    git("config", "core.autocrlf", "false", cwd=destination)
    git("add", "--", *SOURCE_PATHS, "TASK.md", "task_metadata.json", cwd=destination)
    git("-c", "user.name=Lyra Benchmark", "-c", "user.email=lyra-benchmark@example.invalid",
        "-c", "commit.gpgsign=false", "-c", "core.hooksPath=" + str(destination / ".git" / "disabled-hooks"),
        "commit", "-m", "Seed artificial Lyra death-state task v1", cwd=destination)
    return {"task_id": TASK_ID, "destination": str(destination.resolve()),
            "source_commit": source_commit, "base_commit": git("rev-parse", "HEAD", cwd=destination),
            "verified_mutations": len(mutation_checks)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True, help="A new directory; existing paths are refused")
    args = parser.parse_args()
    try:
        result = prepare(args.source_root, args.destination)
    except (ValueError, OSError, subprocess.TimeoutExpired, UnicodeError) as error:
        parser.exit(1, f"Preparation failed: {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
