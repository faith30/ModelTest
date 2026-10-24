"""Aggregate evidence-backed reviews; never execute or semantically judge a candidate.

Create a review outside the frozen candidate directory with --init-review.
Review items and gates are objects keyed by rubric ID. Items use pass, partial,
missing, incorrect, or unreviewed. Gates use pass, fail, or unreviewed plus an
explicit confirmed boolean. A failed gate caps the total; caps never stack as
deductions. Missing reviews or unconfirmed gates leave final_score null.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import stat
import sys


class ReviewError(ValueError):
    """The review cannot be safely or consistently scored."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReviewError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def _finite_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ReviewError("Non-finite JSON number")
    return result


def _bad_constant(value):
    raise ReviewError("Non-finite JSON number: " + value)


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"),
                          object_pairs_hook=_unique_object,
                          parse_float=_finite_float, parse_constant=_bad_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReviewError(f"Cannot read JSON {path}: {exc}") from exc


def _number(value, label, minimum=0):
    if type(value) not in (int, float):
        raise ReviewError(label + " must be a finite number, not a boolean")
    try:
        valid = math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid or value < minimum:
        raise ReviewError(label + " is non-finite or below its minimum")
    return value


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ReviewError(label + " must be a nonempty string")
    return value


def _is_link(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def candidate_tree(candidate):
    """Hash every regular file, including names; reject links and special files.

    Digest: SHA-256 of canonical UTF-8 JSON [[relative_posix_path, file_sha256],
    ...], sorted by path. No files are silently excluded. The review and output
    must therefore live outside the candidate directory.
    """
    source = Path(candidate).absolute()
    try:
        if _is_link(source):
            raise ReviewError("Candidate root must not be a symlink or reparse point")
        root = source.resolve(strict=True)
        if not root.is_dir():
            raise ReviewError("Candidate must be a directory")
        files = []

        def fail_walk(error):
            raise ReviewError("Cannot enumerate candidate: " + str(error))

        for parent, directories, names in os.walk(root, followlinks=False, onerror=fail_walk):
            directories.sort()
            names.sort()
            for name in directories + names:
                path = Path(parent) / name
                if _is_link(path):
                    raise ReviewError("Candidate contains a symlink/reparse point: " + str(path))
                resolved = path.resolve(strict=True)
                if not resolved.is_relative_to(root):
                    raise ReviewError("Candidate path escapes root: " + str(path))
                mode = path.stat().st_mode
                if name in directories:
                    if not stat.S_ISDIR(mode):
                        raise ReviewError("Candidate entry changed while enumerating: " + str(path))
                elif not stat.S_ISREG(mode):
                    raise ReviewError("Candidate contains a nonregular file: " + str(path))
                else:
                    digest = hashlib.sha256()
                    with path.open("rb") as stream:
                        for block in iter(lambda: stream.read(1024 * 1024), b""):
                            digest.update(block)
                    files.append([path.relative_to(root).as_posix(), digest.hexdigest()])
        if not files:
            raise ReviewError("Candidate directory has no files")
        files.sort()
        encoded = json.dumps(files, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return root, hashlib.sha256(encoded).hexdigest(), files
    except (OSError, RuntimeError) as exc:
        raise ReviewError("Cannot freeze candidate: " + str(exc)) from exc


def _candidate_path(root, value, label, file_only=False):
    _text(value, label)
    # Use one portable path syntax; Windows absolute/drive paths are rejected on Linux too.
    if "\\" in value or "\x00" in value or PureWindowsPath(value).drive:
        raise ReviewError(label + " must be a relative POSIX path")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ReviewError(label + " escapes candidate root")
    path = root
    try:
        for part in relative.parts:
            path = path / part
            if _is_link(path):
                raise ReviewError(label + " traverses a symlink/reparse point")
        path = path.resolve(strict=True)
        if not path.is_relative_to(root):
            raise ReviewError(label + " escapes candidate root")
        if file_only and not path.is_file():
            raise ReviewError(label + " must name a regular file")
        if not path.is_file() and not path.is_dir():
            raise ReviewError(label + " must name a file or directory")
        return path
    except (OSError, RuntimeError) as exc:
        raise ReviewError(label + ": " + str(exc)) from exc


def _evidence(root, value, label, required=False):
    if not isinstance(value, list) or (required and not value):
        raise ReviewError(label + " must be a nonempty evidence list" if required
                          else label + " must be an evidence list")
    for index, entry in enumerate(value):
        prefix = f"{label}[{index}]"
        if not isinstance(entry, dict):
            raise ReviewError(prefix + " must be an object")
        path = _candidate_path(root, entry.get("path"), prefix + ".path", file_only=True)
        start, end = entry.get("line_start"), entry.get("line_end")
        if type(start) is not int or type(end) is not int or start < 1 or end < start:
            raise ReviewError(prefix + " requires positive, ordered integer line numbers")
        quote = _text(entry.get("quote"), prefix + ".quote")
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines(keepends=True)
        except (OSError, UnicodeError) as exc:
            raise ReviewError(prefix + " requires a readable UTF-8 evidence file") from exc
        if end > len(lines) or quote not in "".join(lines[start - 1:end]):
            raise ReviewError(prefix + " quote does not occur in the stated line interval")
    return value


def _reviewed_paths(root, value, label):
    if not isinstance(value, list):
        raise ReviewError(label + " must be a list")
    for index, path in enumerate(value):
        _candidate_path(root, path, f"{label}[{index}]")
    return value


def validate_rubric(rubric):
    if not isinstance(rubric, dict):
        raise ReviewError("Rubric must be an object")
    items, gates = rubric.get("items"), rubric.get("gates")
    if not isinstance(items, list) or not items or not isinstance(gates, list):
        raise ReviewError("Rubric requires nonempty items and a gates list")
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            raise ReviewError("Rubric item must be an object")
        item_id = _text(item.get("id"), "rubric item id")
        if item_id in seen:
            raise ReviewError("Duplicate rubric id: " + item_id)
        seen.add(item_id)
        _text(item.get("category"), item_id + ".category")
        if _number(item.get("weight"), item_id + ".weight") <= 0:
            raise ReviewError(item_id + ".weight must be positive")
    try:
        total = math.fsum(item["weight"] for item in items)
    except OverflowError as exc:
        raise ReviewError("Rubric total is not finite") from exc
    if not math.isfinite(total):
        raise ReviewError("Rubric total is not finite")
    for gate in gates:
        if not isinstance(gate, dict):
            raise ReviewError("Rubric gate must be an object")
        gate_id = _text(gate.get("id"), "rubric gate id")
        if gate_id in seen:
            raise ReviewError("Duplicate rubric id: " + gate_id)
        seen.add(gate_id)
        if _number(gate.get("cap"), gate_id + ".cap") > total:
            raise ReviewError(gate_id + ".cap exceeds maximum score")
    return items, gates, total


def init_review(rubric, candidate):
    items, gates, _ = validate_rubric(rubric)
    _, digest, _ = candidate_tree(candidate)
    return {
        "schema_version": 1,
        "candidate_sha256": digest,
        "reviewer": "",
        "notes": "Fill evidence from the frozen candidate. This tool does not judge semantics.",
        "items": {item["id"]: {"status": "unreviewed", "reason": "Awaiting independent review.",
                                  "evidence": [], "reviewed_paths": []} for item in items},
        "gates": {gate["id"]: {"status": "unreviewed", "confirmed": False,
                                  "reason": "Awaiting independent review.", "evidence": []} for gate in gates},
    }


def score_review(rubric, review, candidate):
    items, gates, total = validate_rubric(rubric)
    if not isinstance(review, dict) or type(review.get("schema_version")) is not int or review["schema_version"] != 1:
        raise ReviewError("Review schema_version must be 1")
    root, digest, files = candidate_tree(candidate)
    if review.get("candidate_sha256") != digest:
        raise ReviewError("Candidate hash mismatch: this review belongs to different candidate bytes or paths")
    item_reviews, gate_reviews = review.get("items"), review.get("gates")
    if not isinstance(item_reviews, dict) or not isinstance(gate_reviews, dict):
        raise ReviewError("Review items and gates must be objects keyed by rubric ID")
    for name, mapping, definitions in (("items", item_reviews, items), ("gates", gate_reviews, gates)):
        unknown = set(mapping) - {entry["id"] for entry in definitions}
        if unknown:
            raise ReviewError("Unknown review " + name + " IDs: " + ", ".join(sorted(unknown)))
    rows, gate_rows, categories = [], [], {}
    for item in items:
        item_id, weight, category = item["id"], item["weight"], item["category"]
        entry = item_reviews.get(item_id, {"status": "unreviewed", "reason": "Item omitted from review."})
        if not isinstance(entry, dict):
            raise ReviewError(item_id + " review must be an object")
        status = entry.get("status")
        if status not in ("pass", "partial", "missing", "incorrect", "unreviewed"):
            raise ReviewError(item_id + " has invalid review status")
        evidence = _evidence(root, entry.get("evidence", []), item_id + ".evidence", status in ("pass", "partial"))
        paths = _reviewed_paths(root, entry.get("reviewed_paths", []), item_id + ".reviewed_paths")
        reason = entry.get("reason", "")
        if not isinstance(reason, str):
            raise ReviewError(item_id + ".reason must be a string")
        if status == "partial":
            awarded = _number(entry.get("awarded"), item_id + ".awarded")
            if not 0 < awarded < weight:
                raise ReviewError(item_id + ": partial award must be positive and below its weight")
            _text(reason, item_id + ".reason")
        elif status == "pass":
            awarded = weight
        elif status in ("missing", "incorrect"):
            awarded = 0
            _text(reason, item_id + ".reason")
            if not evidence and not paths:
                raise ReviewError(item_id + " needs reviewed_paths or evidence for an adverse finding")
        else:
            awarded = None
        if status != "partial" and "awarded" in entry:
            supplied = entry["awarded"]
            if status == "unreviewed":
                if supplied is not None:
                    raise ReviewError(item_id + ": unreviewed cannot receive points")
            elif _number(supplied, item_id + ".awarded") != awarded:
                raise ReviewError(item_id + ": awarded conflicts with status")
        row = {"id": item_id, "category": category, "status": status, "weight": weight,
               "awarded": awarded, "deduction": None if awarded is None else weight - awarded,
               "reason": reason, "evidence": evidence, "reviewed_paths": paths}
        rows.append(row)
        categories.setdefault(category, []).append(row)
    for gate in gates:
        gate_id = gate["id"]
        entry = gate_reviews.get(gate_id, {"status": "unreviewed", "confirmed": False,
                                           "reason": "Gate omitted from review."})
        if not isinstance(entry, dict):
            raise ReviewError(gate_id + " review must be an object")
        status, confirmed = entry.get("status"), entry.get("confirmed")
        if status not in ("pass", "fail", "unreviewed") or type(confirmed) is not bool:
            raise ReviewError(gate_id + " needs status pass/fail/unreviewed and a confirmed boolean")
        if status == "unreviewed" and confirmed:
            raise ReviewError(gate_id + ": unreviewed cannot be confirmed")
        reason = _text(entry.get("reason"), gate_id + ".reason")
        evidence = _evidence(root, entry.get("evidence", []), gate_id + ".evidence")
        paths = _reviewed_paths(root, entry.get("reviewed_paths", []), gate_id + ".reviewed_paths")
        if confirmed and status in ("pass", "fail") and not evidence and not paths:
            raise ReviewError(gate_id + " needs reviewed_paths or evidence for a confirmed gate finding")
        gate_rows.append({"id": gate_id, "status": status, "confirmed": confirmed,
                          "review_complete": confirmed and status != "unreviewed",
                          "cap": gate["cap"], "applied": confirmed and status == "fail",
                          "reason": reason, "evidence": evidence, "reviewed_paths": paths})
    reviewed = [row for row in rows if row["awarded"] is not None]
    subtotal = math.fsum(row["awarded"] for row in reviewed)
    reviewed_weight = math.fsum(row["weight"] for row in reviewed)
    applied_caps = [row["cap"] for row in gate_rows if row["applied"]]
    cap = min([total] + applied_caps)
    items_complete = len(reviewed) == len(rows)
    gates_complete = all(row["review_complete"] for row in gate_rows)
    complete = items_complete and gates_complete
    final = min(subtotal, cap) if complete else None
    if candidate_tree(root)[1] != digest:
        raise ReviewError("Candidate changed during review validation")
    return {
        "schema_version": 1, "status": "complete" if complete else "incomplete_review",
        "candidate_sha256": digest, "candidate_file_count": len(files),
        "semantic_judgment": "Provided by the reviewer; this tool validates evidence locations and arithmetic only.",
        "max_score": total, "reviewed_subscore": subtotal, "reviewed_max_score": reviewed_weight,
        "reviewed_deductions": reviewed_weight - subtotal,
        "coverage": {"reviewed_items": len(reviewed), "total_items": len(rows),
                     "weight_fraction": reviewed_weight / total,
                     "reviewed_gates": sum(row["review_complete"] for row in gate_rows), "total_gates": len(gate_rows)},
        "unreviewed_items": [row["id"] for row in rows if row["awarded"] is None],
        "unreviewed_gates": [row["id"] for row in gate_rows if not row["review_complete"]],
        "raw_score": subtotal if items_complete else None, "effective_cap": cap,
        "cap_deduction": subtotal - final if complete else None, "final_score": final,
        "categories": {name: {"reviewed_subscore": math.fsum(row["awarded"] for row in group if row["awarded"] is not None),
                               "reviewed_max_score": math.fsum(row["weight"] for row in group if row["awarded"] is not None),
                               "max_score": math.fsum(row["weight"] for row in group)} for name, group in categories.items()},
        "items": rows, "gates": gate_rows,
    }


def _outside_candidate(path, root, label):
    resolved = Path(path).resolve()
    if resolved.is_relative_to(root):
        raise ReviewError(label + " must be outside the frozen candidate directory")
    return resolved


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rubric", required=True)
    parser.add_argument("--review")
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--init-review", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.init_review == bool(args.review):
            raise ReviewError("Use either --init-review or --review, but not both")
        root = Path(args.candidate).resolve(strict=True)
        output = _outside_candidate(args.output, root, "Output")
        rubric_path = _outside_candidate(args.rubric, root, "Rubric")
        rubric = read_json(rubric_path)
        rubric_sha = hashlib.sha256(rubric_path.read_bytes()).hexdigest()
        if args.init_review:
            if output.exists():
                raise ReviewError("Refusing to overwrite an existing review template")
            result = init_review(rubric, args.candidate)
            result["rubric_sha256"] = rubric_sha
        else:
            review_path = _outside_candidate(args.review, root, "Review")
            if output == review_path or output == rubric_path:
                raise ReviewError("Output must not overwrite the review or rubric")
            review = read_json(review_path)
            if not isinstance(review, dict) or review.get("rubric_sha256") != rubric_sha:
                raise ReviewError("Rubric hash missing or mismatched: use the rubric frozen with this review")
            result = score_review(rubric, review, args.candidate)
            result["rubric_sha256"] = rubric_sha
            result["review_sha256"] = hashlib.sha256(review_path.read_bytes()).hexdigest()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(json.dumps({"output": str(output), "status": result.get("status", "review_template"),
                          "final_score": result.get("final_score")}, ensure_ascii=False))
        return 0
    except (ReviewError, OSError) as exc:
        print("Review validation failed: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
