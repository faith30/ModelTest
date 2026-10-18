# 生命值与战斗逻辑 demo

基于 Lyra 生命值属性和死亡阶段规则的独立 Python 参考样例，支持命令行、JSON API 和交互网页。只需要 **Python 3.9+**，无需 pip、Node、GPU、UE 引擎或 Content 资源。

这是单角色、单进程的规则演示，不运行 Unreal C++，也不验证 GAS、网络复制、预测、动画、销毁或重生。

## 运行

在仓库根目录执行；Windows 将 `python3` 换为 `python`。

```bash
python3 Demo/Combat/demo.py list
python3 Demo/Combat/demo.py scenario --name normal
python3 Demo/Combat/demo.py scenario --name lethal --json
python3 -m unittest discover -s Demo/Combat/tests -v
python3 Demo/Combat/demo.py serve --port 8000
```

本机访问 `http://127.0.0.1:8000/`。远程容器使用 code-server 的端口转发/代理打开 8000 端口，保留地址末尾的 `/`；页面资源与 API 使用相对路径。服务默认监听容器内的 `127.0.0.1`。仅在平台明确需要容器网卡监听时添加 `--host 0.0.0.0`，并使用平台提供的访问控制。

Ctrl+C 停止服务。服务不写数据库或会话；每次请求重新执行给定的初始状态与动作序列，不同页面之间不会共享角色状态。网页“重置”只清空当前样例历史，不代表 Lyra 复活能力。

## 可演示的规则

| 操作 | 行为 |
| --- | --- |
| 伤害 / 治疗 | 改变生命值并限制在 `[0, MaxHealth]` |
| 伤害免疫 | 拒绝普通正数伤害 |
| 自毁伤害标记 | 此次伤害绕过免疫；仍使用输入的伤害量，不自动击杀 |
| 设置生命值上限 | 上限至少为 1；降低上限会压低超限生命值，提高上限不会补血 |
| 生命值归零 | 进入零血时发出一次事件；继续受伤不重复，治疗后再次归零可再次发出 |
| 开始 / 完成死亡 | 显式推进 `NotDead → DeathStarted → DeathFinished`；重复或乱序调用不推进 |

**生命值与死亡阶段独立。** 治疗可以从零恢复生命值，但不会将死亡阶段重置为 NotDead。demo 显式提供开始/完成死亡按钮，省略了 UE 中 `GameplayEvent.Death → Death GA` 的自动调用链。

源码依据：

- [LyraHealthSet.cpp](../../Source/LyraGame/AbilitySystem/Attributes/LyraHealthSet.cpp)：默认生命值、伤害免疫、自毁标签、伤害/治疗、属性限制和零血事件。
- [LyraHealthComponent.cpp](../../Source/LyraGame/Character/LyraHealthComponent.cpp)：StartDeath / FinishDeath 的状态限制。
- [LyraGameplayAbility_Death.cpp](../../Source/LyraGame/AbilitySystem/Abilities/LyraGameplayAbility_Death.cpp)：原工程的自动开始死亡与结束死亡调用链。

稀疏克隆只下载 demo 时，可在 GitHub 仓库浏览完整 Source。

输入伤害代表已经结算的伤害值，不包含武器、团队、距离、材质或护甲结算。开发作弊开关和完整 GameplayTag 层级不在此样例范围内。

## JSON API 与自定义场景

- `GET api/health`：服务状态，包含 `ue_runtime: false`。
- `GET api/scenarios`：内置场景及动作数据。
- `POST api/simulate`：重放请求，返回 `initial`、最终 `state` 和包含 before/after/events 的 `steps`。

```json
{
  "initial": {"health": 100, "max_health": 100, "damage_immunity": false},
  "actions": [
    {"type": "damage", "amount": 30},
    {"type": "heal", "amount": 20},
    {"type": "set_immunity", "enabled": true},
    {"type": "damage", "amount": 150, "self_destruct": true},
    {"type": "start_death"},
    {"type": "finish_death"}
  ]
}
```

将请求保存为 `scenario.json` 后执行：

```bash
python3 Demo/Combat/demo.py scenario --file scenario.json --json
curl -sS -H 'Content-Type: application/json' --data-binary @scenario.json http://127.0.0.1:8000/api/simulate
```

输入约束是 demo 自身的 API 约定：最多 200 个动作，HTTP 请求不超过 64 KiB，数字必须有限且绝对值不超过 10 亿；拒绝布尔值冒充数字、负伤害/负治疗及未知字段。非法请求返回 JSON 错误，不修改任何服务器会话。CLI 非法输入返回非零退出码。

Git 同步与目标容器记录见 [Linux 部署说明](../../Docs/LinuxDemo.md)。
