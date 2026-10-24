# IMPLEMENTATION — Lyra 风格无武器平地移动（静态交付）

本交付**未在 UE 中验证**，未运行任何 AnimGraph，也没有做姿态评估或姿态质量测量。控制器输出的是动画执行计划，不是最终骨骼姿态。

## 文件
| 文件 | 作用 |
| --- | --- |
| `src/build_assets.py` | 资源加工入口（CLI 见下） |
| `src/anim_math.py` | 四元数 / yaw / 曲线采样与反查（距离匹配用） |
| `assets/authored_assets.json` | 生成的资源表：16 条 ready（15 条采样素材 + 1 条派生静态姿态），22 条 `deferred_missing_samples` |
| `assets/authored/*.pose.json` | 15 份加工后姿态产物（角色空间，相对 root） |
| `config/animation_graph.json` | 控制器读取的声明式图：参数、状态机、选择表、回退策略、同步组、姿态操作顺序 |
| `src/controller.py` | `LocomotionController`：每帧计划 |
| `src/locomotion_conditions.py` | 图中 `condition` 名称对应的转移谓词 |
| `.work/selfcheck.py` | 本地自查（计划级断言 + 确定性 + 非法输入），不是姿态验证 |

## 使用
```
python src/build_assets.py --manifest raw/manifest.json --output assets/authored_assets.json
python .work/selfcheck.py        # 可选，加 -v 打印逐帧摘要
```
```python
ctl = LocomotionController(graph_dict, assets_dict); ctl.reset(seed=0); plan = ctl.step(frame)
```

## 资源加工（实际执行的步骤）
对每条 `pose_samples` 素材：读取并校验（26 骨、60 Hz 等间隔、有限值、各文件骨骼层级一致）→ 基变换 → 抽出 root 轨迹 → 姿态改为相对 root → 从采样派生曲线/标记 → 写产物并记录 SHA-256。
- **坐标**：源 +Y 前、+X 左、+Z 上 → 角色 +X 前、+Y 右、+Z 上。`p_actor = M·p_src`，`M=[[0,1,0],[-1,0,0],[0,0,1]]`（绕 +Z −90°，det=+1）；`q_actor = q_conv ⊗ q_src`，`q_conv=(0,0,-√½,√½)`，Hamilton、主动旋转。正 yaw 使 +X 转向 +Y。核对：TurnLeft_90 的 root yaw 为 −90（解剖左转 = 负 actor yaw），TurnRight_180 为 +180；Walk_Left 位移朝向 −90°。
- **root motion**：root 轨迹以第 0 帧为原点存为 `data.root_motion`（tx,ty,tz,yaw）；姿态产物中 root=单位变换，位移只存在一处。运行时为 capsule 驱动，平移类 root motion 不再施加；只有原地转身消耗 `root_yaw_deg` 曲线（经 root yaw offset）。
- **派生数据**（全部可由采样复算，方法写在 recipe 中，不是原始打点/曲线）：循环的闭合误差、速度、步幅、脚着地区间及 `foot_l_plant/foot_r_plant` 同步标记（高度 + 水平速度阈值）；Start 的 `distance_traveled_cm`；Stop 的 `distance_to_stop_cm` 与静止时刻；Pivot 的 pivot 时刻（最小 root 速度）、`signed_distance_to_pivot_cm` 与进出方向（数据显示 Jog_Fwd_Pivot 进入 0°、离开 180°）；Turn 的 `root_yaw_deg`、`remaining_turn_yaw_deg`、转身结束时刻。
- **ready_pose_static**：取 walk_fwd_start 第 0 帧，并与其他 start 首帧、stop 末帧、turn 首帧交叉校验（偏差 <0.01 cm）。它**不是** Idle_Ready（motion_37 仍为 deferred），没有呼吸/待机动作。
- **skeleton**：仅记录采样中的 26 骨精简层级，`is_full_manny_skeleton=false`，无 bind/reference pose。
- **deferred**：22 条只有元数据的素材保留 clip 引用和同类型完整 recipe，`data=null`，不填任何时长、曲线或姿态。补齐采样后重跑构建即可生成。

## 控制器语义
- **时间**：控制器是唯一时钟。`sample_time_seconds` 为本帧权威采样时间；`play_rate` 是本帧推进该时间所用倍率，仅作说明，消费方不应再次推进。
- **派生量**：水平速度、局部速度角（相对 actor yaw）、带死区滞回的四向（fwd/right/bwd/left）、walk/jog 速度滞回（470/420 cm/s）、加速度与速度夹角、从观测减速估计的刹车减速度（初值 1400）。
- **加速度语义**：`input_intent`（类似 CharacterMovement 的输入加速度）：有加速度=想移动；移动中加速度≈0=停步；加速度与速度夹角 ≥120° 且足够大=pivot。若调用方传入的是运动学加速度，停步判断会不同，这是关键假设。
- **状态机**（图中定义，按 priority 求值，每帧至多一次转移）：idle / start / cycle / stop / pivot / turn_in_place。
  - start：距离匹配 `distance_traveled_cm`（内部积分 speed·dt），播放倍率限制在 [0.6,1.6]；达到循环速度 90%、时长 85% 或方向改变时进入 cycle，并按 start 中最近着地的脚对齐 cycle 相位。
  - cycle：倍率 = speed/资源速度，限制在 [0.8,1.25]，余量交给 stride_warping；gait/方向变化时在同步组内交叉淡入，按 `foot_l_plant` 标记相位对齐。
  - stop：预测停步距离 v²/(2b) 反查 `distance_to_stop_cm`；
  - pivot：减速段用 −v²/(2|a∥|)，速度反向后用累计距离，反查 `signed_distance_to_pivot_cm`；资源离开方向与加速度方向偏差 >35° 时不用该 pivot。
  - turn_in_place：idle 时 actor 旋转被 root yaw offset 吸收（脚不滑）；|aim − mesh 朝向| > 60° 时触发，>130° 选 180 资源，按请求角度缩放 root yaw 曲线（`root_yaw_scale`）。
- **姿态操作**（只是意图，未执行）：`weighted_blend` → `rotate_root_yaw` → `orientation_warping`（与四向中心的夹角，±50°）→ `stride_warping`（无 IK 执行）→ `spine_yaw_distribution`（由瞄准 yaw 分配到脊柱；清单中没有 aim offset 资源，这是程序化替代）。
- **缺失资源**：选择表总是先选语义资源；若为 deferred，就按图中的回退策略处理，并在 `diagnostics.fallbacks_this_frame`、播放器的 `substitutes_for_asset_id/substituted_asset_status` 和 `deferred_assets_substituted` 中写明 `materialized:false`。播放器只引用 ready 资源。回退：Idle→ready_pose_static；非前向 start→直接进 cycle；非前向 stop→按预测停步时间交叉淡化到静态姿态；缺失 pivot→跳过并切到新方向 cycle；TurnRight_90→TurnRight_180 缩放 0.5；TurnLeft_180→TurnRight_180（终止朝向相同）。
- **非法输入**：缺字段、非有限数、dt≤0 时抛出 `FrameValidationError`；dt>0.25 s 时截断为 0.25 并在诊断里标记 `dt_clamped`。
- 无随机数；相同输入与 seed 产生相同计划（自查脚本已比对）。

## 限制与未完成
- 22 条素材缺采样：全部 walk 的 pivot、bwd/left/right 的 start/stop、jog 的 bwd/left/right 的 start/stop/pivot、TurnLeft_180、TurnRight_90、Idle_Ready。补齐采样后，回退表中对应项会自动改用真实资源（选择器优先 ready）。
- 着地标记、闭合误差等都是由精简骨架自动推导的，未经美术确认；walk_left/right、jog_right 的循环首尾存在 2–4 cm / 2–5° 的接缝（数值已记录），未做修补。
- 没有镜像资源：精简采样缺少骨骼局部轴/参考姿态，无法可靠镜像左右骨骼。
- 起步时速度≈0，只能按当前 gait（通常为 walk）选择起步动画，jog 起步后会在同步组内切到 jog cycle。
- 没有 IK、脚锁定、姿态求值器或 UE 执行；warping 与 blend 只是参数化描述。参数（阈值、混合时间）为经验值，未在实际角色上调过。
