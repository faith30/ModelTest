# 组织者 CLI 监督入口

`run_model_session.py` 是 Linux 上的进程监督器，不启动 UE 验收、不评分、不调用 `suite.py start`，也不暂存、提交或推送 Git。只运行组织者在 `--` 后明确提供的命令，无 shell 拼接。

在环境和平台确认轮完成之后、正式任务开始之前，先用假进程测试此入口。正式任务的完整 Prompt 必须已合并并核对，计时从 CLI 启动尝试之前开始，默认 2700 秒，包含启动开销；CLI 提前退出就结束，不伪装为已运行满 45 分钟。三题分别使用独立的工作目录、证据目录和新 CLI session。若另用 `suite.py start`，它是独立时钟，必须保存二者的偏差，不能视为自动同步。

以下是路径核实后的调用形式，`claude` 参数仅是已知形式；权限策略、新 session 身份和平台快照采集须由组织者在现场确认。可按现场核验结果添加 CLI 参数。正式 Prompt 从文件按原字节送入子进程 stdin，不经 shell 展开。

```bash
python3 /workspace/lyra-feature-kit/run_model_session.py \
  --workspace /workspace/lyra-runs/interaction-deepseek-r1 \
  --prompt /workspace/interaction-complete-prompt.txt \
  --output /workspace/lyra-results/interaction-model-session-01 \
  --seconds 2700 \
  -- claude --model deepseek-v4-pro --print --output-format json
```

应以有权运行 CLI、读写候选工程的非 root 身份启动；若需 `runuser`，由组织者明确放在命令外层或明确的子命令中。输出目录必须是工程之外的新目录，拒绝覆盖。`--seconds` 的短预算只用于自测，不能算正式 45 分钟。

输出：原样 `prompt.txt`、直接流入文件的 `stdout.log` / `stderr.log`、`run.json`。报告包括完整 argv、Prompt SHA-256、启动/截止/停止请求/观察到停止的 UTC、单调时钟用时与 overshoot、子进程身份和信号、清理残留、前后 Git HEAD/分支/状态。`run.json` 初始为 `not_started` 或 `running`，只有最终写入后才有完成状态；进程被 `SIGKILL` 或容器销毁时不能假定最终报告存在。

到期或收到 SIGINT/SIGTERM/SIGHUP 时，监督器用已校验归属的 PID/starttime 和 pidfd 发送 SIGSTOP，再 SIGKILL，回收包括另建 session 的孙进程。正常 CLI 退出也清理遗留子进程。没有允许继续写入的 TERM 宽限。逐个信号并非原子冻结，调度或不可中断进程可能导致延迟，报告如实记录；`cleanup.complete=false` 时绝不能称已冻结。`stopped_at_utc` 表示观察到自有进程树为空，不是文件系统最后一次写入时间。

监督器不提供文件写保护，不能阻止恶意 root/同权限进程篡改报告，也不覆盖常驻 VS Code、外部工具服务、其他用户或远程进程代为写入。组织者须预先核实正式 CLI 的工具执行都在其子进程树内。清理完成后另外核查源文件、保护文件和最终提交；有未提交修改时，报告仅如实记录 dirty，不能冒充已提交成果。截止后不再请求模型补提交或补答案。

退出码：正常 CLI 成功并完成清理为 0；预算到期为 124；清理不完整为 125；中断为 128+信号；CLI 非零退出或监督错误为 1。124 仅表示到期结束，不代表题目失败；任何状态均不是功能分数。中断 CLI 可能影响平台轮次完成钩子，必须实际检查平台 session / 快照，不能据本地退出日志推断保存成功。到期硬停后不得续发模型回合补快照；保留 Git 和监督证据，另行处理平台收录。

假进程验证（不调用模型或 UE）：

```bash
python3 -B /workspace/lyra-feature-kit/test_run_model_session.py
```
