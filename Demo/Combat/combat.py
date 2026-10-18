"""Independent Python reference model, not an Unreal Engine/GAS runtime.

Rules: Source/LyraGame/AbilitySystem/Attributes/LyraHealthSet.cpp:75-86,
147-182,203-231; Source/LyraGame/Character/LyraHealthComponent.cpp:235-276.
Death transitions are explicit. Healing clears out_of_health, not death_state.
The damage action's self_destruct flag models the HealthSet immunity bypass;
it does not call the component helper that supplies MaxHealth as damage.
Events describe this model; they do not reproduce GAS/replication callbacks.
"""

import math


MAX_ACTIONS = 200
MAX_MAGNITUDE = 1_000_000_000
ACTION_FIELDS = {
    "damage": ({"amount"}, {"self_destruct"}),
    "heal": ({"amount"}, set()),
    "set_max_health": ({"value"}, set()),
    "set_immunity": ({"enabled"}, set()),
    "start_death": (set(), set()),
    "finish_death": (set(), set()),
}


def _fields(value, allowed, location):
    if not isinstance(value, dict):
        raise ValueError(f"{location} 必须是对象")
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"{location} 包含未知字段：{', '.join(sorted(map(str, unknown)))}")


def _number(value, location, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{location} 必须是数字，不能是布尔值")
    if abs(value) > MAX_MAGNITUDE or not math.isfinite(value):
        raise ValueError(f"{location} 必须是绝对值不超过 {MAX_MAGNITUDE} 的有限数字")
    if nonnegative and value < 0:
        raise ValueError(f"{location} 不能为负数")
    return float(value)


def _boolean(value, location):
    if not isinstance(value, bool):
        raise ValueError(f"{location} 必须是布尔值")
    return value


def _validate(payload):
    _fields(payload, {"initial", "actions"}, "请求")
    initial = payload.get("initial", {})
    _fields(initial, {"health", "max_health", "damage_immunity"}, "initial")
    max_health = max(1.0, _number(initial.get("max_health", 100), "initial.max_health"))
    health = min(max_health, _number(initial.get("health", 100), "initial.health", True))
    state = {
        "health": health,
        "max_health": max_health,
        "damage_immunity": _boolean(initial.get("damage_immunity", False), "initial.damage_immunity"),
        "out_of_health": health == 0,
        "death_state": "NotDead",
    }
    if "actions" not in payload or not isinstance(payload["actions"], list):
        raise ValueError("actions 必须是数组，且不能缺省")
    if len(payload["actions"]) > MAX_ACTIONS:
        raise ValueError(f"actions 最多包含 {MAX_ACTIONS} 项")
    actions = []
    for index, action in enumerate(payload["actions"], 1):
        location = f"actions[{index}]"
        if not isinstance(action, dict):
            raise ValueError(f"{location} 必须是对象")
        kind = action.get("type")
        if not isinstance(kind, str) or kind not in ACTION_FIELDS:
            raise ValueError(f"{location}.type 缺失或不支持")
        required, optional = ACTION_FIELDS[kind]
        _fields(action, {"type"} | required | optional, location)
        missing = required - set(action)
        if missing:
            raise ValueError(f"{location} 缺少字段：{', '.join(sorted(missing))}")
        normalized = {"type": kind}
        if kind in ("damage", "heal"):
            normalized["amount"] = _number(action["amount"], f"{location}.amount", True)
        if kind == "damage":
            normalized["self_destruct"] = _boolean(action.get("self_destruct", False), f"{location}.self_destruct")
        if kind == "set_max_health":
            normalized["value"] = _number(action["value"], f"{location}.value")
        if kind == "set_immunity":
            normalized["enabled"] = _boolean(action["enabled"], f"{location}.enabled")
        actions.append(normalized)
    return state, actions


def _apply(state, action):
    events = []

    def emit(kind, message):
        events.append({"type": kind, "message": message})

    before_health = state["health"]
    was_out = state["out_of_health"]
    kind = action["type"]
    if kind == "damage":
        amount = action["amount"]
        if amount > 0 and state["damage_immunity"] and not action["self_destruct"]:
            emit("damage_blocked", f"伤害免疫阻止了 {amount:g} 点普通伤害，生命值保持不变。")
            return events
        if amount > 0:
            detail = "（带自毁标记，可绕过伤害免疫）" if action["self_destruct"] else ""
            emit("damage_message", f"收到 {amount:g} 点伤害{detail}；这是请求伤害量，实际扣血受当前生命值限制。")
        state["health"] = max(0.0, before_health - amount)
    elif kind == "heal":
        state["health"] = min(state["max_health"], before_health + action["amount"])
    elif kind == "set_max_health":
        old_max = state["max_health"]
        state["max_health"] = max(1.0, action["value"])
        state["health"] = min(before_health, state["max_health"])
        emit("max_health_changed", f"请求上限 {action['value']:g}；上限从 {old_max:g} 变为 {state['max_health']:g}，增加上限不会补血。")
    elif kind == "set_immunity":
        state["damage_immunity"] = action["enabled"]
        emit("immunity_set", "已开启伤害免疫。" if action["enabled"] else "已关闭伤害免疫。")
    elif kind == "start_death":
        if state["death_state"] == "NotDead":
            state["death_state"] = "DeathStarted"
            emit("death_started", "显式开始死亡：NotDead → DeathStarted。")
        else:
            emit("no_op", "开始死亡被忽略：当前状态已经不是 NotDead。")
    elif kind == "finish_death":
        if state["death_state"] == "DeathStarted":
            state["death_state"] = "DeathFinished"
            emit("death_finished", "显式结束死亡：DeathStarted → DeathFinished。")
        else:
            emit("no_op", "结束死亡被忽略：当前状态不是 DeathStarted。")
    if state["health"] != before_health:
        emit("health_changed", f"生命值从 {before_health:g} 变为 {state['health']:g}；死亡状态保持 {state['death_state']}。")
    state["out_of_health"] = state["health"] == 0
    if state["out_of_health"] and not was_out:
        emit("out_of_health", "生命值首次降至零；本演示需显式调用 start_death，不自动启动死亡能力。")
    if not events:
        emit("no_op", "本次操作未改变生命值，未产生生命值变化事件。")
    return events


def simulate(payload):
    """Validate the entire request, then return independent snapshots and events."""
    state, actions = _validate(payload)
    initial = state.copy()
    steps = []
    for index, action in enumerate(actions, 1):
        before = state.copy()
        events = _apply(state, action)
        steps.append({"index": index, "action": action, "before": before,
                      "after": state.copy(), "events": events})
    return {"initial": initial, "state": state.copy(), "steps": steps}
