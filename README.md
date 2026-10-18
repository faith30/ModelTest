# Lyra 死亡状态 Linux 运行产物

本目录用于通过 Git / Git LFS 传输真实 UE 运行包与评测证据。固定版本：

- 候选：`3daa3a32b5ddbe106d8c997a6e2514df5fdb0e8d`
- 人工缺陷 seed：`240a1617ee9ae96eb841114bf79268bdad6d92d0`
- 构建方式：使用真实 UE 5.8.3，在 Windows 上交叉编译 Linux x86_64 的 `LyraServer Development`，并 cook、stage 运行内容。

首轮产物保存在 `candidate/`、`seed/`，构建证据放入 `evidence/`。候选首次在真实 Linux 启动时因缺少引擎默认材质崩溃，尚未进入测试；无效证据保存在 `evidence/linux/candidate-attempt-01/`，其中零分不是模型成绩。

`candidate-v2/` 修正了 cook 参数，保留引擎启动资源，已完成真实 BuildCookRun；ELF 与冻结候选原包一致。新构建证据与 cook 清单位于 `evidence/candidate-v2/`。正式 Linux 分数仍待完整运行报告确认。重跑时使用新产物目录和新的解包/结果目录，不混用旧包资源。

本轮是带明确规格和缺陷线索的三处人工修复题，分数仅用于本题。23 项测试使用真实 UE 状态、标签及委托，但由测试直接驱动 OnRep；不证明实际网络传输、PIE 或游戏画面。

## Linux 运行

要求 Python 3.12 或更新版本、非 root 用户，以及已通过 Git LFS 下载的完整产物分片。由同一非 root 用户解包和运行。以下命令均在本仓库根目录执行；每次重跑必须使用新的输出目录。

候选：

```bash
python3 candidate/extract_runtime.py --artifact-root candidate --output ../lyra-runtime-runs/candidate-3daa3a3-package-01
python3 candidate/run_linux.py --package-root ../lyra-runtime-runs/candidate-3daa3a3-package-01/LinuxServer --build-manifest candidate/build-manifest.json --output ../lyra-runtime-runs/candidate-3daa3a3-result-01
```

人工缺陷对照：

```bash
python3 seed/extract_runtime.py --artifact-root seed --output ../lyra-runtime-runs/seed-240a161-package-01
python3 seed/run_linux.py --package-root ../lyra-runtime-runs/seed-240a161-package-01/LinuxServer --build-manifest seed/build-manifest.json --output ../lyra-runtime-runs/seed-240a161-result-01
```

提取脚本会校验分片、运行包和评测脚本哈希，再生成一层 `LinuxServer/`。运行器调用真实服务器执行 23 项 UE Automation 测试，并保存 `result.json`、`runtime.json`、日志及 UE 报告。

`run_linux.py` 的退出码：`0` 表示有效验收且全部通过；`1` 表示证据有效且存在未通过用例；`2` 表示证据无效或运行前置条件、超时等问题。seed 预期触发人工缺陷用例；当完整报告确认 `valid_evidence=true` 时，其退出码 `1` 是有效对照结果，不代表基础设施失败。最终分数以本次 Linux 输出为准。

## 传输文件

各产物目录中的 `.gitattributes` 负责将 `runtime.tar.gz.part*` 标记为 LFS 文件。`artifact_manifest.json` 记录分片与整包哈希、文件体积清单；`build-manifest.json` 记录对应候选及构建信息。根目录规则保持日志、JSON、Python 脚本的原始字节。
