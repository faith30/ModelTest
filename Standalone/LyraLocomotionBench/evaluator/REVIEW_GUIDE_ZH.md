# 静态证据审查指南

本基准审查独立目录里的资源制作、动画图配置和 Python 控制逻辑。它不运行 UE，不修改原工程，不评实际蒙皮画面、脚滑程度、引擎线程性能或网络表现。模型输出的 `players`、`sync_groups`、`pose_operations` 是动画执行计划，不能当作已经求出的最终姿态。

`rubric.json` 是裁判资料，40 项共 100 分。只把候选包交给被测模型；不要把本文件、清单、原始蓝图答案或其他模型答案混入候选目录。正式对比前冻结候选输入、评分版本、工具权限、联网权限、时限及模型路由记录。

## 1. 先认清三种证据

| 类型 | 可以支持什么 | 不可以推断什么 |
| --- | --- | --- |
| 官方机制 | Sync Groups、Distance Matching、Warping、节点生命周期等机制及其重要性 | 某份本地 Lyra 已经采用某个精确值、名字或默认属性 |
| 本地有界导出 | `local_lyra_facts.json` 中明确记录的资产引用、节点属性及导出索引 | 未导出的默认值、完整运行调用链、最终姿态或绝对 L/R 标记相位 |
| 本题设计 | 平地 Unarmed 输入、独立数据格式、接口、40 项评分、延后加工策略 | Epic 官方验收标准，或对 UE 版本完全等价的承诺 |

每个条目的 `basis`、`source_ids` 与可选 `local_fact_refs` 标明依据。官方来源的 URL 在 `rubric.json.sources`。本地来源只作有界解释，不作为隐藏的逐字答案。

例如，本地记录可显示 Cycle 的 `Locomotion / AlwaysFollower` 和 Stop 的独立同步组。候选使用其他组名、角色组织或显式时间控制，只要语义自洽、能处理相位与距离驱动的竞争，就不因未照抄字符串扣分。也不能因为标记叫 L/R，就断定它必须对应原作者某一帧落脚点。

## 2. 输入不足不是候选缺陷

冻结题包有 37 条目录项，其中 15 段有 26 根骨骼的 component-space 抽样；其他 22 项是 `metadata_only`，时长等未知值为 `null`。具体以候选的冻结 `raw/manifest.json` 为准。

- 有 `pose_samples` 的条目，检查模型是否实际读取并加工，是否提交有效结果。
- `metadata_only` 的条目，检查可复用的制作代码/recipe、来源引用及 `deferred_missing_samples`。满足这些条件可以取得相关条目的完整分数，不要求精确 marker 时间或曲线样本。
- 不允许编造未知时长、骨骼轨道、曲线或“已完成”结果。把未知值填成 0 也不等同于正确延期。
- 只有 26 骨骼子集，不要求完整 Manny、164 骨骼、缺失的 IK/虚拟骨骼或真实求解器。
- 源 mesh 前向 +Y，抽象 actor 前向 +X；数据为 cm、Z-up、component-space、xyzw。坐标转换必须有具体依据，不能把空间约定错误归因于缺素材。
- frame 只有 dt、世界速度/加速度、actor yaw 和 aim yaw。没有武器、碰撞、网络、grounded 变化、actor 世界位置或输入按键。允许基于现有输入和已声明的内部制动参数进行近似预测。
- Warp 和分层项检查具体参数计算、操作顺序、有效引用及计划使用。无需执行真实 IK/FK、渲染、换武器或多线程。
- 跳跃、落地、坡地及网络不在本版分数范围内。不能通过额外实现这些内容弥补核心缺项。

所有条目均带 `applicability_inputs` 和 `unavailable_input_handling`。固定分母为 100；不要把缺采样项改成 N/A 再重新计算分母。

## 3. 检查方法

先阅读候选 `INTERFACE.md`，然后沿一条完整链检查：

1. `raw/manifest.json` 和姿态采样被 `src/build_assets.py` 读取。
2. 制作逻辑生成 `assets/authored_assets.json` 中的资源、marker、曲线、recipe 或延期记录。
3. `config/animation_graph.json` 引用这些资源，声明状态、连接、同步及修正配置。
4. `LocomotionController(graph, assets)` 实际消费配置；`reset(seed=0)` 初始化状态，`step(frame)` 计算所需参数。
5. 返回计划引用有效 asset/player/group/operation，并保留缺样本资源的不可物化状态。

只列出 “Distance Matching” 或 “Sync Group” 不构成实现。文件存在、README 自报完成、注释中的公式、模型自报测试通过也不能单独支持 `pass`。应检查实际代码、图配置、生成数据以及它们之间的连接。

静态审查允许依据代码手工推导边界行为，例如速度过零、反向、循环跨尾、leader 接管、Stop 再起步。审查者无需执行候选代码；若另有运行观察，应单独报告，并且不要把它扩大成 UE 视觉验证。

同步和 Notify 条目接受具体计算与同步/事件计划：相位规则、leader 归属、事件区间、缺标记回退等应有明确语义，并关联当前播放器和资源。无需制作通用 Sync 引擎、事件执行器或 UE 图解释器。反过来，只写一个角色枚举或一个未定义的设置字段，也不能证明这部分已经交付。判分依据是本题计划层的具体逻辑，而非是否执行出音效或最终姿态。

## 4. 状态与给分

| status | awarded | 使用条件 |
| --- | --- | --- |
| `pass` | 该项 weight | 直接证据覆盖 check 的实质要求 |
| `partial` | 有限数，严格大于 0 且小于 weight | 有实质工作，只覆盖部分要求；必须解释已实现和缺口，不限制 0.5 分粒度 |
| `missing` | 0 | 所需交付/逻辑缺失；记录实际查看过的路径和范围 |
| `incorrect` | 0 | 交付存在但语义错误、内部矛盾或用关键词伪装实现 |
| `unreviewed` | null | 尚未审查或证据不可读取；不能偷偷算成 0 或通过 |

不要按关键词数量平均分配分数。`partial` 应根据该项具体的行为覆盖给分，并写出依据。零分用 `missing` 或 `incorrect`，不使用零分 partial。

任何条目未审，最终总分保持 `null`。已审部分可以显示 `reviewed_subscore / reviewed_max_score`，但不得将其当作最终成绩或进行排名。条目全部完成但门槛未确认时，工具可能给出 raw_score，final_score 仍为 null。

## 5. 门槛与避免重复扣分

| Gate | 触发条件 | 最终上限 |
| --- | --- | --- |
| G01 | 只有文字、伪代码或模板壳，资源处理及动画决策均缺少实质实现 | 30 |
| G02 | 资源制作逻辑/recipe 和派生资源元数据两者均缺失或仅空模板 | 60 |
| G03 | 缺少有效状态、过渡和节点/层组合逻辑，无法辨认整体动画流程 | 60 |

门槛判断必须检查实际内容。某个文件叫 `animation_graph.json` 并不证明图已完成；存在草稿也不自动触发 G03。代码与配置协同表达有效逻辑即可。缺样本资源的有效延期 recipe 属于交付，不触发 G02。只缺一项实现入口时，不机械触发“纯文字”G01。

每个 gate 使用：

- `status: "pass"`：不触发上限。
- `status: "fail"`：触发上限。
- `status: "unreviewed"`：尚未判断。
- `confirmed: true`：独立审查者确认该判断；它不是“触发”的同义词。

任一 gate 未 confirmed 或仍 unreviewed，最终总分为 null。确认后的最终分计算为：

```text
raw_score = 所有条目 awarded 之和
final_score = min(raw_score, 所有触发 gate 的 cap)
```

cap 不叠加为额外罚分。例如 raw_score=75 且 G02、G03 都触发，最终为 60，不是 45，也不是扣两次 40。

单个缺陷优先记在最直接所属项。例如曲线反查平台段错误主要记 DST04；ROB01 只有整体输入保障另有独立失败才继续扣分。缺整个交付类别时，其多个条目确实可能都无证据；可以分别判 missing，并应用最终 cap，但不再附加“严重错误扣分”。

## 6. 审查文件与工具

评分器验证文件摘要、证据定位与算术，不代替人判断动画语义。候选目录冻结后，不要把 review、rubric 或 score 写回候选内，否则会改变候选摘要。目录摘要包含文件名及所有普通文件内容；符号链接或 reparse point 不受支持。

以下命令在仓库根目录运行。路径仅为示例，请换成实际冻结候选和独立审查目录：

```powershell
python -B tools/score_review.py --rubric evaluator/rubric.json --candidate D:/BenchRuns/model-a/candidate --init-review --output D:/BenchRuns/model-a/review.json
python -B tools/score_review.py --rubric evaluator/rubric.json --candidate D:/BenchRuns/model-a/candidate --review D:/BenchRuns/model-a/review.json --output D:/BenchRuns/model-a/score.json
```

先生成模板，再人工填写。模板绑定 `candidate_sha256` 和 `rubric_sha256`；不要为掩盖后续修改而手改摘要。候选更新后应生成新的审查记录，不能沿用旧证据。

review 顶层包含 `schema_version`、摘要、`reviewer`、`items` 和 `gates`。`items` 与 `gates` 均为以 rubric ID 为键的对象，不是数组。每个条目填写 status、reason、evidence、reviewed_paths；partial 另填 awarded。

每条 evidence 格式：

```json
{
  "path": "src/controller.py",
  "line_start": 20,
  "line_end": 23,
  "quote": "这里必须替换成指定行区间里真实存在的非空原文"
}
```

这是格式示意，不能直接当作有效证据。path 是相对冻结候选的 POSIX 路径，使用正斜杠；行号从 1 开始，区间为闭区间。quote 必须出现在该文件对应区间，文件须为可读取 UTF-8。证据应尽量短并直接支撑判断。

- pass/partial 必须有非空 evidence。
- partial 必须有理由和合法 awarded。
- missing/incorrect 必须有理由，并有非空 evidence 或 reviewed_paths；后者指确实存在且已检查的候选文件/目录，不能填虚构的缺失路径。
- gate 必须有 status、confirmed 和非空 reason；当 confirmed=true 且 status 为 pass/fail 时，必须有非空有效 evidence 或 reviewed_paths。尚未确认或 unreviewed 不要求证据，最终分会继续保持 null。
- 缺失的 rubric ID 会保留为 unreviewed；未知 ID、越界行号、伪造引文、摘要变化等会使评分器拒绝汇总。

## 7. 出分前核对

确认 40 项和 3 个 gate 都已审，引用可读取、关键部分没有只据文字给 pass；对同一类错误采用一致 partial 尺度，并核对缺采样是否被误罚。范围和权重只在正式对比前调整，不能看完某个模型结果再为它修改。

报告应分开列出模型实际路由、输入包/候选/评分版本摘要、工具权限、人工参与与重试、静态总分、主要扣分和未验证范围。当前工具测试是评分工具的验证，不是任何模型成绩。

本版最高 100 分代表该静态清单全部有充分证据；仍不代表 UE 编译、运行、动画姿态、脚滑、性能或网络验收已经通过。

