# Lyra real UE evaluation

Status: **invalid_evidence**
Valid score: **0/100**
Final pass: **False**

Final evaluation requires complete Linux runtime and build evidence.

Real UE Automation execution of ULyraHealthComponent with a real UWorld, ASC, gameplay tags and dynamic delegates. OnRep_DeathState is driven directly by the fixture; this does not prove multi-machine network replication, gameplay presentation, or complete-game correctness.

The report and build manifest must come from the trusted evaluator. This parser checks their structure and consistency; metadata hashes alone do not independently attest a binary or remote execution.

Candidate: `3daa3a32b5ddbe106d8c997a6e2514df5fdb0e8d`
Cases passed: 0/23

| Group | Observed points | Passed |
| --- | ---: | ---: |
| DirectFinished | 0.0/20 | 0/4 |
| StepSequence | 0.0/20 | 0/4 |
| Idempotence | 0.0/20 | 0/5 |
| PredictionAhead | 0.0/20 | 0/5 |
| ASCNull | 0.0/20 | 0/5 |

Observed case points are diagnostic only; evidence validation failed.

- UE report requires a nonempty devices array
- UE report requires a tests array
- UE report contains zero tests
- missing_tests: 23
- UE summary succeeded must be 0, got None
- UE summary succeededWithWarnings must be 0, got None
- UE summary failed must be 0, got None
- UE summary notRun must be 0, got None
- UE summary inProcess must be 0, got None
- No actual test execution platform established
- Unable to read /workspace/lyra-runner/candidate-result-01/ue-report/index.json: [Errno 2] No such file or directory: '/workspace/lyra-runner/candidate-result-01/ue-report/index.json'

missing_tests:

- Lyra.Benchmark.Death.ASCNull.DirectFinished
- Lyra.Benchmark.Death.ASCNull.DuplicateMethods
- Lyra.Benchmark.Death.ASCNull.FinishBeforeStart
- Lyra.Benchmark.Death.ASCNull.LocalSequence
- Lyra.Benchmark.Death.ASCNull.PredictionAhead
- Lyra.Benchmark.Death.DirectFinished.AfterPrematureFinish
- Lyra.Benchmark.Death.DirectFinished.DuplicateFinishedSnapshot
- Lyra.Benchmark.Death.DirectFinished.SkipStartedNotification
- Lyra.Benchmark.Death.DirectFinished.ThenDuplicateMethods
- Lyra.Benchmark.Death.Idempotence.DuplicateFinish
- Lyra.Benchmark.Death.Idempotence.DuplicateStart
- Lyra.Benchmark.Death.Idempotence.FinishBeforeStart
- Lyra.Benchmark.Death.Idempotence.RepeatedSequence
- Lyra.Benchmark.Death.Idempotence.StartAfterFinished
- Lyra.Benchmark.Death.PredictionAhead.FinishedReceivesNotDead
- Lyra.Benchmark.Death.PredictionAhead.FinishedReceivesStarted
- Lyra.Benchmark.Death.PredictionAhead.RepeatedOlderState
- Lyra.Benchmark.Death.PredictionAhead.StartedReceivesNotDead
- Lyra.Benchmark.Death.PredictionAhead.TwoOlderStates
- Lyra.Benchmark.Death.StepSequence.LocalStartReplicatedFinish
- Lyra.Benchmark.Death.StepSequence.ReplicatedStart
- Lyra.Benchmark.Death.StepSequence.ReplicatedStartAndFinish
- Lyra.Benchmark.Death.StepSequence.ReplicatedStartLocalFinish

Cases without credit:

- Lyra.Benchmark.Death.DirectFinished.SkipStartedNotification: missing
- Lyra.Benchmark.Death.DirectFinished.DuplicateFinishedSnapshot: missing
- Lyra.Benchmark.Death.DirectFinished.ThenDuplicateMethods: missing
- Lyra.Benchmark.Death.DirectFinished.AfterPrematureFinish: missing
- Lyra.Benchmark.Death.StepSequence.ReplicatedStart: missing
- Lyra.Benchmark.Death.StepSequence.ReplicatedStartAndFinish: missing
- Lyra.Benchmark.Death.StepSequence.LocalStartReplicatedFinish: missing
- Lyra.Benchmark.Death.StepSequence.ReplicatedStartLocalFinish: missing
- Lyra.Benchmark.Death.Idempotence.FinishBeforeStart: missing
- Lyra.Benchmark.Death.Idempotence.DuplicateStart: missing
- Lyra.Benchmark.Death.Idempotence.DuplicateFinish: missing
- Lyra.Benchmark.Death.Idempotence.StartAfterFinished: missing
- Lyra.Benchmark.Death.Idempotence.RepeatedSequence: missing
- Lyra.Benchmark.Death.PredictionAhead.StartedReceivesNotDead: missing
- Lyra.Benchmark.Death.PredictionAhead.FinishedReceivesStarted: missing
- Lyra.Benchmark.Death.PredictionAhead.FinishedReceivesNotDead: missing
- Lyra.Benchmark.Death.PredictionAhead.RepeatedOlderState: missing
- Lyra.Benchmark.Death.PredictionAhead.TwoOlderStates: missing
- Lyra.Benchmark.Death.ASCNull.LocalSequence: missing
- Lyra.Benchmark.Death.ASCNull.DirectFinished: missing
- Lyra.Benchmark.Death.ASCNull.FinishBeforeStart: missing
- Lyra.Benchmark.Death.ASCNull.DuplicateMethods: missing
- Lyra.Benchmark.Death.ASCNull.PredictionAhead: missing
