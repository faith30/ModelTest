# Lyra 死亡状态修复题：真实 UE Linux 评测

本题让远程 VS Code 中的 Claude 插件使用 `deepseek-v4-pro` 修复三个 Lyra C++ 函数。候选通过 Git 提交冻结，在 Windows 完整 Lyra 工程中使用 UE 5.8.3 和 v26 Linux 工具链交叉编译、cook、stage，再通过 Git/LFS 传到 Linux 容器，运行真实 UE 自动化测试并评分。

**最终实测：`deepseek-v4-pro` 候选 `3daa3a3` 在目标 Linux 容器完成真实 UE 自动化，23/23 通过，100/100 分；人工缺陷 seed `240a1617` 为 7/23 通过、16 项失败，29/100 分。两份结果均为完整、有效的最终 Linux 评测。首轮缺少引擎默认材质导致的启动失败另行保留，不计作模型成绩。**

2026-10-18 的两次正式运行均在 Linux x86_64、非 root UID `996` 下完成，没有超时；候选 UE 进程耗时 `8.582` 秒，seed 为 `8.680` 秒。

| 执行对象 | 有效成绩 | 通过 / 失败 | UE 退出码 | 最终状态 |
| --- | ---: | ---: | ---: | --- |
| 候选 `3daa3a3` | 100/100 | 23 / 0 | 0 | `final_pass` |
| 人工缺陷 seed `240a1617` | 29/100 | 7 / 16 | 255 | `final_test_failure` |

最终结果位于传输仓库 `evidence/linux/candidate/` 和 `evidence/linux/seed/`，本机副本位于 `Saved/LyraEvaluation/linux-runtime-repo/` 下的相同路径。两份 `result.json` 均记录 `valid_evidence=true`、`is_final=true`、`problems=[]`；候选 `final_pass=true`，seed 为 `false`。各目录同时保存 `runtime.json`、`result.md`、完整 `ue-report/index.json` 和实际日志。seed 的包装器退出码 `1` 表示有效报告中的测试失败，符合缺陷对照用途。

已有校准证据位于 `Saved/LyraEvaluation/windows-golden-v2/index.json` 和 `Saved/LyraEvaluation/windows-golden-v2-score/score.json`。后者明确记录 `calibration_only=true`、`is_final=false`、`final_pass=false`，设备为 `WindowsEditor`。该目录属于本机生成文件，不保证随 Git 传输。

移除 `-CookSkipRequests` 后，两份 Linux 构建清单均记录 `build_exit_code=0`、`engine_version=5.8.3`、`target_platform=Linux`。清单保留构建时的 `runtime_validated=false`；它只记录构建证据，后续 Linux 执行由独立的 `runtime.json` 和 `result.json` 证明，不回写构建清单：

| 构建对象 | 本机构建证据 | 构建耗时 |
| --- | --- | ---: |
| 候选 `3daa3a32b5ddbe106d8c997a6e2514df5fdb0e8d` | `Saved/LyraEvaluation/LinuxCandidate-3daa3a3-startup-content-v2/build-manifest.json` | 219.875 秒 |
| 人工缺陷 seed `240a1617ee9ae96eb841114bf79268bdad6d92d0` | `Saved/LyraEvaluation/LinuxSeed-240a1617-startup-content-v2/build-manifest.json` | 185.805 秒 |

两份清单同目录的 `build.log` 保存真实构建输出；清单绑定源码、ELF、启动脚本和构建日志哈希。

首轮候选运行证据位于传输仓库的 `evidence/linux/candidate-attempt-01/`；本机副本为 `Saved/LyraEvaluation/linux-runtime-repo/evidence/linux/candidate-attempt-01/`：

- `runtime.json` 记录实际平台为 Linux x86_64、非 root UID `996`、进程退出码 `139`、耗时 `3.941` 秒且未超时；没有 Automation 完成标记，也没有 `ue-report/index.json`。
- `ue.log` 和 `stdout.log` 记录 `/Engine/EngineMaterials/WorldGridMaterial.WorldGridMaterial` 不存在，随后触发 `GDefaultMaterials[Domain] != nullptr` 断言。首轮 cook 使用 `-CookSkipRequests`，会跳过包含默认材质的启动包收集；当前修正保留 UE 默认启动包收集。
- `result.json` 明确为 `status=runtime_crash_or_error`、`valid_evidence=false`、`is_final=false`、`final_pass=false`。全部 23 项均为缺失，`score=0` 是无效运行的门禁值，不能作为修复能力评分。

修正构建补齐启动内容后，候选与 seed 已分别完成上述有效 Linux 运行。WindowsEditor 参考校准的 23/23 仅作校准，不参与本轮最终成绩。

## 评测边界

- 这是准备脚本注入三处缺陷的人工修复题，`TASK.md` 已明确给出目标函数、状态迁移、标签和回调规格。候选仓库中的 `task_metadata.json` 还通过 `mutation_checks` 提供缺陷 ID 与对应函数等线索，例如 `replication_skips_start`、`start_allows_duplicate`、`finish_clears_dead`。因此本题不是盲测，成绩只反映模型依据这些规格与线索修复本题的表现，不代表综合 UE 开发能力或整体编程能力，也不表示上游 Lyra 原本存在这些缺陷。
- 正式执行对象是完整 Lyra 中编译出的 `ULyraHealthComponent`，测试使用真实 UWorld、Actor、AbilitySystemComponent、GameplayTag、动态委托和网络更新调用。Python 负责准备、启动和解析报告，不替代 UE 行为。
- 真实 UE 自动化共 23 例；其中复制状态通知由测试手动调用 `OnRep_DeathState` 驱动，而非通过网络传输触发。测试验证状态迁移、标签、委托及网络更新调用等副作用，不证明真实网络包传输、多机复制、PIE、游戏画面、动画或完整游戏流程正确。
- Linux 入口是 Development Dedicated Server，使用 NullRHI，不展示 GPU 游戏画面。它与 `Demo/Combat` 的独立 Python 逻辑 demo 是不同的验证路径。
- Windows 运行只能用于校准，已有 WindowsEditor 23/23 不能作为候选的 Linux 最终成绩。正式成绩要求冻结候选的真实 Linux 构建、目标 Linux 运行、完整 23 项报告和一致的退出状态；首轮 Linux 启动失败的无效门禁结果不构成最终分数。

## 文件用途

| 文件 | 用途 |
| --- | --- |
| `prepare.py` | 从完整工程制作仅含题目材料的独立 Git 候选仓库，注入三个缺陷 |
| `task/TASK.md` | 候选仓库根目录 `TASK.md` 的模板，交给模型阅读 |
| `apply_candidate.py` | 从冻结 Git 提交读取源码，验证修改范围，应用到完整评测工程并记录来源 |
| `build_linux.ps1` | 在 Windows 调用真实 RunUAT 构建、cook、stage；成功后生成构建清单 |
| `package_runtime.py` | 将 stage 包压缩分片，附带固定评测脚本、构建清单和 Git/LFS 属性 |
| `extract_runtime.py` | 在非 root Linux 下校验分片、脚本与包内文件，并流式解包到新目录 |
| `run_linux.py` | 在非 root Linux 用户下验证二进制、运行真实 UE、调用固定评分器并生成最终结果 |
| `score_ue_report.py` | 严格解析 UE 的 `index.json`；单独运行它不会执行 UE |
| `tests/test_score_ue_report.py` | 报告解析器测试，不是 UE 行为测试 |

构建端需要 Windows、PowerShell 7、完整 Lyra C++/Content、UE 5.8.3 源码构建环境、`v26_clang-20.1.8-rockylinux8`、Python 3.12+、Git/LFS。容器运行端需要 Linux x86_64、Python 3.12+、Git/LFS、可执行的 stage 包及非 root 用户。解包脚本明确要求 Python 3.12+。容器不需要重新编译整个 UE，也不需要 GPU。

## 1. 准备题目并让模型修复

在评测端运行，`--destination` 必须是尚不存在的新目录：

```powershell
python Benchmarks/LyraDeath/prepare.py `
  --source-root D:\ModelTest `
  --destination '<新的独立候选仓库绝对路径>'
```

保存输出中的 `base_commit`，它是后续 `--seed-sha`。将这个源码题目仓库通过 Git 传到远程容器；不要把完整原版工程、评分器、测试源码或答案混入模型工作目录。

在远程 VS Code 中打开候选仓库，确认 Claude 插件实际选择的模型为 **`deepseek-v4-pro`**，记录模型选择及任务会话。模型名不能仅凭提交说明推断。向插件发送：

```text
请阅读当前仓库根目录 TASK.md，严格按其中要求完成修复并新增 SOLUTION.md。
只使用当前候选仓库材料，不读取外部原版、测试或答案。
如实记录你实际完成的验证，不将未运行的 UE 构建或测试描述为通过。
```

允许修改的源码范围是 `LyraHealthComponent.cpp` 的 `OnRep_DeathState`、`StartDeath`、`FinishDeath` 三个函数体，以及新增 `SOLUTION.md`。以生成的 `TASK.md` 为准。

## 2. 冻结 Git 候选，应用到完整工程

模型结束后，由评测者检查变更并提交。只暂存题目允许的文件：

```bash
git -c core.whitespace=cr-at-eol diff --check
git diff -- Source/LyraGame/Character/LyraHealthComponent.cpp
git add -- Source/LyraGame/Character/LyraHealthComponent.cpp SOLUTION.md
git commit -m "Complete Lyra death-state repair"
git status --porcelain
git rev-parse HEAD
```

题目原 Git blob 保存 CRLF；上面的检查允许 CRLF 行尾，保留候选原始字节，无需为消除 Linux 默认检查的提示而统一换行。要求工作区干净，记录最后输出的完整 40 位候选 SHA，再通过已配置的 Git remote 推送该分支。后续固定使用这个 SHA；模型继续修改后必须形成新的提交和评测记录。

Windows 构建端获取该提交，在**独立的完整 Lyra 评测工作树**应用候选。不要把只有三个源码文件的题目目录当作完整工程：

```powershell
python Benchmarks/LyraDeath/apply_candidate.py `
  --candidate-repo '<已获取冻结提交的候选仓库绝对路径>' `
  --seed-sha '<prepare.py 输出的完整 base_commit>' `
  --candidate-sha '<冻结候选的完整40位SHA>' `
  --project '<包含 Lyra.uproject 的完整评测工程目录>' `
  --output '<新的来源记录JSON绝对路径>'
```

该脚本读取 Git 提交 blob，不执行候选脚本，也不使用未提交的工作区源码。它拒绝越界文件或三个函数体之外的源码改动；目标源码存在无法识别的本地变更时会拒绝覆盖。保存产生的来源记录，并核对其中 `candidate_sha`、`source_sha256` 与后续构建清单一致。

## 3. Windows 真实 UE 交叉编译与打包

以下是脚本的实际参数；替换尖括号占位符。`OutputRoot` 必须不存在，失败后重试也使用新目录：

```powershell
& .\Benchmarks\LyraDeath\build_linux.ps1 `
  -EngineRoot 'C:\Users\huaqijiang\Documents\Study\UE5' `
  -ProjectRoot '<已应用冻结候选的完整评测工程目录>' `
  -ToolchainRoot 'D:\ModelTest\Saved\LyraEvaluation\Toolchains\v26_clang-20.1.8-rockylinux8' `
  -CandidateSha '<冻结候选的完整40位SHA>' `
  -OutputRoot '<新的构建输出目录>'
```

上面的引擎与工具链路径是本机已检查的路径；其他机器需填写自己的实际位置。脚本只在进程范围设置 `LINUX_MULTIARCH_ROOT`，结束时恢复此前值。

脚本调用 `RunUAT.bat BuildCookRun`，目标为 `LyraServer Linux Development`，执行真实 `-build -cook -stage -pak -archive`。Cook 根包为 `/Engine/Maps/Entry` 和 `/Game/DefaultGameData`，保留 UE 默认启动包收集，不使用会跳过这些包的 `-CookSkipRequests`。脚本覆盖 GameInstance 为原生 `LyraGameInstance`、GameMode 为 `GameModeBase`，避免自动进入 Lyra Experience/在线比赛。启动包及依赖包仍由 UE cook 处理，不能据此声称产物只有两个文件。构建并发参数为 `-MaxParallelActions=12`。

成功输出包括：

| 输出 | 含义 |
| --- | --- |
| `build-request.json` | 实际 RunUAT 参数、构建输入和开始时间 |
| `build.log` | 真实构建 stdout/stderr |
| `archive/` | UE 归档的完整 Linux stage 内容 |
| `build-manifest.json` | 构建成功、已定位 ELF 与启动脚本后的证据清单 |

失败写入 `build-failure.json`，不产生成功清单。构建成功只证明该步骤成功，清单中的 `runtime_validated` 仍为 `false`；最终结果由 Linux 包装器产生。`CandidateSha` 是评测者提供的冻结标识，构建脚本本身不替代前一步的 Git 范围和来源校验。

构建清单由评测者的实际构建生成，不能手填成功码或虚构哈希：

| 字段 | 要求 |
| --- | --- |
| `candidate_sha` | 冻结候选的完整 Git 提交 ID；本流程为 40 位 |
| `target_platform` | `Linux` |
| `build_exit_code` | 真实 BuildCookRun 的整数退出码 `0` |
| `engine_version` | 实际引擎版本，本流程为 `5.8.3` |
| `source_sha256` | 实际构建的 `LyraHealthComponent.cpp` 字节 SHA256 |
| `binary_sha256` | 归档内实际 LyraServer ELF 的 SHA256 |
| `binary_relpath` | 相对包含 `LyraServer.sh` 的 stage 根目录，以 `/` 分隔；运行器会验证 |
| `build_log_sha256` | 真实 `build.log` 的 SHA256 |
| `launcher_sha256` | `LyraServer.sh` 的 SHA256；构建脚本生成，运行器核对 |
| `package_root` | 构建机发现的 stage 根目录；传到 Linux 后由 `--package-root` 指定新位置 |

不要改写清单里的 Windows 路径来模拟 Linux 执行。远端路径、实际运行设备与日志记录在独立的 `runtime.json` 中。

## 4. 通过 Git/LFS 传输构建产物

本轮产物和最终证据使用私有仓库 `faith30/ModelTest` 的 `codex/lyra-linux-runtime-3daa3a3` 分支，完整结果提交为 `fa4e775f76b058c7511a73af93abb8a7b9bc8149`。容器仓库位于 `/workspace/LyraLinuxRuntime`；修正后的包分别位于 `candidate-v2/`、`seed-v2/`，构建证据位于 `evidence/candidate-v2/`、`evidence/seed-v2/`，最终运行证据位于 `evidence/linux/candidate/`、`evidence/linux/seed/`。

首轮候选传输提交 `c001e39de063ef8b0a73ffcd6ef2af27d9bbc411` 对应缺少启动内容的旧包；修正后的候选包从提交 `71bb752d6b640e53fdfda307651b58cfd32840a8` 加入。复跑使用 `candidate-v2/` 和 `seed-v2/`，不使用旧的 `candidate/`、`seed/` 包。

源码候选和构建产物都通过 Git 传输。UE 启动需要 ELF、配置、cooked 内容和运行库，不能只传可执行文件。传输仓库或分支由评测者选定，先完成 GitHub 授权，不把令牌写进聊天、命令参数或仓库。

在 Windows 构建端使用构建清单中的实际 `package_root`：

```powershell
python Benchmarks/LyraDeath/package_runtime.py `
  --package-root '<build-manifest.json 中的实际 package_root>' `
  --build-manifest '<本次构建输出>/build-manifest.json' `
  --output '<传输仓库内尚不存在且未被忽略的产物目录>'
```

脚本保留 stage 中的运行文件与调试符号，排除生成的 `Saved` 内容，将 tar.gz 流切成最多 1 GiB 的 `runtime.tar.gz.part0000` 等分片，并生成 `artifact_manifest.json`。它复制 `build-manifest.json`、`run_linux.py`、`score_ue_report.py`、`extract_runtime.py`，为分片、脚本和包内文件记录 SHA256。生成的 `.gitattributes` 将分片交给 LFS，并保护 Python/JSON 文件字节。不要在打包后改写这些文件。真实构建日志和候选来源记录应另行保留；脚本不会自动复制它们。

在传输仓库根目录执行，替换相对目录占位符：

```bash
git lfs install --local
git add -- '<本次产物相对目录>'
git commit -m "Add frozen Lyra Linux evaluation package"
git rev-parse HEAD
git push
```

记录传输提交 SHA，再让容器获取该固定提交。当前项目 `.gitignore` 会忽略 `Saved/` 与 `Binaries/`；选择未被忽略的传输目录，并将生成的 `.gitattributes` 一起提交。确认 Git/LFS 推送完整成功。

在容器中，以非 root 用户使用 Python 3.12+，在获取的传输仓库中执行：

```bash
git lfs pull
git lfs fsck
python3 '<本次产物绝对目录>/extract_runtime.py' \
  --artifact-root '<本次产物绝对目录>' \
  --output '<尚不存在的解包目录绝对路径>'
```

解包脚本校验分片、完整归档、评测脚本和包内文件的哈希，拒绝链接与越界路径，流式解包为 `<解包目录>/LinuxServer`，无需先拼接完整归档。LFS 指针文件不能通过校验。ELF 的执行权限在解包时设置；`LyraServer.sh` 由运行器通过 `sh` 启动。

传输提交及其评测脚本由评测者固定，脚本位于 `LinuxServer` stage 包之外；不要从模型候选目录选择评分脚本。校验清单的可信来源仍是这个固定 Git 提交，而不是哈希自身。

## 5. 在目标 Linux 容器运行并取分

先确认当前终端用户和平台：

```bash
id -u
uname -m
python3 --version
```

实际运行 UE 的用户 ID 必须非 `0`，架构为 `x86_64`。UE 在进入 `main()` 前拒绝 root 运行，包装器会提前报错；应使用容器中的非 root 用户，并确保它能读取包、设置 ELF 执行权限和写入新结果目录。root 终端可使用下方的 `runuser` 命令切换执行用户，不要依靠 `-AllowRoot`。

本次容器已有 `lyra-eval` 用户（UID `996`），两份校验后的 stage 包分别位于 `/workspace/lyra-runner/candidate-package-02/LinuxServer` 和 `/workspace/lyra-runner/seed-package-02/LinuxServer`。已完成的运行结果保存在 `/workspace/lyra-runner/candidate-result-02` 和 `/workspace/lyra-runner/seed-result-02`。

需要复跑时，可在该容器的 **root 终端**复制以下命令。它们通过 `runuser` 切换为 `lyra-eval` 执行；要求 Python 3.12+、上述包和固定脚本仍在原位置，且 `lyra-eval` 对 `/workspace/lyra-runner` 有写权限。输出使用尚不存在的新目录 `candidate-result-03`、`seed-result-03`；若已存在，改用新的目录名，不覆盖已保存证据：

```bash
runuser -u lyra-eval -- python3 /workspace/LyraLinuxRuntime/candidate-v2/run_linux.py \
  --package-root /workspace/lyra-runner/candidate-package-02/LinuxServer \
  --build-manifest /workspace/LyraLinuxRuntime/candidate-v2/build-manifest.json \
  --output /workspace/lyra-runner/candidate-result-03 \
  --score-script /workspace/LyraLinuxRuntime/candidate-v2/score_ue_report.py \
  --timeout 300
```

```bash
runuser -u lyra-eval -- python3 /workspace/LyraLinuxRuntime/seed-v2/run_linux.py \
  --package-root /workspace/lyra-runner/seed-package-02/LinuxServer \
  --build-manifest /workspace/LyraLinuxRuntime/seed-v2/build-manifest.json \
  --output /workspace/lyra-runner/seed-result-03 \
  --score-script /workspace/LyraLinuxRuntime/seed-v2/score_ue_report.py \
  --timeout 300
```

复跑验收以新目录的 `result.json` 为准：候选应为 `final_pass`、100 分、23 项通过，命令退出 `0`；seed 应为 `final_test_failure`、29 分、7 项通过和 16 项失败，命令退出 `1`。seed 的这个非零退出码是有效缺陷对照的正常结果；两份结果都应满足 `valid_evidence=true`、`is_final=true`、`problems=[]`。

将下面路径替换为容器中的真实绝对路径。使用刚校验过的产物目录中的固定评测脚本；输出目录必须是新目录，且在 stage 包之外：

```bash
python3 '<本次产物绝对目录>/run_linux.py' \
  --package-root '<解包目录绝对路径>/LinuxServer' \
  --build-manifest '<本次产物绝对目录>/build-manifest.json' \
  --output '<本次尚不存在的结果目录>' \
  --score-script '<本次产物绝对目录>/score_ue_report.py' \
  --timeout 180
```

`--score-script` 可省略，默认使用 `run_linux.py` 同目录的固定评分器。包装器通过 `sh LyraServer.sh` 运行真实服务器，指定 Entry + 原生 GameMode、NullRHI、绝对日志/报告路径，以及：

```text
Automation RunTests StartsWith:Lyra.Benchmark.Death; Quit
```

这里的 `Quit` 属于 Automation 内部队列，会等待测试完成；不是另一个引擎级立即退出命令。超时时包装器终止整个进程组。

| 结果文件 | 用途 |
| --- | --- |
| `result.json`、`result.md` | **最终运行门禁结果**，含总分、分组分数、逐项状态和无效原因 |
| `runtime.json` | 实际命令、Linux uname、UID、退出码、时间、超时标记及输入/日志哈希 |
| `stdout.log`、`ue.log` | 实际进程输出与 UE 日志；启动失败时 UE 日志可能不存在 |
| `ue-report/index.json` | UE Automation 写出的原始报告；缺失则评测无效 |
| `build-manifest.json` | 本次运行保存的构建清单副本 |
| `scorer.log`、`report-score/` | 固定评分器输出与诊断；不能绕过根目录 `result.json` 的运行校验 |

包装器退出码：`0` 为有效且全部通过，`1` 为有效报告中的测试失败，`2` 为运行或证据无效。完整测试失败时 UE 自身可能退出 `255`；只有完整 23 项报告、相应失败状态和 `TEST COMPLETE ... -1` 标记一致时，才接受有效部分分数。崩溃、超时、零测试、缺项、重复、跳过、非 Linux 报告或哈希不匹配，都不能产生有效成绩。

## 评分规则

| 组 | 用例数 | 满分 | 验证重点 |
| --- | ---: | ---: | --- |
| `DirectFinished` | 4 | 20 | 直接收到完成状态时，开始与完成阶段的顺序和副作用 |
| `StepSequence` | 4 | 20 | 正常分阶段通知和本地/回调操作组合 |
| `Idempotence` | 5 | 20 | 重复及越序调用不产生重复副作用 |
| `PredictionAhead` | 5 | 20 | 本地预测领先时不倒退 |
| `ASCNull` | 5 | 20 | ASC 为空时仍保持合法生命周期行为 |
| 合计 | 23 | 100 | 本人工任务的限定行为 |

每组 20 分在组内均分，组分保留两位小数后求和；不是每个用例统一 `100/23` 分。只有完整、有效的 Linux 执行证据才得到正式分数。`observed_case_score` 和无效报告中的分组观察值仅供诊断。

模型来源、Git 冻结、源码应用、构建与运行证据应由可信评测流程保存。哈希用于绑定文件和发现变化，本身不能独立证明模型身份、源码到二进制的真实性或远程执行。
