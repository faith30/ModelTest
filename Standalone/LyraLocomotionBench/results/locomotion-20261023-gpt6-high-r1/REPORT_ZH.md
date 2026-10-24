# Lyra动画细节：Opus、DeepSeek、GPT-6三路对比

三路均已独立交付，并按同一冻结的40项/100分清单完成静态审查。分数衡量本题交付的细节覆盖与正确性，不是UE运行通过率或最终动画视觉质量。

| 实际响应模型 | 静态分数 | 正式用时 | 正式调用 |
|---|---:|---:|---:|
| `claude-opus-5-5` | **84.5/100** | 14分55秒 | 1 |
| `deepseek-v4-pro-202606` | **46.5/100** | 12分54秒 | 1 |
| `gpt-6-astra` | **87.5/100** | 15分53秒 | 1 |

本轮加权静态结果为 GPT-6 87.5、Opus 84.5、DeepSeek 46.5。GPT-6 领先主要来自资源坐标与接触制作、匀速移动判断和 L–R–L 标记相位；Opus 的 Pivot 距离预测与反查更完整，但存在匀速零加速度误入 Stop 的关键错误。DeepSeek 完成了基础加工和状态框架，距离匹配、同步和 Warp 的核心细节缺失较多。三路都没有完整交付同步事件的归属与跨圈唯一性契约；总分不替代对这些具体缺陷的判断。

## 分项比较

| 类别 | 满分 | Opus | DeepSeek | GPT-6 |
|---|---:|---:|---:|---:|
| 资源制作 | 20 | 18 | 12 | 20 |
| 移动状态 | 18 | 16.5 | 12 | 18 |
| 同步组 | 16 | 10.5 | 2.5 | 12 |
| 距离匹配 | 16 | 13 | 2 | 11 |
| Warp与朝向 | 12 | 9 | 2.5 | 9.5 |
| 架构与生命周期 | 10 | 10 | 9 | 9 |
| 健壮性与复现 | 8 | 7.5 | 6.5 | 8 |

## claude-opus-5-5：主要发现

整体方案完整，起停及 Pivot 距离匹配、上身朝向分层有实际实现；主要风险集中在移动意图判断、坐标闭合和同步细节。

| 项目 | 发现 | 证据 |
|---|---|---|
| DST02, DST03, ARC02 | 起步按位移推进，停止预测制动距离，Pivot 区分减速与反向阶段；上身朝向有具体骨骼权重和组合顺序。其中 Pivot 距离处理和上身朝向分层比 GPT 本轮交付更完整。 | [DST02](../locomotion-20261023-high-r1/opus/candidate/src/controller.py#L369) · [DST03](../locomotion-20261023-high-r1/opus/candidate/config/animation_graph.json#L15) · [ARC02](../locomotion-20261023-high-r1/opus/candidate/config/animation_graph.json#L31) |
| LOC01 | 把加速度当作移动输入意图，非零匀速、零加速度时会误进 Stop；这是高总分仍不能忽略的关键行为错误。 | [LOC01](../locomotion-20261023-high-r1/opus/candidate/src/controller.py#L180) |
| RES02, RES06 | 去除完整根旋转时抵消固定坐标转换；循环接缝又重复制作接触起点。姿态坐标与标记制作均有实际缺口。 | [RES02](../locomotion-20261023-high-r1/opus/candidate/src/build_assets.py#L142) · [RES06](../locomotion-20261023-high-r1/opus/candidate/src/build_assets.py#L214) |
| SYN02, SYN03, SYN04, SYN06 | 同步只按左脚到下一左脚映射，缺左右脚分段相位；公共标记退化、按声明权重选择 leader、Notify 归属及跨圈事件唯一性不完整。 | [SYN02](../locomotion-20261023-high-r1/opus/candidate/src/controller.py#L281) · [SYN03](../locomotion-20261023-high-r1/opus/candidate/src/controller.py#L297) · [SYN04](../locomotion-20261023-high-r1/opus/candidate/src/controller.py#L324) · [SYN06](../locomotion-20261023-high-r1/opus/candidate/src/controller.py#L256) |
| WRP01, WRP02, WRP04 | 方向补偿未扣除有效根朝向偏移，步幅缺零速分母保护与平滑，Start 缺 RootYaw Hold。 | [WRP01](../locomotion-20261023-high-r1/opus/candidate/src/controller.py#L224) · [WRP02](../locomotion-20261023-high-r1/opus/candidate/src/controller.py#L603) · [WRP04](../locomotion-20261023-high-r1/opus/candidate/src/controller.py#L224) |
| DST04, DST05, DST06, ROB01 | 曲线合法性、距离限速残差与 seek 副作用契约不足；极大但有限的输入仍可能在派生速度处溢出。 | [DST04](../locomotion-20261023-high-r1/opus/candidate/src/anim_math.py#L110) · [DST05](../locomotion-20261023-high-r1/opus/candidate/src/controller.py#L268) · [DST06](../locomotion-20261023-high-r1/opus/candidate/src/controller.py#L239) · [ROB01](../locomotion-20261023-high-r1/opus/candidate/src/controller.py#L138) |

[原始答复](../locomotion-20261023-high-r1/opus/FINAL_ANSWER.txt) · [交付说明](../locomotion-20261023-high-r1/opus/candidate/IMPLEMENTATION.md) · [40项扣分证据](../locomotion-20261023-high-r1/opus/REVIEW_ZH.md) · [结构化评分](../locomotion-20261023-high-r1/opus/score.json)

## deepseek-v4-pro-202606：主要发现

提交了可追踪的基础资源加工、四向走跑与姿态操作框架，但许多 Lyra 移动关键机制停留在基础播放层。缺采样的22项没有作为扣分原因。

| 项目 | 发现 | 证据 |
|---|---|---|
| ARC02, ARC04 | 根运动与上身 aim 有独立操作、骨骼范围和顺序，输入快照与状态边界也清楚，基础架构获得较高分。 | [ARC02](../locomotion-20261023-high-r1/deepseek/candidate/src/controller.py#L326) · [ARC04](../locomotion-20261023-high-r1/deepseek/candidate/src/controller.py#L59) |
| RES06, RES07 | 对已有15段采样未制作脚接触标记和距离曲线，属于实际制作缺失，并非题包缺素材造成。 | [RES06](../locomotion-20261023-high-r1/deepseek/candidate/src/build_assets.py#L194) · [RES07](../locomotion-20261023-high-r1/deepseek/candidate/src/build_assets.py#L76) |
| SYN01, SYN02, SYN03, SYN04, SYN05, SYN06 | 同步输出为 independent；缺标记相位映射、公共标记退化、leader 与事件归属，组配置与实际消费也不一致。 | [SYN01](../locomotion-20261023-high-r1/deepseek/candidate/config/animation_graph.json#L460) · [SYN02](../locomotion-20261023-high-r1/deepseek/candidate/src/controller.py#L311) · [SYN03](../locomotion-20261023-high-r1/deepseek/candidate/src/controller.py#L281) · [SYN04](../locomotion-20261023-high-r1/deepseek/candidate/src/controller.py#L311) · [SYN05](../locomotion-20261023-high-r1/deepseek/candidate/src/controller.py#L467) · [SYN06](../locomotion-20261023-high-r1/deepseek/candidate/src/controller.py#L281) |
| DST01, DST02, DST03, DST04 | Start、Stop、Pivot 主要按时间播放，缺距离语义、停止及反向目标预测和曲线反查。 | [DST01](../locomotion-20261023-high-r1/deepseek/candidate/src/build_assets.py#L76) · [DST02](../locomotion-20261023-high-r1/deepseek/candidate/src/controller.py#L281) · [DST03](../locomotion-20261023-high-r1/deepseek/candidate/src/controller.py#L391) · [DST04](../locomotion-20261023-high-r1/deepseek/candidate/src/controller.py#L281) |
| WRP01, WRP02, WRP04 | 缺方向补偿、步幅补偿和 RootYaw 状态策略；四向选片与播放倍率不能完成这些职责。 | [WRP01](../locomotion-20261023-high-r1/deepseek/candidate/src/controller.py#L326) · [WRP02](../locomotion-20261023-high-r1/deepseek/candidate/src/controller.py#L458) · [WRP04](../locomotion-20261023-high-r1/deepseek/candidate/src/controller.py#L120) |
| LOC04, LOC05, LOC06, ROB01, ROB02 | 重入 Start 不重置时钟，Stop 播完直接 Idle，Pivot 按瞄准差而非移动反向触发；另有字符串 nan 与自定义输出位置的边界问题。 | [LOC04](../locomotion-20261023-high-r1/deepseek/candidate/src/controller.py#L120) · [LOC05](../locomotion-20261023-high-r1/deepseek/candidate/src/controller.py#L403) · [LOC06](../locomotion-20261023-high-r1/deepseek/candidate/src/controller.py#L418) · [ROB01](../locomotion-20261023-high-r1/deepseek/candidate/src/controller.py#L46) · [ROB02](../locomotion-20261023-high-r1/deepseek/candidate/src/build_assets.py#L108) |

[原始答复](../locomotion-20261023-high-r1/deepseek/FINAL_ANSWER.txt) · [交付说明](../locomotion-20261023-high-r1/deepseek/candidate/IMPLEMENTATION.md) · [40项扣分证据](../locomotion-20261023-high-r1/deepseek/REVIEW_ZH.md) · [结构化评分](../locomotion-20261023-high-r1/deepseek/score.json)

## gpt-6-astra：主要发现

资源加工和状态细节表现较好，实测接触与 L–R–L 相位进入了实际计算，异常输入边界也较完整；主要未完成项是 Pivot 距离匹配、同步事件规则和上身朝向分层。

| 项目 | 发现 | 证据 |
|---|---|---|
| RES02, RES06, RES08, LOC01, LOC04, LOC05, LOC06, ROB01 | 保留坐标变换基底并只移除相对 root yaw，按实测接触选择循环区间；能区分匀速零加速度和停止，重入时钟、移动反向及输入校验也有明确路径。37项资源中15项实做、22项延期，未伪造缺样数据。 | [RES02](gpt6/candidate/IMPLEMENTATION.md#L40) · [RES06](gpt6/candidate/src/asset_analysis.py#L18) · [RES08](gpt6/candidate/src/build_assets.py#L23) · [LOC01](gpt6/candidate/src/controller.py#L239) · [LOC04](gpt6/candidate/src/controller.py#L147) · [LOC05](gpt6/candidate/src/controller.py#L266) · [LOC06](gpt6/candidate/src/controller.py#L269) · [ROB01](gpt6/candidate/src/controller.py#L38) |
| SYN02, SYN03, SYN04, SYN06 | L→R→L 分段相位与统一时钟完整，leader 按实际权重确定；但没有组级公共 marker 退化规则，也缺 Notify 归属和跨圈事件区间/唯一性。 | [SYN02](gpt6/candidate/src/asset_analysis.py#L47) · [SYN03](gpt6/candidate/src/asset_analysis.py#L61) · [SYN04](gpt6/candidate/config/animation_graph.json#L240) · [SYN06](gpt6/candidate/src/controller.py#L185) |
| DST02, DST03 | Start/Stop 有距离驱动；Pivot 仅按有界播放倍率推进，未把运动预测的反向目标距离生成与反查消费接起来。DST03 评价目标生成，DST02 评价目标消费，不因同一问题再扣资源或状态项。 | [DST02](gpt6/candidate/src/controller.py#L161) · [DST03](gpt6/candidate/src/controller.py#L214) |
| DST04, DST05, DST06 | 曲线反查缺非法/非单调输入契约，Stop 限速后固定 stride=1 且未声明残差取舍；初始化、重入和相位对齐也缺 seek/advance 的事件副作用约定。 | [DST04](gpt6/candidate/src/controller.py#L28) · [DST05](gpt6/candidate/src/controller.py#L220) · [DST06](gpt6/candidate/src/controller.py#L147) |
| WRP01, WRP02, WRP04 | 方向补偿未计入已施加的根偏移；步幅有分母保护但缺平滑；Start 与 Cycle 一样淡出，缺 RootYaw Hold。 | [WRP01](gpt6/candidate/src/controller.py#L247) · [WRP02](gpt6/candidate/src/controller.py#L378) · [WRP04](gpt6/candidate/src/controller.py#L250) |
| ARC02 | 已有 root 归属、操作顺序和脊柱范围，但 lean 只由加速度生成 pitch/roll，缺协调下肢移动与上身朝向偏差的独立计划。 | [ARC02](gpt6/candidate/config/animation_graph.json#L160) |

[原始答复](gpt6/FINAL_ANSWER.txt) · [交付说明](gpt6/candidate/IMPLEMENTATION.md) · [40项扣分证据](gpt6/REVIEW_ZH.md) · [结构化评分](gpt6/score.json)

## 可比条件与实际链路

- 题包、系统提示和任务提示逐字节一致，评分版本保持不变；三路均请求high、2700秒、每轮输出8192，仅Bash/Read/Write，不向模型提供裁判或其他答案。
- Opus、DeepSeek通过TClaude 0.1.9 / Claude Code 2.1.295；GPT-6通过原生Claude Code 2.1.289 / TT Switch。链路及版本不同，上游实际推理预算和输出限制没有独立确认。
- GPT正式作答前，旧OAuth刷新令牌导致一次无题目探针的9条401；用户重新授权后，短路径探针仍遭遇写入拒绝。只将GPT工作目录规范为完整路径后，文本、三工具及代理路由审计通过，CLI权限参数未扩大。
- 同期修复了评测日志解析器对字符串system.message事件的兼容；旧两路原始日志重解析结果保持相同。所有准备故障均与模型能力评分分开，失败记录保留，未向正式模型追加提示或补代码。
- 每路一次正式调用，控制器重试和人工跟进均为0。模型自行改错/自查及CLI输出长度续接保留在日志中；不可见的服务内部重试不作零次保证。
- 评分由主审与三个子审查代理分工，主审核对归属和跨项去重；评分器检查摘要、精确引文、完整性和算术，不自动裁判动画语义。
- 模型自行执行的Python检查与独立静态评分分开。评测端未执行候选或UE；没有脚滑、最终姿态、性能或网络验收结论。22条缺采样资源的合规延期不扣分。
- 隔离依靠独立工作目录、统一指令和可见访问日志审计，没有操作系统级文件/网络沙箱。未观察到读取裁判、其他答案、原UE工程或联网；不作不可越界保证。
- 每模型仅一份答案，结论限于本次任务和清单，不推断一般游戏开发能力或多次运行稳定性。

GPT正式路由审计（本机留存，未发布） · GPT完整访问审计（本机留存，未发布） · [推理预算可观测性](effort-observability.json) · 历史认证阻断报告（本机留存，未发布） · 路径兼容诊断（本机留存，未发布）

## 40项得分矩阵

| ID | 细节 | 满分 | Opus | DeepSeek | GPT-6 |
|---|---|---:|---:|---:|---:|
| RES01 | 原始输入、派生资源与来源可追溯 | 2 | 2 (pass) | 2 (pass) | 2 (pass) |
| RES02 | 骨架、单位和坐标系一致 | 3 | 2 (partial) | 2 (partial) | 3 (pass) |
| RES03 | 走跑与方向资源覆盖 | 3 | 3 (pass) | 3 (pass) | 3 (pass) |
| RES04 | 片段时域、循环与边界 | 2 | 2 (pass) | 2 (pass) | 2 (pass) |
| RES05 | 根轨迹数据与角色位移职责 | 3 | 3 (pass) | 2 (partial) | 3 (pass) |
| RES06 | 同步相位标记的制作 | 3 | 2 (partial) | 0 (missing) | 3 (pass) |
| RES07 | 曲线制作及可索引表示 | 2 | 2 (pass) | 0 (missing) | 2 (pass) |
| RES08 | 资源制作流程闭合 | 2 | 2 (pass) | 1 (partial) | 2 (pass) |
| LOC01 | 移动快照与派生量 | 3 | 1.5 (partial) | 3 (pass) | 3 (pass) |
| LOC02 | Walk/Jog选择与阈值稳定 | 2 | 2 (pass) | 2 (pass) | 2 (pass) |
| LOC03 | 四方向与斜向选择 | 3 | 3 (pass) | 2 (partial) | 3 (pass) |
| LOC04 | Idle到Start到Cycle | 3 | 3 (pass) | 1.5 (partial) | 3 (pass) |
| LOC05 | 减速、Stop与Idle | 3 | 3 (pass) | 1.5 (partial) | 3 (pass) |
| LOC06 | Pivot及重新起步 | 2 | 2 (pass) | 1 (partial) | 2 (pass) |
| LOC07 | 过渡竞争与连续性 | 2 | 2 (pass) | 1 (partial) | 2 (pass) |
| SYN01 | 组作用域与角色配置 | 3 | 3 (pass) | 1 (partial) | 3 (pass) |
| SYN02 | Marker相位不是Notify | 3 | 2 (partial) | 0 (missing) | 3 (pass) |
| SYN03 | 公共标记与退化策略 | 3 | 1 (partial) | 0 (missing) | 1 (partial) |
| SYN04 | Leader选择与事件归属 | 2 | 0.5 (partial) | 0 (missing) | 1 (partial) |
| SYN05 | 非循环起停与距离匹配的同步策略 | 3 | 3 (pass) | 1 (partial) | 3 (pass) |
| SYN06 | 接管、跨尾与事件唯一性 | 2 | 1 (partial) | 0.5 (partial) | 1 (partial) |
| DST01 | 距离曲线含义与符号 | 2 | 2 (pass) | 0 (missing) | 2 (pass) |
| DST02 | 按位移推进与按目标定位分开 | 3 | 3 (pass) | 0 (missing) | 2 (partial) |
| DST03 | 停止/转向目标来源 | 3 | 3 (pass) | 0 (missing) | 2 (partial) |
| DST04 | 曲线反查的确定性和边界 | 3 | 2 (partial) | 0 (missing) | 2 (partial) |
| DST05 | 播放速率限制与步幅补偿 | 3 | 2 (partial) | 1 (partial) | 2 (partial) |
| DST06 | Evaluator推进、跳转与副作用 | 2 | 1 (partial) | 1 (partial) | 1 (partial) |
| WRP01 | Orientation Warping的朝向分工 | 3 | 2 (partial) | 0 (missing) | 2 (partial) |
| WRP02 | Stride Warping的比例与限制 | 3 | 2 (partial) | 0 (missing) | 2.5 (partial) |
| WRP03 | 骨骼约束与姿态补偿契约 | 2 | 2 (pass) | 2 (pass) | 2 (pass) |
| WRP04 | RootYawOffset三类状态策略 | 3 | 2 (partial) | 0 (missing) | 2 (partial) |
| WRP05 | Turn In Place与转向曲线 | 1 | 1 (pass) | 0.5 (partial) | 1 (pass) |
| ARC01 | 状态逻辑、资源集与修正职责分开 | 2 | 2 (pass) | 2 (pass) | 2 (pass) |
| ARC02 | 移动与上身朝向的分层契约 | 2 | 2 (pass) | 2 (pass) | 1 (partial) |
| ARC03 | 节点生命周期 | 2 | 2 (pass) | 2 (pass) | 2 (pass) |
| ARC04 | 快照与共享派生数据边界 | 2 | 2 (pass) | 2 (pass) | 2 (pass) |
| ARC05 | 资源与图配置进入实际决策 | 2 | 2 (pass) | 1 (partial) | 2 (pass) |
| ROB01 | 输入异常与稳定退化 | 3 | 2.5 (partial) | 2 (partial) | 3 (pass) |
| ROB02 | 独立复现与提交完整性 | 3 | 3 (pass) | 2.5 (partial) | 3 (pass) |
| ROB03 | 证据与限制诚实可审查 | 2 | 2 (pass) | 2 (pass) | 2 (pass) |

## 冻结与复核

- 题包：`b8c3c2523e5f2efee6e6f9799d2926fa5bca94822211523e56253dc96945a87e`
- 清单：`5d40aaf760fa9c3b965cf9f8ea4e05badcf4ea632c1700187466404a019b5486`
- opus候选：`9a649cd8c60d007f03149069e3475c262082825c8c8317dab1bd59ad558c8b86`；40项与3个门槛均已审查。
- deepseek候选：`b00081836bc60711cc1899ee31704637d82e3a655b0e93fe2914d58c738f24c6`；40项与3个门槛均已审查。
- gpt6候选：`a8cfd07be7c3c6e34d75b63e3ab668cf61331392984fbc48d5edacb0ab095270`；40项与3个门槛均已审查。

[结构化三路结果](comparison-three-models.json) · 统一配置计划（本机留存，未发布） · GPT执行记录（本机留存，未发布）

[冻结细节清单与来源](../../evaluator/DETAIL_CHECKLIST_ZH.md) · [审查与扣分方法](../../evaluator/REVIEW_GUIDE_ZH.md)
