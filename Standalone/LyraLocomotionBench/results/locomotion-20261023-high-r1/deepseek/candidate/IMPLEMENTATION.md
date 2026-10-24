# 实现说明：Lyra 风格平地移动动画交付

## 概览

本交付把 `raw/manifest.json` 中的 37 条无武器地面素材整理为可审查的动画资源表、动画图与每帧控制逻辑。15 条具有 26 骨骼姿态抽样的素材被实际读取、转换并落盘为运行时空间加工产物；22 条仅有元数据的素材保留原始条目引用，登记可复用的通用加工配方，并标记为 `deferred_missing_samples`，不编造骨骼姿态、曲线、打点时间或执行结果。

## 文件与入口

- `src/build_assets.py`：资源制作入口。`build_assets(manifest, manifest_dir)` 完成读取、坐标转换、指标计算和产物写入；CLI 与接口一致。
- `assets/authored_assets.json`：生成的资源表。`assets/processed/*.json` 为加工产物。
- `config/animation_graph.json`：声明式动画图（输入、参数阈值、播放器节点、同步组、输出语义），控制器实际读取其中参数与播放器节点。
- `src/controller.py`：`LocomotionController(graph, assets)`，提供 `reset`/`step`，返回播放计划、同步组和姿态操作描述。
- `IMPLEMENTATION.md`：本文件。

运行方式：

```text
python src/build_assets.py --manifest raw/manifest.json --output assets/authored_assets.json
```

## 坐标转换（build_assets）

源空间：前向 `+Y`、左向 `+X`、上向 `+Z`。运行时角色空间：前向 `+X`、左向 `-Y`、上向 `+Z`。

- 位置：`[sx, sy, sz] -> [sy, -sx, sz]`。
- 旋转：xyzw 四元数、Hamilton 乘法、主动旋转；`q_runtime = rotZ(-90°) * q_source * rotZ(+90°)`。
- 根轨迹：源姿态中的 root 位移随全部姿态一次性转换，加工产物只记录转换后的 root 轨迹；运行时不再二次应用源位移。

处理只做显式基变换，不做重定向、重采样或曲线伪造。循环素材记录整段 `loop_range_seconds`；非循环素材记录时长、帧数、平均速度、根位移等指标。

## 资源表

`assets` 中共 39 条条目：

- 17 条 `ready`：15 条直接来自抽样的 clip（保持 `asset_id == clip_id`），另有 2 条派生转身 `turn_right_90_reverse`（`motion_33` 时间反转）、`turn_left_180_reverse`（`motion_36` 时间反转），用于物化缺失的右转 90°、左转 180°。
- 22 条 `deferred_missing_samples`：对应清单中 `metadata_only` 的 start/stop/pivot/turn/idle。每条含 `recipe`（通用可复用加工配方）和缺失输入记录，`data` 为 `null`。

## 动画图（config/animation_graph.json）

- `parameters.inputs`：5 个每帧输入。
- `parameters.speed_thresholds` 与 `parameters.playback`：状态机阈值和播放倍率限制，控制器在 `step` 中读取。
- `nodes`：输入节点、`locomotion_state` 状态机节点、以及 39 个 `kind: "player"` 节点；控制器从播放器节点读取 `loop` 与 `sync_group` 声明。
- `output`：加权平均混合，姿态操作顺序为 `extract_root_delta_world`、`aim_yaw_offset`、`hold_sample`。

## 控制器状态机

状态：`idle / start / cycle / stop / pivot / turn`（平地、持续 grounded、无武器）。

- 速度用世界速度的水平模长。局部速度由 `actor_yaw` 旋转得到，`+X` 前、`-Y` 左，据此判定 fwd/bwd/left/right。
- 步态：速度低于 `gait_blend_low_cm_s` 走，高于 `gait_blend_high_cm_s` 跑，中间线性混合两套 cycle；cycle 的 `play_rate = 速度 / 该素材实测平均速度`，并夹在 `[min_play_rate, max_play_rate]`。
- `start`：优先播放对应方向/步态的 start 素材；该素材缺失采样时，播放对应方向 cycle 并以权重斜坡从 0 升起，同时保留 deferred 引用。
- `stop`：优先播放 stop 素材；缺失时用对应方向 cycle 随速度下降自然减速，速度低于阈值后进入 `idle`。
- `idle`：用已就绪的 `motion_03`（walk fwd stop）末帧保持，`play_rate=0`；`motion_37`（idle）以 `materialized=false` 保留依赖。
- `turn`：停止时若瞄准与角色朝向差超过死区，选择 90°/180° 转身素材；右转 90°、左转 180° 用派生反转素材物化，同时保留 `motion_34/35` 的 deferred 引用。转角未完成时链式续转。
- `pivot`：移动中瞄准与角色朝向差较大时进入短暂 pivot；优先用语义匹配素材，缺失时用就绪的 `motion_20`（jog fwd pivot）物化并保留 deferred 引用。

姿态操作均为执行意图描述：`extract_root_delta_world` 将转换后的根增量按角色 yaw 映射到世界；`aim_yaw_offset` 描述上半身朝向偏移意图；`hold_sample` 描述保持当前采样。控制器不生成最终骨骼变换。

## 关键假设

- 场景为平地、持续 grounded、无武器；不处理跳跃、斜坡、网络状态或碰撞。
- 精简 26 骨骼抽样按 component-space 解释；不假设其等于完整 Manny 骨架。
- 缺失采样不是缺陷：通用配方已登记，控制器通过方向匹配 cycle 斜坡、就绪 stop 末帧保持、派生反转转身等方式保持可物化回退，并把不可物化依赖写入计划/诊断。
- 播放器采样时间由控制器自行推进；`sample_time_seconds` 是加工资源时间轴上的时间，`play_rate` 为无量纲倍率。

## 限制与未完成

- 22 条 `metadata_only` 素材没有可播放姿态；相关行为以可物化回退表达，尚未具备这些原始素材的最终姿态。
- 无脚步标记/notify 数据，同步组仅作计时级描述。
- 无 UE 执行器、AnimGraph 解释器或姿态渲染器；本交付是静态资源与计划，未在 UE 中运行或做姿态质量测量。
- 派生转身通过时间反转物化，是回放配方而非原始拍摄；尚未获得原始 `motion_34/35` 采样前不应视为等价素材。

## 本地自检

- `python -m py_compile src/build_assets.py src/controller.py`
- 运行 build CLI 后检查 `assets/authored_assets.json` 与 `assets/processed/`。
- 用接口示例构造 `LocomotionController` 并输入前进/后退/左右、加速/减速、转身帧，检查计划字段、确定性（同输入同 seed 同计划）与非法输入报错。
