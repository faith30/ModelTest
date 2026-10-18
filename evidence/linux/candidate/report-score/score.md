# Lyra real UE evaluation

Status: **final_pass**
Valid score: **100.0/100**
Final pass: **True**

Final evaluation requires complete Linux runtime and build evidence.

Real UE Automation execution of ULyraHealthComponent with a real UWorld, ASC, gameplay tags and dynamic delegates. OnRep_DeathState is driven directly by the fixture; this does not prove multi-machine network replication, gameplay presentation, or complete-game correctness.

The report and build manifest must come from the trusted evaluator. This parser checks their structure and consistency; metadata hashes alone do not independently attest a binary or remote execution.

Candidate: `3daa3a32b5ddbe106d8c997a6e2514df5fdb0e8d`
Cases passed: 23/23

| Group | Observed points | Passed |
| --- | ---: | ---: |
| DirectFinished | 20.0/20 | 4/4 |
| StepSequence | 20.0/20 | 4/4 |
| Idempotence | 20.0/20 | 5/5 |
| PredictionAhead | 20.0/20 | 5/5 |
| ASCNull | 20.0/20 | 5/5 |
