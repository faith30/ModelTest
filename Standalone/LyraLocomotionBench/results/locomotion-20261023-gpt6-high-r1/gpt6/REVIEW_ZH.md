# gpt6：40项静态审查

得分 **87.5 / 100**；扣分 12.5。40项与3个门槛均已审查。

证据仅来自冻结代码、图和资源数据。没有执行候选或UE；输出计划不代表最终动画姿态。

候选目录SHA256：`a8cfd07be7c3c6e34d75b63e3ab668cf61331392984fbc48d5edacb0ab095270`。

## RES01 原始输入、派生资源与来源可追溯 — 2/2

原始清单与样本只作输入；每个派生资源记录 source_clip_ids、源名、version=1 的具体加工配方，ready 条目保存源文件 SHA256，资源表保存清单规范化 SHA256。已读产物中 auth_motion_01 对应 motion_01；启发式接触明确不冒充原 Lyra 通知/真实标签。

证据：[src/build_assets.py:90](candidate/src/build_assets.py#L90) · [src/build_assets.py:106](candidate/src/build_assets.py#L106) · [src/build_assets.py:123](candidate/src/build_assets.py#L123) · [assets/authored_assets.json:1](candidate/assets/authored_assets.json#L1)

## RES02 骨架、单位和坐标系一致 — 3/3

声明并实际执行 cm/秒/度、26 骨骼 component-space 与 Hamilton xyzw；位置 B(x,y,z)=(y,-x,z)，旋转用 B*q*B^-1 重新表达局部基，随后只移除相对首帧 root yaw，保留固定 actor 基。世界速度/加速度按 actor yaw 转局部；TIP 将负 actor yaw 对应人体左转正角。已有左右转样本的相对 yaw 分别为 -90 与约 +180，与声明一致；未扩造完整骨架。

证据：[IMPLEMENTATION.md:40](candidate/IMPLEMENTATION.md#L40) · [src/build_assets.py:59](candidate/src/build_assets.py#L59) · [src/build_assets.py:117](candidate/src/build_assets.py#L117) · [src/controller.py:155](candidate/src/controller.py#L155) · [src/controller.py:247](candidate/src/controller.py#L247)

## RES03 走跑与方向资源覆盖 — 3/3

37 个唯一派生资源及 37 个图绑定覆盖 walk/jog 四方向 cycle/start/stop/pivot、四类 TIP 与 idle。独立读取 JSON 确认全部 15 条有样本资源含实际加工帧和对应源哈希，22 条 metadata_only 保留通用 recipe、deferred_missing_samples 与 data=null；没有以正向片段冒充缺片，也没有制造 idle 姿态。延期本身不扣分。

证据：[config/animation_graph.json:74](candidate/config/animation_graph.json#L74) · [src/build_assets.py:106](candidate/src/build_assets.py#L106) · [assets/authored_assets.json:1](candidate/assets/authored_assets.json#L1) · [assets/authored_assets.json:1](candidate/assets/authored_assets.json#L1) · [IMPLEMENTATION.md:32](candidate/IMPLEMENTATION.md#L32)

## RES04 片段时域、循环与边界 — 2/2

保留原始全部抽样时刻并以首帧为零，duration 取最后时刻，不以帧数额外加一帧。循环另记录实测窗口起止与时长；采样时间仍在完整加工时间轴，输出/退出玩家在该窗口 wrap，单次动作 clamp 到末时刻。缺样 sample_time=null、rate=0，策略超时明确不是已知资源时长或进度。

证据：[src/build_assets.py:75](candidate/src/build_assets.py#L75) · [src/asset_analysis.py:76](candidate/src/asset_analysis.py#L76) · [src/controller.py:222](candidate/src/controller.py#L222) · [src/controller.py:326](candidate/src/controller.py#L326) · [IMPLEMENTATION.md:45](candidate/IMPLEMENTATION.md#L45)

## RES05 根轨迹数据与角色位移职责 — 3/3

提取并保存 root XYZ 轨迹、XY 弧长及连续相对 yaw；加工姿态从每个 component transform 去除当前 root XY 与相对 yaw，同时保留 Z。外部游戏系统拥有世界平移和 actor yaw，轨迹仅用于分析/匹配；转身只以 yaw 曲线增量更新 visual facing，操作显式不施加 gameplay root motion，不会把同一平移施加两次。

证据：[src/build_assets.py:65](candidate/src/build_assets.py#L65) · [src/build_assets.py:104](candidate/src/build_assets.py#L104) · [src/controller.py:225](candidate/src/controller.py#L225) · [src/controller.py:371](candidate/src/controller.py#L371) · [IMPLEMENTATION.md:41](candidate/IMPLEMENTATION.md#L41)

## RES06 同步相位标记的制作 — 3/3

按源 component 足高、XY 有限差分速度、三点中值与迟滞估计左右接触起点；已处于接触的首帧不伪造新 onset。仅接受一个 R 位于相邻 L 起点之间且周期合法的 L-R-L 窗口，无合格区间则明确无 marker 回退。独立读取产物确认 8 个循环都有有序实测窗口，L/R 跨资源语义相同；启发式标记明确不是原始可播放 Notify。

证据：[src/asset_analysis.py:18](candidate/src/asset_analysis.py#L18) · [src/asset_analysis.py:55](candidate/src/asset_analysis.py#L55) · [assets/authored_assets.json:1](candidate/assets/authored_assets.json#L1) · [IMPLEMENTATION.md:44](candidate/IMPLEMENTATION.md#L44)

## RES07 曲线制作及可索引表示 — 2/2

从相邻 root XY 样本累计弧长，生成与 sample_times_seconds 一一对应的 distance_cm 和 total-distance 的 remaining_distance_cm；轴、单位、起点和停步末帧参考点明确。数组既可按时间线性插值，也有实际距离反查函数；这是可读取的独立数据表示，不只列 UE 压缩器名称。反查对非法输入的边界缺口仅归 DST04。

证据：[src/build_assets.py:65](candidate/src/build_assets.py#L65) · [src/controller.py:20](candidate/src/controller.py#L20) · [IMPLEMENTATION.md:42](candidate/IMPLEMENTATION.md#L42)

## RES08 资源制作流程闭合 — 2/2

构建入口接收 manifest/output，按清单稳定顺序逐项处理，样本必须位于清单目录内且 clip_id、骨架和帧维度一致；缺文件/缺骨、非递增时刻及无效四元数会抛出可定位失败，序列化拒绝非有限值。产物内嵌加工帧，不依赖固定输出目录的旁文件；图初始化校验 ID 与引用。独立只读检查本次 15 个源哈希、源/产物帧数及 37 个资源引用未见不一致；未执行候选构建，自查声明不作为本次运行证据。

证据：[src/build_assets.py:23](candidate/src/build_assets.py#L23) · [src/build_assets.py:44](candidate/src/build_assets.py#L44) · [src/build_assets.py:109](candidate/src/build_assets.py#L109) · [src/build_assets.py:139](candidate/src/build_assets.py#L139) · [src/controller.py:38](candidate/src/controller.py#L38)

## LOC01 移动快照与派生量 — 3/3

从同一frame读取dt/速度/加速度/actor/aim，按actor yaw计算局部量，用速度区分移动/停稳并由速度与加速度投影判断制动。虽然内部变量名为intent，Cycle并不以零加速度为停止条件；非零匀速不会因a=0误进Stop。没有读取未提供的按键或世界位置。

证据：[src/controller.py:239](candidate/src/controller.py#L239) · [src/controller.py:314](candidate/src/controller.py#L314)

## LOC02 Walk/Jog选择与阈值稳定 — 2/2

walk/jog动作选择有440/380上下阈值，循环在350–500间连续混合并对jog_alpha指数平滑；两套gait权重进入真实资源选择及播放器计划。阈值、平滑和播放行为均可定位，满足与旧两路一致的等价防抖口径。

证据：[config/animation_graph.json:10](candidate/config/animation_graph.json#L10) · [src/controller.py:253](candidate/src/controller.py#L253) · [src/controller.py:167](candidate/src/controller.py#L167)

## LOC03 四方向与斜向选择 — 3/3

actor局部速度决定方向，最短角指数平滑处理环绕；动作四向选择保留当前扇区12度滞回，低速采用加速度方向或保留方向。循环对圆周上相邻四向做连续混合，覆盖前后左右与斜向；姿态根偏移未计入方向补偿的独立问题只在WRP01扣。

证据：[src/controller.py:101](candidate/src/controller.py#L101) · [src/controller.py:167](candidate/src/controller.py#L167) · [src/controller.py:247](candidate/src/controller.py#L247) · [config/animation_graph.json:129](candidate/config/animation_graph.json#L129)

## LOC04 Idle到Start到Cycle — 3/3

Idle->Start->Cycle路径可达；_enter清零state_age、time/travel，创建新action ID，方向/步态变更有最短持有时间，片段完成或明确超时后转Cycle。缺采样动作保留null时间/不可物化状态，策略计时不冒称实际片段时长；未出现每帧重置或重入沿用结束时钟。

证据：[src/controller.py:147](candidate/src/controller.py#L147) · [src/controller.py:299](candidate/src/controller.py#L299) · [src/controller.py:206](candidate/src/controller.py#L206) · [IMPLEMENTATION.md:55](candidate/IMPLEMENTATION.md#L55)

## LOC05 减速、Stop与Idle — 3/3

用沿速度的加速度投影估算减速及到停时间；Stop按声明的v²/(2a)模型定位并有最小推进，完成后依据实际stopped选择Idle或Cycle，重新移动可进入Start。未知素材以明确策略超时退化并报告不可物化，不按缺样本扣分。距离算法细节由DST项独立评。

证据：[src/controller.py:266](candidate/src/controller.py#L266) · [src/controller.py:306](candidate/src/controller.py#L306) · [src/controller.py:214](candidate/src/controller.py#L214) · [IMPLEMENTATION.md:54](candidate/IMPLEMENTATION.md#L54)

## LOC06 Pivot及重新起步 — 2/2

反向由帧间速度夹角或速度+加速度短期预测判断，与瞄准角分开；保留进入方向和进入步态选择Pivot，锁存/冷却避免每帧重新进入，Stop再起步和Pivot结束/中断均明确。文档承认无期望速度时强制动与主动反向存在歧义；这是允许的受限预测，不按未提供输入扣分。Pivot距离驱动覆盖由DST审查，不在此重扣。

证据：[src/controller.py:269](candidate/src/controller.py#L269) · [src/controller.py:303](candidate/src/controller.py#L303) · [src/controller.py:147](candidate/src/controller.py#L147) · [IMPLEMENTATION.md:52](candidate/IMPLEMENTATION.md#L52)

## LOC07 过渡竞争与连续性 — 2/2

代码按movement interrupts turn、reversal、stop/restart/completion给出确定顺序；_enter重建当前action但保留已有players，旧玩家继续推进，权重指数淡出并归一，消退后清理。转移不以非零权重反复触发，跨状态并非硬切。

证据：[src/controller.py:289](candidate/src/controller.py#L289) · [src/controller.py:326](candidate/src/controller.py#L326) · [src/controller.py:147](candidate/src/controller.py#L147)

## SYN01 组作用域与角色配置 — 3/3

cycles 节点显式绑定 locomotion 组，单次动作节点不入组；控制器实际查找该组配置，只将仍有有效淡化权重的 cycle 播放器列为成员。walk/jog 及方向间共享接触相位，动作使用独立 distance/one-shot 时钟，没有机械地把 idle、start、stop、turn 全塞入循环组。这是范围固定的配置化计划器，不以必须支持任意节点类型为额外门槛。

证据：[config/animation_graph.json:128](candidate/config/animation_graph.json#L128) · [src/controller.py:59](candidate/src/controller.py#L59) · [src/controller.py:359](candidate/src/controller.py#L359)

## SYN02 Marker相位不是Notify — 3/3

加工过程从实测接触起点选 L-R-L 窗口；控制器按 L→R、R→下一 L 两段分别映射公共相位到各资源时间，并使用分段导数计算 play_rate，能保持不同长度和不同 R 接触时刻资源的区间进度对应。当前八个循环的生成数据均有 measured_single_stride 与 L-R-L 标记。这不是仅复制 normalized time；接触估计明确不是原始 Notify。独立的 Notify 归属缺口只在 SYN04 扣分，跨越事件区间另在 SYN06 扣分。

证据：[src/asset_analysis.py:47](candidate/src/asset_analysis.py#L47) · [src/controller.py:130](candidate/src/controller.py#L130) · [src/controller.py:185](candidate/src/controller.py#L185) · [IMPLEMENTATION.md:44](candidate/IMPLEMENTATION.md#L44)

## SYN03 公共标记与退化策略 — 1/3

已覆盖单个资源缺完整 L-R-L 时返回无 markers 的全窗口数据，并在时间映射时采用 normalized phase；当前八个循环由同一加工规则得到兼容 L-R-L。缺口是组内没有共同 marker 集合或等价的共同模式校验/决策：若一个成员走无标记退化、另一个仍有 R，前者按全窗口线性、后者按两个接触区间映射，控制器仍报告同一 L/R marker_mapping，不会将整组统一退化、拒绝或报告失配。这是消费端混合标记可用性策略的独立缺口，不因缺原始 Notify/缺采样或 marker 制作本身重复扣分。

证据：[src/asset_analysis.py:61](candidate/src/asset_analysis.py#L61) · [src/controller.py:130](candidate/src/controller.py#L130) · [src/controller.py:185](candidate/src/controller.py#L185) · [src/controller.py:360](candidate/src/controller.py#L360)

## SYN04 Leader选择与事件归属 — 1/2

leader 从当前实际输出归一化权重选取，使用 asset_id 对同权确定性排序，符合配置的 highest_weight_then_asset_id。共享主时钟不依赖 leader 驱动，作为明确说明的替代方案可接受。但返回组/播放器/操作计划均没有 Notify/event 的归属、leader-only 触发或 follower 抑制规则；接触曲线与 leader 名称不能替代事件调度计划。此项只扣事件归属，不与 SYN06 的区间/去重缺口合并重复。

证据：[config/animation_graph.json:240](candidate/config/animation_graph.json#L240) · [src/controller.py:352](candidate/src/controller.py#L352) · [src/controller.py:383](candidate/src/controller.py#L383) · [IMPLEMENTATION.md:62](candidate/IMPLEMENTATION.md#L62)

## SYN05 非循环起停与距离匹配的同步策略 — 3/3

start/stop 为不循环的独立动作播放器，时间由实际距离反求并限速，组成员只包含 cycles，因此不会被 follower 同步覆盖距离匹配时间。进入 cycle 前，读取当前动作的两脚相对位置，在目标循环实际窗口内选最近采样并反求公共相位；给出了动作到循环的具体衔接。不因没有 Always Leader 字面设置扣分；单次动作隔离加明确接入属于可接受方案。

证据：[src/controller.py:107](candidate/src/controller.py#L107) · [src/controller.py:147](candidate/src/controller.py#L147) · [src/controller.py:206](candidate/src/controller.py#L206) · [src/controller.py:360](candidate/src/controller.py#L360)

## SYN06 接管、跨尾与事件唯一性 — 1/2

共享相位持续推进，leader 更替不会重新初始化 follower；每个循环按实际 loop_range 回绕，普通尾部跨越与动作接入有具体时间路径。缺口是 phase 直接取模且没有保留圈数/上一相位、无前后 marker 的遍历或事件区间计划；大 dt 一次跨多个 marker/整圈时无法从输出恢复全部经过区间，也未定义半开端点及已触发事件键以避免漏发/重发。这里只扣区间唯一性，leader 选择本身不再次扣。

证据：[src/controller.py:185](candidate/src/controller.py#L185) · [src/controller.py:327](candidate/src/controller.py#L327) · [src/controller.py:360](candidate/src/controller.py#L360) · [src/controller.py:394](candidate/src/controller.py#L394)

## DST01 距离曲线含义与符号 — 2/2

曲线单位 cm，distance_cm 是从首帧起的 XY 累计弧长，remaining_distance_cm 是到末帧的剩余弧长。start 以本次动作累计实走路程反查；stop 将预测剩余距离转换成 total-remaining 后反查。pivot 明确保留累计弧长及入向投影反向提示，并声明当前采用时间播放，没有把未解释的正值曲线冒充 pivot 目标距离。pivot 目标生成/消费缺失分别在 DST03/DST02 评价，本项不再次扣分。

证据：[src/build_assets.py:78](candidate/src/build_assets.py#L78) · [IMPLEMENTATION.md:43](candidate/IMPLEMENTATION.md#L43) · [src/asset_analysis.py:86](candidate/src/asset_analysis.py#L86) · [src/controller.py:211](candidate/src/controller.py#L211) · [config/animation_graph.json:150](candidate/config/animation_graph.json#L150)

## DST02 按位移推进与按目标定位分开 — 2/3

start 将每次更新的 speed*dt 加到本次动作 travel，再反查绝对采样时间；stop 每帧由剩余目标反查，随后统一限制时间，未把累计路程反复加到当前时钟。缺少的独立消费路径是 ready pivot：它只按 previous+dt*clamp(speed/average_speed) 播放，没有按转向目标距离定位或按 pivot 前后距离阶段消费。此项只扣目标到播放器时间的映射缺失；目标预测本身另归 DST03，不在 RES/DST01 再罚。

证据：[src/controller.py:161](candidate/src/controller.py#L161) · [src/controller.py:206](candidate/src/controller.py#L206) · [config/animation_graph.json:150](candidate/config/animation_graph.json#L150)

## DST03 停止/转向目标来源 — 2/3

stop 使用沿当前速度的观测减速度与 v²/(2a) 估计；不足 1 cm/s² 时使用图内可配置 default_braking_cm_s2=700，且明确这是常减速近似，不是碰撞感知世界停点。缺少的是 ready pivot 的目标生产：v+a*prediction_seconds 仅用于反向触发，实测 reversal_hint 只是资源证据，没有依据给定运动量推导到转向点的距离/阶段目标。已有源片总弧长没有被冒充真实预测。此项评目标来源，DST02 评已有目标怎样控制时间，分别对应冻结条目的独立要求。

证据：[src/controller.py:214](candidate/src/controller.py#L214) · [src/controller.py:266](candidate/src/controller.py#L266) · [config/animation_graph.json:27](candidate/config/animation_graph.json#L27) · [config/animation_graph.json:150](candidate/config/animation_graph.json#L150) · [IMPLEMENTATION.md:54](candidate/IMPLEMENTATION.md#L54)

## DST04 曲线反查的确定性和边界 — 2/3

反查使用二分及线性插值，端点 clamp、近零平台差分支可定位，距离驱动结果还限制不倒退和有效倍率；源弧长构造避免往返轨迹直接造成非单调投影。缺口与 Opus 同尺度：inverse_distance 直接索引并 bisect，未验证 times/values 长度、有限性、全序单调，也没有拒绝或处理非法/非单调传入曲线的明确契约；构造器只校验图/资源引用。此处不为 pivot 未接入距离路径再扣分。

证据：[src/controller.py:28](candidate/src/controller.py#L28) · [src/controller.py:38](candidate/src/controller.py#L38) · [src/controller.py:220](candidate/src/controller.py#L220)

## DST05 播放速率限制与步幅补偿 — 2/3

start/stop 距离反查受 dt*min/max rate 限制并输出实际有效倍率；cycle 另用平均动画速度做 speed matching，stride 以 speed/(名义动画速度*实际倍率) 有界补偿，避免同一速度差完整乘两次。接受其声明的片段平均速度近似，不额外要求逐帧导数。直接缺口是 stop 分支固定 stride=1：距离时间受限后未匹配部分既无补偿计划，也未明确声明允许的滑步取舍。文档只说明限制和不保证停点一致，尚未给出限速残差的处理约定；沿用 Opus 本项 2/3 尺度。

证据：[src/controller.py:220](candidate/src/controller.py#L220) · [src/controller.py:177](candidate/src/controller.py#L177) · [src/controller.py:378](candidate/src/controller.py#L378) · [config/animation_graph.json:18](candidate/config/animation_graph.json#L18) · [config/animation_graph.json:30](candidate/config/animation_graph.json#L30) · [IMPLEMENTATION.md:54](candidate/IMPLEMENTATION.md#L54) · [IMPLEMENTATION.md:67](candidate/IMPLEMENTATION.md#L67)

## DST06 Evaluator推进、跳转与副作用 — 1/2

sample_time 是权威位置且禁止外部二次推进；distance_bounded/one_shot 时钟、循环窗口以及转身 yaw 的采样差消费都有具体路径，未宣称 UE 等价。缺口是动作初次定位、重新进入及动作到循环相位对齐的显式时间变化，没有公开区分 seek 与 advancing 的事件规则，也未声明是否抑制/补发 Notify 或提供相应事件计划。只要求独立简化副作用契约，不要求 UE 事件执行器；root 所有权已有 RES05 得分，不在这里重复扣。

证据：[src/controller.py:147](candidate/src/controller.py#L147) · [src/controller.py:220](candidate/src/controller.py#L220) · [src/controller.py:107](candidate/src/controller.py#L107) · [src/controller.py:362](candidate/src/controller.py#L362) · [IMPLEMENTATION.md:60](candidate/IMPLEMENTATION.md#L60)

## WRP01 Orientation Warping的朝向分工 — 2/3

动作使用有界的局部移动方向与源方向差；循环采用四向连续混合作等价方向表达，actor与visual yaw也明确分开。但计划先将全部component变换旋转root offset，动作warp仍仅raw_direction-reference，循环方向也仍基于actor空间，没有消去有效mesh/root偏移；存在offset时方向补偿不闭合。按Opus同类缺口扣1分。上身aim分层缺口由ARC02处理，不在此追加；也不重复扣资源坐标制作问题。

证据：[src/controller.py:247](candidate/src/controller.py#L247) · [src/controller.py:167](candidate/src/controller.py#L167) · [src/controller.py:371](candidate/src/controller.py#L371)

## WRP02 Stride Warping的比例与限制 — 2.5/3

按当前玩家权重与play_rate形成名义速度，speed/max(nominal,1)有分母保护，比例限幅并进入有效stride操作及pelvis/feet引用。但stride直接随原始speed和当前state逐帧输出，未保存/平滑该参数，进入Stop等状态还会直接改为1；动作权重淡化不能替代后置stride参数过渡。独立无平滑缺口扣0.5，较Opus多有分母保护；整段平均速度替代当前有效速度及Stop残余补偿归DST05，不在本项重复扣。

证据：[src/controller.py:378](candidate/src/controller.py#L378) · [src/controller.py:346](candidate/src/controller.py#L346) · [config/animation_graph.json:18](candidate/config/animation_graph.json#L18)

## WRP03 骨骼约束与姿态补偿契约 — 2/2

姿态计划有明确有序输入链：混合、root yaw、方向、stride、lean、foot IK意图；引用已有player/上一operation，pelvis/feet/spine均在所给26骨子集中。说明承认无完整骨架/绑定/solver/世界位置和最终姿态，foot IK与接触估计的边界明确。不要求实际IK/FK或渲染；算法缺口在独立WRP/DST项评分。

证据：[src/controller.py:366](candidate/src/controller.py#L366) · [src/controller.py:383](candidate/src/controller.py#L383) · [config/animation_graph.json:170](candidate/config/animation_graph.json#L170) · [IMPLEMENTATION.md:64](candidate/IMPLEMENTATION.md#L64)

## WRP04 RootYawOffset三类状态策略 — 2/3

Idle/Turn保留visual世界朝向，因此相对actor offset能累积抵消actor转动；输出wrap/clamp并在移动时半衰期淡出。缺口与Opus相同：Start和Cycle都进入state not in ('idle','turn')的淡出分支，没有Start Hold策略。扣1分；未因WRP01方向空间不闭合重复扣。

证据：[src/controller.py:250](candidate/src/controller.py#L250) · [src/controller.py:322](candidate/src/controller.py#L322) · [src/controller.py:371](candidate/src/controller.py#L371) · [IMPLEMENTATION.md:58](candidate/IMPLEMENTATION.md#L58)

## WRP05 Turn In Place与转向曲线 — 1/1

TIP使用aim-visual最短角、进入阈值/冷却、90/180与人体角符号对应选择，源root_yaw按本帧前后采样差持续累加到visual_yaw并输出offset。缺样转身保留不可物化，不伪造曲线进度，策略超时后抑制同一aim重复请求。符合计划层曲线消耗要求，不要求真实姿态求解。

证据：[src/controller.py:155](candidate/src/controller.py#L155) · [src/controller.py:225](candidate/src/controller.py#L225) · [src/controller.py:286](candidate/src/controller.py#L286) · [src/controller.py:371](candidate/src/controller.py#L371) · [IMPLEMENTATION.md:58](candidate/IMPLEMENTATION.md#L58)

## ARC01 状态逻辑、资源集与修正职责分开 — 2/2

制作模块承担采样转换和派生数据，graph 提供状态资源绑定、阈值、组及骨骼范围；控制器分为状态选择/进入、循环与动作时钟、混合和姿态修正计划，引用同一已计算的 speed/local_v/local_a。资源选择通过 bindings→asset table 路径，职责可追踪。无需额外实现武器切换或 UE Linked Layer 才满足此项。

证据：[src/build_assets.py:109](candidate/src/build_assets.py#L109) · [src/controller.py:41](candidate/src/controller.py#L41) · [src/controller.py:98](candidate/src/controller.py#L98) · [src/controller.py:239](candidate/src/controller.py#L239) · [src/controller.py:367](candidate/src/controller.py#L367)

## ARC02 移动与上身朝向的分层契约 — 1/2

已明确根平移/actor yaw 由外部 gameplay 拥有，输出链规定全身 root yaw、方向 warp、pelvis/feet stride、限定 spine_01/02/03 的倾斜及 feet IK，引用与顺序有效。但冻结 rubric 要求下肢移动与上身瞄准/方向修正协调；当前脊柱操作仅由 local acceleration 产生 pitch/roll，不是朝向偏差修正。aim 主要驱动原地全身 turn，移动时未输出 aim/yaw 驱动的上身层或等价朝向契约；全身 root yaw 不能代替上下身分工。给已有范围/所有权/组合顺序 1 分。此缺口不同于 WRP01 的方向补偿问题，未因无最终骨骼 pose、无武器或无专用瞄准素材扣分。

证据：[config/animation_graph.json:160](candidate/config/animation_graph.json#L160) · [src/controller.py:299](candidate/src/controller.py#L299) · [src/controller.py:322](candidate/src/controller.py#L322) · [src/controller.py:367](candidate/src/controller.py#L367) · [src/controller.py:396](candidate/src/controller.py#L396) · [src/build_assets.py:102](candidate/src/build_assets.py#L102)

## ARC03 节点生命周期 — 2/2

reset 清空长期状态；每次 _enter 重置 state_age，并给单次动作新 player_id、time=0、travel=0、yaw_applied=0，重新选取资源。每帧 update 与进入处理分开；仍有权重的退出播放器继续淡化，低权重后从 players 移除。循环保留全局共享相位是图中明确的 master-phase 策略，动作进入循环时显式对齐；不把这一刻意保留的组时钟误判为 inactive 动作节点暗中推进。

证据：[src/controller.py:64](candidate/src/controller.py#L64) · [src/controller.py:147](candidate/src/controller.py#L147) · [src/controller.py:303](candidate/src/controller.py#L303) · [src/controller.py:327](candidate/src/controller.py#L327) · [config/animation_graph.json:243](candidate/config/animation_graph.json#L243)

## ARC04 快照与共享派生数据边界 — 2/2

每步先将输入标量/向量验证并复制为本次局部数值，再统一计算速度、角色空间速度/加速度和派生参数供各层使用。配置与资源通过 self.p/nodes/table 只读引用，运行状态由 reset/_enter/step 单独维护，未在每帧访问外部世界或磁盘。本项确认一致快照及数据边界，不宣称多线程性能或 UE Property Access 行为。

证据：[src/controller.py:38](candidate/src/controller.py#L38) · [src/controller.py:64](candidate/src/controller.py#L64) · [src/controller.py:239](candidate/src/controller.py#L239) · [src/controller.py:378](candidate/src/controller.py#L378)

## ARC05 资源与图配置进入实际决策 — 2/2

实际加载节点、参数、资源表和状态 bindings，校验连接/输出属于支持的操作链；资源选择、walk/jog 和方向混合阈值、距离匹配倍率、同步组身份/模式及 pelvis/feet/spine 集合进入计算或计划。它明确只支持声明的固定语义图，而不是任意图解释器；主要配置不是游离说明或只输出节点名字。SYN03 的组级 fallback 实现不足已在对应条目扣分，不在这里重复扣。

证据：[src/controller.py:38](candidate/src/controller.py#L38) · [src/controller.py:98](candidate/src/controller.py#L98) · [src/controller.py:173](candidate/src/controller.py#L173) · [src/controller.py:211](candidate/src/controller.py#L211) · [src/controller.py:352](candidate/src/controller.py#L352) · [src/controller.py:378](candidate/src/controller.py#L378)

## ROB01 输入异常与稳定退化 — 3/3

帧入口在状态更新前验证必填字段、三维数组、类型、bool、非有限数和正dt；对有限极值也声明并执行拒绝边界(dt>3600或向量分量绝对值>1e9)，yaw先规范化，派生水平模长另检查有限性。缺绑定资源/非法图引用在构造时报错，metadata_only有明确None/不可物化与策略计时退化，近零速度路径可追踪。无效曲线的特定反查问题归DST04，不在ROB重复扣分。证据为静态代码，不等同于独立运行验收。

证据：[src/controller.py:38](candidate/src/controller.py#L38) · [src/controller.py:73](candidate/src/controller.py#L73) · [config/animation_graph.json:52](candidate/config/animation_graph.json#L52) · [src/controller.py:239](candidate/src/controller.py#L239) · [src/controller.py:229](candidate/src/controller.py#L229) · [src/controller.py:353](candidate/src/controller.py#L353)

## ROB02 独立复现与提交完整性 — 3/3

保留build_assets(manifest,manifest_dir)、必填manifest/output CLI、LocomotionController/reset/step与约定返回结构；加工数据内嵌资源表，没有依赖输出目录的悬空派生产物路径。reset清理状态、时钟、玩家、权重和冷却；播放器遍历与权重集合排序，未引入随机性，固定输入/配置下可复现。五项交付及说明/保留自查脚本均实质存在。模型自报的跨进程自查不作为本项独立执行证明。

证据：[src/build_assets.py:88](candidate/src/build_assets.py#L88) · [src/build_assets.py:139](candidate/src/build_assets.py#L139) · [src/controller.py:64](candidate/src/controller.py#L64) · [src/controller.py:346](candidate/src/controller.py#L346) · [src/controller.py:394](candidate/src/controller.py#L394) · [IMPLEMENTATION.md:3](candidate/IMPLEMENTATION.md#L3)

## ROB03 证据与限制诚实可审查 — 2/2

说明可定位资源制作、状态与时钟、同步及操作顺序，明确15条ready与22条缺样延期，记录输入/制动/接触估计的假设以及执行计划和最终姿态的边界。自查明确限于软件/data，未伪称UE、脚锁或视觉验收。其他项对实现缺口的扣分不因说明坦诚而免除。

证据：[IMPLEMENTATION.md:30](candidate/IMPLEMENTATION.md#L30) · [IMPLEMENTATION.md:55](candidate/IMPLEMENTATION.md#L55) · [IMPLEMENTATION.md:70](candidate/IMPLEMENTATION.md#L70)

## 门槛

- G01: pass。实际资源加工、控制器与图配置均有实质实现，不是仅文字或空模板。
- G02: pass。有制作逻辑、15段已加工帧/轨迹/曲线，以及22项通用配方延期，不属于资源制作逻辑和数据均缺失。
- G03: pass。有可追踪的状态/过渡、播放器、权重混合及有序姿态操作；局部功能缺口按对应条目评分，不触发整类缺失上限。
