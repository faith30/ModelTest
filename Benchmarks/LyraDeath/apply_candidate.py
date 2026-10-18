#!/usr/bin/env python3
"""Apply one scope-checked Git submission to a complete Lyra build checkout.

This writes only LyraHealthComponent.cpp and a new provenance JSON. It does not
build UE or create evidence of build/runtime success. Candidate scripts and the
candidate working tree are never executed or used as source input.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

from prepare import COMPONENT_CPP, MUTATIONS, SOURCE_PATHS, function_span


FUNCTIONS = ("OnRep_DeathState", "StartDeath", "FinishDeath")
ALLOWED_PATHS = {COMPONENT_CPP, "SOLUTION.md"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git_bytes(repo, *arguments, allowed_codes=(0,)):
    environment = os.environ.copy()
    environment["GIT_NO_LAZY_FETCH"] = "1"
    environment["GIT_TERMINAL_PROMPT"] = "0"
    command = ["git", "-c", "core.fsmonitor=false", "-c", "submodule.recurse=false",
               "-c", "core.hooksPath=" + str(Path(__file__).resolve().parent / "disabled-hooks"),
               "-C", str(repo), *arguments]
    result = subprocess.run(command, capture_output=True, timeout=30, env=environment)
    if result.returncode not in allowed_codes:
        raise ValueError("Git read failed: " + result.stderr.decode("utf-8", "replace").strip())
    return result.stdout, result.returncode


def commit_id(repo, value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", value):
        raise ValueError("Both seed-sha and candidate-sha must be complete 40-character Git commit IDs")
    actual = git_bytes(repo, "rev-parse", "--verify", value + "^{commit}")[0].decode("ascii").strip()
    if actual != value.lower():
        raise ValueError("Commit argument must identify a commit directly, not a tag")
    return actual


def tree(repo, commit):
    entries = {}
    for entry in git_bytes(repo, "ls-tree", "-r", "-z", "--full-tree", commit)[0].split(b"\0"):
        if not entry:
            continue
        header, name = entry.split(b"\t", 1)
        mode, object_type, object_id = header.decode("ascii").split()
        path = name.decode("utf-8")
        entries[path] = (mode, object_type, object_id)
    return entries


def blob(repo, entry):
    if entry[0] != "100644" or entry[1] != "blob":
        raise ValueError("Task source and SOLUTION.md must remain ordinary non-executable Git files")
    return git_bytes(repo, "cat-file", "blob", entry[2])[0]


def normalized_text(data):
    # Compare source text across Windows/Linux checkouts, but always write the
    # exact candidate blob bytes, without newline or encoding transformations.
    text = data.decode("utf-8")
    if "\x00" in text:
        raise ValueError("C++ source contains a NUL byte")
    return text.replace("\r\n", "\n")


def body_span(text, name):
    start, end = function_span(text, name)
    opening = text.find("{", start, end)
    closing = end - 1
    while closing > opening and text[closing].isspace():
        closing -= 1
    if opening < 0 or closing <= opening or text[closing] != "}":
        raise ValueError("Unsupported function definition: " + name)
    # Confirm the selected column-zero brace actually closes this function,
    # ignoring braces in comments and normal quoted literals. Unsupported raw
    # strings/directives fail closed instead of broadening the allowed region.
    depth = 1
    cursor = opening + 1
    while cursor < closing:
        if text.startswith("//", cursor):
            newline = text.find("\n", cursor + 2)
            cursor = closing if newline < 0 else newline
            continue
        if text.startswith("/*", cursor):
            comment_end = text.find("*/", cursor + 2)
            if comment_end < 0 or comment_end > closing:
                raise ValueError("Unterminated comment in " + name)
            cursor = comment_end + 2
            continue
        if text.startswith('R"', cursor):
            raise ValueError("Raw C++ string literals are unsupported in task function bodies")
        if text[cursor] in ('"', "'"):
            quote = text[cursor]
            cursor += 1
            while cursor < closing:
                if text[cursor] == "\\":
                    cursor += 2
                elif text[cursor] == quote:
                    cursor += 1
                    break
                else:
                    cursor += 1
            else:
                raise ValueError("Unterminated literal in " + name)
            continue
        if text[cursor] == "#":
            raise ValueError("Preprocessor directives are unsupported inside task functions")
        if text[cursor] == "{":
            depth += 1
        elif text[cursor] == "}":
            depth -= 1
            if depth <= 0:
                raise ValueError("Function closes before the permitted boundary: " + name)
        cursor += 1
    if depth != 1:
        raise ValueError("Unbalanced function body: " + name)
    return opening + 1, closing


def outside_bodies(text):
    spans = sorted(body_span(text, name) for name in FUNCTIONS)
    if any(left[1] >= right[0] for left, right in zip(spans, spans[1:])):
        raise ValueError("Target function definitions overlap")
    for start, end in reversed(spans):
        text = text[:start] + "/* permitted task body */" + text[end:]
    return text


def original_baseline(seed_text):
    original = seed_text
    for mutation_id, name, before, after in reversed(MUTATIONS):
        start, end = function_span(original, name)
        section = original[start:end]
        if section.count(after) != 1 or section.count(before) != 0:
            raise ValueError("Specified seed does not contain the fixed task mutation: " + mutation_id)
        original = original[:start] + section.replace(after, before, 1) + original[end:]
    return original


def validate_submission(candidate_repo, seed_sha, candidate_sha):
    repo = Path(candidate_repo).resolve(strict=True)
    seed_sha = commit_id(repo, seed_sha)
    candidate_sha = commit_id(repo, candidate_sha)
    _, ancestry = git_bytes(repo, "merge-base", "--is-ancestor", seed_sha, candidate_sha, allowed_codes=(0, 1))
    if ancestry:
        raise ValueError("The specified seed is not an ancestor of the candidate commit")
    seed_tree, candidate_tree = tree(repo, seed_sha), tree(repo, candidate_sha)
    changed = sorted(path for path in set(seed_tree) | set(candidate_tree)
                     if seed_tree.get(path) != candidate_tree.get(path))
    forbidden = set(changed) - ALLOWED_PATHS
    if forbidden:
        raise ValueError("Submission changes files outside task scope: " + ", ".join(sorted(forbidden)))
    for path in SOURCE_PATHS:
        if path not in seed_tree or path not in candidate_tree:
            raise ValueError("Required task source is missing: " + path)
        blob(repo, seed_tree[path])
        blob(repo, candidate_tree[path])
    if "SOLUTION.md" in candidate_tree:
        blob(repo, candidate_tree["SOLUTION.md"]).decode("utf-8")
    seed_data = blob(repo, seed_tree[COMPONENT_CPP])
    candidate_data = blob(repo, candidate_tree[COMPONENT_CPP])
    seed_text, candidate_text = normalized_text(seed_data), normalized_text(candidate_data)
    if outside_bodies(seed_text) != outside_bodies(candidate_text):
        raise ValueError("Candidate changes the target source outside the three permitted function bodies")
    baseline_text = original_baseline(seed_text)
    return {"repo": repo, "seed_sha": seed_sha, "candidate_sha": candidate_sha,
            "changed_paths": changed, "seed_bytes": seed_data, "candidate_bytes": candidate_data,
            "baseline_text": baseline_text}


def apply_candidate(candidate_repo, seed_sha, candidate_sha, project, output):
    submission = validate_submission(candidate_repo, seed_sha, candidate_sha)
    project = Path(project).resolve(strict=True)
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("Output provenance path already exists; choose a new JSON path")
    required = ("Lyra.uproject", "Source/LyraGame/LyraGame.Build.cs", *SOURCE_PATHS)
    for relative in required:
        path = (project / relative).resolve(strict=True)
        if not path.is_relative_to(project) or not path.is_file():
            raise ValueError("Build project is missing required Lyra project/source file: " + relative)
    project_description = json.loads((project / "Lyra.uproject").read_text(encoding="utf-8-sig"))
    if not any(isinstance(item, dict) and item.get("Name") == "LyraGame"
               for item in project_description.get("Modules", [])):
        raise ValueError("Lyra.uproject does not declare the LyraGame module")
    target = project / COMPONENT_CPP
    if target.is_symlink():
        raise ValueError("Refusing to replace a symlinked production source")
    existing = target.read_bytes()
    existing_text = normalized_text(existing)
    allowed_contents = {"original_baseline": submission["baseline_text"],
                        "seed": normalized_text(submission["seed_bytes"]),
                        "candidate": normalized_text(submission["candidate_bytes"])}
    matched = [name for name, value in allowed_contents.items() if existing_text == value]
    if not matched:
        raise ValueError("Existing production source matches neither original baseline, seed, nor candidate; refusing to overwrite local changes")
    record = {"schema_version": 1, "record_type": "candidate_source_application",
              "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "candidate_repo": str(submission["repo"]), "seed_sha": submission["seed_sha"],
              "candidate_sha": submission["candidate_sha"], "project": str(project),
              "source_path": COMPONENT_CPP, "source_sha256": digest(submission["candidate_bytes"]),
              "seed_source_sha256": digest(submission["seed_bytes"]),
              "previous_source_sha256": digest(existing), "previous_source_matches": matched,
              "changed_paths": submission["changed_paths"], "permitted_functions": list(FUNCTIONS),
              "candidate_blob_bytes_preserved": True,
              "source_changed": existing != submission["candidate_bytes"],
              "build_performed": False, "runtime_performed": False,
              "scope": "Scope-checked source application only; not evidence of UE build or runtime success."}
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    created_output = False
    try:
        # Exclusive creation prevents overwriting another run's provenance.
        with output.open("xb") as manifest:
            created_output = True
            manifest.write((json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
            manifest.flush()
            os.fsync(manifest.fileno())
            if existing != submission["candidate_bytes"]:
                with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".lyra-candidate-", delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(submission["candidate_bytes"])
                    stream.flush()
                    os.fsync(stream.fileno())
                os.chmod(temporary, stat.S_IMODE(target.stat().st_mode))
                if target.read_bytes() != existing:
                    raise ValueError("Production source changed during validation; no candidate applied")
                os.replace(temporary, target)
                temporary = None
    except Exception:
        if created_output:
            output.unlink(missing_ok=True)
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-repo", type=Path, required=True)
    parser.add_argument("--seed-sha", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New source-provenance JSON file")
    args = parser.parse_args(argv)
    try:
        record = apply_candidate(args.candidate_repo, args.seed_sha, args.candidate_sha, args.project, args.output)
    except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"Candidate was not applied: {error}\n")
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
