# Lyra 动画开发：40项细节扣分清单

裁判专用。检查资源、配置和代码之间的对应关系；不用 UE，不以术语出现次数评分。

完整完成得该项满分；实质部分完成得部分分；缺失或错误得0分。未审查不算0分，最终总分保持空值。

| 类别 | 项数 | 分值 |
|---|---:|---:|
| 资源制作 | 8 | 20 |
| 状态与方向 | 7 | 18 |
| 同步组与相位 | 6 | 16 |
| 距离匹配 | 6 | 16 |
| 方向、步幅与根旋转 | 5 | 12 |
| 分层与生命周期 | 5 | 10 |
| 稳定性与复现 | 3 | 8 |

## 资源制作

### RES01 · 原始输入、派生资源与来源可追溯（2分）

区分只读原始片段、模型制作规则和派生元数据；每个派生资源能追溯输入ID、制作参数及版本。不得把猜测的Lyra原配置标成本地实测。

应查证据：资源清单/制作定义的路径与键；至少一例输入到派生资源的映射。

### RES02 · 骨架、单位和坐标系一致（3分）

遵守题包cm/秒/度、component-space、xyzw及骨骼子集约定；明确源+Y前向到actor+X前向的基变换、旋转符号、左右方向及世界/局部转换。不能把component-space当local-space或虚构完整Manny骨骼。

应查证据：骨架和坐标约定；转换逻辑及使用处。

### RES03 · 走跑与方向资源覆盖（3分）

资源映射覆盖walk/jog、四方向、start/stop/pivot/TIP；共享、镜像或补偿允许但须说明语义和左右marker映射。有pose_samples者实际加工，metadata_only者通用recipe+deferred_missing_samples即可；不要求不存在样本的精确产物。

应查证据：资源覆盖矩阵或等价配置；缺片段/镜像/补偿的选择规则。

### RES04 · 片段时域、循环与边界（2分）

明确duration、采样率/时间戳、loop属性及首尾采样规则；循环与非循环资源分开，末帧处理不凭空多走一帧，不将停止片段无条件循环。 duration=null表示未知，不能当0长片段；缺样本时允许延后时间域派生。

应查证据：片段时域元数据；采样、wrap/clamp的实现或明确规则。

### RES05 · 根轨迹数据与角色位移职责（3分）

保留可供距离/方向/步幅计算的根轨迹或等价采样；区分源动画根运动数据、提取出的root delta与角色移动驱动，不能把数据存在等同于胶囊必由root motion移动，也不能重复施加同一位移。

应查证据：根轨迹及提取定义；角色移动与动画输出接口。

### RES06 · 同步相位标记的制作（3分）

有样本者依据采样和明确规则生成左右步态相位标记，可选择脚接触等自洽约定；同名marker跨资源语义一致、时间有效、顺序合理。marker与可播放Notify分开；不要求复刻原Lyra L/R绝对时间，无样本允许可复用recipe+延期。

应查证据：marker制作实现、所采用的相位约定及有样本输出实例；左右语义、排序、合法区间校验与无样本延期记录。

### RES07 · 曲线制作及可索引表示（2分）

为距离匹配提供从源轨迹生成曲线的规则，说明XY等轴选择、采样与停止参考点；输出能按时间读取并支持距离反查。可用数组等独立格式代替UE Uniform Indexable，但只写压缩器名称不得分。

应查证据：曲线制作规则；实际派生曲线及反查接口。

### RES08 · 资源制作流程闭合（2分）

定义从输入到派生资源的完整步骤、确定性排序和引用校验；同输入同参数应得到同语义结果，缺骨骼/无效时长/缺关键曲线应报告可定位失败，不能静默假造有效资源。

应查证据：制作入口或可复现制作步骤；验证规则和错误上下文。


## 状态与方向

### LOC01 · 移动快照与派生量（3分）

从同一frame一致读取velocity/acceleration/actor_yaw/aim_yaw/dt，计算局部速度、方向和移动状态；速度与加速度用途不同，不能把加速度为零直接当作停止，也不能假定收到未提供的input或世界位置。

应查证据：输入快照结构；派生量计算与调用位置。

### LOC02 · Walk/Jog选择与阈值稳定（2分）

walk/jog有显式选择条件及混合策略，阈值附近有滞回、平滑或等价防抖措施；不会仅更换状态名却始终使用同一未说明的播放行为。具体阈值自定，无须照抄Lyra。

应查证据：gait配置及选择逻辑；阈值边界处理证据。

### LOC03 · 四方向与斜向选择（3分）

前后左右覆盖完整，斜向采用可解释的基片段选择和补偿/混合；明确速度过零、后退、±180度环绕及方向边界防抖。保持strafe的朝向/移动方向区分。

应查证据：方向选择逻辑；方向到资源/warp的映射。

### LOC04 · Idle到Start到Cycle（3分）

状态图包含可达的idle/start/cycle链；进入start时选定合适资源并初始化，转入cycle有明确完成/中断条件，不能每帧重置start或仅凭非零速度立即跳过它。

应查证据：状态图及转移条件；start进入和更新逻辑。

### LOC05 · 减速、Stop与Idle（3分）

结合速度、加速度与明确内部减速/制动推导选择stop，并说明何时进入idle；frame没有松键字段，不能直接读取虚构input。避免仍移动时静止、stop永久卡住或每帧重启；对未知片段时间采用明确延期/回退。

应查证据：停止触发/完成逻辑；stop资源和距离驱动关联。

### LOC06 · Pivot及重新起步（2分）

区分常规停止、反向pivot与stop期间再起步；定义触发依据、打断和资源重新选择，允许简化pivot但必须保留方向反转语义并声明限度。

应查证据：pivot/restart转移及优先级；方向/加速度判断与资源选择。

### LOC07 · 过渡竞争与连续性（2分）

同帧多个条件满足时有确定的转移优先级；说明混合时长/权重及中断保留状态，避免多个互斥状态同时主导或在阈值处反复切换。不得把非零blend权重误当作重新进入事件。

应查证据：转移优先级/互斥规则；混合与中断处理。


## 同步组与相位

### SYN01 · 组作用域与角色配置（3分）

明确哪些兼容片段共享同步组及为什么；组名自定，但生产配置与消费路径一致，角色与作用域可追踪。非相关动作不因同名意外同步；不要把所有片段机械塞入一个组。

应查证据：同步组成员及角色配置；组查找和使用位置。

### SYN02 · Marker相位不是Notify（3分）

同步计算或计划按前后marker及区间内相对进度定义，覆盖不同长度/不同接触时刻的片段；Notify归属/调度计划单独表达，不能用触发脚步音代替同步，也不能只以相同normalized time宣称marker sync。无需实际执行音效或通用同步器。

应查证据：marker区间/相位映射的具体计算或计划定义；独立的Notify/event数据及归属/调度计划。

### SYN03 · 公共标记与退化策略（3分）

定义组内公共marker集合及缺失时处理；不能对每个follower任意使用互不一致的marker。无匹配标记时采用长度同步或显式拒绝并报告，声明的策略必须在逻辑中实现。

应查证据：公共marker求交或等价规则；无公共marker/缺单侧marker分支。

### SYN04 · Leader选择与事件归属（2分）

根据配置角色与有效权重确定leader，并说明同权重/多强制leader的确定性处理；Notify计划将事件归属限定到合适播放器，防止follower重复事件。展示具体选择计算和事件归属/抑制计划即可，不要求运行通用事件执行器；只列角色枚举不足以通过。

应查证据：leader决策实现；Notify归属/抑制的具体计划与播放器关联。

### SYN05 · 非循环起停与距离匹配的同步策略（3分）

start/stop的角色和是否参与同步须与距离驱动一致；避免follower强制时间破坏距离匹配，也不声称距离反查会自动保持cycle脚相。Always Leader是一种官方建议，并非所有情形的必填答案；替代策略须解释过渡连续性。

应查证据：start/stop节点同步配置；同步与距离时间决策优先级；起停衔接的明确策略。

### SYN06 · 接管、跨尾与事件唯一性（2分）

leader变化、循环跨尾、单帧越过多个marker时，计算或计划规则给出确定的相位与事件区间，说明如何避免漏/重复及无原因跳变；不要求通用运行引擎。只处理[0,duration)普通帧或未定义计划语义不足以满分。

应查证据：接管和跨尾分支；事件区间端点和去重约定。


## 距离匹配

### DST01 · 距离曲线含义与符号（2分）

每类曲线明确表示累计距离或到目标的剩余距离，并标明单位、参考零点/符号；start、stop、pivot不盲目复用未经解释的正值曲线。曲线数据与运行时输入语义必须一致。

应查证据：曲线契约及样例；消费者参数和符号转换。

### DST02 · 按位移推进与按目标定位分开（3分）

起步等推进使用本次动画更新区间的DistanceTraveled；停止/转向定位使用DistanceToTarget。不得把累计路程反复加到当前时间，或把speed直接当distance；dt和更新频率变化有明确语义。

应查证据：两类时间驱动路径；位移/dt取值依据。

### DST03 · 停止/转向目标来源（3分）

停止/pivot距离由已给速度、加速度、dt与声明的内部制动参数/模型推导；固定但明确且可配置的制动参数允许，不要求题包未给的摩擦、碰撞或actor位置。不以动画剩余长度冒充真实停止预测，标明模型假设和异常参数策略。

应查证据：目标/距离来源及预测公式或接口；运动假设与失效策略。

### DST04 · 曲线反查的确定性和边界（3分）

反查包含插值以及越界、平台段、重复值、无效/非单调曲线的明确处理；pivot可能出现不同阶段，须指定分支/搜索区间而非全曲线任取最近点。结果不产生NaN、倒退或未声明的跳帧。

应查证据：曲线采样/反查实现；边界与多解决策规则。

### DST05 · 播放速率限制与步幅补偿（3分）

显式限制距离驱动产生的有效playrate，并将未匹配部分交给有界stride补偿或声明允许的滑步；区分匀速cycle的speed matching假设。不能同时对相同速度差完整乘两次造成过补偿。具体限制值自定。

应查证据：playrate与stride组合计算；clamp与零速分支。

### DST06 · Evaluator推进、跳转与副作用（2分）

明确显式时间变化是推进还是瞬移，以及Notify和root delta如何处理；若模拟UE语义须覆盖同步组可能强制advancing的例外。允许独立简化语义，但须公开声明并保持实现/配置一致，不能错误声称与UE完全相同。

应查证据：Evaluator模式配置；时间变化到事件/root delta的处理。


## 方向、步幅与根旋转

### WRP01 · Orientation Warping的朝向分工（3分）

用所选动画运动方向与实际局部移动方向的差得到有界角度，区分actor/mesh/root/aim朝向；下肢补偿与上身面向职责明确，处理角度环绕，不能把角色整体转向移动方向冒充strafe补偿。

应查证据：方向补偿公式及空间约定；上下身/根骨输出契约。

### WRP02 · Stride Warping的比例与限制（3分）

步幅比依据有效动画位移速度和实际速度，考虑已应用playrate；有零根速/低速保护、范围和过渡平滑，结果进入具有有效引用的pose_operations计划。无需执行IK/FK或最终骨骼姿态。

应查证据：stride参数计算、限制及低速分支；输出pose_operations对参数及播放器的有效引用。

### WRP03 · 骨骼约束与姿态补偿契约（2分）

姿态计划明确方向/步幅/骨盆或脊柱修正的职责和顺序，骨骼引用只使用已知子集或明确待解析绑定；缺失IK/虚拟骨骼应承认范围，不要求补齐完整骨架。区分计划与最终姿态、warp与地面Foot IK，不要求运行真实求解器。

应查证据：姿态操作顺序及引用/骨骼范围；输入不具备绑定时的声明与退化/延后计划。

### WRP04 · RootYawOffset三类状态策略（3分）

idle累积抵消、start保持、cycle淡出三种语义可追踪并由状态请求；处理角度归一和模式切换，避免每帧清零/无限累积或双重旋转。名称可自定，不要求与Lyra函数逐字相同。

应查证据：yaw状态策略与计算；状态到模式的配置/调用。

### WRP05 · Turn In Place与转向曲线（1分）

TIP有角度/等待条件及对应资源/曲线选择；转身过程中按源转向信息消耗offset，或明示受限替代方案，不凭计时直接抹掉全部角差。

应查证据：TIP触发/资源配置；转向曲线或替代消耗规则。


## 分层与生命周期

### ARC01 · 状态逻辑、资源集与修正职责分开（2分）

高层状态/过渡、Unarmed资源集、方向/步幅等修正职责清晰分开，公共移动数据一致复用；不需要武器输入、实际换武器或多套武器资产。代码与图能追踪到相应职责即可。

应查证据：状态/资源/修正的接口与配置；共享派生数据的读取路径。

### ARC02 · 移动与上身朝向的分层契约（2分）

用明确mask、层或姿态操作契约协调下肢移动与上身瞄准/方向修正，说明根骨归属及组合顺序；不要求射击/换弹动作。计划参数和引用有效即可，不要求生成最终分骨骼pose。

应查证据：移动与瞄准/朝向修正的组合计划；根骨/上下身影响范围及顺序。

### ARC03 · 节点生命周期（2分）

区分首次初始化、每次变相关和每次更新；再次进入start/stop会按规则重新选择资源/初始化时间，inactive节点不无意推进。On Become Relevant不等价于每帧权重非零。

应查证据：生命周期实现或可执行图定义；状态重入与inactive分支。

### ARC04 · 快照与共享派生数据边界（2分）

每次step基于给定frame作一致计算，状态与只读配置/资源分开，层间共享派生数据不产生互相矛盾副本；无需实际多线程或UE Property Access。不能宣称静态代码证明引擎线程性能。

应查证据：输入快照和可变状态边界；外部读取点/共享数据路径。

### ARC05 · 资源与图配置进入实际决策（2分）

实现确实读取所交付的资源制作结果、组配置、状态规则和曲线；能追踪从配置键到选择/计算/输出的路径。硬编码另一份隐藏答案、未使用配置或仅列节点名不能通过。

应查证据：配置加载/引用路径；至少一条完整配置到输出调用链。


## 稳定性与复现

### ROB01 · 输入异常与稳定退化（3分）

对dt<=0、近零速度、缺资源/曲线、无效数值、极大位移/角度有明确有限结果、失败或退化策略；不能靠无限重试或传播NaN。此项评整体入口保障，不重复因某一曲线缺陷再次扣已归属DST04的分。

应查证据：输入校验与错误/退化路径；正常与异常状态隔离。

### ROB02 · 独立复现与提交完整性（3分）

按INTERFACE.md保留build_assets CLI、LocomotionController/reset/step和约定输出；提供实质Python、图配置、制作数据及简要复现说明，reset清理状态，相同输入/配置/seed确定。metadata_only延期合法；不要求本次执行候选代码或UE。

应查证据：文件清单与入口说明；版本/依赖/确定性约定。

### ROB03 · 证据与限制诚实可审查（2分）

说明关键决策、假设与限制，关键实现能定位追踪；区分资源制作完成/缺样本延期和计划/最终姿态。不强制提供运行截图或已执行trace，自查案例可以是有代码依据的静态推导，不能伪称UE验证。

应查证据：证据索引和自查案例；已实现/简化/未验证范围。

## 判分边界

22条只有元数据的素材允许通用配方与 deferred_missing_samples，不因输入缺失扣模型分。语义等价实现可以通过；不要求照抄 Lyra 名称或绝对打点。

分项完成审查后再检查交付门槛；仅文字最高30分，整体缺资源制作或有效动画图最高60分。门槛只取最低上限，不叠加扣分。精确触发条件以 rubric.json 为准。

同一缺陷在直接所属项扣分；其他项须有独立失败证据。静态得分不等于运行时正确、低滑步或美术质量。

## 一手资料

- [Animation in Lyra](https://dev.epicgames.com/documentation/en-us/unreal-engine/animation-in-lyra-sample-game-in-unreal-engine)
- [Adapting Lyra animation to your UE5 game](https://www.unrealengine.com/tech-blog/adapting-lyra-animation-to-your-ue5-game)
- [Animation Sync Groups](https://dev.epicgames.com/documentation/en-us/unreal-engine/animation-sync-groups-in-unreal-engine)
- [Distance Matching](https://dev.epicgames.com/documentation/en-us/unreal-engine/distance-matching-in-unreal-engine)
- [UAnimDistanceMatchingLibrary::AdvanceTimeByDistanceMatching](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Plugins/AnimationLocomotionLibraryRuntim-/UAnimDistanceMatchingLibrary/AdvanceTimeByDis-)
- [UAnimDistanceMatchingLibrary::DistanceMatchToTarget](https://dev.epicgames.com/documentation/unreal-engine/API/Plugins/AnimationLocomotionLibraryRuntim-/UAnimDistanceMatchingLibrary/DistanceMatchToT-)
- [UAnimDistanceMatchingLibrary::SetPlayrateToMatchSpeed](https://dev.epicgames.com/documentation/unreal-engine/API/Plugins/AnimationLocomotionLibraryRuntim-/UAnimDistanceMatchingLibrary/SetPlayrateToMat-)
- [Pose Warping](https://dev.epicgames.com/documentation/en-us/unreal-engine/pose-warping-in-unreal-engine)
- [Animation Blueprint Node Functions](https://dev.epicgames.com/documentation/en-us/unreal-engine/animation-blueprint-node-functions-in-unreal-engine)
- [FAnimNode_SequenceEvaluator::GetTeleportToExplicitTime (5.5)](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/AnimGraphRuntime/AnimNodes/FAnimNode_SequenceEvaluator/GetTeleportToExp-?application_version=5.5)
