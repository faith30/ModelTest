# 平地移动动画交付

## 使用

在本目录执行（仅 Python 标准库）：

```text
python src/build_assets.py --manifest raw/manifest.json --output assets/authored_assets.json
python .work/self_check.py
```

```python
import json
from src.controller import LocomotionController
with open('config/animation_graph.json', encoding='utf-8') as f:
    graph = json.load(f)
with open('assets/authored_assets.json', encoding='utf-8') as f:
    assets = json.load(f)
controller = LocomotionController(graph, assets)
controller.reset(seed=0)
plan = controller.step({
    'dt_seconds': 1 / 60,
    'velocity_world_cm_s': [300, 0, 0],
    'acceleration_world_cm_s2': [0, 0, 0],
    'actor_yaw_degrees': 0,
    'aim_yaw_degrees': 0,
})
```

## 文件与边界

- `src/build_assets.py`、`src/asset_analysis.py`：读取清单及全部 15 条有抽样资源，实际加工 26 骨骼姿态、root 轨迹/距离、接触估计和循环窗口。
- `assets/authored_assets.json`：37 个唯一资源；15 个 `ready` 内嵌加工帧，22 个 `deferred_missing_samples` 的 `data` 为 `null`。没有复制或伪造缺失姿态。条目包含原始 ID、语义、加工配方和抽样文件 SHA256。
- `config/animation_graph.json`：控制器实际消费的节点绑定、阈值、方向角、同步组和骨骼集合。它是本实现专用声明式计划图，不是 UE AnimGraph 文件，也不是通用图执行器。
- `src/controller.py`：逐帧计划器，包含验证、状态、时钟、混合、同步和有序姿态操作意图。
- `.work/`：本地生成与自查脚本；`.tmp/`：自查中间文件。`SELF_CHECK.json` 是计划/数值检查，不是最终姿态质量报告。

## 资源加工约定

1. 源 `+Y` 前、`+X` 左变为角色 `+X` 前、`-Y` 左：`B(x,y,z)=(y,-x,z)`，相当于绕 Z 旋转 -90°。四元数使用 Hamilton 主动旋转 xyzw；同时重新表达骨骼局部基，故 `q'=B*q*B^-1`，不是把源四元数不加处理地复制。
2. 对 component-space 每帧：提取 root 位置和相对首帧的连续 yaw；所有骨骼减去当前 root XY，再反转相对 root yaw。保留 Z 与初始 root 旋转。加工资源为 in-place；位移由外部角色系统拥有，root 路径只用于分析/匹配，不能再施加为世界位移。
3. 保留全部原始抽样时刻，以首帧为时间零点，不声称重新取得高精度数据。归一化四元数并统一相邻帧半球。位置/曲线线性插值，旋转由下游以最短弧 slerp 求值。
4. 距离曲线来自 root XY 累计弧长。停步剩余距离为总弧长减当前弧长，不是投影距离；pivot 用累计弧长避免往返导致非单调。同时保存 incoming 轴上最大位移时刻作为实测反向提示。
5. 足部接触估计来自原始含 root 位移的 component-space 足部 XY 速度与高度。使用每足高度 5% 分位值、2–7cm 高度过渡、速度阈值、3 点中值与迟滞；所有参数/曲线/估计事件都可追溯。它们不是原始动画通知，也没有地面碰撞或压力标注。
6. 8 个循环各自选择有实测 L–R–L 接触起点的单步幅窗口，以端点 component 位置 RMS 最小为准；不裁掉其它加工帧。`loop_range_seconds` 使用完整加工时间轴上的真实起止时间，播放器不把窗口起点当作零。端点位置/旋转差也保留用于审查；没有做 seam 修复，不能声称无缝。
7. 缺样资源保留原始 ID 和同一通用配方。补入合法采样后重新运行构建即可走相同流程；当前不为其填 duration、接触、距离或转身曲线。Idle 也不能物化。

## 每帧逻辑

- 输入验证：缺字段、非三维向量、bool、非有限数、非正 dt 明确抛出 `ValueError`。有限但超出数值支持范围的输入也明确拒绝：dt > 3600 秒或任意速度/加速度分量绝对值 > 1e9；防止平方溢出，不将其当正常游戏运动。yaw 规范化到等价角度。只使用 XY，Z 经有限性验证后忽略；假设持续 grounded。
- 用 actor yaw 将世界速度/加速度投到角色局部。四方向在圆周上相邻线性混合，方向平滑走最短角，离散动作方向有迟滞。速度连续混合 walk/jog，起停动作另有 gait 迟滞。这里跑步对应输入的 `jog`，没有虚构 sprint。
- 状态为 Idle、Start、Cycle、Stop、Pivot、Turn。起步由速度或加速度意图触发；可在加速中更换方向/步态，受最短持有时间约束。停步由低速或制动到停时间触发；重新加速可中断。反向由帧间速度反转或速度加短时加速度预测触发，优先于停步，并有锁存与冷却，避免每帧重开。已进入 Stop 后不再仅凭短时预测触发 pivot，需要观测到实际反向；这是没有期望速度输入时对普通制动的保守处理。起停/变向选择保留入向步态，避免骤停瞬间因速度为零误选 walk-stop。
- Pivot 的目录方向解释为 **进入变向前的方向**，不是离开方向。已有 jog-fwd-pivot 的 root 确实先前进再后退；缺样方向只是保留该绑定假设，不能声称已检查它们的真实运动。输入没有期望速度，强制动和主动反向存在不可完全消除的歧义。
- 起步累计实际输入速度距离，并在源距离曲线上反求时间；停步用 `v²/(2a)` 估算剩余距离、在源曲线上反求时间。时间保持单调、倍率有限；低速时保留最小时间推进，不会卡在距离平台。它不是碰撞感知 stop-location prediction，也不保证实际停点与动画完全一致。
- 动作缺采样时仍输出所请求资源，但 `sample_time_seconds=null`、`play_rate=0`、`pose_materializable=false`。状态机的策略超时仅决定何时切换，**不是资源时长、播放到某一打点或已经完成动作的证据**。不默默以正向片段假冒侧向起停，不把 Idle 当可播放兜底。
- 循环共享一个步幅相位：L=0、R=0.5、下一 L=1。每个资源在自己的实测循环窗口内分段线性映射采样时间，倍率为映射导数。速度决定相位推进，方向/步态切换不重置相位；动作接入循环时用当前两足相对位置选择最近循环采样相位。单次动作不强行成为循环同步成员。缺标记时使用整个窗口归一化相位，明确降级。
- 权重指数交叉淡化，所有有效玩家权重归一化；中断时保留已有玩家时间，直到权重消退。第一次调用直接采用目标计划。没有隐式 UE inertialization。
- 转身用 `aim - visual_yaw` 的最短角：负值选人体左转（目录正角），正值选右转（目录负角）。根据偏差选 90/180。实测 root yaw 已从帧中移除，由控制器按曲线累积到 visual facing，输出相对当前 actor 的 yaw offset，避免外部 actor yaw 更新时重复旋转。移动时 offset 衰减回 actor；控制器不修改输入 actor yaw、不输出角色运动命令。缺样转身不会编造 root yaw 进度；策略超时后对同一未改变的 aim 抑制重复请求，待 aim 改变后可重新触发。

## 输出时钟、操作语义

`sample_time_seconds` 是本帧的权威采样位置。执行方应按它直接采样，**不可再额外乘 dt 推进一次**。`play_rate` 对循环为当前相位映射导数，对单次动作为本帧实际前进量/dt，缺失资源为 0。循环回绕限定在资源记录的窗口。同步 leader 只是最高权重玩家的报告身份，所有成员的时间由控制器统一计算，不依赖外部同步服务。

操作按数组顺序：播放器权重混合 → component 全身 root yaw offset → 有限动作方向 warp → stride warp → 加速度 lean → 基于实测接触权重的足部 IK 意图。每个操作引用上一操作或已有 player ID。这些是执行意图，不是算出的最终骨骼变换：

- 方向循环本身已混合四方向，不重复做全角度方向 warp；pivot 保持入向对齐，不在反向帧把整个 pivot 再翻一次。
- stride 倍率有上下界；lean 是参数化操作意图，不伪称存在原始 additive clip。
- 接触权重按当前玩家/时间实际读取曲线；缺样玩家贡献为未知覆盖率，不当作已确认离地。没有 actor 世界位置，不能实现可信世界足锁；不生成虚构足锁目标。没有 IK solver、完整骨架、脚底绑定或碰撞查询，IK 必须由下游另行实现。

## 限制与待完成

这是静态资源及执行计划交付，没有 UE、完整 AnimGraph 运行、渲染器或最终姿态验收。足部窗口端点误差、启发式接触、跨方向/步态混合、身体倾斜和足部 IK 都需补齐下游执行器后人工与数值检查；不能由本地计划测试推断观感或滑步质量。只有 26 骨骼子集及其已有父索引，不扩写 Manny 全骨架、绑定姿态或 IK 骨。22 条缺样资源（含 Idle、部分起停/pivot/转身）仍待合法采样；资源依赖完整但行为可物化性不完整。

## 本地自查结果

`SELF_CHECK.json` 记录 11 组检查、41 个输入场景、14,073 帧计划验证，包括 8 个走跑循环、8 个突停、8 个入向 pivot、正常制动/重启、四类转身与缺样策略、actor yaw 跟随、跨 ±180°、变步长、方向/步态扫动、随机输入变化、输入拒绝、reset 重现与图配置变更。逐帧检查权重和引用、同步相位、窗口范围、接触曲线取值及 JSON 有限性；逐资源检查源哈希、源帧数、距离单调性、四元数单位长度，以及由加工姿态加回提取 root 变换后与源转换结果的一致性。

另用不同 `PYTHONHASHSEED` 的独立进程检查同一 900 帧计划摘要一致，并检查 CLI 重建资源表逐字节一致。结果是软件/data 自查通过，不代表最终动画观感、足锁效果或 UE 集成验证通过。
