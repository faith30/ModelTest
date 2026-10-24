"""Render the frozen machine-readable rubric for a human reviewer."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = {
    "asset_authoring": "资源制作",
    "locomotion_states": "状态与方向",
    "synchronization": "同步组与相位",
    "distance_matching": "距离匹配",
    "warping_and_yaw": "方向、步幅与根旋转",
    "architecture_and_lifecycle": "分层与生命周期",
    "robustness_and_reproducibility": "稳定性与复现",
}


def main():
    rubric = json.loads((ROOT / "evaluator/rubric.json").read_text("utf-8"))
    items = rubric["items"]
    assert len(items) == 40 and sum(x["weight"] for x in items) == 100
    assert len({x["id"] for x in items}) == len(items)
    assert {x["category"] for x in items} == set(CATEGORIES)
    assert all(source in rubric["sources"] for item in items for source in item["source_ids"])
    lines = ["# Lyra 动画开发：40项细节扣分清单", "", "裁判专用。检查资源、配置和代码之间的对应关系；不用 UE，不以术语出现次数评分。", "",
             "完整完成得该项满分；实质部分完成得部分分；缺失或错误得0分。未审查不算0分，最终总分保持空值。", "",
             "| 类别 | 项数 | 分值 |", "|---|---:|---:|"]
    for key, title in CATEGORIES.items():
        group = [x for x in items if x["category"] == key]
        lines.append(f"| {title} | {len(group)} | {sum(x['weight'] for x in group)} |")
    for key, title in CATEGORIES.items():
        lines.extend(["", "## " + title, ""])
        for item in (x for x in items if x["category"] == key):
            lines.extend([f"### {item['id']} · {item['title']}（{item['weight']}分）", "", item["check"], "",
                          "应查证据：" + "；".join(item["evidence_required"]) + "。", ""])
    lines.extend(["## 判分边界", "", "22条只有元数据的素材允许通用配方与 deferred_missing_samples，不因输入缺失扣模型分。语义等价实现可以通过；不要求照抄 Lyra 名称或绝对打点。", "",
                  "分项完成审查后再检查交付门槛；仅文字最高30分，整体缺资源制作或有效动画图最高60分。门槛只取最低上限，不叠加扣分。精确触发条件以 rubric.json 为准。", "",
                  "同一缺陷在直接所属项扣分；其他项须有独立失败证据。静态得分不等于运行时正确、低滑步或美术质量。", "", "## 一手资料", ""])
    for source in rubric["sources"].values():
        if source.get("url"):
            lines.append(f"- [{source['title']}]({source['url']})")
    destination = ROOT / "evaluator/DETAIL_CHECKLIST_ZH.md"
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(destination), "items": len(items), "points": 100}))


if __name__ == "__main__":
    main()
