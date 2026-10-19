# Lyra 三题：DeepSeek 远程开发与无窗口 UE 验证

三份起点已通过 Git / Git LFS 发布，使用原 GPT 六场评测的相同单根起始提交。它们是待实现的题目，不是已经完成的游戏 Demo。

| 题目 | 远程起点分支 | 固定起点 |
| --- | --- | --- |
| 交互、拾取与背包 | `codex/deepseek-start-interaction` | `dcba4d7625373ed1f128af1de54e4e376b0fb4af` |
| 击杀荣誉与播报 | `codex/deepseek-start-accolades` | `3da5f9f5f11f7efb162ef91307a3f19c2ca5de74` |
| 脚步与上下文效果 | `codex/deepseek-start-context-effects` | `6763942e663c5549e0bfff30cb1372ce31e6094c` |

本工具分支是 `codex/deepseek-feature-kit`。它只包含操作工具和说明，不包含 UE 引擎，也不包含其他模型答案。

## 当前状态与内存限制

旧容器 `25343ccf` 已停止且无可恢复快照。新容器 `a60d60d4` 已完成 GitHub 认证、官方 UE 5.8.3 下载与解压，并恢复精确 interaction 基线及 8689 个 LFS 文件。当前容器的最小真实 UE 无窗口探针已通过：退出 0，8.32 秒，GNU time 最大 RSS 1178120 KiB，OOM 增量为 0。完整 Lyra 默认单并发构建在 SharedPCH 阶段失败，退出 6，146.822 秒，编译器被信号 9 终止，同时 cgroup 的 `oom` 增加 2、`oom_kill` 增加 1。低内存第二轮推进到 19/54 后因持续内存压力，由操作方中止以缩小编译批次；该轮没有新增 OOM，不能记为源码编译失败或超时。[本轮原始证据](evidence/2026-10-19-linux-lyra-a60d60d4/)。**完整 Lyra 构建和加载仍未验证通过，模型计时尚未开始。**

新容器已实测 `cpu.max=200000 100000`（2 CPU 配额）、`memory.max=4294967296`（4 GiB）、`memory.swap.max=0`（不能使用 swap）。平台手动 `snap` 已返回 `ok=true` 及快照编号，但刷新后快照列表仍显示没有可用快照，尚未验证引擎恢复成功，不能把它当作已经完成的备份。结束容器前应把所需代码和证据保存到 Git。

历史证据：2026-10-19 19:27（北京时间）曾在旧容器以非 root 用户完成 **真实 UE 5.8.3 最小无窗口编辑器探针**：退出 0，耗时 9.572 秒，GNU time 最大 RSS 993032 KiB（约 970 MiB），cgroup 的 `oom/oom_kill` 增量均为 0。[完整结果](evidence/2026-10-19-linux-editor/result.json)、[UE 日志](evidence/2026-10-19-linux-editor/ue.log)和[内存记录](evidence/2026-10-19-linux-editor/memory.txt)已随本分支保存。约 970 MiB 是该命令的 RSS 指标，不是整容器总量；容器总量含后台服务和文件缓存，采样曾接近 4 GiB。第一次探针因缺系统动态库退出 127，补齐依赖后重测成功；两次均未观察到 OOM 增量。

**历史探针只证明当时的最小项目能启动，不证明当前容器已就绪，也不证明完整 Lyra 构建、加载或三题功能验收通过。** 旧容器中曾准备好的 `interaction-deepseek-r1` 同样需要在新容器重新核实或拉取，不能据旧状态直接开始计时。

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

最小探针成功不证明 Lyra 构建或完整场景在 4 GiB 内能完成。确认插件齐全后再构建，避免与下载、解压等大任务同时进行：

```bash
runuser -u lyra-eval -- python3 /workspace/lyra-feature-kit/run_lyra_build.py \
  --engine /workspace/UE_5.8.3 \
  --project /workspace/lyra-runs/interaction-deepseek-r1/Lyra.uproject \
  --output /workspace/lyra-results/interaction-baseline-build-01 \
  --timeout 3600
```

这是完整 `LyraEditor Linux Development` 目标的构建调用，可能复用已有构建缓存，并非只编探针或测试替身。`-MaxParallelActions=1` 只限制构建动作并发；单个编译或链接任务仍可能超过可用内存。默认超时 3600 秒，超时会对本次进程组发送 TERM/KILL。输出目录必须不存在。

检查命令退出码、`result.json` 的 `passed`、`run.exit_code`、超时和启动错误，再阅读 `stdout.log` 中的编译结果。构建证据包括 `doctor.json`、`run.json`、`result.json`、`stdout.log`、`exit-code.txt`、`memory.txt`、`memory-samples.jsonl`、`cgroup-before.json` 和 `cgroup-after.json`。构建通过只证明该次目标构建调用成功，不代表游戏运行或功能验收通过；内存采样的范围与局限同最小探针，不能仅凭 137 判定 OOM。

### 可选：4 GiB 环境下的低内存重试

保留上一轮日志，确认没有其他构建任务仍在运行，再使用新的输出目录重试：

```bash
runuser -u lyra-eval -- env \
  DOTNET_gcServer=0 \
  DOTNET_GCHeapHardLimit=0x20000000 \
  DOTNET_GCConserveMemory=7 \
  python3 /workspace/lyra-feature-kit/run_lyra_build.py \
  --engine /workspace/UE_5.8.3 \
  --project /workspace/lyra-runs/interaction-deepseek-r1/Lyra.uproject \
  --output /workspace/lyra-results/interaction-baseline-build-lowmem-01 \
  --no-pch --no-shared-pch --no-uba --timeout 2700
```

`0x20000000` 为 512 MiB，限制的是 .NET GC 管理的堆，并非整个 UBT 进程的 RSS，更不限制 Clang、链接器或整容器总内存。`--no-pch` 绕过全部预编译头，`--no-shared-pch` 显式禁用共享预编译头；UE 5.8.3 的 `--no-uba` 只关闭 detour，仍可能使用 UBAExecutor。这些设置可能降低部分内存需求，也可能使构建更慢，不能保证在 4 GiB 或 2700 秒内成功。

运行器会在测量记录中保存追加参数后的完整构建命令，`build_environment` 仅记录上述三个 DOTNET 环境变量。仍按本次实际退出码、日志和 cgroup 增量判定结果，不将重试配置本身视为通过证据。

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

本节提供待执行步骤，不宣称完整 Lyra 构建或加载已经通过。正式开始计时前应保存本次新容器的构建、加载和所需资源工具验证结果。

## 3. 在 Claude 插件开始一题

### 开始计时

只有基线构建和所需资源工具验证成功后才开始正式计时。VS Code 只打开这一题的目录，不把其他候选、原工程或评估器一起打开。在 Claude 插件选择 `deepseek-v4-pro`、开启全新会话；记录平台实际支持的推理档位，不假定它与 GPT 的 high 等价。

```bash
python3 /workspace/lyra-feature-kit/suite.py start /workspace/lyra-runs/interaction-deepseek-r1
cat /workspace/lyra-runs/interaction-deepseek-r1.prompt.txt
```

把显示的完整提示词发给模型。`start` 记录 45 分钟截止时间，**不会自动停止插件**；组织者需到点停止并保存会话日志。只准备环境或事后评估时不要启动模型计时。

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

模型结束后检查 `git diff`，由用户或模型提交本题相关的代码和真实资源；不要 `git add .` 把无关文件全部加入。使用该工程属主账户执行：

```bash
python3 /workspace/lyra-feature-kit/suite.py status /workspace/lyra-runs/interaction-deepseek-r1
# 在工程中 git add 明确的文件，然后 git commit。
python3 /workspace/lyra-feature-kit/suite.py submit /workspace/lyra-runs/interaction-deepseek-r1
```

结果分支为 `codex/deepseek-interaction-deepseek-r1`，其他题同理。工具不会替你暂存或提交，也不会强制推送；工作区不干净、改题目/基线文件、非原起点衍生或远端分叉时拒绝。提交完成只表示传输完成，不表示 UE 通过。旁边的 `.session.json` / `.result.json` / `.prompt.txt` 应由组织者另存为评估证据。

## 工具自身验证

`test_suite.py` 使用本地临时 Git/LFS 仓库验证下载、计时保护、题目保护、脏工作区拒绝、普通推送和非快进拒绝。它验证的是传输工具，不是 Lyra 功能。

`headless_ue.py` 已使用已有真实 UE 报告验证成功/失败解析及零项、计数不符、重复名、缺报告等拒绝路径。报告解析自检与 UE 实际执行是两类证据；旧容器最小 Linux Editor 的历史实测见上面的证据目录，新容器环境需重新核实，三题完整功能验收仍未进行。
