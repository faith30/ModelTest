# 已发布结果与复核

这里保留三路最终候选、40 项静态评审和评分结果。先读[最终三路对比](locomotion-20261023-gpt6-high-r1/REPORT_ZH.md)；先前的 [Opus / DeepSeek 两路报告](locomotion-20261023-high-r1/REPORT_ZH.md)作为独立历史记录保留。

| 实际模型 | 分数 | 报告与原始文件 |
|---|---:|---|
| `gpt-6-astra` | 87.5/100 | [评审](locomotion-20261023-gpt6-high-r1/gpt6/REVIEW_ZH.md) · [候选](locomotion-20261023-gpt6-high-r1/gpt6/candidate/) · [review.json](locomotion-20261023-gpt6-high-r1/gpt6/review.json) · [score.json](locomotion-20261023-gpt6-high-r1/gpt6/score.json) · [最终答复](locomotion-20261023-gpt6-high-r1/gpt6/FINAL_ANSWER.txt) |
| `claude-opus-5-5` | 84.5/100 | [评审](locomotion-20261023-high-r1/opus/REVIEW_ZH.md) · [候选](locomotion-20261023-high-r1/opus/candidate/) · [review.json](locomotion-20261023-high-r1/opus/review.json) · [score.json](locomotion-20261023-high-r1/opus/score.json) · [最终答复](locomotion-20261023-high-r1/opus/FINAL_ANSWER.txt) |
| `deepseek-v4-pro-202606` | 46.5/100 | [评审](locomotion-20261023-high-r1/deepseek/REVIEW_ZH.md) · [候选](locomotion-20261023-high-r1/deepseek/candidate/) · [review.json](locomotion-20261023-high-r1/deepseek/review.json) · [score.json](locomotion-20261023-high-r1/deepseek/score.json) · [最终答复](locomotion-20261023-high-r1/deepseek/FINAL_ANSWER.txt) |

[结构化三路比较](locomotion-20261023-gpt6-high-r1/comparison-three-models.json) · [请求强度与可观测边界](locomotion-20261023-gpt6-high-r1/effort-observability.json) · [三路结果摘要](../evaluator/model-runs/locomotion-20261023-gpt6-high-r1.json)

这些分数是冻结清单上的静态交付分。评测端没有执行候选代码或 UE，分数不代表最终动画观感、运行通过率或通用模型排名。

## 复算

以下命令从 `Standalone/LyraLocomotionBench` 目录运行，只读取候选和评审、重算汇总分数，不执行候选代码：

```sh
python tools/score_review.py --rubric evaluator/rubric.json --review results/locomotion-20261023-gpt6-high-r1/gpt6/review.json --candidate results/locomotion-20261023-gpt6-high-r1/gpt6/candidate --output reports/gpt6-recomputed.json
python tools/score_review.py --rubric evaluator/rubric.json --review results/locomotion-20261023-high-r1/opus/review.json --candidate results/locomotion-20261023-high-r1/opus/candidate --output reports/opus-recomputed.json
python tools/score_review.py --rubric evaluator/rubric.json --review results/locomotion-20261023-high-r1/deepseek/review.json --candidate results/locomotion-20261023-high-r1/deepseek/candidate --output reports/deepseek-recomputed.json
```

预期均为 `complete`，对应 87.5、84.5、46.5。2026-10-24 在 Windows 发布副本中已复算一致。评分器只检查证据引用、哈希、门槛和计算，代码语义仍由逐项评审承担。

## 冻结文件与发布范围

三份 `candidate/` 完整保留原始文件：Opus 48 个、DeepSeek 44 个、GPT 33 个。评分器把每个文件的相对路径和字节纳入候选哈希，因此 `.tmp/`、`.work/` 和已有的 `.pyc` 也保留；删除、重新生成或自动转换换行都会改变冻结哈希。阅读代码无需执行这些辅助文件。部分模型产物含当时的本机临时路径，它们也是历史候选的一部分。

`review.json`、`score.json`、比较 JSON 和 `evaluator/model-runs/` 摘要按原样保留。JSON 中的本机绝对路径、会话标识和原报告哈希是历史元数据，不是当前可点击链接；原报告哈希对应发布前的本机 Markdown。此处仅把报告和评审 Markdown 的导航改为仓库相对链接，分数、评审结论和候选文件没有改写。

公开结果包含最终报告、逐项评审、完整候选、模型最终答复及比较数据。原始调用日志、连通探针、认证故障记录、详细访问/路由审计和控制器快照本机留存，未发布。报告中原来指向这些文件的链接已改为“本机留存，未发布”；公开材料可复核静态分数，不能独立重建全部调用与访问审计。

不要把本目录作为盲测输入。模型应仅接收[冻结候选题包](../dist/LyraLocomotionBench-candidate.zip?raw=true)，评分方保留本目录和裁判资料。
