# 本机 TClaude 调用运行库

这些 Python 文件逐字节复用了本机 `D:/AnimationMarkBench/scripts` 的既有调用代码（复制后已核对 SHA256），不包含旧模型的作答或评分：

| 本目录 | 原文件 | SHA256 |
|---|---|---|
| cli_transport.py | cli_transport.py | b663715d2d65cbd7259ef9b572d3df65ab4a56107b4aaa0d7e6e8738783fa16c |
| cli_agent_transport.py | cli_agent_transport.py | 0ca881f53da86f4b41aa7864d9e5f104dcc429ca83cf4d56be3b543950f89cde |
| cli_windows_job.py | cli_windows_job.py | ac4296e9c9e9e891cfc1fa0e90cd84bce91680465506f1195503ca702c0ab6eb |
| paired_runtime.py | run_paired_asset_tasks.py | acf445cefd9c45bd361b0a492b3f47b66a30c6206c7b0fe4d38ee23b95deca97 |

本题入口是 `../run_models.py`，仅复用进程启动、日志、指纹、归档及原生CLI参数辅助函数；不运行旧题包或旧评分器。每次正式调用将运行器源码复制到该模型记录的 `controller_snapshot/`，本轮参数、提示词和摘要独立保存。

Windows Job 负责超时后的进程树回收，不是文件或网络访问沙箱。独立目录与指令约束需要另做可见工具访问审计，不能宣称强隔离。`result.ok` 只表示调用结果，输入完整性、交付内容和静态分数需要分别核对。
