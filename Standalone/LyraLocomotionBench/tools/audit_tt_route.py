"""Read only TT Switch proxy metadata for one explicit Claude session UUID.

Never reads authentication, provider settings, request bodies, raw traffic,
conversion traces or error text. No model request is made. Absence of a session
match is reported as unassociated; timestamps are never used to infer a match.
"""
import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import sys
from uuid import UUID


SAFE_COLUMNS = (
    "request_id", "provider_id", "app_type", "model", "request_model",
    "status_code", "session_id", "provider_type", "created_at", "latency_ms",
    "is_streaming", "data_source", "conversion_trace_completeness",
)
REQUIRED_COLUMNS = (
    "request_id", "provider_id", "app_type", "model", "request_model",
    "status_code", "session_id", "data_source",
)


def canonical_session(value):
    try:
        parsed = str(UUID(value))
    except (ValueError, AttributeError) as exc:
        raise ValueError("session-id must be a canonical UUID") from exc
    if value.lower() != parsed:
        raise ValueError("session-id must use the canonical hyphenated UUID form")
    return parsed


def read_session(db_path, session_id, expected_model=None, expected_provider_id=None):
    session_id = canonical_session(session_id)
    db_path = Path(db_path).resolve(strict=True)
    if not db_path.is_file():
        raise ValueError("Database path must be a file")
    # mode=ro is needed: a normal sqlite connection can create a missing DB.
    with closing(sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True, timeout=5)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        columns = {row[1] for row in conn.execute("PRAGMA table_info(proxy_request_logs)")}
        missing = sorted(set(REQUIRED_COLUMNS) - columns)
        if missing:
            raise ValueError("Required proxy metadata columns missing: " + ", ".join(missing))
        selected = [name for name in SAFE_COLUMNS if name in columns]
        # This expression reads only the presence of an error; error text can
        # contain upstream payload snippets, so do not fetch or export it.
        has_error = (
            "CASE WHEN error_message IS NULL OR error_message = '' THEN 0 ELSE 1 END AS has_error"
            if "error_message" in columns else "NULL AS has_error"
        )
        query = (
            "SELECT " + ", ".join(selected) + ", " + has_error
            + " FROM proxy_request_logs"
            + " WHERE app_type = 'claude' AND data_source = 'proxy'"
            + " AND instr(lower(coalesce(session_id, '')), ?) > 0"
            + (" ORDER BY created_at, request_id" if "created_at" in columns else " ORDER BY request_id")
        )
        raw_matches = [dict(row) for row in conn.execute(query, (session_id,))]

    # Accept exact UUID or a UUID embedded in a composite session field, but
    # reject a longer hexadecimal identifier that merely contains its text.
    pattern = re.compile(r"(?<![0-9a-f])" + re.escape(session_id) + r"(?![0-9a-f])", re.I)
    rows = [row for row in raw_matches if pattern.search(row["session_id"] or "")]
    for row in rows:
        if row["has_error"] is not None:
            row["has_error"] = bool(row["has_error"])
        row["session_match"] = (
            "exact" if row["session_id"].lower() == session_id else "contains_uuid"
        )
    model_values = sorted({row["model"] for row in rows if row["model"] is not None})
    provider_values = sorted({row["provider_id"] for row in rows if row["provider_id"] is not None})
    return {
        "schema_version": 1,
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "database_path": str(db_path),
        "session_id": session_id,
        "association_status": "matched_session_metadata" if rows else "unassociated",
        "association_rule": "app_type=claude AND data_source=proxy AND session_id contains the explicit UUID as a complete identifier",
        "time_based_association_used": False,
        "record_count": len(rows),
        "rejected_nonboundary_substring_matches": len(raw_matches) - len(rows),
        "available_exported_columns": selected + ["has_error", "session_match"],
        "missing_optional_columns": sorted(set(SAFE_COLUMNS) - columns),
        "models": model_values,
        "request_models": sorted({row["request_model"] for row in rows if row["request_model"] is not None}),
        "provider_ids": provider_values,
        "status_code_counts": dict(Counter(str(row["status_code"]) for row in rows)),
        "expected_model": expected_model,
        "all_records_match_expected_model": (
            all(row["model"] == expected_model for row in rows) if rows and expected_model else None
        ),
        "expected_provider_id": expected_provider_id,
        "all_records_match_expected_provider": (
            all(row["provider_id"] == expected_provider_id for row in rows)
            if rows and expected_provider_id else None
        ),
        "effort_verification": "not_observable_in_exported_proxy_metadata",
        "records": rows,
        "limits": [
            "No session match means this audit cannot associate any proxy request with the run; it does not prove the run made no request.",
            "Model and provider metadata must be checked together with CLI completion and response identity; HTTP success alone is insufficient.",
            "CLI --effort records the requested level; these metadata do not prove the upstream reasoning level or budget.",
            "Imported session_log records are excluded; no authentication, raw body, conversion trace or error text is exported.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--db", type=Path, default=Path.home() / ".tt-switch" / "tt-switch.db")
    parser.add_argument("--expected-model")
    parser.add_argument("--expected-provider-id")
    args = parser.parse_args(argv)
    try:
        output = args.output.resolve()
        if output.exists():
            raise ValueError("Refusing to overwrite an existing audit output")
        if output == args.db.resolve():
            raise ValueError("Output must not be the database")
        result = read_session(args.db, args.session_id, args.expected_model, args.expected_provider_id)
        output.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive create also prevents a concurrent run from replacing output.
        with output.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        print(json.dumps({"output": str(output), "association_status": result["association_status"],
                          "record_count": result["record_count"], "models": result["models"]}))
        return 0
    except (ValueError, OSError, sqlite3.Error) as exc:
        print("Route audit failed: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
