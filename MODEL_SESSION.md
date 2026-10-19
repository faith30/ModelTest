# 组织者 CLI 监督入口

`run_model_session.py` 是 Linux 上的进程监督器，不启动 UE 验收、不评分、不调用 `suite.py start`，也不暂存、提交或推送 Git。只运行组织者在 `--` 后明确提供的 argv，不隐式启动 shell；组织者可以明确传入下述平台所需的 `bash -lc` 包装。

在环境和平台确认轮完成之后、正式任务开始之前，先用假进程测试此入口。正式任务的完整 Prompt 必须已合并并核对，计时从 CLI 启动尝试之前开始，默认 2700 秒，包含启动开销；CLI 提前退出就结束，不伪装为已运行满 45 分钟。三题分别使用独立的工作目录和证据目录，各自建立包含环境确认轮的 session，避免带入其他题目历史。按用户提供教程的环境准备与轮次选择流程，每个新建或恢复的容器都要新建 CC session，先做环境确认轮，再在同一 session 进入任务轮，供平台读取任务轮的前一轮快照；不能用旧容器的 session 续聊代替新容器采集。现场保存的 CLI help 已确认 `--resume <已知 session UUID>` 的按 ID 续聊语法，但尚未实际验证续聊及对应平台收录；`--continue` 选择当前目录最近会话，`--fork-session` 会另建 ID，均不能据此推定是在预期 session 进入下一轮。若另用 `suite.py start`，它是独立时钟，必须保存二者的偏差，不能视为自动同步。

现场已确认 `claude` 是 shell function，Python `shutil.which("claude")` 返回 None，而 `bash -lc` 可加载该函数。必须保留平台包装，不能将裸 `claude` 直接作为 Popen 的可执行文件。已验证的包装保存 `claude` 函数返回码，并用 `wait` 等待该 shell 可等待的后台任务，以保留平台退出钩子的执行机会；这部分等待仍在总预算内。`wait` 不能证明已脱离该 shell 的服务或远端快照任务完成，函数返回码和监督器 `completed` 也不是所有钩子成功的证明。

以下仅展示正式预算下的包装调用骨架，尚不是已经核验完整的正式任务命令：组织者还须确认 Bash/Edit 权限策略、按明确 UUID 续聊的实际效果及前一轮快照可用，再补入对应 CLI 参数。完整 Prompt 从文件按原字节送入子进程 stdin，不经 shell 展开。脚本字符串之后的第二个 `bash` 是 shell 的 `$0` 占位，需保留，后续 CLI 参数才会完整传入 `"$@"`。

```bash
python3 /workspace/lyra-feature-kit/run_model_session.py \
  --workspace /workspace/lyra-runs/interaction-deepseek-r1 \
  --prompt /workspace/interaction-complete-prompt.txt \
  --output /workspace/lyra-results/interaction-model-session-01 \
  --seconds 2700 \
  -- bash -lc 'claude "$@"; cli_status=$?; wait; exit "$cli_status"' bash \
  --model deepseek-v4-pro --print --output-format json
```

本次 Read 工具调用及进程退出成功的记录为监督器 `uid=0/euid=0`，只验证了该身份下的 CLI 调用与清理，没有证明平台轮次已经结束；也没有证明 `lyra-eval` 登录 shell 同样能加载函数、访问 CLI 配置或接续 session。CLI 执行身份可沿用已核实的 root 包装，但正式平台采集路径仍待验证，不为切换 CLI 用户而绕过平台函数或迁移凭据。UE 与构建必须另用 `runuser -u lyra-eval -- ...` 等现场已核实的非 root 调用，并事先配好工程/输出权限。输出目录必须是工程之外的新目录，拒绝覆盖。`--seconds` 的短预算只用于自测，不能算正式 45 分钟。

输出：原样 `prompt.txt`、直接流入文件的 `stdout.log` / `stderr.log`、`run.json`。报告包括完整 argv、Prompt SHA-256、启动/截止/停止请求/观察到停止的 UTC、单调时钟用时与 overshoot、子进程身份和信号、清理残留、前后 Git HEAD/分支/状态。`run.json` 初始为 `not_started` 或 `running`，只有最终写入后才有完成状态；进程被 `SIGKILL` 或容器销毁时不能假定最终报告存在。

到期或收到 SIGINT/SIGTERM/SIGHUP 时，监督器用已校验归属的 PID/starttime 和 pidfd 发送 SIGSTOP，再 SIGKILL，回收包括另建 session 的孙进程。正常 CLI 退出也清理遗留子进程。没有允许继续写入的 TERM 宽限。逐个信号并非原子冻结，调度或不可中断进程可能导致延迟，报告如实记录；`cleanup.complete=false` 时绝不能称已冻结。`stopped_at_utc` 表示观察到自有进程树为空，不是文件系统最后一次写入时间。

监督器不提供文件写保护，不能阻止恶意 root/同权限进程篡改报告，也不覆盖常驻 VS Code、外部工具服务、其他用户或远程进程代为写入。组织者须预先核实正式 CLI 的工具执行都在其子进程树内。清理完成后另外核查源文件、保护文件和最终提交；有未提交修改时，报告仅如实记录 dirty，不能冒充已提交成果。截止后不再请求模型补提交或补答案。

退出码：正常 CLI 成功并完成清理为 0；预算到期为 124；清理不完整为 125；中断为 128+信号；CLI 非零退出或监督错误为 1。124 仅表示到期结束，不代表题目失败；任何状态均不是功能分数。中断 CLI 可能影响平台轮次完成钩子，必须实际检查平台 session / 快照，不能据本地退出日志推断保存成功。到期硬停后不得续发模型回合补快照；保留 Git 和监督证据，另行处理平台收录。

假进程验证（不调用模型或 UE）：

```bash
python3 -B /workspace/lyra-feature-kit/test_run_model_session.py
```

2026-10-20 的现场验证记录见 [证据说明](evidence/2026-10-20-lean-editor-8e3c3ace/RESULTS.md)：[11 项自测](evidence/2026-10-20-lean-editor-8e3c3ace/model-session-self-test.log) 在远程 Linux 全部通过，其中 7 项为真实 Linux 进程场景，均未调用模型或 UE。另一次实际 DeepSeek CLI 环境确认使用 `--tools Read --allowedTools Read --permission-mode default`，300 秒上限下约 11.6 秒正常结束，退出码 0、清理完成，见 [监督记录](evidence/2026-10-20-lean-editor-8e3c3ace/environment-cc-confirm-01/run.json) 和 [实际回复](evidence/2026-10-20-lean-editor-8e3c3ace/environment-cc-confirm-01/stdout.log)。这只验证 Read 确认轮；正式任务的 Bash/Edit 权限仍需现场核验。

平台完整轨迹的最终回复已另存为[截图](evidence/2026-10-20-lean-editor-8e3c3ace/platform-claude-response.png)。快照状态截图记录的中国时间 00:40，含引擎的大快照仍为“等快照”，尚未证明可恢复。以上自测和确认轮都不是 45 分钟功能测试，不产生题目分数。

随后平台 UI 的现场观察进一步区分了 session 与 Turn 状态：成功的小快照实验来自 VS Code Claude 插件，session 前缀 `67d71a47` 的 Turn 1 显示中国时间 2026-10-19 23:45:38 至 23:45:43、耗时 5.0 秒并完成 Snapshot。CLI session `aaa514c7-ae0f-4a96-a119-d85ed090c849` 虽显示 session/pipeline completed 且保存了 raw response，Turn 1 在当时仍显示 2026-10-20 00:38:08 至 `-`、进行中，至 01:09 仍为“等快照”。这些是平台 UI 的历史状态，不能据此认定本地没有触发轮次结束。

进一步只读检查 `/tmp/sidecar.log` 并过滤敏感字段后，两个入口均有本地触发证据，已保存为 [诊断记录](evidence/2026-10-20-lean-editor-8e3c3ace/snapshot-trigger-diagnostic.json)（以下为日志原始时间）：

- CLI：`2026/10/19 16:38:17 [agent] turn-end: snapshot_id=aaa514c7-ae0f-4a96-a119-d85ed090c849_turn_1_33a18996`。
- 插件：`2026/10/19 17:16:51 [agent] turn-end: snapshot_id=d5bee8fd-cf4c-4b6a-b401-72317b19a600_turn_1_5d67223b`。

同容器插件新 session `d5bee8fd-cf4c-4b6a-b401-72317b19a600` 已读取 6 个文件并返回只读环境确认。上述记录证明 CLI 与插件均触发了本地 `turn-end`，但产生 `snapshot_id` 不等于远端快照已落盘或可恢复；仍需现场核验快照生成和恢复。不能推断 CLI 的 `--print` 模式导致失败，也不能将函数返回 0、`wait` 返回或 `cleanup.complete=true` 当作远端恢复成功的证据。

另一次只读核对发现本次浏览器粘贴存在文本传输差异：仅提取上述插件 session 的 `/root/.claude/projects/-workspace/d5bee8fd-cf4c-4b6a-b401-72317b19a600.jsonl` 中 [实际 user 消息](evidence/2026-10-20-lean-editor-8e3c3ace/plugin-actual-user-message.txt)，与已保存的 [源 Prompt](evidence/2026-10-20-lean-editor-8e3c3ace/plugin-confirmation-prompt.txt) 比较，源文本为 623 字符、13 个换行，实际消息为 610 字符、0 个换行；去除源文本换行后，两者字节相同。[该确认轮的传输比对记录](evidence/2026-10-20-lean-editor-8e3c3ace/plugin-prompt-transport.json) 保存了两者的 SHA。因此本次粘贴丢失了全部换行，不能将源文件 SHA 当作实际发送消息的 SHA。确认轮仍正确读取了 6 个文件，正式题尚未开始，未受此次差异影响。

随后对 CLI session `aaa514c7-ae0f-4a96-a119-d85ed090c849` 的实际 user 消息进行了只读回查，[传输审计](evidence/2026-10-20-lean-editor-8e3c3ace/cli-prompt-transport.json) 记录其与 `environment-cc-confirm-01/prompt.txt` 完全一致：376 字符、6 个换行、742 UTF-8 字节，SHA-256 为 `ddac448fb0c30dca5e412774b832271ba9727847d6f2f8a8eac58bfbaef5e9d5`。这证明本次只读 CLI 确认轮的实际消息保真，不能替代尚未发送的正式冻结 Prompt 验证。

正式冻结任务优先使用已验证向子进程 stdin 提供原字节的 CLI 监督入口，并分别保存源 Prompt 与实际 session user 消息的核对证据和哈希。监督器的 Prompt SHA 记录的是 stdin 源字节，仍不能替代每次实际会话消息回读。按 UUID 续聊、正式 Bash/Edit 权限和平台快照恢复仍须现场验证，不能仅凭本次只读消息传输检查就认定完整流程已跑通。

这些仍是环境验证，正式 45 分钟任务尚未启动，没有功能分数。插件的小快照成功不能代替含引擎环境的恢复验证，CLI 监督器的测试也不能证明插件 UI 任务及其后台写入进程已受同样监督；正式入口及其停止边界仍须按实际运行方式核实。
