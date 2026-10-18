# Lyra Linux runtime evaluation

Status: **runtime_crash_or_error**

Valid score: **0/100**

Final pass: **False**

Candidate: `3daa3a32b5ddbe106d8c997a6e2514df5fdb0e8d`

UE exit code: `139`

The authoritative runtime-gated result is result.json. The report-score directory contains scorer diagnostics only.

Real Linux UE Automation execution; this does not prove multi-machine replication or game presentation.

Evaluator-produced build and report required. File hashes do not independently attest execution.

| Group | Valid points | Observed points | Cases passed |
| --- | ---: | ---: | ---: |
| DirectFinished | 0/20 | 0.0 | 0/4 |
| StepSequence | 0/20 | 0.0 | 0/4 |
| Idempotence | 0/20 | 0.0 | 0/5 |
| PredictionAhead | 0/20 | 0.0 | 0/5 |
| ASCNull | 0/20 | 0.0 | 0/5 |

Evidence problems:

- Unexpected UE process exit code: 139
- UE report/build evidence did not pass the trusted scorer
- Scorer result is not a final Linux evaluation
- A complete terminal report for all 23 fixed cases is required
- Trusted scorer exit code is inconsistent with the report: 2
- UE exit code must be 255 for the observed case results
- UE stdout must contain exactly one matching Automation TEST COMPLETE marker
