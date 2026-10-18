"use strict";

const DEFAULT_INITIAL = Object.freeze({ health: 100, max_health: 100, damage_immunity: false });
const ACTION_LIMIT = 200;
const deathLabels = { NotDead: "未开始死亡", DeathStarted: "死亡已开始", DeathFinished: "死亡已完成" };
const elements = Object.fromEntries([
  "connectionStatus", "errorBanner", "liveStatus", "healthValue", "maxHealthValue", "healthBar", "healthFill", "healthPercent", "lifeBadge", "immunityValue", "deathValue", "deathCode", "stepCount", "actionControls", "scenarioControls", "resetButton", "amount", "selfDestruct", "immunityToggle", "maxHealth", "combatForm", "maxHealthForm", "startDeathButton", "finishDeathButton", "scenarioSelect", "replayButton", "scenarioDescription", "emptyState", "eventList", "timelineCount"
].map(id => [id, document.getElementById(id)]));

let initial = { ...DEFAULT_INITIAL };
let actions = [];
let currentState = { ...DEFAULT_INITIAL, out_of_health: false, death_state: "NotDead" };
let scenarios = {};
let busy = false;
let connected = false;

function number(value) {
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 4 }).format(value);
}

function setBusy(value) {
  busy = value;
  elements.actionControls.disabled = value;
  elements.scenarioControls.disabled = value || Object.keys(scenarios).length === 0;
  elements.resetButton.disabled = value;
  elements.connectionStatus.textContent = value ? "正在计算" : connected ? "服务已连接" : "连接异常";
  elements.connectionStatus.className = "connection " + (value ? "busy" : connected ? "ready" : "error");
}

function showError(error) {
  elements.errorBanner.textContent = error instanceof Error ? error.message : String(error);
  elements.errorBanner.hidden = false;
}

async function api(path, payload) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(path, {
      method: payload === undefined ? "GET" : "POST",
      headers: payload === undefined ? { Accept: "application/json" } : { Accept: "application/json", "Content-Type": "application/json" },
      body: payload === undefined ? undefined : JSON.stringify(payload),
      signal: controller.signal
    });
    let result;
    try {
      result = await response.json();
    } catch {
      throw new Error(`服务返回了无法读取的内容（HTTP ${response.status}）。请确认 Python 演示服务正在运行。`);
    }
    if (!response.ok) {
      throw new Error(result.error || `请求失败（HTTP ${response.status}）。`);
    }
    return result;
  } catch (error) {
    if (error.name === "AbortError") {
      connected = false;
      throw new Error("请求超时，请检查演示服务连接后重试。当前操作历史未更改。");
    }
    if (error instanceof TypeError) {
      connected = false;
      throw new Error("无法连接演示服务。请检查 Python 服务和代理地址后重试。当前操作历史未更改。");
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

function actionTitle(action) {
  switch (action.type) {
    case "damage": return `造成 ${number(action.amount)} 伤害${action.self_destruct ? " · 自毁伤害标记" : ""}`;
    case "heal": return `恢复 ${number(action.amount)} 生命值`;
    case "set_max_health": return `设置最大生命值为 ${number(action.value)}`;
    case "set_immunity": return action.enabled ? "开启伤害免疫" : "关闭伤害免疫";
    case "start_death": return "开始死亡";
    case "finish_death": return "完成死亡";
    default: return action.type;
  }
}

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function renderState(state) {
  const ratio = Math.min(100, Math.max(0, state.health / state.max_health * 100));
  elements.healthValue.textContent = number(state.health);
  elements.maxHealthValue.textContent = number(state.max_health);
  elements.healthBar.setAttribute("aria-valuemax", state.max_health);
  elements.healthBar.setAttribute("aria-valuenow", state.health);
  elements.healthBar.setAttribute("aria-valuetext", `${number(state.health)} / ${number(state.max_health)} 生命值`);
  elements.healthFill.style.width = `${ratio}%`;
  elements.healthFill.classList.toggle("low", ratio <= 25);
  elements.healthPercent.textContent = `${number(ratio)}%`;
  elements.lifeBadge.textContent = state.out_of_health ? "生命值耗尽" : "生命值大于零";
  elements.lifeBadge.classList.toggle("empty", state.out_of_health);
  elements.immunityValue.textContent = state.damage_immunity ? "开启" : "关闭";
  elements.immunityValue.classList.toggle("active", state.damage_immunity);
  elements.immunityToggle.checked = state.damage_immunity;
  elements.maxHealth.value = state.max_health;
  elements.deathValue.textContent = deathLabels[state.death_state] || state.death_state;
  elements.deathValue.classList.toggle("warning", state.death_state !== "NotDead");
  elements.deathCode.textContent = state.death_state;
  elements.stepCount.textContent = actions.length;
}

function renderSteps(steps) {
  const fragment = document.createDocumentFragment();
  for (const step of steps) {
    const item = node("li", "timeline-step");
    item.append(node("span", "step-index", step.index));
    const heading = node("div", "step-heading");
    heading.append(node("h3", "step-title", actionTitle(step.action)));
    const delta = step.after.health - step.before.health;
    heading.append(node("span", `step-delta ${delta > 0 ? "positive" : delta < 0 ? "negative" : ""}`, `${delta > 0 ? "+" : ""}${number(delta)} HP`));
    item.append(heading);
    item.append(node("p", "step-state", `HP ${number(step.before.health)} / ${number(step.before.max_health)} → ${number(step.after.health)} / ${number(step.after.max_health)}`));
    if (step.before.damage_immunity !== step.after.damage_immunity) {
      item.append(node("p", "step-state", `免疫：${step.before.damage_immunity ? "开启" : "关闭"} → ${step.after.damage_immunity ? "开启" : "关闭"}`));
    }
    if (step.before.death_state !== step.after.death_state) {
      item.append(node("p", "step-state", `死亡阶段：${deathLabels[step.before.death_state]} → ${deathLabels[step.after.death_state]}`));
    }
    if (step.events.length) {
      const messages = node("ul", "event-messages");
      for (const event of step.events) {
        const message = node("li", "", event.message);
        message.append(node("code", "", event.type));
        messages.append(message);
      }
      item.append(messages);
    } else {
      item.append(node("p", "no-event", "未产生额外事件。"));
    }
    fragment.append(item);
  }
  elements.eventList.replaceChildren(fragment);
  elements.emptyState.hidden = steps.length > 0;
  elements.timelineCount.textContent = `${steps.length} 次操作`;
  elements.eventList.scrollTop = elements.eventList.scrollHeight;
}

async function simulate(nextInitial, nextActions, successMessage) {
  if (busy) return;
  if (nextActions.length > ACTION_LIMIT) {
    showError("已达到 200 次操作上限。请先重置实验，或回放一个内置场景后继续。");
    renderState(currentState);
    return;
  }
  elements.errorBanner.hidden = true;
  setBusy(true);
  try {
    const result = await api("api/simulate", { initial: nextInitial, actions: nextActions });
    // Only commit local history after the complete request succeeds.
    initial = { ...nextInitial };
    actions = nextActions.map(action => ({ ...action }));
    currentState = result.state;
    connected = true;
    renderState(currentState);
    renderSteps(result.steps);
    elements.liveStatus.textContent = `${successMessage}。当前生命值 ${number(currentState.health)}，${deathLabels[currentState.death_state]}。`;
  } catch (error) {
    showError(error);
    renderState(currentState);
  } finally {
    setBusy(false);
  }
}

function submitAction(action) {
  return simulate(initial, [...actions, action], actionTitle(action));
}

elements.combatForm.addEventListener("submit", event => {
  event.preventDefault();
  const amount = elements.amount.valueAsNumber;
  if (!Number.isFinite(amount)) {
    showError("请输入有效的伤害或治疗数值。");
    return;
  }
  const type = event.submitter?.value || "damage";
  const action = { type, amount };
  if (type === "damage") action.self_destruct = elements.selfDestruct.checked;
  submitAction(action);
});

elements.maxHealthForm.addEventListener("submit", event => {
  event.preventDefault();
  const value = elements.maxHealth.valueAsNumber;
  if (!Number.isFinite(value)) {
    showError("请输入有效的最大生命值。");
    return;
  }
  submitAction({ type: "set_max_health", value });
});

elements.immunityToggle.addEventListener("change", () => submitAction({ type: "set_immunity", enabled: elements.immunityToggle.checked }));
elements.startDeathButton.addEventListener("click", () => submitAction({ type: "start_death" }));
elements.finishDeathButton.addEventListener("click", () => submitAction({ type: "finish_death" }));
elements.resetButton.addEventListener("click", () => simulate({ ...DEFAULT_INITIAL }, [], "实验已重置"));

function updateScenarioDescription() {
  const selected = scenarios[elements.scenarioSelect.value];
  elements.scenarioDescription.textContent = selected ? `${selected.description}（${selected.actions.length} 次操作）` : "暂无可用场景。";
}

elements.scenarioSelect.addEventListener("change", updateScenarioDescription);
elements.replayButton.addEventListener("click", () => {
  const selected = scenarios[elements.scenarioSelect.value];
  if (selected) simulate({ ...selected.initial }, selected.actions.map(action => ({ ...action })), `已回放：${selected.title}`);
});

async function initialize() {
  setBusy(true);
  const results = await Promise.allSettled([
    api("api/scenarios"),
    api("api/simulate", { initial, actions: [] })
  ]);
  const errors = [];
  if (results[0].status === "fulfilled") {
    scenarios = results[0].value.scenarios;
    elements.scenarioSelect.replaceChildren();
    for (const [id, scenario] of Object.entries(scenarios)) {
      const option = node("option", "", scenario.title);
      option.value = id;
      elements.scenarioSelect.append(option);
    }
    if (scenarios.normal) elements.scenarioSelect.value = "normal";
    updateScenarioDescription();
  } else {
    errors.push(`场景加载失败：${results[0].reason.message}`);
    elements.scenarioSelect.replaceChildren(node("option", "", "场景暂不可用"));
    elements.scenarioDescription.textContent = "仍可手动执行战斗操作；刷新页面可重新加载场景。";
  }
  if (results[1].status === "fulfilled") {
    currentState = results[1].value.state;
    connected = true;
    renderState(currentState);
    renderSteps(results[1].value.steps);
  } else {
    errors.push(results[1].reason.message);
  }
  if (errors.length) showError(errors.join(" "));
  setBusy(false);
}

initialize();
