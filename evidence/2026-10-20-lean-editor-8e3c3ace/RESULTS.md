# 精简 Linux UE 环境与 CLI 确认记录

容器：`8e3c3aceaa504364833a5085188dff19`。这是环境验证，不是三道功能题的模型成绩。三题尚未启动计时，也没有候选提交或分数。

## 已实际验证

- 官方 Linux UE 5.8.3 ZIP 共 39,818,576,005 字节，SHA-256 为 `81985a9542e15761fa3cc0d4483a26ebe5fd0b448120faddaa2fe05d94142934`。
- 仅省略 `.debug` / `.sym`：5,584 个文件、14,846,571,177 字节。其余选中文件共 62,119,622,165 字节（57.85 GiB），通过 unzip CRC 校验，退出码 0。完成后删除本任务下载的冗余 ZIP。
- 非 root 用户实际执行 UE 5.8.3 Python commandlet 启动探针：退出码 0，8.006 秒，探针内容校验通过。GNU time 最大 RSS 1,177,184 KiB；本轮 cgroup OOM / OOM kill 增量均为 0。
- CLI 监督器的 11 项测试在本容器全部通过，包含真实 Linux 的 setsid 后代、孤儿进程、截止、中断、退出码和持续写入检查。这些是假进程测试，不执行 UE 或模型。
- 新 DeepSeek CLI session `aaa514c7-ae0f-4a96-a119-d85ed090c849` 仅用 Read 读取安装及探针结果。CLI 返回 `deepseek-v4-pro` 模型记录，退出码 0，进程树清理完成，工具仓库前后干净且 HEAD 相同。

平台的 `claude` 是 shell 函数；`bash -lc` 能加载它，而 `shutil.which("claude")` 返回 None。本轮显式调用该平台函数并等待其后台退出钩子，未绕过平台包装。

## 时间与范围

确认轮开始：2026-10-19 16:38:06.764066 UTC；监督器观察到进程树已清空：16:38:18.365709 UTC。该轮是 300 秒上限的只读环境确认，实际约 11.6 秒；绝不能称为一次 45 分钟功能测试。

截至平台页面 2026-10-20 00:40（中国时间）的收录状态，session 为 `completed`，轮次仍为“等快照”，恢复选择器尚无可用项。**含引擎的大快照恢复尚未证明成功。** 此前小文件快照的成功恢复记录在相邻的 `2026-10-19-environment-probe` 目录，不能代替本次验证。

`ue-lean-install.json` 的状态反映解压完成时刻，因此保留 `extracted_not_yet_runtime_verified`；随后真实启动成功的证据是 `editor-probe-lean-01/result.json` 及原始 UE 日志。

最初的编辑器启动探针只证明真实 UE 启动与 Python API 暴露，不能单独证明 Lyra 编译或功能通过。

## 后续真实 Lyra 基线构建与加载

中国时间 2026-10-20 01:15 归档的[汇总](lyra-baseline-summary.json)记录了后续验证。第一题固定基线仍为 `dcba4d7625373ed1f128af1de54e4e376b0fb4af`，8,689 个 LFS 文件已恢复并校验，正式任务计时未启动。

- 首次冷构建使用 512 MiB .NET GC 堆上限，反复出现 `System.OutOfMemoryException`。组织者停止了该次构建；后代进程清理完成，cgroup OOM / OOM kill 均为 0。见 [build-01](interaction-baseline-lean-build-01/run.json)。这不是模型作答失败。
- 将 GC 堆上限改为 `0x40000000`（1 GiB），保留单并发、`-NoPCH -NoSharedPCH -NoUBA -BytesPerUnityCPP=131072` 后，[build-02](interaction-baseline-lean-build-02/run.json) 完成 61/61 项，退出码 0，耗时 481.096 秒，最大 RSS 1,664,152 KiB，清理完成。重试可能复用前次生成的缓存，不能称为全无缓存构建。
- 随后的[真实加载探针](interaction-baseline-lean-load-01/probe.json)在非 root UE 5.8.3 进程内核对了 `LyraGame` / `LyraEditor` 实际可执行映射和模块哈希，并加载原生交互类、DefaultGameData、GA_Interact 和 L_InventoryTestMap。退出码 0，耗时 36.758 秒，最大 RSS 2,256,388 KiB。
- 构建与加载的 OOM / OOM kill 增量都为 0；cgroup 内存采样接近或达到 4 GiB 上限，包含其他进程与可回收文件缓存。单进程 RSS 不能代表容器总内存，尚未证明多个编辑器或多人客户端可并行运行。

以上只证明当前固定基线的构建、模块和资源加载，不验证游戏功能、UI、实际音频或多人行为，不产生三题分数。模型修改后仍须重新构建并独立验收。

01:16 后通过同容器 Claude 插件发送了[只读环境确认](plugin-confirmation-prompt.txt)，用于核对与此前成功的小快照相同的保存流程。当前仍须验证含引擎快照可恢复，再给予每题完整 2700 秒预算、冻结模型交付并按原评分规则评估。
