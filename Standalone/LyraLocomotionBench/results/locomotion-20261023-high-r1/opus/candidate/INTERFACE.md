# 静态交付接口 v1

状态：`template`。这些文件规定候选交付的边界；当前没有完成的动画执行器或姿态验收器。模板中的 TODO 需要候选自行实现。本次审查资源加工、配置和代码，播放计划不会被解释为已经执行出的最终 pose。

## 目录与构建入口

从候选目录运行：

```text
python src/build_assets.py --manifest raw/manifest.json --output assets/authored_assets.json
```

两个参数均为必填路径。相对路径以当前工作目录为基准。清单中 `pose_file` 相对于清单所在目录解析，例如 `poses/motion_01.json` 对应 `raw/poses/motion_01.json`。生成资源表中新增的产物路径相对于生成资源表所在目录解析。不得通过修改 `raw/` 把加工结果覆盖回输入。

Python 构建入口：

```python
def build_assets(manifest: dict, manifest_dir: Path) -> dict:
    ...
```

返回可序列化的资源表。可扩展内部函数和辅助产物，但保留 CLI。模板 CLI 只提供读写外壳，不实现资源加工；未完成时应失败，不应输出看似完成的空结果。

## 原始清单

`raw/manifest.json` 的主要字段如下：

| 字段 | 约定 |
| --- | --- |
| `schema_version` | `1` |
| `coordinate_system` | 单位、轴向及源到角色的转换说明 |
| `pose_format` | 抽样空间和旋转存储形式 |
| `clips` | 原始素材条目数组 |

每个 `clips` 条目包含：

| 字段 | 约定 |
| --- | --- |
| `clip_id` | 资源身份；引用时使用清单给定值 |
| `semantic` | `gait`、`action`、`direction`、`anatomical_turn_degrees` 等目录元数据；转身角度为人体左转正、右转负，不是输入 actor yaw 的符号约定 |
| `source_name` | 原始素材名称 |
| `duration_seconds` | 已知时为实际秒数，否则为 `null` |
| `pose_file` | 相对清单目录的抽样文件路径；无抽样时为 `null` |
| `sample_rate_hz` | 已知抽样率；未知时为 `null` |
| `pose_bone_count` | 已知骨骼数量；未知时为 `null` |
| `availability` | `pose_samples` 或 `metadata_only` |

抽样文件包含 `bones` 和 `frames`。`bones` 中的 `parent` 是父骨骼索引，根为 `-1`；`frames` 中包含 `time`、`positions`、`rotations_xyzw`。姿态是 26 骨骼的 component-space 抽样，root 轨迹已包含在抽样中。不得假设清单中的所有素材都具有这些数据，也不得把精简骨架当作完整 Manny 骨架。

完整骨架及额外骨骼信息预留在生成资源表的 `skeleton` 字段；尚无可靠信息时保留 `null`，或记录有来源的精简骨架信息及其范围。不要补写不存在的骨骼或绑定关系。

## 时间、单位与坐标

- 时间使用秒，角度输入使用度，距离使用厘米；速度为厘米/秒，加速度为厘米/秒平方。
- `dt_seconds` 是本次输入的时间步长；每次 `step` 调用代表一个新帧。控制器应自行维护所需状态，调用 `reset` 后重新开始。
- 播放器的 `sample_time_seconds` 是对应加工资源时间轴上的采样时间，`play_rate` 是无量纲倍率。裁判不提供隐含的播放器时钟；候选需要说明两者如何配合。循环范围、裁剪后的时间原点及时间重映射由加工资源显式记录。
- 角色局部轴约定为 `+X` 前、`+Y` 右、`+Z` 上；世界同样以 `+Z` 为上。yaw 为 `0` 时角色前向与世界 `+X` 对齐；正 yaw 把 `+X` 方向转向 `+Y`。输入 yaw 可以跨过整圈，控制器自行处理等价角度。
- 现有源抽样的前向为 `+Y`，左向为 `+X`，上向为 `+Z`。加工资源必须记录源到角色空间的显式转换，以及 root 轨迹如何处理。不能将源抽样坐标直接解释成角色局部坐标。
- 四元数按 `xyzw` 存储，采用 Hamilton 乘法与主动旋转；`q_parent * q_local` 表示父变换与局部变换的组合。只写“左手系”或“右手系”不足以说明转换；应以轴向、旋转符号和上述乘法约定为准。
- 抽样文件是已有源证据。转换、裁剪、重采样等操作必须由候选的制作逻辑明确表达，并保留可追溯的源引用。

## 加工资源表

`assets/authored_assets.json` 保留 `schema_version`、`status`、`source_manifest`、`coordinate_conversion`、`skeleton` 和 `assets` 顶层字段。其余结构可扩展。

`assets` 中的条目至少使用唯一 `asset_id`，并给出 `source_clip_ids`、`status`、`recipe` 和 `data`。`recipe` 描述实际加工操作及参数；`data` 保存生成数据或生成产物引用。字段的内部结构由候选自行设计，并与代码及动画图保持一致。

已完成加工的条目使用 `status: "ready"`，前提是其声明的产物确实生成。缺少必要采样的条目使用 `status: "deferred_missing_samples"`，记录缺失输入与将来使用的加工配方，不填入伪造结果。未知值使用 `null`，不把 `0` 当作未知值。新增、裁剪或组合资源必须声明来源，不能伪称为额外原始素材。

## 动画图

`config/animation_graph.json` 保留 `schema_version`、`status`、`parameters`、`nodes`、`connections`、`sync_groups` 和 `output` 顶层字段。节点需有唯一 `id`，连接与资源引用必须可解析。节点种类、参数、状态表达方式和组配置由候选自行设计；可增加字段。

这是候选实现所消费或生成的声明式配置，不是 UE AnimGraph 序列化格式。控制器代码应与图配置有实际关联，不能将图文件作为与代码无关的说明附件。模板不提供节点执行语义；候选需以代码和必要说明使自己的语义明确。

## 控制器入口

```python
controller = LocomotionController(graph, assets)
controller.reset(seed=0)
plan = controller.step(frame)
```

`graph`、`assets` 分别是读取两个 JSON 文件后得到的字典。`reset` 清除会影响后续结果的控制器状态。相同输入、配置和 seed 应产生相同计划；无需使用随机数。

每帧 `frame` 含以下字段，不包含参考答案或预选动画：

| 字段 | 类型及含义 |
| --- | --- |
| `dt_seconds` | 正的有限浮点数，秒 |
| `velocity_world_cm_s` | 三元素数组，世界空间速度 |
| `acceleration_world_cm_s2` | 三元素数组，世界空间加速度 |
| `actor_yaw_degrees` | 角色世界 yaw |
| `aim_yaw_degrees` | 瞄准方向的世界 yaw |

场景为无武器、平地、持续 grounded；没有跳跃、斜坡或网络状态输入。每帧输入不含 actor 世界位置，也不承诺提供碰撞或运动预测服务。候选可以声明自己的内部推导和状态，但不能假称收到未提供的输入。

上表是正常输入域。接口也应对域外输入（例如非正 dt、非有限数、缺字段）作明确校验并报告失败，或采用有记录的有限退化策略；不要求将非法输入解释成正常动作。

`step` 返回 JSON 可序列化字典，保留如下字段：

| 字段 | 内容 |
| --- | --- |
| `schema_version` | `1` |
| `players` | 播放器计划数组；每项含唯一 `player_id`、`asset_id`、`sample_time_seconds`、`weight`、`play_rate`、`loop`；可增加描述播放行为的字段 |
| `sync_groups` | 组设置数组；每项含唯一 `group_id`、`member_player_ids`、`settings`；具体设置语义由候选定义并由代码体现 |
| `pose_operations` | 有序操作描述数组；每项含唯一 `operation_id`、`operation_type`、`inputs`、`parameters`，引用对象及操作语义由候选定义 |
| `diagnostics` | 可选诊断信息；不能替代实际计划与实现 |

每个播放器必须引用生成资源表中的资源。依赖 `deferred_missing_samples` 资源时，应在计划或诊断中准确保留其不可物化状态，不能声称输出了该资源的实际 pose。姿态操作是执行意图描述，不是执行后的骨骼变换。没有操作时数组可以为空；空数组不表示任何隐含的算法已经运行。

## 当前边界

不要求网络、窗口、图形界面、renderer 或 UE 调用。不提供隐藏的姿态求值、骨骼 IK、同步修正或距离匹配服务。需要的行为应体现在候选自己的数据、配置和控制代码里。候选可以本地运行 Python 检查构建和计划输出，但不得把这类检查描述为 UE 或最终姿态验证。
