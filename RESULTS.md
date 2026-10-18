# 真实 UE Linux 评测结果

**deepseek-v4-pro 修复版通过：23/23，100/100。**

UE 5.8.3 · LinuxServer Development · 远程 Linux x86_64 · 2 核 / 4 GiB · 非 root UID 996

| 实际运行对象 | 通过 / 总数 | 得分 | 执行证据 |
| --- | ---: | ---: | --- |
| 模型修复版 | **23 / 23** | **100 / 100** | 有效，UE 退出 0 |
| 原始人工缺陷版 | **7 / 23** | **29 / 100** | 有效，16 项失败，UE 退出 255 |

两次运行均完成全部 23 项测试，没有缺失或跳过。候选耗时 8.582 秒，对照耗时 8.680 秒。对照版的测试失败是有效对照结果；运行器退出 1。

| 测试组 | 修复版 | 缺陷版 | 满分 |
| --- | ---: | ---: | ---: |
| 直接收到死亡完成状态 | 20 | 0 | 20 |
| 分阶段死亡流程 | 20 | 5 | 20 |
| 重复与越序调用 | 20 | 4 | 20 |
| 本地预测领先 | 20 | 8 | 20 |
| AbilitySystemComponent 为空 | 20 | 12 | 20 |

这是带明确规格与缺陷线索的三处人工修复题，分数仅适用于本题。测试运行真实 UE、Lyra 健康组件、标签和委托；OnRep 由测试直接调用，不验证实际网络传输或游戏画面。

## 查看原始证据

- [修复版最终结果](evidence/linux/candidate/result.json) · [UE 原始报告](evidence/linux/candidate/ue-report/index.json) · [运行命令和哈希](evidence/linux/candidate/runtime.json)
- [缺陷版最终结果](evidence/linux/seed/result.json) · [UE 原始报告](evidence/linux/seed/ue-report/index.json) · [运行命令和哈希](evidence/linux/seed/runtime.json)
- [修复版真实构建日志](evidence/candidate-v2/build.log) · [缺陷版真实构建日志](evidence/seed-v2/build.log)

原始运行证据已冻结于 Git 提交 `fa4e775f76b058c7511a73af93abb8a7b9bc8149`，分支 `codex/lyra-linux-runtime-3daa3a3`。

## 在当前容器复跑 demo

在 VS Code 的 root 终端执行。现有两份包已验证并解包；每次重跑需换一个尚不存在的 `--output` 路径。

修复版：

```bash
runuser -u lyra-eval -- python3 /workspace/LyraLinuxRuntime/candidate-v2/run_linux.py \
  --package-root /workspace/lyra-runner/candidate-package-02/LinuxServer \
  --build-manifest /workspace/LyraLinuxRuntime/candidate-v2/build-manifest.json \
  --output /workspace/lyra-runner/candidate-result-03 --timeout 300
```

缺陷对照版（有效失败时返回 1）：

```bash
runuser -u lyra-eval -- python3 /workspace/LyraLinuxRuntime/seed-v2/run_linux.py \
  --package-root /workspace/lyra-runner/seed-package-02/LinuxServer \
  --build-manifest /workspace/LyraLinuxRuntime/seed-v2/build-manifest.json \
  --output /workspace/lyra-runner/seed-result-03 --timeout 300
```

新容器需重新通过 Git/LFS 获取产物，再按 [README 的非 root 解包流程](README.md#linux-运行) 准备目录。无需在小容器中安装整个 UE 编辑器或使用 GPU。

## 来源与运行记录

- 模型：远程 VS Code 的 Claude Code 插件选择 `deepseek-v4-pro`；原任务会话 `719779a0-1588-4f2a-bd10-2e0a85e1c948`。原容器已过期，当前容器恢复的是冻结候选，新的空白插件会话不作为原始生成记录。
- 候选 Git：`3daa3a32b5ddbe106d8c997a6e2514df5fdb0e8d`；缺陷 seed：`240a1617ee9ae96eb841114bf79268bdad6d92d0`。模型完成修改后由评测端检查范围、冻结提交。
- 构建：Windows 完整 Lyra 工程使用官方 v26 工具链，真实编译 Linux UE 服务器并 cook、stage；执行：远程容器 `a685f7f9e4bb4a2abe281440b6e4223f`，主机 `edge-1-debea7fa`。
- 候选运行时间：2026-10-18 23:34:16–23:34:25；对照：23:38:08–23:38:16（Asia/Shanghai）。
- 首次候选运行在引擎初始化时因 cook 省略默认材质而崩溃，[原始失败记录](evidence/linux/candidate-attempt-01/result.json) 保留。移除 `CookSkipRequests` 后重新构建两套完整资源；模型源码、各自 ELF 和评分脚本未因此改变。
- 构建清单中的 `runtime_validated=false` 保留原始构建阶段事实；最终执行以各自 `result.json` 的 `valid_evidence=true`、`is_final=true` 为准。

哈希用于绑定 Git、构建和运行文件；模型身份与执行来源还依赖评测过程记录，哈希本身不构成独立远程证明。
