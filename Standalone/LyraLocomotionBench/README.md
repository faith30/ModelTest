# LyraLocomotionBench：独立动画开发评测

这是以 Lyra 走跑动作为素材的 Python 评测工程，用于检查模型能否完成动画资源加工、动画图配置和控制逻辑。分包、制作、静态审查和分数汇总均无需安装或运行 Unreal Engine。

模型交付动画数据、声明式动画图和抽象控制器。评分依据冻结的 **40 项、100 分**细节清单；分数表示本题的静态交付质量，不表示 UE 运行通过率、最终动画观感或一般模型能力排名。

[下载冻结候选 ZIP](dist/LyraLocomotionBench-candidate.zip?raw=true) · [中文任务](candidate_template/TASK_ZH.md) · [输入输出接口](candidate_template/INTERFACE.md) · [40 项评分清单](evaluator/DETAIL_CHECKLIST_ZH.md) · [三路结果与代码](results/README.md)

## 快速开始

需要 Python 3.10 或更新版本。核心工具仅使用标准库，无需安装 Python 包、UE 或 GPU。克隆仓库后进入本目录：

```sh
cd Standalone/LyraLocomotionBench
python -m unittest discover -s tests -v
python tools/package_candidate.py --output dist/LyraLocomotionBench-candidate-local.zip
python tools/score_review.py --help
```

测试集包含 10 项评分器边界测试。分包命令从 `candidate_template/` 按白名单生成候选 ZIP 和逐文件 SHA-256 清单；上面的自定义名称保留已发布的冻结包。

正式使用时，把[冻结候选 ZIP](dist/LyraLocomotionBench-candidate.zip?raw=true) 解压到模型独立工作目录，让模型阅读 `TASK_ZH.md` 和 `INTERFACE.md` 并保存交付文件。**只把候选包交给模型**；本仓库同时包含裁判资料与历史答案。目录分离不是操作系统沙箱，盲测环境应限制模型访问额外资料。

冻结 ZIP 的 SHA-256：

```text
b8c3c2523e5f2efee6e6f9799d2926fa5bca94822211523e56253dc96945a87e
```

[包内文件清单](dist/LyraLocomotionBench-candidate.manifest.json) · [运行前冻结记录](evaluator/benchmark-freeze.json)。冻结记录中的 `prepared_not_run` 是当时的准备状态，后续结果单独保存在 `results/` 和 `evaluator/model-runs/`。

## 模型需要交付什么

| 层 | 主要产物 | 检查内容 |
|---|---|---|
| 资源加工 | `src/build_assets.py`、`assets/authored_assets.json` | 生成标记、事件、曲线和资源描述，且数据被实际引用 |
| 动画图 | `config/animation_graph.json` | 状态、过渡、播放器、同步组、动画层和姿态修正的连接关系 |
| 控制逻辑 | `src/controller.py`、`IMPLEMENTATION.md` | 逐帧选片、采样时间、混合与修正计划，以及缺失素材的处理 |

控制器输出抽象动画执行计划，不要求实现完整动画引擎。只在说明中提到 Sync Group、Distance Matching 等名称而没有相应配置和消费逻辑，不算完成实现。

题目有 **37** 个地面动作条目，其中 **15** 段有 26 根主要骨骼采样，覆盖八段走跑循环、四段前向起停、一段 Pivot 和两段原地转身。其余 **22** 项标为 `metadata_only`。缺样本时应提交通用配方并标记 `deferred_missing_samples`，不应虚构精确时长、轨道或打点。

采样使用 component-space、厘米、Z-up 和 XYZW 四元数。源片前向为 mesh 的 +Y，抽象 actor 前向为 +X；实现需要说明坐标转换，避免重复施加已包含在采样中的 root 位移。本题不评分跳跃/落地、坡地、网络复制、引擎线程性能、完整 Manny IK、蒙皮或美术质量。

## 最新三路结果

2026-10-24 完成三路正式作答和全部 40 项静态审查：

| 实际响应模型 | 静态分数 | 逐项评审与原始候选 |
|---|---:|---|
| `gpt-6-astra` | **87.5/100** | [GPT 评审](results/locomotion-20261023-gpt6-high-r1/gpt6/REVIEW_ZH.md) · [候选](results/locomotion-20261023-gpt6-high-r1/gpt6/candidate/) |
| `claude-opus-5-5` | **84.5/100** | [Opus 评审](results/locomotion-20261023-high-r1/opus/REVIEW_ZH.md) · [候选](results/locomotion-20261023-high-r1/opus/candidate/) |
| `deepseek-v4-pro-202606` | **46.5/100** | [DeepSeek 评审](results/locomotion-20261023-high-r1/deepseek/REVIEW_ZH.md) · [候选](results/locomotion-20261023-high-r1/deepseek/candidate/) |

详细结论见[三路对比报告](results/locomotion-20261023-gpt6-high-r1/REPORT_ZH.md)和[结构化比较](results/locomotion-20261023-gpt6-high-r1/comparison-three-models.json)。GPT 在资源加工、匀速移动和双脚标记相位上更完整，Opus 的 Pivot 距离处理和上身朝向分层更完整；三路均有同步事件细节缺口。

三路使用同一冻结题包和提示词，均请求 high、45 分钟及每轮 8192 输出 token。GPT 使用 Claude Code 2.1.289 经 TT Switch，另两路使用 TClaude / Claude Code 2.1.295；这些请求设置不证明服务端采用相同计算预算。正式作答各调用一次，没有人工补写候选。认证与路径兼容故障作为基础设施历史单独记录，不计为模型扣分。原始调用日志和认证排查资料本机留存，未发布。

## 复核评分

评测者根据冻结候选逐项填写 `pass / partial / missing / incorrect / unreviewed`、文件引用和理由，再由 `tools/score_review.py` 汇总。任何未审项目或未确认门槛都会让最终总分保持 `null`。该工具验证哈希、证据引用和分数计算，不会自动判断代码语义，也不会执行候选代码。

以已发布的 GPT 评审为例，在本目录执行：

```sh
python tools/score_review.py --rubric evaluator/rubric.json --review results/locomotion-20261023-gpt6-high-r1/gpt6/review.json --candidate results/locomotion-20261023-gpt6-high-r1/gpt6/candidate --output reports/gpt6-recomputed.json
```

预期为 `complete`、`87.5`。另两路路径及复核说明见 [results/README.md](results/README.md)，新建评审的方法见[审查指南](evaluator/REVIEW_GUIDE_ZH.md)。

2026-10-24 发布副本验证：10 项评分器测试通过；重新分包生成 23 个候选文件，ZIP 哈希与冻结记录一致；三份完整候选和原始评审在新目录重算均为 `complete`，分数分别为 87.5、84.5、46.5。本次只复算静态审查，没有执行候选代码、调用模型或运行 UE。验证环境为 Windows，Linux 实测尚未进行。

## 目录与可选工具

```text
candidate_template/      空白作答接口、原始动作清单与骨骼采样
dist/                    冻结候选 ZIP 与逐文件哈希清单
evaluator/               评分清单、Lyra 静态事实、冻结记录和结果摘要
results/                 报告、完整模型候选、逐项评审与分数
tests/                   评分器边界测试
tools/                   分包、静态审查汇总及可选的本机工具
```

`tools/run_models.py` 和 `tools/cli_runtime/` 是可选本机调用器，需要自行安装并登录 Node/TClaude，确认实际模型路由后才能使用。`tools/run_gpt6_tt.py` 保留本次特定 Claude Code 版本、TT Switch 路由和旧轮次依赖；`tools/audit_tt_route.py` 读取本机 TT Switch 数据库元数据。它们不是开箱即用的跨机器入口，核心分包和评分不依赖它们，也不包含账号凭据。

`tools/prepare_inputs.py` 读取准备机已有的 Lyra 源资产和 AnimationMarkBench 导出；`tools/verify_benchmark.py` 还会检查源文件与本机准备记录，并写回准备冻结记录。这两个脚本仅供原始准备环境使用，下载者无需运行。`evaluator/source-audit.json` 等文件中的绝对路径保留为历史来源信息，不是公开下载链接或运行依赖。

原始 `review.json`、`score.json` 和结果摘要保持不变。发布报告仅调整导航链接，历史 JSON 中的路径与报告哈希仍指原始本机记录；完整候选每个文件和换行均需保持原样，才能复核冻结哈希。详情见[结果发布说明](results/README.md)。

## 来源

动画素材源于 Epic Lyra Starter Game，授权说明见 [LICENSE-Lyra.md](candidate_template/LICENSE-Lyra.md)。动作设计参考 [Epic Lyra 动画文档](https://dev.epicgames.com/documentation/en-us/unreal-engine/animation-in-lyra-sample-game-in-unreal-engine)与[动画适配技术文章](https://www.unrealengine.com/tech-blog/adapting-lyra-animation-to-your-ue5-game)。机制语义与本地证据列在[评分清单](evaluator/DETAIL_CHECKLIST_ZH.md)和[准备说明](evaluator/PREPARATION_ZH.md)。
