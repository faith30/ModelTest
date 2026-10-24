# Opus / DeepSeek：Lyra 动画细节静态评测

两路均通过 TClaude 独立作答。以下是冻结的40项/100分清单对实际交付的静态评分，不是UE运行、脚滑或动画视觉质量排名。分数按细节加权，不是功能通过率；高分也不能抵消匀速误停等关键行为错误。

| 实际响应模型 | 静态分数 | 用时 | 交付/输入 |
|---|---:|---:|---|
| `claude-opus-5-5` | **84.5/100** | 14分55秒 | 五项已保存；不可改输入一致 |
| `deepseek-v4-pro-202606` | **46.5/100** | 12分54秒 | 五项已保存；不可改输入一致 |

两路均审完40项、确认3个门槛；均未触发整类缺交付的分数上限。缺失采样的22条素材不作为扣分理由。

## 主要差异

- Opus实际制作了标记、距离/转身曲线，也有状态机和参数化Warp计划；但把加速度当输入意图，零加速度会误判停止。其坐标去根、同步区间和RootYaw状态分工也存在缺口，详见逐项证据。
- DeepSeek完成了资源转换和基本播放控制，但未交付距离曲线/距离匹配，组配置没有形成实际同步算法；pivot按瞄准角差触发，方向与步幅Warp、RootYaw分工覆盖不足。

## 分项

| 类别 | 满分 | Opus | DeepSeek |
|---|---:|---:|---:|
| 资源制作 | 20 | 18 | 12 |
| 移动状态 | 18 | 16.5 | 12 |
| 同步组 | 16 | 10.5 | 2.5 |
| 距离匹配 | 16 | 13 | 2 |
| Warp与朝向 | 12 | 9 | 2.5 |
| 架构与生命周期 | 10 | 10 | 9 |
| 健壮性与复现 | 8 | 7.5 | 6.5 |

## 原始作答与审查

- opus: [模型原始答复](opus/FINAL_ANSWER.txt) · [交付说明](opus/candidate/IMPLEMENTATION.md) · [40项扣分证据](opus/REVIEW_ZH.md) · [结构化审查](opus/review.json) · [评分器结果](opus/score.json)
- deepseek: [模型原始答复](deepseek/FINAL_ANSWER.txt) · [交付说明](deepseek/candidate/IMPLEMENTATION.md) · [40项扣分证据](deepseek/REVIEW_ZH.md) · [结构化审查](deepseek/review.json) · [评分器结果](deepseek/score.json)

## 执行与证据边界

- 相同题包、系统提示、题目提示和工具；请求high，每路最多2700秒，每轮输出预算请求8192。响应确认了模型名，但服务端是否实际应用相同推理预算/输出限制没有独立回读。
- 每路一次正式调用；各有一次不含题目的连通探针。控制器重试0、人工跟进0、评测者补代码0；模型自行修正和自查保留在原始日志中。CLI服务内部不可见重试不作零次保证。
- 审查由主助手与三个子审查代理分工，主助手核对归属及跨项去重；评分器验证摘要、引文位置、完整性与算术，不自动判断动画语义。
- 模型自行运行的Python加工/自查与本次独立静态评分分开。评测端未执行候选、未启动/编译UE，没有最终姿态、脚滑、性能、网络验收结论。
- 隔离为独立目录、统一指令和日志审计，没有操作系统级文件/网络沙箱。可见工具记录未发现读取裁判、其他答案、原UE项目或网络资料；这不等于证明任何宿主访问都不可能发生。
- 原D:/ModelTest的Git状态与运行前记录一致；本轮工具和交付均存于独立D:/LyraLocomotionBench。
- 本轮只有一次任务/每模型一次作答；分数只反映这份冻结清单上的交付，不推断模型的一般开发能力或跨次稳定性。

完整访问审计（本机留存，未发布） · 执行原始记录（本机留存，未发布） · 统一运行计划（本机留存，未发布）

## 40项得分矩阵

| ID | 细节 | 满分 | Opus | DeepSeek |
|---|---|---:|---:|---:|
| RES01 | 原始输入、派生资源与来源可追溯 | 2 | 2 (pass) | 2 (pass) |
| RES02 | 骨架、单位和坐标系一致 | 3 | 2 (partial) | 2 (partial) |
| RES03 | 走跑与方向资源覆盖 | 3 | 3 (pass) | 3 (pass) |
| RES04 | 片段时域、循环与边界 | 2 | 2 (pass) | 2 (pass) |
| RES05 | 根轨迹数据与角色位移职责 | 3 | 3 (pass) | 2 (partial) |
| RES06 | 同步相位标记的制作 | 3 | 2 (partial) | 0 (missing) |
| RES07 | 曲线制作及可索引表示 | 2 | 2 (pass) | 0 (missing) |
| RES08 | 资源制作流程闭合 | 2 | 2 (pass) | 1 (partial) |
| LOC01 | 移动快照与派生量 | 3 | 1.5 (partial) | 3 (pass) |
| LOC02 | Walk/Jog选择与阈值稳定 | 2 | 2 (pass) | 2 (pass) |
| LOC03 | 四方向与斜向选择 | 3 | 3 (pass) | 2 (partial) |
| LOC04 | Idle到Start到Cycle | 3 | 3 (pass) | 1.5 (partial) |
| LOC05 | 减速、Stop与Idle | 3 | 3 (pass) | 1.5 (partial) |
| LOC06 | Pivot及重新起步 | 2 | 2 (pass) | 1 (partial) |
| LOC07 | 过渡竞争与连续性 | 2 | 2 (pass) | 1 (partial) |
| SYN01 | 组作用域与角色配置 | 3 | 3 (pass) | 1 (partial) |
| SYN02 | Marker相位不是Notify | 3 | 2 (partial) | 0 (missing) |
| SYN03 | 公共标记与退化策略 | 3 | 1 (partial) | 0 (missing) |
| SYN04 | Leader选择与事件归属 | 2 | 0.5 (partial) | 0 (missing) |
| SYN05 | 非循环起停与距离匹配的同步策略 | 3 | 3 (pass) | 1 (partial) |
| SYN06 | 接管、跨尾与事件唯一性 | 2 | 1 (partial) | 0.5 (partial) |
| DST01 | 距离曲线含义与符号 | 2 | 2 (pass) | 0 (missing) |
| DST02 | 按位移推进与按目标定位分开 | 3 | 3 (pass) | 0 (missing) |
| DST03 | 停止/转向目标来源 | 3 | 3 (pass) | 0 (missing) |
| DST04 | 曲线反查的确定性和边界 | 3 | 2 (partial) | 0 (missing) |
| DST05 | 播放速率限制与步幅补偿 | 3 | 2 (partial) | 1 (partial) |
| DST06 | Evaluator推进、跳转与副作用 | 2 | 1 (partial) | 1 (partial) |
| WRP01 | Orientation Warping的朝向分工 | 3 | 2 (partial) | 0 (missing) |
| WRP02 | Stride Warping的比例与限制 | 3 | 2 (partial) | 0 (missing) |
| WRP03 | 骨骼约束与姿态补偿契约 | 2 | 2 (pass) | 2 (pass) |
| WRP04 | RootYawOffset三类状态策略 | 3 | 2 (partial) | 0 (missing) |
| WRP05 | Turn In Place与转向曲线 | 1 | 1 (pass) | 0.5 (partial) |
| ARC01 | 状态逻辑、资源集与修正职责分开 | 2 | 2 (pass) | 2 (pass) |
| ARC02 | 移动与上身朝向的分层契约 | 2 | 2 (pass) | 2 (pass) |
| ARC03 | 节点生命周期 | 2 | 2 (pass) | 2 (pass) |
| ARC04 | 快照与共享派生数据边界 | 2 | 2 (pass) | 2 (pass) |
| ARC05 | 资源与图配置进入实际决策 | 2 | 2 (pass) | 1 (partial) |
| ROB01 | 输入异常与稳定退化 | 3 | 2.5 (partial) | 2 (partial) |
| ROB02 | 独立复现与提交完整性 | 3 | 3 (pass) | 2.5 (partial) |
| ROB03 | 证据与限制诚实可审查 | 2 | 2 (pass) | 2 (pass) |

## 冻结摘要

- 输入ZIP：`b8c3c2523e5f2efee6e6f9799d2926fa5bca94822211523e56253dc96945a87e`
- 裁判清单：`5d40aaf760fa9c3b965cf9f8ea4e05badcf4ea632c1700187466404a019b5486`
- opus最终候选：`9a649cd8c60d007f03149069e3475c262082825c8c8317dab1bd59ad558c8b86`
- deepseek最终候选：`b00081836bc60711cc1899ee31704637d82e3a655b0e93fe2914d58c738f24c6`
