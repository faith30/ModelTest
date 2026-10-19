# Snapshot persistence control experiment

Observed on 2026-10-19, Asia/Shanghai. This is an environment check, not one of the three feature tasks and not a scored model implementation.

- Source: `bd6403b47d8d46b69153267072b35abe`, `Lyra-UE-Environment-Recovery`, started at 23:42.
- Claude Code session: `67d71a47-0db7-433d-b2b7-26dc4996ba1e`, explicitly selected `deepseek-v4-pro`.
- The model read `/workspace/environment_probe.json` and ran SHA-256 and byte-count commands. It returned the values below without modifying the file.
- The platform's round row changed to `已完成`, and the source instance's snapshot picker listed a 23:45 snapshot.
- Clicking `恢复运行` created instance `8e3c3aceaa504364833a5085188dff19` at 23:49. Its live shell hostname was `edge-1-e1aa858e`.
- The restored file was independently read and hashed in the restored terminal. It had exactly the same marker, size and hash.

| Field | Verified value |
| --- | --- |
| bytes | 187 |
| marker | `LYRA_ENV_REUSE_20261019_2343` |
| SHA-256 | `6bc0dd432585db40a2cb5bc15cdcd09e49740211d39d5f1fd041b77f8204de9c` |

Evidence: `restored-marker.png` shows the command and returned values in the new shell.

## Large-environment comparison

At approximately 23:51 the old UE instance `a60d60d4667e4b99b1811a3a20c2e696` still had no available snapshots in its picker. Its normal confirmation round ended at 22:50 and remained `等快照`. `ue-no-snapshot-after-hour.png` records the empty picker.

The small test proves that the platform snapshot and Resume path can preserve files. It does not prove a size limit, diagnose the large snapshot's failure, or establish that UE has been restored. No 45-minute feature-development timer has started.

## Next attempt

Use the restored small container to prepare the official Linux editor again, inspect archive composition, and avoid snapshotting a redundant installer. Verify the actual editor and project before triggering a fresh confirmation round. A new Claude Code session is required in the resumed container, as documented in the user-provided tutorial.

The three Git baselines and task prompt hashes have been checked. They have no DeepSeek candidate results yet; scores remain unmeasured, not zero.
