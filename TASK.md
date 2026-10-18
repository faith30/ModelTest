# Lyra 死亡状态回调修复任务

任务编号：`lyra-death-v1`。

这是从 Lyra C++ 文件制作的**人工缺陷题**。准备阶段注入了三个缺陷，它们不是对上游 Lyra 存在这些问题的断言。本目录是独立的候选 Git 仓库，初始提交只包含注入后的代码、接口和参考文件，不包含原版答案、评分器或 Unreal Engine。

请阅读本目录代码，修复 `Source/LyraGame/Character/LyraHealthComponent.cpp` 中以下三个函数的行为：

- `ULyraHealthComponent::OnRep_DeathState`
- `ULyraHealthComponent::StartDeath`
- `ULyraHealthComponent::FinishDeath`

## 行为要求

死亡阶段依次为 `NotDead`、`DeathStarted`、`DeathFinished`。生命周期推进与当前生命值是不同概念，**不得增加“生命值必须为零才允许开始或完成死亡”的条件**。

1. `StartDeath` 只允许从 `NotDead` 进入 `DeathStarted`。有 AbilitySystemComponent 时，将 `Status_Death_Dying` 的计数设为 1；随后广播一次 `OnDeathStarted`，并对 Owner 调用一次 `ForceNetUpdate`。
2. `FinishDeath` 只允许从 `DeathStarted` 进入 `DeathFinished`。有 AbilitySystemComponent 时，将 `Status_Death_Dead` 的计数设为 1；随后广播一次 `OnDeathFinished`，并对 Owner 调用一次 `ForceNetUpdate`。保持已有 Dying 标签值，不要求也不允许在此额外清除它。
3. 重复开始、重复完成、完成后再次开始，以及尚未开始时直接调用 `FinishDeath`，都应保持状态不变，不重复广播、不重复写入标签、不重复请求网络更新。
4. `OnRep_DeathState` 读取到的新阶段可能直接从 `NotDead` 跳至 `DeathFinished`。此时必须按“开始死亡、完成死亡”的顺序执行两次阶段转换，依次广播 `OnDeathStarted` 和 `OnDeathFinished`，各一次，并完成相应标签和网络更新。
5. 正常复制序列 `NotDead → DeathStarted → DeathFinished` 具有相同的最终状态和事件顺序。相同阶段的通知不重复触发上述副作用。
6. 本地预测阶段已经领先于新复制阶段时，保留本地阶段，不倒退，也不重新广播或写入标签。
7. AbilitySystemComponent 为空时，跳过标签操作，但合法的状态推进、事件广播和 Owner 网络更新仍然发生。Owner 按原有函数契约有效；保留现有检查。

## 修改范围

只允许修改上述 `.cpp` 文件中的三个函数体，并新增 `SOLUTION.md`。保留函数签名、其他函数、头文件、包含项和原有对外接口。

`SOLUTION.md` 请简述缺陷原因、修改点、做过的验证及验证限制。不要把未运行的检查描述为通过，不要自行填写最终评分。

以下文件为只读：

- `Source/LyraGame/Character/LyraHealthComponent.h`：相关接口与状态枚举。
- `Source/LyraGame/AbilitySystem/Attributes/LyraHealthSet.cpp`：生命值逻辑参考，不是本题修改对象。
- `TASK.md`、`task_metadata.json`：任务要求与来源记录。

不要修改评测基础设施、Git 元数据或来源记录；不要添加替代实现、硬编码测试结果或尝试改变评测流程。不要读取候选工作目录以外的项目文件、原版仓库、评分器或答案，也不要通过网络检索或下载答案。请仅依据本目录材料独立完成。

## 验证边界

本目录是模型编辑用的源码提交包，完整 Lyra 工程和 UE 引擎由独立构建端管理。提交冻结后，评测端将修改应用到完整工程，通过真实 UE 构建生成 Linux 程序，再在目标 Linux 容器中运行真实 UE 自动化测试。测试使用真实 UObject、Actor、HealthComponent、AbilitySystemComponent 和动态委托，不以 Python 或 C++ 类型替身代替引擎。

本题测试状态迁移和回调行为；OnRep 由测试直接驱动，不宣称覆盖实际多机网络复制、动画或游戏画面。本目录自身没有完整引擎及工程依赖，因此不能将普通 C++ 片段检查冒充 UE 编译成功。编译失败、程序无法在目标 Linux 启动或缺少正式测试报告，都不能视为最终通过。

没有提供评分器或参考答案。保留修改供外部评测，并在 `SOLUTION.md` 如实说明本地能够完成的验证。
