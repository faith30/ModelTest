# Lyra 模型开发能力测试基线

三个分支分别剥离一个功能，同一题的不同模型应从同一提交开始。它们是**有意缺少目标功能的起始工程**，不是已经实现好的示例答案。公共角色、移动、GAS、Experience、消息总线和美术素材保留；源码业务实现、指定蓝图行为以及功能配置已经清除。

| 分支 | 功能 | 主要协作边界 | 需求入口 |
| --- | --- | --- | --- |
| `codex/benchmark-interaction` | 交互、拾取与背包展示 | LyraGame 交互/GAS、ShooterCoreRuntime 世界物品、ShooterExplorer 输入与 UMG | `Benchmarks/interaction/TASK.md` |
| `codex/benchmark-accolades` | 连杀荣誉与定向 HUD 通知 | ShooterCoreRuntime 统计、GameplayMessageRuntime、DataRegistry、网络 Relay、UMG | `Benchmarks/accolades/TASK.md` |
| `codex/benchmark-context-effects` | 表面相关脚步与落地反馈 | LyraGame Notify/Subsystem、LyraEditor 资源创作、蓝图、物理表面、音效/Niagara | `Benchmarks/context-effects/TASK.md` |

每个分支只带自己的题目，均从同一个完整 Lyra 提交派生，互不叠加剥离。`scope.json` 记录源码、资源外壳及公共依赖边界；`baseline-validation.json` 记录本次验证。被公共内容引用的资源保留路径、反射类型及必要签名，避免引入无关丢失引用。保留的控件布局或素材不是完整功能；题目明确要求交付可运行蓝图和多种资源配置。

## 交给模型前

1. 为每个模型使用同一题的同一份起始快照、完整 TASK 文本和相同引擎版本（UE 5.8.3）。记录模型版本、推理档位、工具权限、运行时间和 token 预算。
2. 组织者分支继承完整 Git 历史，历史中有原实现。正式评测请使用下述导出工具生成**仅一个根提交、没有 remote 的独立副本**，并限制模型访问原仓库、其他分支/工作副本及原版答案。只写“不要看历史”不足以形成隔离。
3. 同样提供编辑器和原生资源编辑工具。不能只给一个模型文本工具，另一个模型完整 Editor 能力，再将得分当作模型本身差异。
4. 用分支 TASK 作为固定需求，不临时追加只针对某一个模型的提示；澄清、人工操作和修复次数应记录。

在已提交且 tracked 文件干净的基线工作副本中执行（Python 3.9+、Git、Git LFS）：

```powershell
python Benchmarks/tools/export_snapshot.py --destination D:/ModelRuns/interaction-model-a
```

目标目录必须尚不存在。导出仅复制受 Git 跟踪且已落地的文件，不复制原 `.git`、remote、Binaries、Intermediate、Saved 或本地 IDE 状态；新副本需关联本机 UE 5.8.3 并构建。详见 [导出工具说明](tools/README.md)。给不同模型各导出一份，使用同一基线提交。

## 验收与记录

每题 TASK 给出 100 分标准和具体场景。先执行功能/多人/资源验收，再评判结构与实现质量。仅 C++ 代码、临时 Python 内存对象、未保存的蓝图或口头说明不算完成资源交付。没有实际执行的检查标记为“未验证”，不可记为通过。

各题复杂度不同，优先在同一题内比较模型，分别报告代码、蓝图、资源配置、多人正确性与验证质量，不仅给一个总分。建议每题重复多次并记录成功率；所有模型使用相同复测规则。

## 基线自检

`tools/verify_assets.py` 只用于验证**剥离后的起点**：通过 UE 原生 API 重新加载包、检查功能图节点和配置为空、编译外壳及指定共享蓝图；不会保存资源。它不是模型完成后的功能测试，模型实现功能后应不再满足“空实现”断言。

```powershell
$UE = '你的UE5.8.3目录'
$Project = (Resolve-Path ./Lyra.uproject).Path
& "$UE/Engine/Build/BatchFiles/Build.bat" LyraEditor Win64 Development "-Project=$Project" -Module=LyraGame+LyraEditor+ShooterCoreRuntime -WaitMutex -NoHotReloadFromIDE
& "$UE/Engine/Binaries/Win64/UnrealEditor-Cmd.exe" $Project -run=pythonscript "-script=$((Resolve-Path ./Benchmarks/tools/verify_assets.py).Path)" -EnablePlugins=PythonScriptPlugin -unattended -nullrhi -nosound -NoShaderCompile -NoSourceControl
```

首次在全新副本中仍需完整构建 `LyraEditor` 及项目插件；上面的限定模块命令用于已有完整编译环境的后续核验。资源检查结果写入 `Saved/BenchmarkPreparation/readback.json`，必须同时检查退出码和 `passed: true`。原生资源处理不等于实际游戏验证；PIE、多人和打包结果以各题记录为准。
