# Lyra real UE evaluation

Status: **final_fail**
Valid score: **29.0/100**
Final pass: **False**

Final evaluation requires complete Linux runtime and build evidence.

Real UE Automation execution of ULyraHealthComponent with a real UWorld, ASC, gameplay tags and dynamic delegates. OnRep_DeathState is driven directly by the fixture; this does not prove multi-machine network replication, gameplay presentation, or complete-game correctness.

The report and build manifest must come from the trusted evaluator. This parser checks their structure and consistency; metadata hashes alone do not independently attest a binary or remote execution.

Candidate: `240a1617ee9ae96eb841114bf79268bdad6d92d0`
Cases passed: 7/23

| Group | Observed points | Passed |
| --- | ---: | ---: |
| DirectFinished | 0.0/20 | 0/4 |
| StepSequence | 5.0/20 | 1/4 |
| Idempotence | 4.0/20 | 1/5 |
| PredictionAhead | 8.0/20 | 2/5 |
| ASCNull | 12.0/20 | 3/5 |

Cases without credit:

- Lyra.Benchmark.Death.DirectFinished.SkipStartedNotification: state must be Success and errors must be 0
- Lyra.Benchmark.Death.DirectFinished.DuplicateFinishedSnapshot: state must be Success and errors must be 0
- Lyra.Benchmark.Death.DirectFinished.ThenDuplicateMethods: state must be Success and errors must be 0
- Lyra.Benchmark.Death.DirectFinished.AfterPrematureFinish: state must be Success and errors must be 0
- Lyra.Benchmark.Death.StepSequence.ReplicatedStartAndFinish: state must be Success and errors must be 0
- Lyra.Benchmark.Death.StepSequence.LocalStartReplicatedFinish: state must be Success and errors must be 0
- Lyra.Benchmark.Death.StepSequence.ReplicatedStartLocalFinish: state must be Success and errors must be 0
- Lyra.Benchmark.Death.Idempotence.DuplicateStart: state must be Success and errors must be 0
- Lyra.Benchmark.Death.Idempotence.DuplicateFinish: state must be Success and errors must be 0
- Lyra.Benchmark.Death.Idempotence.StartAfterFinished: state must be Success and errors must be 0
- Lyra.Benchmark.Death.Idempotence.RepeatedSequence: state must be Success and errors must be 0
- Lyra.Benchmark.Death.PredictionAhead.FinishedReceivesStarted: state must be Success and errors must be 0
- Lyra.Benchmark.Death.PredictionAhead.FinishedReceivesNotDead: state must be Success and errors must be 0
- Lyra.Benchmark.Death.PredictionAhead.TwoOlderStates: state must be Success and errors must be 0
- Lyra.Benchmark.Death.ASCNull.DirectFinished: state must be Success and errors must be 0
- Lyra.Benchmark.Death.ASCNull.DuplicateMethods: state must be Success and errors must be 0
