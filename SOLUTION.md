# SOLUTION — lyra-death-v1

## 缺陷原因

`Source/LyraGame/Character/LyraHealthComponent.cpp` 中三个函数各注入了一处人工缺陷，均与死亡状态机推进和副作用（标签、委托、网络更新）的触发时机有关：

1. **`OnRep_DeathState`（复制跳过开始阶段）**
   当复制到达的新状态从 `NotDead` 直接跳到 `DeathFinished` 时，原代码只调用 `FinishDeath()`。但函数开头已把 `DeathState` 回退为 `OldDeathState`（此时为 `NotDead`），`FinishDeath` 的守卫 `DeathState != DeathStarted` 会立即返回，导致状态停在 `NotDead`，既没有广播 `OnDeathStarted` 也没有广播 `OnDeathFinished`，标签与网络更新全部丢失。

2. **`StartDeath`（允许重复开始）**
   原守卫只拦截 `DeathFinished`，没有拦截 `DeathStarted`。当已经处于 `DeathStarted` 时再次调用 `StartDeath`，会重复广播 `OnDeathStarted`、重复写入 `Status_Death_Dying` 标签、重复触发 `ForceNetUpdate`。

3. **`FinishDeath`（清除而非置位 Dead 标签）**
   原代码把 `Status_Death_Dead` 的 loose tag 计数写为 `0`，等价于“清除”而非“置位”，导致死亡完成阶段后 Dead 标签未生效。

## 修改点

仅修改了三个函数体，未改动函数签名、头文件、包含项或其他对外接口。

- `StartDeath`：守卫由 `if (DeathState == ELyraDeathState::DeathFinished) return;` 改为 `if (DeathState != ELyraDeathState::NotDead) return;`，确保只允许 `NotDead → DeathStarted`。
- `FinishDeath`：`SetLooseGameplayTagCount(LyraGameplayTags::Status_Death_Dead, 0)` 改为 `... , 1)`，正确置位 Dead 标签。保留原有 `DeathState != DeathStarted` 守卫，即只允许 `DeathStarted → DeathFinished`，且不清除 Dying 标签。
- `OnRep_DeathState`：`NotDead → DeathFinished` 分支由单独调用 `FinishDeath()` 改为依次调用 `StartDeath(); FinishDeath();`，按“开始死亡、完成死亡”顺序执行两次转换，各广播一次 `OnDeathStarted` / `OnDeathFinished`，并完成相应标签与网络更新。

## 验证

### 静态推演（已做）

逐一遍历状态机（枚举 `NotDead=0`、`DeathStarted=1`、`DeathFinished=2`）：

| 场景 | 结果 |
| --- | --- |
| `StartDeath` 于 `NotDead` | 进入 `DeathStarted`，置 Dying=1，广播 `OnDeathStarted` 一次，`ForceNetUpdate` 一次 |
| `StartDeath` 于 `DeathStarted` / `DeathFinished`（重复开始、完成后再次开始） | 立即返回，状态不变，无重复副作用 |
| `FinishDeath` 于 `DeathStarted` | 进入 `DeathFinished`，置 Dead=1，保留 Dying，广播 `OnDeathFinished` 一次，`ForceNetUpdate` 一次 |
| `FinishDeath` 于 `NotDead`（未开始即完成）或 `DeathFinished`（重复完成） | 立即返回，状态不变，无重复副作用 |
| `OnRep`：`NotDead → DeathStarted` | 回退后调 `StartDeath`，一次开始副作用 |
| `OnRep`：`DeathStarted → DeathFinished` | 回退后调 `FinishDeath`，一次完成副作用 |
| `OnRep`：`NotDead → DeathFinished`（跳变） | 依次 `StartDeath` + `FinishDeath`，开始/完成事件各一次，标签与网络更新齐全，`ensureMsgf(DeathState == NewDeathState)` 成立 |
| `OnRep`：本地已领先（`OldDeathState > NewDeathState`） | 提前返回，保留本地阶段，不倒退、不重复广播/写标签 |
| `AbilitySystemComponent == nullptr` | 跳过标签写入，状态推进、委托广播、`ForceNetUpdate` 仍发生（由既有 `if (AbilitySystemComponent)` 守卫与 `Owner` 检查保证） |

以上推演未发现任何路径会重复触发副作用或使最终状态与 `NewDeathState` 不一致。

### 未能完成的验证（如实说明）

本目录不含 Unreal Engine 及完整 Lyra 工程，无法进行真实 UE 编译、运行 UE 自动化测试或验证多机网络复制。我**没有**把普通 C++ 片段检查伪装成 UE 编译通过。上述仅为基于源码的静态推演，真实构建与运行由独立评测端完成。

## 限制

- 未修改 `Source/LyraGame/Character/LyraHealthComponent.h`、`LyraHealthSet.cpp`、`TASK.md`、`task_metadata.json` 等只读文件。
- 未添加替代实现、硬编码结果或改动评测流程/Git 元数据。
- 未提交或推送任何 Git 变更。
- `OnRep_DeathState` 中 `NotDead → NotDead`、`DeathStarted → DeathStarted` 等“同阶段”复制的错误日志分支为上游既有逻辑，非本题缺陷，未做改动。
