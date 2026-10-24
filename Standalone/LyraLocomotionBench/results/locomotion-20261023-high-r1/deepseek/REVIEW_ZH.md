# deepseek：40项静态审查

得分 **46.5 / 100**；扣分 53.5。40项与3个门槛均已审查。

证据仅来自冻结代码、图和资源数据。没有执行候选或UE；输出计划不代表最终动画姿态。

候选目录SHA256：`b00081836bc60711cc1899ee31704637d82e3a655b0e93fe2914d58c738f24c6`。

## RES01 原始输入、派生资源与来源可追溯 — 2/2

原始 raw 与 assets/processed 分开；输出有 schema_version，逐项关联 source_clip_ids，实际坐标转换参数写入 recipe，派生反转资源记录来源和具体操作并明确非原始 take。未将生成结果冒称本地 Lyra 已核验配置。CLI 自定义输出目录的引用根问题由 ROB02 处理，本项不重复扣分。

证据：[src/build_assets.py:201](candidate/src/build_assets.py#L201) · [src/build_assets.py:217](candidate/src/build_assets.py#L217) · [src/build_assets.py:295](candidate/src/build_assets.py#L295) · [src/build_assets.py:319](candidate/src/build_assets.py#L319)

## RES02 骨架、单位和坐标系一致 — 2/3

位置映射 [sy,-sx,sz]、cm/component/xyzw 与精简骨骼约束有实现，world/local 速度也使用 actor yaw。但 TIP 使用 aim_yaw-actor_yaw 的正差直接选择 motion_33/Left90，并把该资源弧度标为 +90；输入契约中左转是解剖角度为正、actor yaw 为负，实际 Left90 root 四元数也向负 yaw 旋转。这是 anatomical_turn_degrees 与 actor yaw 符号混用。只在本项扣符号根因，其他转身/warp 项勿重扣。

证据：[src/build_assets.py:117](candidate/src/build_assets.py#L117) · [src/controller.py:181](candidate/src/controller.py#L181) · [src/controller.py:261](candidate/src/controller.py#L261) · [src/controller.py:595](candidate/src/controller.py#L595) · [assets/authored_assets.json:1338](candidate/assets/authored_assets.json#L1338)

## RES03 走跑与方向资源覆盖 — 3/3

代码/资源表覆盖两种步态四方向 cycle/start/stop/pivot 及转身，15 条有样本输入生成实际转换后的帧文件；22 条 metadata_only 使用通用 recipe+延期，data=null。另以实际样本时间反转生成两种转身并明确替代性质，Idle 使用 stop 末帧保持。缺输入不扣分；正确的时间/方向消费问题分别归专属项。

证据：[src/controller.py:221](candidate/src/controller.py#L221) · [src/build_assets.py:180](candidate/src/build_assets.py#L180) · [src/build_assets.py:238](candidate/src/build_assets.py#L238) · [src/build_assets.py:255](candidate/src/build_assets.py#L255) · [IMPLEMENTATION.md:35](candidate/IMPLEMENTATION.md#L35) · [IMPLEMENTATION.md:51](candidate/IMPLEMENTATION.md#L51)

## RES04 片段时域、循环与边界 — 2/2

已采样资源保留源时间戳，duration 来自首尾差，cycle 标记 loop/range；_advance 用 dt*rate，循环 fmod(duration)、非循环到时长后 clamp，没有 duration+一帧的错误。metadata_only 为 null 产物且调用处走 ready/fallback，不以辅助 _duration 返回 0 冒充可播放资产。无效采样数据校验问题专计 RES08。

证据：[src/build_assets.py:76](candidate/src/build_assets.py#L76) · [src/build_assets.py:95](candidate/src/build_assets.py#L95) · [src/build_assets.py:199](candidate/src/build_assets.py#L199) · [src/build_assets.py:238](candidate/src/build_assets.py#L238) · [src/controller.py:281](candidate/src/controller.py#L281) · [src/controller.py:473](candidate/src/controller.py#L473)

## RES05 根轨迹数据与角色位移职责 — 2/3

转换后的全帧保留 root 轨迹，附端点/位移指标，并有 extract_root_delta_world 计划和不要二次应用源位移的说明。缺口是产品仍保留完整移动 root，而计划只写 apply world delta after pose，没有约定抽取后去除 pose 中的 root，也没有明确由输入速度驱动的角色运动与该 world delta 谁拥有最终位移。这是接口职责未闭合，静态上不能断言实际已发生双重移动；扣的是该契约缺失，坐标/角度符号不在本项重复扣。

证据：[src/build_assets.py:95](candidate/src/build_assets.py#L95) · [src/build_assets.py:201](candidate/src/build_assets.py#L201) · [src/build_assets.py:125](candidate/src/build_assets.py#L125) · [src/controller.py:326](candidate/src/controller.py#L326) · [IMPLEMENTATION.md:27](candidate/IMPLEMENTATION.md#L27) · [IMPLEMENTATION.md:57](candidate/IMPLEMENTATION.md#L57)

## RES06 同步相位标记的制作 — 0/3

检查完整 builder、实际资源表和同步计划，只有坐标转换/时长速度指标，没有从现有脚部采样生成 L/R 相位标记的逻辑、实际 marker 表或明确的替代相位配方。同步输出明确 independent 并称 no authored footstep/notify markers。原始输入未附 marker 不妨碍从15段已有采样制作；本项不因为22条 metadata_only 缺采样扣分。

证据：[src/build_assets.py:194](candidate/src/build_assets.py#L194) · [src/controller.py:311](candidate/src/controller.py#L311) · [IMPLEMENTATION.md:29](candidate/IMPLEMENTATION.md#L29) · [IMPLEMENTATION.md:69](candidate/IMPLEMENTATION.md#L69)

## RES07 曲线制作及可索引表示 — 0/2

资源加工只计算根首尾位移/平均速度并写转换后的姿态，没有按样本生成距离曲线、停止参考点/轴定义或可供 time-index/distance-inverse 使用的数据接口；完整 builder/controller 未发现相应曲线读取或反查实现。这里判定的是可用采样的曲线制作交付缺失，不是要求 UE 压缩资产，也不为 metadata_only 罚分。

证据：[src/build_assets.py:76](candidate/src/build_assets.py#L76) · [src/build_assets.py:194](candidate/src/build_assets.py#L194) · [src/build_assets.py:230](candidate/src/build_assets.py#L230) · [src/controller.py:458](candidate/src/controller.py#L458)

## RES08 资源制作流程闭合 — 1/2

具有真实构建入口、确定性坐标转换和写文件，manifest 指向的姿态文件不存在会明确报错，JSON 输出拒绝 NaN。缺口是缺少骨骼层级/帧数组一致性及时间合法性验证，骨架仅取首次有值的文件；duration=max(last-first,0) 把非正时间范围静默转成 0，仍建立 ready 资源，不能把非法素材定位为失败。自定义 --output 的相对引用缺陷由 ROB02 处理，本项不扣它；距离曲线类别缺失也不在此再扣。

证据：[src/build_assets.py:76](candidate/src/build_assets.py#L76) · [src/build_assets.py:108](candidate/src/build_assets.py#L108) · [src/build_assets.py:180](candidate/src/build_assets.py#L180) · [src/build_assets.py:217](candidate/src/build_assets.py#L217)

## LOC01 移动快照与派生量 — 3/3

同一frame校验并读取给定字段，以actor yaw将世界速度转局部，使用水平速度和上帧速度差/dt推导观察减速；没有把零加速度解释为松键，也未读取虚构输入。原acceleration字段未直接使用，但该项接受明确的速度差推导。Pivot使用aim差的独立行为错误仅在LOC06扣分。

证据：[src/controller.py:172](candidate/src/controller.py#L172) · [src/controller.py:379](candidate/src/controller.py#L379) · [src/controller.py:595](candidate/src/controller.py#L595)

## LOC02 Walk/Jog选择与阈值稳定 — 2/2

配置明确walk/jog低高阈值，之间线性混合两套Cycle，分别按实测平均速度计算播放倍率。连续权重足以满足本项平滑策略，不强制必须使用上下阈值滞回。

证据：[src/controller.py:195](candidate/src/controller.py#L195) · [src/controller.py:491](candidate/src/controller.py#L491) · [config/animation_graph.json:24](candidate/config/animation_graph.json#L24)

## LOC03 四方向与斜向选择 — 2/3

局部轴转换、四向覆盖、低速保留方向均实现；但方向直接按abs(lx)>=abs(ly)切换，扇区边界没有滞回/角度平滑。虽计算smoothed_velocity，方向已由原速度选完且未消费该平滑值，因此45度边界轻微摆动会切换资源。扣1分；未将缺斜向Orientation Warp在此重复扣，归WRP01。

证据：[src/controller.py:181](candidate/src/controller.py#L181) · [src/controller.py:598](candidate/src/controller.py#L598)

## LOC04 Idle到Start到Cycle — 1.5/3

Idle->Start->Cycle首轮路径、方向Start选择和缺样本Cycle回退存在；但sample_times按asset保存，仅全局reset时清空，Stop->Start等状态重入没有重置片段时间，结束过的Start再次进入会立即到Cycle。mode_elapsed也仅全局初始化并持续累加，延期Start的权重斜坡不能按每次进入重新开始。作为同一状态进入生命周期根因扣1.5分，请ARC03不要重复扣。

证据：[src/controller.py:120](candidate/src/controller.py#L120) · [src/controller.py:281](candidate/src/controller.py#L281) · [src/controller.py:415](candidate/src/controller.py#L415) · [src/controller.py:467](candidate/src/controller.py#L467) · [src/controller.py:650](candidate/src/controller.py#L650)

## LOC05 减速、Stop与Idle — 1.5/3

利用观察减速触发Stop，低速回Idle，并能对无样本Stop使用对应Cycle回退；但ready Stop到片段末尾直接设置mode=idle，不再要求实际速度达到stop_done。在速度仍非零时可进入静止姿态，下一帧又因速度重启Start。独立结束条件缺陷扣1.5分；没有重复因距离匹配未实现或重入时钟问题扣分。

证据：[src/controller.py:403](candidate/src/controller.py#L403) · [src/controller.py:518](candidate/src/controller.py#L518)

## LOC06 Pivot及重新起步 — 1/2

Stop期间根据速度增加重启Start，Pivot有独立资源选择和状态；但Pivot触发是abs(aim_yaw-actor_yaw)>阈值而非移动反向，维持同向速度只改变瞄准即可触发，真实速度反向且aim不变则不触发。没有保留所要求的运动方向反转语义，扣1分；不再因unused acceleration单独扣LOC01。

证据：[src/controller.py:418](candidate/src/controller.py#L418) · [src/controller.py:542](candidate/src/controller.py#L542) · [src/controller.py:595](candidate/src/controller.py#L595)

## LOC07 过渡竞争与连续性 — 1/2

if/return结构给出确定的状态条件优先级，每帧只输出当前模式；但状态切换没有保存旧播放器及交叉淡出，ready Start/Stop/Pivot直接以weight=1输出，跨状态为硬切。扣1分；未重复因LOC03角度防抖或LOC04进入计时根因扣分。

证据：[src/controller.py:395](candidate/src/controller.py#L395) · [src/controller.py:473](candidate/src/controller.py#L473) · [src/controller.py:615](candidate/src/controller.py#L615)

## SYN01 组作用域与角色配置 — 1/3

图有locomotion/turn/idle分组及成员列表，已形成部分作用域配置。但sync_group_defs只保存未用于消费；_sync_groups_for不管当前动作一律输出locomotion/independent，实际组引用与配置中的turn/idle不一致，没有角色关联。该项只扣组配置与消费不一致，不以缺marker资源代替同步算法判断。

证据：[config/animation_graph.json:460](candidate/config/animation_graph.json#L460) · [src/controller.py:78](candidate/src/controller.py#L78) · [src/controller.py:311](candidate/src/controller.py#L311) · [src/controller.py:630](candidate/src/controller.py#L630)

## SYN02 Marker相位不是Notify — 0/3

检查控制器、图及实现说明后，未发现前后marker区间、相对进度映射或可审查的等价同步计划。walk/jog混合时分别按各自速度推进时钟；independent说明不是marker同步算法。这里扣缺通用同步逻辑，即使资源随后补充marker仍不会被消费；不重复扣资源制作不足。Notify所属者问题由SYN04承担。

证据：[src/controller.py:311](candidate/src/controller.py#L311) · [src/controller.py:507](candidate/src/controller.py#L507)

## SYN03 公共标记与退化策略 — 0/3

没有公共marker求交/一致性验证，也没有缺标记时统一长度相位同步或显式拒绝报告的分支。独立时钟不构成长度同步，尤其walk/jog各自按自身平均速度求rate。本项缺的是不兼容/缺标记的退化策略，和SYN02缺主同步计算是两个独立要求。

证据：[src/controller.py:281](candidate/src/controller.py#L281) · [src/controller.py:311](candidate/src/controller.py#L311) · [src/controller.py:507](candidate/src/controller.py#L507)

## SYN04 Leader选择与事件归属 — 0/2

没有由权重/角色确定leader的计算或计划，sync_groups只有成员和independent说明；也没有Notify归属、follower抑制及平局规则。混合权重用于player输出，未进入leader选择。

证据：[src/controller.py:311](candidate/src/controller.py#L311) · [src/controller.py:507](candidate/src/controller.py#L507) · [src/controller.py:630](candidate/src/controller.py#L630)

## SYN05 非循环起停与距离匹配的同步策略 — 1/3

起停按非循环时钟独立推进，实际未被任何follower强制覆盖，提供了基本时间所有权。但没有从起停接触或相位到cycle的接管连续性规则，start结束直接切mode，cycle继续各自时钟。此处只扣同步接管策略缺失；距离曲线/反查缺失由相应DST/LOC项目承担，起停重入未重置也由LOC04承担。

证据：[src/controller.py:467](candidate/src/controller.py#L467) · [src/controller.py:491](candidate/src/controller.py#L491) · [src/controller.py:518](candidate/src/controller.py#L518)

## SYN06 接管、跨尾与事件唯一性 — 0.5/2

时钟对loop执行fmod，并处理负余数，对普通跨尾有确定的采样时间。没有同步接管状态、未保留跨圈数/前后marker序列，也没有跨多个事件的端点或去重计划。因此仅给基本跨尾时间处理分；不在此重复扣起停重入时钟未清空的LOC04缺陷。

证据：[src/controller.py:281](candidate/src/controller.py#L281) · [src/controller.py:311](candidate/src/controller.py#L311) · [src/controller.py:507](candidate/src/controller.py#L507)

## DST01 距离曲线含义与符号 — 0/2

没有累计路程/剩余目标/有符号 pivot 距离的定义及生产消费协议。现有 horizontal_displacement_cm 是全段首尾位移，average_speed_cm_s 只供 cycle 倍率使用，不能替代三类距离语义。本项是运行消费契约缺失；资源曲线制作缺失另归 RES07，没有追加统一惩罚。

证据：[src/build_assets.py:76](candidate/src/build_assets.py#L76) · [src/controller.py:458](candidate/src/controller.py#L458) · [src/controller.py:473](candidate/src/controller.py#L473) · [src/controller.py:524](candidate/src/controller.py#L524) · [src/controller.py:555](candidate/src/controller.py#L555)

## DST02 按位移推进与按目标定位分开 — 0/3

有样本 start/stop/pivot 都调用同一个 _advance(dt,1.0)，既没有按本帧 speed*dt 推进，也没有按目标距离定位；不是把累计值用错，而是这两条距离消费路径未实现。该判定来自实际 ready 资源分支，不涉及缺采样回退。

证据：[src/controller.py:281](candidate/src/controller.py#L281) · [src/controller.py:473](candidate/src/controller.py#L473) · [src/controller.py:524](candidate/src/controller.py#L524) · [src/controller.py:555](candidate/src/controller.py#L555)

## DST03 停止/转向目标来源 — 0/3

没有从速度、加速度或声明的制动模型得到 stop/pivot 目标距离。dv_dt 仅用作状态阈值，输入 acceleration 被接收后未使用；pivot 用固定 pivot_seconds 结束，stop 按时间播放。已有状态判断不能替代停步/反向目标预测；不要求额外的碰撞、摩擦、actor 位置输入。

证据：[src/controller.py:391](candidate/src/controller.py#L391) · [src/controller.py:426](candidate/src/controller.py#L426) · [src/controller.py:518](candidate/src/controller.py#L518) · [src/controller.py:555](candidate/src/controller.py#L555) · [src/controller.py:595](candidate/src/controller.py#L595)

## DST04 曲线反查的确定性和边界 — 0/3

完整控制器没有距离曲线查找/插值/反查函数，也没有平台、非单调、无效曲线或 pivot 距离分段策略。_advance 仅实现时钟的取模/时长上限，并不满足距离反查边界项；因此是消费者算法类别缺失，不能因已有普通时钟 clamp 给本项分。

证据：[src/controller.py:281](candidate/src/controller.py#L281) · [src/controller.py:473](candidate/src/controller.py#L473) · [src/controller.py:524](candidate/src/controller.py#L524) · [src/controller.py:555](candidate/src/controller.py#L555)

## DST05 播放速率限制与步幅补偿 — 1/3

cycle 有实测平均速度匹配 speed/avg 并用图内 min/max clamp，且没有对同一速度重复补偿，给予该部分分数。没有距离驱动的有效倍率限制，也没有 clamp 后的剩余位移/stride 方案或明确允许滑动的取舍；已有 start/stop/pivot 恒定1倍不属于距离匹配限幅。此项仅评价倍率/残差组合，不追加曲线缺失罚分。

证据：[src/controller.py:458](candidate/src/controller.py#L458) · [src/controller.py:491](candidate/src/controller.py#L491) · [src/controller.py:326](candidate/src/controller.py#L326) · [IMPLEMENTATION.md:50](candidate/IMPLEMENTATION.md#L50)

## DST06 Evaluator推进、跳转与副作用 — 1/2

控制器自行按 dt*rate 推进并输出权威 sample_time，循环/非循环边界可定位，root 操作也声明为计划而非 UE 执行。缺口是只有每资产 sample_times，没有对初次定位、重新进入或链式转身的 seek/advance 区间与 Notify/root-delta 的副作用规则；no authored footstep/notify markers 只说明数据缺失，未定义跳转时的消费语义。允许简化计划，不要求事件引擎；root 位移所有权缺口只计 RES05。

证据：[src/controller.py:120](candidate/src/controller.py#L120) · [src/controller.py:281](candidate/src/controller.py#L281) · [src/controller.py:563](candidate/src/controller.py#L563) · [src/controller.py:326](candidate/src/controller.py#L326) · [IMPLEMENTATION.md:57](candidate/IMPLEMENTATION.md#L57) · [IMPLEMENTATION.md:64](candidate/IMPLEMENTATION.md#L64)

## WRP01 Orientation Warping的朝向分工 — 0/3

最终姿态操作仅有root提取、上身aim_yaw_offset及hold；没有所选动画运动方向与实际局部移动方向差的下身Orientation Warping参数或等价计划。仅选择四向和上身瞄准不能替代该功能。按缺失记0；未重复扣RES02转身符号问题。

证据：[src/controller.py:326](candidate/src/controller.py#L326) · [config/animation_graph.json:491](candidate/config/animation_graph.json#L491)

## WRP02 Stride Warping的比例与限制 — 0/3

有基于speed/average_speed的播放倍率调整和clamp，但没有步幅比例、空间补偿操作或等价姿态计划；rate达到限制后的差异也未传给stride。此项功能缺失记0，不要求真实骨骼求解。

证据：[src/controller.py:458](candidate/src/controller.py#L458) · [src/controller.py:326](candidate/src/controller.py#L326)

## WRP03 骨骼约束与姿态补偿契约 — 2/2

已有姿态操作按root提取/上身aim/hold顺序输出，player引用明确，spine/neck/head目标属于给定26骨子集，文档承认component-space子集和执行意图边界；满足本项计划/骨骼范围契约。Orientation/Stride功能本身缺失已经在WRP01/02记分，不在此重复扣，也不要求实际IK。

证据：[src/controller.py:326](candidate/src/controller.py#L326) · [IMPLEMENTATION.md:57](candidate/IMPLEMENTATION.md#L57) · [IMPLEMENTATION.md:66](candidate/IMPLEMENTATION.md#L66)

## WRP04 RootYawOffset三类状态策略 — 0/3

reset及输出操作没有RootYawOffset状态，Idle抵消actor yaw、Start Hold、Cycle BlendOut均未实现；aim-actor yaw差只用于上身瞄准/TIP触发，不等同于这三类根yaw策略。按独立功能缺失记0。

证据：[src/controller.py:120](candidate/src/controller.py#L120) · [src/controller.py:326](candidate/src/controller.py#L326) · [src/controller.py:595](candidate/src/controller.py#L595)

## WRP05 Turn In Place与转向曲线 — 0.5/1

静止时有角度阈值、90/180资源选择与回退，能推进转身片段；但remaining只在采样到片段末尾后减去固定arc，没有按源turn曲线/相邻根旋转逐帧消耗offset，亦未给出持续的受限替代消耗计划。扣0.5分；本项没有因左/右符号错误重复扣RES02。

证据：[src/controller.py:403](candidate/src/controller.py#L403) · [src/controller.py:261](candidate/src/controller.py#L261) · [src/controller.py:570](candidate/src/controller.py#L570)

## ARC01 状态逻辑、资源集与修正职责分开 — 2/2

资产索引/参数加载、局部方向与gait派生、_update_mode高层状态、各动作plan、_pose_operations根与上身修正分别承担职责；step复用同一speed/direction/aim_delta。具体未实现的warp能力归WRP条目，本项只确认组织边界。

证据：[src/controller.py:62](candidate/src/controller.py#L62) · [src/controller.py:379](candidate/src/controller.py#L379) · [src/controller.py:595](candidate/src/controller.py#L595) · [src/controller.py:630](candidate/src/controller.py#L630)

## ARC02 移动与上身朝向的分层契约 — 2/2

输出将root delta提取/转换与上身aim_yaw_offset分为独立操作，顺序明确；上身使用具体spine/neck/head范围和actor_local角度，根平移采用一次世界转换后应用的契约。引用当前有效player并将idle冻结单独表达，满足允许的计划层组合，不宣称已渲染pose。

证据：[src/controller.py:326](candidate/src/controller.py#L326) · [src/controller.py:363](candidate/src/controller.py#L363) · [src/controller.py:630](candidate/src/controller.py#L630)

## ARC03 节点生命周期 — 2/2

reset集中初始化持久状态，step只调用当前mode的plan，inactive动作不会每帧推进；turn/pivot有进入时创建或重置相关状态。已确认start/stop再次进入不清sample_times的缺陷，按统一单根因归属由LOC04扣分，本项不重复扣；本项给分不表示该重入缺陷已解决。

证据：[src/controller.py:120](candidate/src/controller.py#L120) · [src/controller.py:409](candidate/src/controller.py#L409) · [src/controller.py:426](candidate/src/controller.py#L426) · [src/controller.py:615](candidate/src/controller.py#L615)

## ARC04 快照与共享派生数据边界 — 2/2

frame校验后复制速度/加速度并得到标量输入，step统一计算speed、aim_delta、direction和gait。运行时mode/sample_times/history与配置/资产索引分开；输出各计划消费同一组本帧派生值。无逐层外部读取或多线程性能已验证之主张。

证据：[src/controller.py:59](candidate/src/controller.py#L59) · [src/controller.py:120](candidate/src/controller.py#L120) · [src/controller.py:172](candidate/src/controller.py#L172) · [src/controller.py:595](candidate/src/controller.py#L595)

## ARC05 资源与图配置进入实际决策 — 1/2

真实消费资产duration/average_speed以及图的speed_thresholds/playback，能追踪到时钟及状态决策。但图的state_machine只有名字清单，player配置大多未驱动动作选择；output_config读取后未使用，实际pose操作顺序固定写在方法中，修改交付图的组合顺序不会进入计划。此处扣图组合/节点配置和实际决策脱节，sync_group_defs未消费已在SYN01扣，不重复计入。

证据：[src/controller.py:72](candidate/src/controller.py#L72) · [src/controller.py:94](candidate/src/controller.py#L94) · [src/controller.py:379](candidate/src/controller.py#L379) · [config/animation_graph.json:68](candidate/config/animation_graph.json#L68) · [config/animation_graph.json:491](candidate/config/animation_graph.json#L491) · [src/controller.py:326](candidate/src/controller.py#L326)

## ROB01 输入异常与稳定退化 — 2/3

有必填项、正dt、常规非有限数检查，近零速度与延期资源有明确回退。独立入口缺口：_finite对非数值最终返回True，速度分量字符串"nan"或"inf"先通过检查再float转换为非有限值，step未二次校验且直接输出speed；极大有限向量也无派生有限性保障。扣1，不重复扣曲线、状态或资源加工项。反例为静态推导。

证据：[src/controller.py:46](candidate/src/controller.py#L46) · [src/controller.py:157](candidate/src/controller.py#L157) · [src/controller.py:595](candidate/src/controller.py#L595) · [src/controller.py:634](candidate/src/controller.py#L634)

## ROB02 独立复现与提交完整性 — 2.5/3

CLI、LocomotionController/reset/step、五项交付及输出结构实质存在，reset清理状态且无随机依赖。缺口：加工产物固定写到manifest_dir/../assets/processed，而--output可指向任意目录；资源表里的processed相对引用在换输出目录时失效，违反产物路径相对生成资源表的接口。按接口可复现性扣0.5，RES01/08不重复扣此根因。

证据：[src/build_assets.py:108](candidate/src/build_assets.py#L108) · [src/build_assets.py:158](candidate/src/build_assets.py#L158) · [src/build_assets.py:329](candidate/src/build_assets.py#L329) · [src/controller.py:120](candidate/src/controller.py#L120) · [src/controller.py:634](candidate/src/controller.py#L634)

## ROB03 证据与限制诚实可审查 — 2/2

实现说明明确列出制作入口、关键假设、22条缺样本延期、派生替代以及静态计划与最终姿态的边界；关键设计可在代码中定位。未伪称UE/姿态验证。说明诚实不免除其他实现项的缺陷扣分。

证据：[IMPLEMENTATION.md:66](candidate/IMPLEMENTATION.md#L66) · [src/controller.py:1](candidate/src/controller.py#L1)

## 门槛

- G01: pass。资源加工和控制器均有实质Python实现，不是仅文字/模板壳；功能缺口按条目评分。
- G02: pass。有实际资源制作逻辑和已生成的派生资源表、产物；曲线/marker缺口不能机械视为整个资源类别均缺失。
- G03: pass。控制器包含可辨认的状态/转移、播放器和组合计划，并消费图参数/资源。图消费不足按ARC项处理，未达到完全无有效动画流程的门槛。
