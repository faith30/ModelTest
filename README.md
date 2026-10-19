# Lyra 三题：DeepSeek 远程开发与无窗口 UE 验证

三份起点已通过 Git / Git LFS 发布，使用原 GPT 六场评测的相同单根起始提交。它们是待实现的题目，不是已经完成的游戏 Demo。

| 题目 | 远程起点分支 | 固定起点 |
| --- | --- | --- |
| 交互、拾取与背包 | `codex/deepseek-start-interaction` | `dcba4d7625373ed1f128af1de54e4e376b0fb4af` |
| 击杀荣誉与播报 | `codex/deepseek-start-accolades` | `3da5f9f5f11f7efb162ef91307a3f19c2ca5de74` |
| 脚步与上下文效果 | `codex/deepseek-start-context-effects` | `6763942e663c5549e0bfff30cb1372ce31e6094c` |

本工具分支是 `codex/deepseek-feature-kit`。它只包含操作工具和说明，不包含 UE 引擎，也不包含其他模型答案。

## DSBenchV2 教程补充（2026-10-19）

依据用户提供的《DSBenchV2平台使用教程》1.1–2.2 节，平台的正式保存与恢复流程如下：

1. 上传文件、安装依赖或完成环境修改后，在 CC 中发送并完成一轮环境确认消息，触发快照。快照包含文件、依赖及磁盘状态，不包含进程内存；本工具不把手动 `snap` 返回编号视为恢复验证。
2. “等快照”按教程可能持续 1–60 分钟，短时间空列表不能判定快照丢失。等待过长可按教程 Q&A 通过平台右下角气泡反馈；本工具不会自行发送客服消息。
3. 容器默认两小时到期，可从“我的容器 → 历史容器 → 更多操作 → Resume”恢复。教程未要求先安装 `snapcode` CLI。恢复后必须新建 CC session，旧 session 的后续轮次不能用于保存新测试快照。
4. 环境确认轮之后，再发送不依赖前文的任务 Prompt。编排测试选择后面的任务轮次，平台使用它的**前一轮快照**；选第一轮会从空工作区开始。下文手动 45 分钟计时不替代平台 Rollout。
5. Code Grade 的脚本须将结果写入 `/eval/code_result.json`，仅含 `resolved`、`score`（0–1）、`reason`（字符串）。额外测试附件挂载到只读 `/test_files/`，教程规定小于 1 MB。

教程还要求最终测试数据独立原创，并限制基于外部公开仓库改题。现有 Lyra 基线保留为技术验证和内部对比用途；未确认符合原创性要求前，不应将它标为可正式提交的样例。本次没有更换题目或修改评分标准。

2026-10-19 23:35（北京时间）的历史复查：`a60d60d4` 已停止，历史容器 Resume 未启动新环境，可选快照仍为空；22:50 的 CC 确认轮仍在“等快照”，当时约等待 45 分钟，尚处于教程给出的窗口内。当时实际引擎恢复未验证，正式计时未开始。详见 [续用记录](evidence/2026-10-19-linux-lyra-a60d60d4/environment-reuse.md)。

## 当前状态与内存限制

**2026-10-20 01:51（北京时间）更新：本轮容器 `8e3c3ace` 已由平台标为 `stopped`，快照恢复列表仍为空。** 下述构建和加载是停止前的已验证结果，不能视为当前仍有可用运行环境。三道正式题未启动、没有新分数。详见[停止及恢复状态证据](evidence/2026-10-20-lean-editor-8e3c3ace/RESULTS.md)。

2026-10-20 本轮容器为 `8e3c3aceaa504364833a5085188dff19`。官方 UE 5.8.3 仅省略 `.debug/.sym`，interaction 固定基线及 8689 个 LFS 文件已恢复并校验。使用 **1 GiB .NET GC 堆上限**的 build-02 完成 61/61 项，退出 0，481.096 秒，GNU time 最大 RSS 1664152 KiB；随后 load-01 退出 0，36.758 秒，最大 RSS 2256388 KiB。两步 `oom/oom_kill` 增量均为 0，整容器采样仍接近或达到 4 GiB。重试可能复用缓存，不是全新冷构建。[本轮构建、加载与范围说明](evidence/2026-10-20-lean-editor-8e3c3ace/RESULTS.md)。**这只证明固定 interaction 基线的真实构建、模块及指定资源加载，不证明三题功能正确；正式计时尚未开始，没有功能分数。**

本轮 cgroup 已记录 `cpu.max=200000 100000`（2 CPU 配额）、`memory.max=4294967296`（4 GiB）、`memory.swap.max=0`（不能使用 swap）。CLI `aaa514c7` 与插件 `d5bee8fd` 均有本地 `turn-end` 和 snapshot ID，但截至 [2026-10-20 01:38（北京时间）的平台截图](evidence/2026-10-20-lean-editor-8e3c3ace/platform-no-engine-snapshot-0138.png)，首轮 CLI 确认后等待已超过 60 分钟，仍无可用的含引擎快照；恢复尚未验证，本地触发不能当作已完成备份。CLI 只读确认和后续同 UUID 续聊的实际消息均已核对一致，指定 Read/Edit/Bash 自检成功；插件本次粘贴则丢失换行。完整正式 Prompt、各题操作和平台恢复的范围边界见 [MODEL_SESSION.md](MODEL_SESSION.md)。

历史容器 `a60d60d4` 于 2026-10-19 22:27（北京时间）完成过 interaction 基线构建和加载：第三轮采用当时的 512 MiB 堆配置与 `--unity-bytes 131072`，49 个构建动作完成，退出 0，406.192 秒；加载退出 0，51.396 秒，最大 RSS 分别为 1613620 和 1874492 KiB，`oom/oom_kill` 增量均为 0。[历史原始证据](evidence/2026-10-19-linux-lyra-a60d60d4/)。旧轮次默认 PCH 曾出现容器 OOM，低内存第二轮由操作方中止，第三轮复用缓存；其最小探针退出 0、8.32 秒。这些历史结果不代表当前容器、冷构建或三题功能均通过。

历史证据：2026-10-19 19:27（北京时间）曾在旧容器以非 root 用户完成 **真实 UE 5.8.3 最小无窗口编辑器探针**：退出 0，耗时 9.572 秒，GNU time 最大 RSS 993032 KiB（约 970 MiB），cgroup 的 `oom/oom_kill` 增量均为 0。[完整结果](evidence/2026-10-19-linux-editor/result.json)、[UE 日志](evidence/2026-10-19-linux-editor/ue.log)和[内存记录](evidence/2026-10-19-linux-editor/memory.txt)已随本分支保存。约 970 MiB 是该命令的 RSS 指标，不是整容器总量；容器总量含后台服务和文件缓存，采样曾接近 4 GiB。第一次探针因缺系统动态库退出 127，补齐依赖后重测成功；两次均未观察到 OOM 增量。

**当前容器的编译和加载结论以本轮证据为准；上述历史探针和历史基线验证均不等于三题功能验收。** 旧容器 `25343ccf` 已停止且无可恢复快照，后续新建或恢复容器仍需重新核对实际文件、登录和运行状态，不能依据旧结果直接开始计时。结束容器前应把所需代码和证据保存到 Git。

### 每次进入或恢复容器后先检查

先在平台确认当前容器处于运行状态，核对容器标识。以下是约定路径的只读检查；缺工具、认证失效、引擎文件缺失或项目目录不存在时，先按后续步骤恢复，再运行 UE：

```bash
git --version
git lfs version
gh auth status --hostname github.com
test -f /workspace/UE_5.8.3/Engine/Build/Build.version
test -x /workspace/UE_5.8.3/Engine/Binaries/Linux/UnrealEditor
test -f /workspace/lyra-runs/interaction-deepseek-r1/Lyra.uproject
```

这些检查不启动 UE，也不开始模型计时。下载文件存在不等于解压、依赖和引擎版本检查通过；是否需要重新认证以当前账户的 `gh auth status` 为准。

无窗口模式仍是真实 UE：Linux Editor 加 `-unattended -nullrhi -nosound` 可以执行适用的 commandlet、资源脚本与 Automation。它节省渲染开销，但不消除编译器、链接器、编辑器和资源加载的内存需求。4 GiB 不作为脚本的硬性拒绝条件；是否足够须由实际启动、构建和内存峰值证明。不能把没有启动 UE 的测试替身算作 UE 验证。

优先安装匹配版本的 Linux **预编译 Editor**，再编 Lyra 项目。当前 Windows 引擎和 Windows-host 的 `clang++.exe` 不能直接在 Linux 运行。2026-10-19 已在官方账户下载页确认 `Linux_Unreal_Engine_5.8.3.zip`，标注约 37.08 GB，上传日期 2026-09-22。安装后仍需检查 PythonScriptPlugin、EditorScriptingUtilities、BlueprintEditorLibrary/UMG 工具是否齐全；不要假定预编译包包含全部实验插件。

- [官方 Linux 安装说明](https://dev.epicgames.com/documentation/en-us/unreal-engine/linux-development-quickstart-for-unreal-engine)
- [官方 Linux 下载](https://www.unrealengine.com/en-US/linux)
- [官方硬件与工具链要求](https://dev.epicgames.com/documentation/en-us/unreal-engine/linux-development-requirements-for-unreal-engine)

## 1. 在容器拉取题目

以下命令在容器终端执行，需先安装 Git、Git LFS、GitHub CLI 和 Python 3.9 或更新版本。已有有效 GitHub 授权时直接使用，不要把令牌写入命令、聊天或仓库。如果新容器尚未授权，先运行 `gh auth login --hostname github.com --git-protocol https --web` 并在浏览器完成确认。下面的 clone 适用于工具目录尚不存在的情况；目录已存在时先核对其来源和本地改动，再使用 `git -C /workspace/lyra-feature-kit pull --ff-only` 更新工具。

```bash
gh auth setup-git
git clone --single-branch --no-tags --branch codex/deepseek-feature-kit \
  https://github.com/faith30/ModelTest.git /workspace/lyra-feature-kit
python3 /workspace/lyra-feature-kit/suite.py prepare interaction \
  --root /workspace/lyra-runs --name deepseek-r1
```

脚本下载真实 LFS 资源，核验固定 SHA、单根历史、资源完整性和题目文件，创建结果分支，并移除工作副本的 origin。失败会保留目录；解决原因后使用新的 `--name`，不删除已有工作。准备不启动模型，也不开始计时。

另外两题把 `interaction` 换成 `accolades` 或 `context-effects`。建议每个容器只运行一题：平台容器本次有效期约两小时，三题各 45 分钟再加环境准备无法放在同一窗口内。容器结束前提交代码、资源和日志到 Git。

## 2. 先把真实 UE 环境跑通

把 Linux UE 5.8.3 解压在 `/workspace/UE_5.8.3`。目录下应直接包含 `Engine/Build/Build.version`。按该包官方说明准备原生 Linux 工具链；本题需要 v26 / clang 20.1.8。编辑器安装与基线预热放在模型的 45 分钟计时之前。

**引擎不必每次重新下载。** 已保留完整的解压目录时，核实版本、权限和依赖后直接使用；只保留官方 ZIP 时重新解压即可。只有新容器中两者都未保留、也没有其他可访问的副本时，才需要重新下载。项目代码与资源通过 Git / Git LFS 传输，本工具仓库不包含官方 UE 引擎。平台快照能否保存并恢复引擎仍需实际验证；创建请求返回 `ok` 或快照 ID，不足以证明它已成为可恢复的引擎备份。

本轮安装包实测为 39818576005 字节（约 37.08 GiB），解压目录约 71.68 GiB，这是磁盘体积，并非运行内存。当前 Debian 13 容器已补齐以下运行库；新容器仍需检查发行版和实际 `ldd` 缺失项，再安装适用的软件包。三个测量运行器还要求 GNU `/usr/bin/time`，下面一并安装 `time` 包：

```bash
apt-get install -y time libglib2.0-0t64 libnss3 libnspr4 libsm6 libice6 \
  libdbus-1-3 libatk1.0-0t64 libatk-bridge2.0-0t64 libdrm2 libx11-6 \
  libxcomposite1 libxdamage1 libxext6 libxfixes3 libxrandr2 libgbm1 \
  libxcb1 libxkbcommon0 libpango-1.0-0 libcairo2 libasound2t64
```

UE 必须以非 root 用户运行。若当前终端是 root，可建立专用用户；以下目录必须先存在，且只调整本次工程和引擎目录的属主：

```bash
id -u lyra-eval >/dev/null 2>&1 || useradd -m -d /workspace/lyra-home -s /bin/bash lyra-eval
chown -R lyra-eval:lyra-eval /workspace/UE_5.8.3 /workspace/lyra-runs/interaction-deepseek-r1
install -d -o lyra-eval -g lyra-eval /workspace/lyra-results

runuser -u lyra-eval -- python3 /workspace/lyra-feature-kit/headless_ue.py doctor \
  --engine /workspace/UE_5.8.3 \
  --project /workspace/lyra-runs/interaction-deepseek-r1/Lyra.uproject
```

若你已使用非 root 用户登录，直接执行 Python 命令，不需要 `runuser`。Git 操作也应使用工程属主账户，避免 Git dubious-ownership；不要通过全局 `safe.directory=*` 关闭保护。专用用户需要自己的 Git 登录时，用该用户的正常 GitHub 授权流程。

`doctor` 只检查文件和环境，不证明 UE 已经启动。下文的 `run_lyra_build.py` 复用 `headless_ue.py build` 调用真实 `Build.sh`，默认单并发，并额外记录内存证据。缺引擎、版本不匹配或 root 运行会明确拒绝；环境依赖缺失、已确认的 OOM 和超时需与源码编译错误分别记录，不能直接混入模型功能得分。

### 先做最小编辑器启动探针

执行以下命令。它只打开最小纯内容项目并查询真实引擎版本及 Python API，不编译 Lyra、不修改资产、不计分。运行器复制模板，使编辑器缓存写到独立输出位置，并限制运行时间为 300 秒。

```bash
runuser -u lyra-eval -- python3 /workspace/lyra-feature-kit/run_editor_probe.py \
  --engine /workspace/UE_5.8.3 \
  --output /workspace/lyra-results/editor-probe-01
```

同时检查运行器退出码为 0、结果通过，以及 `probe.json` 的 `status=completed`、`executed_in_real_unreal=true`。原始 UE 日志、退出码、超时信息和内存诊断会保存在输出目录。cgroup 采样包括容器内其他进程和文件缓存；`memory.peak` 是容器生命周期峰值。不能把这些数值当作 UE 独占内存，也不能仅凭退出 137 判定 OOM。需比较运行前后 `memory.events` 的 `oom/oom_kill` 增量；超时或强杀时 GNU time 的最终 RSS 文件可能不完整。

最小模板只启用 PythonScriptPlugin 和 EditorScriptingUtilities。原始 Lyra 起点还启用了 AIAssistant、ToolsetRegistry、AllToolsets 等插件；应检查官方包中这些插件和递归依赖是否齐全。可选 API 的 `hasattr=false` 也可能是插件未加载，不能直接证明包缺文件。不要静默禁用原始起点插件后仍声称环境一致。

### 再构建真实 Lyra 基线

最小探针成功不证明 Lyra 构建或完整场景在 4 GiB 内能完成。确认插件齐全后再构建，避免与下载、解压等大任务同时进行。下面是通用调用；本测试的 4 GiB 容器请使用下一节已实测的低内存配置，默认 PCH 构建曾出现内存问题：

```bash
runuser -u lyra-eval -- python3 /workspace/lyra-feature-kit/run_lyra_build.py \
  --engine /workspace/UE_5.8.3 \
  --project /workspace/lyra-runs/interaction-deepseek-r1/Lyra.uproject \
  --output /workspace/lyra-results/interaction-baseline-build-01 \
  --timeout 3600
```

这是完整 `LyraEditor Linux Development` 目标的构建调用，可能复用已有构建缓存，并非只编探针或测试替身。`-MaxParallelActions=1` 只限制构建动作并发；单个编译或链接任务仍可能超过可用内存。默认超时 3600 秒，超时会对本次进程组发送 TERM/KILL。输出目录必须不存在。

检查命令退出码、`result.json` 的 `passed`、`run.exit_code`、超时和启动错误，再阅读 `stdout.log` 中的编译结果。构建证据包括 `doctor.json`、`run.json`、`result.json`、`stdout.log`、`exit-code.txt`、`memory.txt`、`memory-samples.jsonl`、`cgroup-before.json` 和 `cgroup-after.json`。构建通过只证明该次目标构建调用成功，不代表游戏运行或功能验收通过；内存采样的范围与局限同最小探针，不能仅凭 137 判定 OOM。

### 本轮通过的 4 GiB 构建配置

保留上一轮日志，确认没有其他构建任务仍在运行，再使用新的输出目录重试：

```bash
runuser -u lyra-eval -- env \
  DOTNET_gcServer=0 \
  DOTNET_GCHeapHardLimit=0x40000000 \
  DOTNET_GCConserveMemory=7 \
  python3 /workspace/lyra-feature-kit/run_lyra_build.py \
  --engine /workspace/UE_5.8.3 \
  --project /workspace/lyra-runs/interaction-deepseek-r1/Lyra.uproject \
  --output /workspace/lyra-results/interaction-baseline-build-lowmem-01 \
  --no-pch --no-shared-pch --no-uba --unity-bytes 131072 --timeout 1800
```

`0x40000000` 为 1 GiB，限制的是 .NET GC 管理的堆，并非整个 UBT 进程的 RSS，更不限制 Clang、链接器或整容器总内存。2026-10-20 的新容器使用旧的 512 MiB 堆上限时出现 `System.OutOfMemoryException`；改用上述 1 GiB 配置后完成 61/61 项，退出码 0，耗时 481.096 秒，OOM / OOM kill 增量为 0。见[本次构建与加载证据](evidence/2026-10-20-lean-editor-8e3c3ace/RESULTS.md)。这是 interaction 基线重试的结果，可能复用此前缓存，不保证其他题目、候选或后台负载下同样成功。

`--no-pch` 绕过全部预编译头，`--no-shared-pch` 显式禁用共享预编译头；UE 5.8.3 的 `--no-uba` 只关闭 detour，仍可能使用 UBAExecutor。

运行器会在测量记录中保存追加参数后的完整构建命令，`build_environment` 仅记录上述三个 DOTNET 环境变量。仍按本次实际退出码、日志和 cgroup 增量判定结果，不将重试配置本身视为通过证据。

`--unity-bytes 131072` 对应真实 UBT 参数 `-BytesPerUnityCPP=131072`，把默认约 384 KiB 的源码合并目标缩到 128 KiB；它不是内存硬上限，可能增加编译动作。2026-10-19 旧容器第三次实测也复用了前两轮留下的缓存。操作方中止的轮次须保留原因，不能仅凭中止退出码认定源码错误、容器 OOM 或自动超时。构建运行器还会清理另建进程组的后代；假子进程自检不属于 UE 功能测试。

### 构建通过后加载真实 Lyra 项目

下面的探针直接打开刚编译的真实 `Lyra.uproject`，不使用最小模板。当前固定检查的是 **interaction 基线** 的模块和指定资源，不能直接当作另外两题的验收器：

```bash
runuser -u lyra-eval -- python3 /workspace/lyra-feature-kit/run_lyra_probe.py \
  --engine /workspace/UE_5.8.3 \
  --project /workspace/lyra-runs/interaction-deepseek-r1/Lyra.uproject \
  --output /workspace/lyra-results/interaction-baseline-probe-01 \
  --timeout 600
```

它核对真实 UE 版本、进程及项目目录，验证 `LyraGame`、`LyraEditor` 动态库的 SHA-256 和进程可执行映射，加载 `LyraGameplayAbility_Interact` 原生类，以及 `DefaultGameData`、`GA_Interact`、`L_InventoryTestMap` 三个指定资源。只加载并回读，不保存资源、不激活 Experience，也不执行拾取、背包或多人对局玩法。

检查运行器退出码为 0、`result.json` 的 `passed=true` 与 `probe_validation.valid=true`，以及 `probe.json` 的 `status=completed`、`executed_in_real_unreal=true`。输出保留模块路径/哈希、指定资源加载结果、生成的探针脚本、`ue.log`、`stdout.log`、退出码和同样的内存诊断；缺库、加载失败、证据不一致、非零退出或超时均不会通过。默认超时 600 秒，必须使用新的输出目录。

| 工具 | 实际验证范围 | 不能据此认定 |
| --- | --- | --- |
| `run_editor_probe.py` | 最小纯内容项目启动、Python API 暴露 | Lyra 已编译或已加载 |
| `run_lyra_build.py` | 完整 LyraEditor 目标的真实构建结果 | 运行时功能正确 |
| `run_lyra_probe.py` | 真实 interaction 基线模块和指定资源加载 | 关卡玩法、Experience、多人、UI/视听表现或三题得分 |

本节提供可复跑步骤；当前容器完整 Lyra 构建及加载的已验证结果见前文证据。正式开始计时前，应确认本次容器可持续运行，并保存构建、加载和所需资源工具验证结果。2026-10-19 的环境续用阻塞及平台核查信息见 [environment-reuse.md](evidence/2026-10-19-linux-lyra-a60d60d4/environment-reuse.md)。

## 3. 开始一题并记录时限

### 开始计时

只有基线构建和所需资源工具验证成功、容器剩余时间足够且环境可恢复后，才开始正式计时。VS Code 只打开这一题的目录，不把其他候选、原工程或评估器一起打开。在新建或恢复的容器中选择 `deepseek-v4-pro` 并开启全新会话，先做环境确认轮并核验快照，再在同一会话发送完整任务轮。平台从任务轮的前一轮快照恢复环境，不能把新会话的第一轮直接作为正式测试。记录平台实际支持的推理档位，不假定它与 GPT 的 high 等价。

正式冻结 Prompt 优先经 CLI 监督器的 stdin 传输。同 UUID 续聊及指定 Read/Edit/Bash 环境自检已通过，实际参数和仍待逐题验证的范围见 [MODEL_SESSION.md](MODEL_SESSION.md)。以下 `suite.py start` 仅是人工计时路线；它与 CLI 监督器是两个独立时钟，不会自动同步。插件本次粘贴曾丢失全部换行，因此无论采用哪个入口，都须保存实际 session user 消息及其哈希，不能只保存源文件哈希。

```bash
python3 /workspace/lyra-feature-kit/suite.py start /workspace/lyra-runs/interaction-deepseek-r1
cat /workspace/lyra-runs/interaction-deepseek-r1.prompt.txt
```

把经核验的 Linux 环境说明与显示的完整冻结提示词合并后发给模型，并保留实际文本及哈希。`start` 记录 45 分钟截止时间，**不会自动停止插件**；组织者需到点停止并保存会话日志。CLI 监督器与插件的进程边界不同，当前验证范围见 [MODEL_SESSION.md](MODEL_SESSION.md)，不能将 CLI 自测当作插件已受自动监督。只准备环境或事后评估时不要启动模型计时。

`original-prompts/` 保留原 Windows 提示词供组织者复核；实际 Linux 提示词保留原题全文，但明确 Linux 环境和人工计时。新环境没有旧 Windows 预热 DLL，工具条件不同，因此不直接与旧分数作严格模型排名。无 remote 也不等于操作系统隔离。

## 4. 无窗口 Automation

在冻结候选的独立评估副本中重新构建，然后使用**已注册且已核对的测试过滤器和预期用例数量**：

```bash
# 先填写真实测试过滤器和用例数；下面不会自动选择测试或生成满分。
export UE_TEST_FILTER='替换为已注册的真实测试前缀'
export UE_TEST_COUNT='替换为正整数'
python3 /workspace/lyra-feature-kit/headless_ue.py automation \
  --engine /workspace/UE_5.8.3 \
  --project /path/to/frozen-evaluator/Lyra.uproject \
  --filter "$UE_TEST_FILTER" --expected-count "$UE_TEST_COUNT" \
  --output /workspace/lyra-results/interaction-automation-01
```

上面的 Automation 命令是运行器模板，**不是三题已移植完成的功能验收套件**。原 Windows 评估夹具仍需适配 Linux，且须针对候选实际接口校核；不能把本题基线自检 `Benchmarks/tools/verify_assets.py` 当作功能测试，也不能把上一轮 LyraDeath 的 23 项测试用于这三题。

输出包含 `doctor.json`、`run.json`、`stdout.log`、`ue.log`、UE `report/index.json` 和 `result.json`。脚本拒绝复用输出目录；零匹配、数量不符、缺报告、失败、未完成、非零进程退出和超时均不会通过。这里不自动计算三题的 100 分。

蓝图编译、实际资产保存和独立回读要分别留证。单纯文件存在、生成脚本或 C++ 编译成功不足以证明资源功能完成。实际多人网络、UI 焦点、画面、音效与特效显示不由 NullRHI 自动化替代。最终逐项标注通过、失败、未验证和环境阻塞。

## 5. 保存结果到 Git

模型应在预算内提交本题相关的代码和真实资源，结束后由组织者检查 `git diff`、停止边界和最终 SHA 并传输。截止后不得让模型继续修改或补提交；若存在未提交改动，只能如实保存截止状态并明确标为组织者归档，不冒充模型按时提交。不要 `git add .` 把无关文件全部加入。使用该工程属主账户执行：

下列 `suite.py submit` 要求事前已执行 `suite.py start`。只使用 CLI 监督器而未启动 suite 计时的轮次，应由组织者按冻结 SHA 另行通过 Git 传输，不能事后补写起始时间；若事前同时使用两者，须保留两个时钟的偏差。

```bash
python3 /workspace/lyra-feature-kit/suite.py status /workspace/lyra-runs/interaction-deepseek-r1
# 在工程中 git add 明确的文件，然后 git commit。
python3 /workspace/lyra-feature-kit/suite.py submit /workspace/lyra-runs/interaction-deepseek-r1
```

结果分支为 `codex/deepseek-interaction-deepseek-r1`，其他题同理。工具不会替你暂存或提交，也不会强制推送；工作区不干净、改题目/基线文件、非原起点衍生或远端分叉时拒绝。提交完成只表示传输完成，不表示 UE 通过。旁边的 `.session.json` / `.result.json` / `.prompt.txt` 应由组织者另存为评估证据。

## 工具自身验证

`test_suite.py` 使用本地临时 Git/LFS 仓库验证下载、计时保护、题目保护、脏工作区拒绝、普通推送和非快进拒绝。它验证的是传输工具，不是 Lyra 功能。

`headless_ue.py` 已使用已有真实 UE 报告验证成功/失败解析及零项、计数不符、重复名、缺报告等拒绝路径。报告解析自检与 UE 实际执行是两类证据；旧容器最小 Linux Editor 的历史实测见上面的证据目录，新容器环境需重新核实，三题完整功能验收仍未进行。
