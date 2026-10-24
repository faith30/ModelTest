# opus：40项静态审查

得分 **84.5 / 100**；扣分 15.5。40项与3个门槛均已审查。

证据仅来自冻结代码、图和资源数据。没有执行候选或UE；输出计划不代表最终动画姿态。

候选目录SHA256：`9a649cd8c60d007f03149069e3475c262082825c8c8317dab1bd59ad558c8b86`。

## RES01 原始输入、派生资源与来源可追溯 — 2/2

原始输入与派生姿态分开；产物记录 source_clip_id/source_pose_file/源 SHA-256，资源表记录 input ID、具体 recipe、builder_version 与产物 SHA。派生曲线及静态替代姿态均明确说明来源，没有冒充原始 Lyra 曲线或 Idle。

证据：[src/build_assets.py:245](candidate/src/build_assets.py#L245) · [src/build_assets.py:339](candidate/src/build_assets.py#L339) · [src/build_assets.py:112](candidate/src/build_assets.py#L112) · [IMPLEMENTATION.md:30](candidate/IMPLEMENTATION.md#L30)

## RES02 骨架、单位和坐标系一致 — 2/3

已给出 cm/component/xyzw、26 骨骼边界、位置基变换与正确的世界转局部速度计算。但 _convert 先把 q_root 左乘 B，_root_relative 随后用该完整 q_root 的逆旋转所有 Bp：对于初始单位源 root，B^-1(Bp)=p，固定 -90° 的 actor 基变换被抵消。产物仍宣称 actor component space，记录 root_origin_yaw_deg=-90，却没有消费者恢复这个常量；pose_operations 只输出动态 root_yaw_offset/速度偏角。故姿态坐标与 actor 前向契约未闭合。这一根因只在本项扣分，不在 RES05 或 warping 重扣。

证据：[src/build_assets.py:142](candidate/src/build_assets.py#L142) · [src/build_assets.py:173](candidate/src/build_assets.py#L173) · [src/build_assets.py:245](candidate/src/build_assets.py#L245) · [assets/authored_assets.json:853](candidate/assets/authored_assets.json#L853) · [src/controller.py:599](candidate/src/controller.py#L599) · [src/controller.py:613](candidate/src/controller.py#L613)

## RES03 走跑与方向资源覆盖 — 3/3

资源表/选择器覆盖 walk/jog 四方向的 cycle/start/stop/pivot 和转身；15 条有样本资源实际处理，22 条 metadata_only 复用同类通用 recipe 并保留延期。缺失 Idle 使用有明确来源的静态首帧；其他缺片采用明确选择表与替代策略，不要求不存在的姿态。

证据：[config/animation_graph.json:86](candidate/config/animation_graph.json#L86) · [src/build_assets.py:424](candidate/src/build_assets.py#L424) · [src/build_assets.py:351](candidate/src/build_assets.py#L351) · [IMPLEMENTATION.md:31](candidate/IMPLEMENTATION.md#L31) · [IMPLEMENTATION.md:46](candidate/IMPLEMENTATION.md#L46)

## RES04 片段时域、循环与边界 — 2/2

保留源时间戳与采样率，时长来自最后/最初样本差；循环显式记录 period 与首尾闭合/是否重复，播放器按 duration 取模，非循环 clamp，不额外增加末帧。metadata_only data=null，选择时改用 ready 资源，不以零时长伪装已有素材。循环接触 seam 的 marker 问题只计 RES06。

证据：[src/build_assets.py:264](candidate/src/build_assets.py#L264) · [src/build_assets.py:284](candidate/src/build_assets.py#L284) · [src/controller.py:256](candidate/src/controller.py#L256) · [src/build_assets.py:357](candidate/src/build_assets.py#L357) · [src/controller.py:121](candidate/src/controller.py#L121)

## RES05 根轨迹数据与角色位移职责 — 3/3

从 root 提取独立 tx/ty/tz/yaw 轨迹并将姿态做 root-relative；制作数据注明 curve 与 capsule 位移二选一。输出播放器明确 ignored_capsule_driven，转身仅消费 root yaw 的帧间差，平移不会再次推动角色。固定基旋转丢失另计 RES02，不重复扣分。

证据：[src/build_assets.py:169](candidate/src/build_assets.py#L169) · [src/build_assets.py:269](candidate/src/build_assets.py#L269) · [src/controller.py:562](candidate/src/controller.py#L562) · [src/controller.py:535](candidate/src/controller.py#L535) · [IMPLEMENTATION.md:29](candidate/IMPLEMENTATION.md#L29)

## RES06 同步相位标记的制作 — 2/3

有实质性的脚/球骨高度+水平速度接触检测，统一 foot_l_plant/foot_r_plant 名称，按时间排序，并声明是派生同步 marker 而非原始 Notify。但接触区间按线性数组切分，循环首尾不合并：walk_fwd_cycle 的右脚接触覆盖 [2.08333,2.2] 与 [0,0.18333]，却同时生成 2.08333 和 0 的右脚 onset；跨 seam 同一次接触被当成两次开始，违反自己的 onset 定义，造成跨循环多一个相位标记。只在制作项扣这一 seam 根因。

证据：[src/build_assets.py:214](candidate/src/build_assets.py#L214) · [src/build_assets.py:295](candidate/src/build_assets.py#L295) · [assets/authored_assets.json:872](candidate/assets/authored_assets.json#L872) · [assets/authored_assets.json:1175](candidate/assets/authored_assets.json#L1175) · [assets/authored_assets.json:1200](candidate/assets/authored_assets.json#L1200)

## RES07 曲线制作及可索引表示 — 2/2

从 XY 根轨迹累计路程，实际生成 start 累计距离、stop 剩余路程、pivot 相对最小速度帧的有符号路程。输出 time_s 与数值数组，独立函数支持按时间线性采样和距离反查，控制器实际引用曲线；不依赖 UE 压缩格式名。无效/非单调输入验证不足只计 DST04。

证据：[src/build_assets.py:182](candidate/src/build_assets.py#L182) · [src/build_assets.py:302](candidate/src/build_assets.py#L302) · [src/anim_math.py:90](candidate/src/anim_math.py#L90) · [src/anim_math.py:110](candidate/src/anim_math.py#L110) · [src/controller.py:515](candidate/src/controller.py#L515)

## RES08 资源制作流程闭合 — 2/2

构建入口可重用并按固定公式/精度写出产物与 SHA；检查 schema、重复 ID、采样数量、骨骼数量/层级一致、均匀时间步和有限姿态数组，错误包含素材 ID。产物引用以输出文件目录为根并由 CLI 传递 output.parent；静态核对最终 ready 引用均存在。曲线反查器专门的无效输入策略缺口只计 DST04。

证据：[src/build_assets.py:118](candidate/src/build_assets.py#L118) · [src/build_assets.py:407](candidate/src/build_assets.py#L407) · [src/build_assets.py:257](candidate/src/build_assets.py#L257) · [src/build_assets.py:479](candidate/src/build_assets.py#L479)

## LOC01 移动快照与派生量 — 1.5/3

同一frame派生水平速度、局部速度/加速度方向、速度-加速度夹角及yaw增量，坐标读取路径明确；但强制把题面加速度改解释为input_intent，wants_to_stop仅判断not has_accel。故非零匀速且零加速度会从Cycle进入Stop；这是输入语义根因，主要在此扣1.5分，LOC05/LOC06不为同一输入假设重复扣分。

证据：[src/controller.py:180](candidate/src/controller.py#L180) · [src/locomotion_conditions.py:7](candidate/src/locomotion_conditions.py#L7) · [config/animation_graph.json:64](candidate/config/animation_graph.json#L64)

## LOC02 Walk/Jog选择与阈值稳定 — 2/2

walk/jog有独立上下行速度阈值，Cycle的gait变化会选新资源并执行0.2秒混合；输出权重由渐变权重归一，满足明确选择与阈值稳定。

证据：[src/controller.py:216](candidate/src/controller.py#L216) · [src/controller.py:485](candidate/src/controller.py#L485) · [src/controller.py:544](candidate/src/controller.py#L544)

## LOC03 四方向与斜向选择 — 3/3

世界速度按actor yaw转局部；四方向选择含当前扇区扩张滞回、低速时保留当前方向，atan2与wrap支持后退及跨角度边界，Cycle选择表覆盖四向。斜向有有界warp计划；其独立mesh offset差异在WRP01评，不在此重复扣分。

证据：[src/controller.py:161](candidate/src/controller.py#L161) · [src/controller.py:436](candidate/src/controller.py#L436) · [src/controller.py:598](candidate/src/controller.py#L598)

## LOC04 Idle到Start到Cycle — 3/3

图定义Idle/Start/Cycle与完成条件；进入Start清零start_distance并新建时间为0的非循环播放器，结束由时长、目标速度或方向变更决定。缺样本的方向Start明确记录延期并回退Cycle，不作为素材缺失扣分。输入意图误解已归LOC01。

证据：[src/controller.py:350](candidate/src/controller.py#L350) · [src/locomotion_conditions.py:33](candidate/src/locomotion_conditions.py#L33) · [config/animation_graph.json:63](candidate/config/animation_graph.json#L63)

## LOC05 减速、Stop与Idle — 3/3

在LOC01已单独归因的输入语义缺陷之外，Stop流程有声明的制动距离反查、低速后的正常时间推进，以及速度足够低且片段达到静止位置才退出Idle的条件；无样本Stop用预测停止时间淡化并标记回退。不重复处罚相同的零加速度Stop触发根因。

证据：[src/controller.py:373](candidate/src/controller.py#L373) · [src/controller.py:519](candidate/src/controller.py#L519) · [src/locomotion_conditions.py:60](candidate/src/locomotion_conditions.py#L60)

## LOC06 Pivot及重新起步 — 2/2

分别定义Stop重启、反向Pivot触发、进入/退出资源与方向匹配；Pivot跟踪进入速度方向、反向后的累计距离，有缺采样/方向不匹配的显式回退。将加速度视为意图导致的普通制动歧义已在LOC01扣，不再次扣此项。

证据：[src/locomotion_conditions.py:24](candidate/src/locomotion_conditions.py#L24) · [src/controller.py:386](candidate/src/controller.py#L386) · [config/animation_graph.json:68](candidate/config/animation_graph.json#L68)

## LOC07 过渡竞争与连续性 — 2/2

转移按priority排序且每帧命中一次后break；进入新播放器时保留旧播放器并设置淡出目标，权重逐帧推进、清理及归一，重入发生于状态调用而非非零权重。

证据：[src/controller.py:41](candidate/src/controller.py#L41) · [src/controller.py:238](candidate/src/controller.py#L238) · [src/controller.py:478](candidate/src/controller.py#L478)

## SYN01 组作用域与角色配置 — 3/3

只将兼容的循环移动播放器置于locomotion_cycle，起停、pivot、turn和idle明确不参加；控制器从图建立组表并按node.sync_group查找真实玩家。角色由组内leader决策给出。leader选取政策本身的错误在SYN04承担，本项认可成员作用域及消费连接。

证据：[config/animation_graph.json:71](candidate/config/animation_graph.json#L71) · [config/animation_graph.json:152](candidate/config/animation_graph.json#L152) · [src/controller.py:313](candidate/src/controller.py#L313)

## SYN02 Marker相位不是Notify — 2/3

实现了带跨尾扩展的前后同名左脚marker区间，按区间内相对进度映射至另一片段，不是简单使用相同normalized time，能适应不同周期与左脚接触偏移。但只保留phase_reference_marker的同名点，配置中的右脚marker不进入分段；当左右接触相对时刻不同，不能按左右相邻marker区间保持两侧接触。这里仅扣该相位表达缺口；Notify归属缺失由SYN04承担，公共集合缺口由SYN03承担。

证据：[src/controller.py:281](candidate/src/controller.py#L281) · [src/controller.py:304](candidate/src/controller.py#L304) · [config/animation_graph.json:153](candidate/config/animation_graph.json#L153)

## SYN03 公共标记与退化策略 — 1/3

有找不到参考marker时转normalized time的可定位实现，故保留退化工作的部分分。没有按当前组成员求公共marker集合或先验证全部成员兼容；leader仍可输出marker_phase，而缺标记的follower直接把marker区间进度当作全长进度，组内语义不一致。也未消费声明的fallback_method来统一全组退化/拒绝并报告。此为兼容性策略问题，独立于SYN02仅使用左脚分段的限制。

证据：[src/controller.py:297](candidate/src/controller.py#L297) · [src/controller.py:317](candidate/src/controller.py#L317) · [config/animation_graph.json:153](candidate/config/animation_graph.json#L153)

## SYN04 Leader选择与事件归属 — 0.5/2

有确定性的leader选择与player_id平局顺序，输出leader关联。但比较weight+target而非图声明highest_weight，刚进入的低权重玩家可提前夺取leader；没有Notify的所属播放器、仅leader触发或抑制follower重复事件的具体计划。diagnostics中的state transition事件不能充当Notify归属计划。

证据：[src/controller.py:324](candidate/src/controller.py#L324) · [config/animation_graph.json:153](candidate/config/animation_graph.json#L153) · [src/controller.py:350](candidate/src/controller.py#L350)

## SYN05 非循环起停与距离匹配的同步策略 — 3/3

起停非循环播放器显式不参与cycle同步组，其时间由距离曲线反查并受速率约束，因此不会被cycle follower时间覆盖。进入cycle时优先继承已有cycle相位，否则从输出start/pivot最近plant接触对应到cycle标记；停止以独立距离时间和交叉淡化衔接。这是明确的替代Always Leader方案，并未声称距离反查天然等于脚相同步。

证据：[config/animation_graph.json:73](candidate/config/animation_graph.json#L73) · [src/controller.py:436](candidate/src/controller.py#L436) · [src/controller.py:502](candidate/src/controller.py#L502)

## SYN06 接管、跨尾与事件唯一性 — 1/2

已有周期取模、跨尾参考点扩展，以及新增cycle玩家时复制已有相位，覆盖基本接管与跨尾。但只保留取模前后时刻，没有跨越圈数/有序marker区间/开闭端点及事件标识去重规则；单帧跨多个marker或整圈的调度区间不能从所交付计划恢复。本项扣时间区间与唯一性规则缺失，SYN04另扣leader选择及事件所属者。

证据：[src/controller.py:256](candidate/src/controller.py#L256) · [src/controller.py:285](candidate/src/controller.py#L285) · [src/controller.py:330](candidate/src/controller.py#L330) · [src/controller.py:436](candidate/src/controller.py#L436)

## DST01 距离曲线含义与符号 — 2/2

三类距离定义独立且单位为 cm：start 自起点累计 XY 路程，stop 到结束的剩余路程，pivot 以最小速度位置为零且前负后正。消费者分别积累 speed*dt、预测正剩余距离、反向前负目标/反向后累计正目标；符号和参考点一致。

证据：[src/build_assets.py:97](candidate/src/build_assets.py#L97) · [src/build_assets.py:302](candidate/src/build_assets.py#L302) · [src/controller.py:515](candidate/src/controller.py#L515)

## DST02 按位移推进与按目标定位分开 — 3/3

start 每帧只向内部累计量加 speed*dt，再由该累计值查绝对时间，未把累计路程反复加到播放器时间；stop 每帧按剩余目标反查，pivot 切换前后距离语义。匹配时间由 _set_matched_time 写入，播放器不二次推进。

证据：[src/controller.py:369](candidate/src/controller.py#L369) · [src/controller.py:515](candidate/src/controller.py#L515) · [src/controller.py:268](candidate/src/controller.py#L268) · [IMPLEMENTATION.md:36](candidate/IMPLEMENTATION.md#L36)

## DST03 停止/转向目标来源 — 3/3

停止距离使用 v²/(2b)，b 有图内可配置默认值和观测减速平滑估计；pivot 使用速度方向上的减速度预测到反向点的距离，分母至少为 1 并在反向后改为实走距离。模型假设及缺片路径有说明。input_intent 与题面加速度语义的兼容性归 LOC 审查，本项不重复扣同一状态判断根因。

证据：[config/animation_graph.json:15](candidate/config/animation_graph.json#L15) · [src/controller.py:195](candidate/src/controller.py#L195) · [src/controller.py:382](candidate/src/controller.py#L382) · [src/controller.py:410](candidate/src/controller.py#L410) · [src/controller.py:525](candidate/src/controller.py#L525) · [IMPLEMENTATION.md:38](candidate/IMPLEMENTATION.md#L38)

## DST04 曲线反查的确定性和边界 — 2/3

反查支持增/减曲线、线性插值、两端 clamp、平台分支，并把生成的 pivot 曲线化为有符号累计路程；播放器限制新时间不倒退。缺口是只检查 times 非空，直接按端点判断单调性，未验证 times/values 对齐、有限性和全序单调，也没有拒绝或分支处理非单调输入的明确契约。对这种输入会静默取第一个命中段或末端；这不是要求通用引擎，而是本项要求的曲线边界策略。

证据：[src/anim_math.py:110](candidate/src/anim_math.py#L110) · [src/build_assets.py:312](candidate/src/build_assets.py#L312) · [src/controller.py:268](candidate/src/controller.py#L268) · [src/controller.py:51](candidate/src/controller.py#L51)

## DST05 播放速率限制与步幅补偿 — 2/3

距离匹配时间有 dt*min/max playrate 的上下限并报告有效倍率；cycle 另用 speed/authored_speed，并在 clamp 后按 speed/(authored_speed*play_rate) 计算剩余 stride，避免同一速度补偿两次。缺口是 stride 只对 cycle 计算：start/stop/pivot 匹配被 .6–1.6 限制后未处理残余距离，也未明确声明这些状态接受受限滑动。只是说无 IK/未调参不等于给出该取舍契约。

证据：[src/controller.py:268](candidate/src/controller.py#L268) · [config/animation_graph.json:26](candidate/config/animation_graph.json#L26) · [src/controller.py:603](candidate/src/controller.py#L603) · [src/controller.py:626](candidate/src/controller.py#L626) · [IMPLEMENTATION.md:40](candidate/IMPLEMENTATION.md#L40) · [IMPLEMENTATION.md:55](candidate/IMPLEMENTATION.md#L55)

## DST06 Evaluator推进、跳转与副作用 — 1/2

显式 time_mode、prev_time、权威 sample_time 和本帧有效倍率可追踪；普通推进/距离推进路径分开，root translation 忽略、转身 yaw 按前后采样差消费，且未宣称 UE 等价。缺口是进入 stop/pivot 直接初始化到反查 t0 与逐帧 advancing 的事件语义未定义，未声明此类跳转/初始化是否抑制或补发 Notify，也没有相应事件计划。只要求可审查的副作用约定，不要求事件执行器；此处不为 RES05 已处理的 root 所有权重复扣分。

证据：[src/controller.py:239](candidate/src/controller.py#L239) · [src/controller.py:382](candidate/src/controller.py#L382) · [src/controller.py:414](candidate/src/controller.py#L414) · [src/controller.py:535](candidate/src/controller.py#L535) · [src/controller.py:562](candidate/src/controller.py#L562) · [IMPLEMENTATION.md:36](candidate/IMPLEMENTATION.md#L36)

## WRP01 Orientation Warping的朝向分工 — 2/3

计算有界的局部移动方向-四向中心角，区分根旋转及脊柱瞄准并形成操作链；但local_velocity_angle基于actor空间，warp只减当前cardinal。计划先施加rotate_root_yaw后仍未从方向差中消去有效root/mesh offset，存在offset时方向补偿与最终下身朝向不一致。扣1分；未因另由RES02处理的烘焙坐标根因重复扣分。

证据：[src/controller.py:224](candidate/src/controller.py#L224) · [src/controller.py:598](candidate/src/controller.py#L598) · [src/controller.py:610](candidate/src/controller.py#L610)

## WRP02 Stride Warping的比例与限制 — 2/3

Cycle使用speed/(authored_speed*play_rate)得到stride并夹在0.5..1.5，低移动速度时禁用，结果进入有效姿态计划；但原动画速度分母未作近零保护，stride也直接逐帧输出，没有独立平滑或入出过渡。扣1分；不要求实际IK/FK，不在本项重复扣Start距离匹配余量的其他问题。

证据：[src/controller.py:603](candidate/src/controller.py#L603) · [src/controller.py:626](candidate/src/controller.py#L626)

## WRP03 骨骼约束与姿态补偿契约 — 2/2

操作链由图指定，输出引用上一操作，依次表达根yaw、方向、步幅和脊柱分配；骨骼均属于给定26骨子集，文档明确无完整Manny/绑定参考姿态/IK执行和姿态求值。该项计划层契约充分，不要求渲染或补齐缺失骨骼；各参数算法缺口在独立WRP项评分。

证据：[src/controller.py:610](candidate/src/controller.py#L610) · [IMPLEMENTATION.md:29](candidate/IMPLEMENTATION.md#L29) · [IMPLEMENTATION.md:45](candidate/IMPLEMENTATION.md#L45)

## WRP04 RootYawOffset三类状态策略 — 2/3

Idle/TIP累积反向actor yaw，并wrap/clamp；移动状态指数淡出且输出根旋转操作。但Start与Cycle走同一else淡出分支，没有Start Hold模式，三类状态策略缺一类。扣1分，未另扣烘焙坐标或TIP符号。

证据：[src/controller.py:224](candidate/src/controller.py#L224) · [src/controller.py:613](candidate/src/controller.py#L613)

## WRP05 Turn In Place与转向曲线 — 1/1

TIP有idle等待和角度阈值、90/180资源选择及缺样本替代；播放器按源root_yaw曲线相邻时间差持续消耗/累加offset，并按请求角缩放。满足计划层转身曲线要求；坐标烘焙根因按RES02单独归属。

证据：[src/locomotion_conditions.py:71](candidate/src/locomotion_conditions.py#L71) · [src/controller.py:418](candidate/src/controller.py#L418) · [src/controller.py:535](candidate/src/controller.py#L535)

## ARC01 状态逻辑、资源集与修正职责分开 — 2/2

图驱动高层状态/过渡，选择器负责资产表与fallback，派生移动数据集中于self.k；最终组合分别计算root yaw、orientation、stride和spine aim，职责可独立追踪。没有因单一Unarmed题包额外要求武器接口。

证据：[src/controller.py:37](candidate/src/controller.py#L37) · [src/controller.py:121](candidate/src/controller.py#L121) · [src/controller.py:209](candidate/src/controller.py#L209) · [src/controller.py:620](candidate/src/controller.py#L620)

## ARC02 移动与上身朝向的分层契约 — 2/2

配置明确capsule拥有根平移、姿态操作顺序与上身骨骼权重；控制器输出加权移动pose后，依序串接root yaw、orientation/stride及spine aim。上身yaw按有效骨骼权重分配，输入链接承接前一操作，符合本题允许的抽象分层契约。未将此证据表述为最终pose验证。

证据：[config/animation_graph.json:31](candidate/config/animation_graph.json#L31) · [config/animation_graph.json:158](candidate/config/animation_graph.json#L158) · [src/controller.py:594](candidate/src/controller.py#L594) · [src/controller.py:630](candidate/src/controller.py#L630)

## ARC03 节点生命周期 — 2/2

reset只初始化控制器状态；_enter_state在每次状态变相关时重选资产/创建独立玩家，start清空累计距离并从0开始、stop按当前预测距离初始化时间。每帧推进单列，淡出玩家的继续推进为显式分支，权重归零后移除，不是无关节点永久推进。

证据：[src/controller.py:82](candidate/src/controller.py#L82) · [src/controller.py:239](candidate/src/controller.py#L239) · [src/controller.py:364](candidate/src/controller.py#L364) · [src/controller.py:502](candidate/src/controller.py#L502) · [src/controller.py:544](candidate/src/controller.py#L544)

## ARC04 快照与共享派生数据边界 — 2/2

step先校验当前frame，再生成一次self.k供状态、同步及姿态操作共用；可变播放器/时间/历史量与图参数、资产索引分别存储，无外部逐层独立采样。本项只确认快照与共享状态边界；输入加速度解释不符由LOC01承担，不重复扣分。

证据：[src/controller.py:31](candidate/src/controller.py#L31) · [src/controller.py:82](candidate/src/controller.py#L82) · [src/controller.py:209](candidate/src/controller.py#L209) · [src/controller.py:467](candidate/src/controller.py#L467)

## ARC05 资源与图配置进入实际决策 — 2/2

有配置到决策的完整链：读取图状态/优先级/条件，step按条件选择目标，selector实际按图表索引资产与fallback，资源曲线用于时间反查，图操作顺序用于输出。同步部分的具体算法/配置缺陷已归SYN02–SYN04，本项认可真实连接而不重复扣分。

证据：[src/controller.py:37](candidate/src/controller.py#L37) · [src/controller.py:121](candidate/src/controller.py#L121) · [src/controller.py:481](candidate/src/controller.py#L481) · [src/controller.py:515](candidate/src/controller.py#L515) · [src/controller.py:610](candidate/src/controller.py#L610)

## ROB01 输入异常与稳定退化 — 2.5/3

常规入口有缺字段、类型、非有限值和非正dt校验；dt超过0.25有显式截断诊断，缺资源有报错/声明回退。缺口：仅检查输入分量有限，未检查派生数值有限；例如两个水平速度分量均为1.7e308仍通过校验，hypot溢为inf并直接写入diagnostics。扣0.5，未重复扣曲线/移动语义项。此反例仅由静态代码推导。

证据：[src/controller.py:138](candidate/src/controller.py#L138) · [src/controller.py:180](candidate/src/controller.py#L180) · [src/controller.py:650](candidate/src/controller.py#L650)

## ROB02 独立复现与提交完整性 — 3/3

CLI保留manifest/output并将输出父目录传给加工函数；控制器入口、reset清理、唯一播放器编号及约定输出完整。随机性未使用，源/配置固定下行为确定；说明给出复现方法。这里只确认静态接口，不把模型自查等同于独立执行通过。

证据：[src/build_assets.py:479](candidate/src/build_assets.py#L479) · [src/controller.py:82](candidate/src/controller.py#L82) · [src/controller.py:645](candidate/src/controller.py#L645) · [IMPLEMENTATION.md:17](candidate/IMPLEMENTATION.md#L17)

## ROB03 证据与限制诚实可审查 — 2/2

实现说明明确列出制作入口、关键假设、22条缺样本延期、派生替代以及静态计划与最终姿态的边界；关键设计可在代码中定位。未伪称UE/姿态验证。说明诚实不免除其他实现项的缺陷扣分。

证据：[IMPLEMENTATION.md:50](candidate/IMPLEMENTATION.md#L50) · [src/controller.py:1](candidate/src/controller.py#L1)

## 门槛

- G01: pass。资源加工和控制器均有实质Python实现，不是仅文字/模板壳；功能缺口按条目评分。
- G02: pass。有实际资源制作逻辑和已生成的派生资源表、产物；曲线/marker缺口不能机械视为整个资源类别均缺失。
- G03: pass。控制器包含可辨认的状态/转移、播放器和组合计划，并消费图参数/资源。图消费不足按ARC项处理，未达到完全无有效动画流程的门槛。
