# Linux 容器逻辑 demo 与 Git 交付

已选择独立的“生命值与战斗逻辑”demo，提供命令行和 Web 页面。它按 Lyra 的部分源码规则实现，只需要 Python 3.9+，适配本次无 GPU 的容器。完整 UE 5.8.3 Lyra 工程保留，demo 不运行 UE 引擎。

功能、命令与验收规则见 [Combat demo](../Demo/Combat/README.md)。独立 demo 不使用 Content，因此不需要安装 Git LFS 或下载约 2.31 GiB 的资产。

## 首次同步与启动

在容器内先通过已有的 GitHub 授权方式取得 `faith30/ModelTest` 的读取权限。不要把令牌写入 clone URL、提交或文档。

```bash
cd /workspace
GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 --filter=blob:none --sparse --branch codex/linux-combat-demo https://github.com/faith30/ModelTest.git ModelTest
cd ModelTest
git sparse-checkout set Demo/Combat Tools Docs
git rev-parse HEAD
python3 --version
python3 Tools/check_linux_demo.py
python3 -m unittest discover -s Demo/Combat/tests -v
python3 Demo/Combat/demo.py scenario --name normal
python3 Demo/Combat/demo.py scenario --name lethal --json
python3 Demo/Combat/demo.py serve --port 8000
```

首次克隆前确认 `/workspace/ModelTest` 不存在；若已经有工作目录，先检查该目录的 `git status` 和分支，不覆盖其中的工作。上述命令只下载 demo、环境检查脚本和文档，不下载 Unreal 资产，也不安装系统软件。

Web 页面通过 code-server 的 Ports / Forward a Port 入口选择 **8000**，再用平台提供的浏览器入口打开。代理地址末尾保留 `/`。服务默认监听容器内的 127.0.0.1，使用平台代理即可；命令行演示不依赖端口转发。Ctrl+C 停止 Web 服务。

后续在同一分支执行：

```bash
git pull --ff-only
git rev-parse HEAD
python3 -m unittest discover -s Demo/Combat/tests -v
```

更新后重启 Web 服务并刷新页面。记录本地与容器的提交号，确保两端运行同一版本。

## 目标容器实测

检查日期：2026-10-18。通过测试平台已有容器的 code-server 终端执行只读检查；以下结果只代表本次实例，新建容器后应重新检查。

| 项目 | 实测结果 | 影响 |
| --- | --- | --- |
| 系统 / 架构 | Debian GNU/Linux 13 / x86_64 | 需要 Linux x86_64 产物 |
| CPU 配额 | `cpu.max = 200000 100000`，相当于 2 核 | 不适合在此完整编译 UE |
| 内存上限 | `memory.max = 4294967296`，即 4 GiB | 不能将 `free` 显示的宿主机 30 GiB 当成容器配额 |
| 当前用户 | root | UE Linux 游戏默认拒绝以 root 运行，应另用普通用户 |
| GPU | 未发现 `/dev/dri/*` 或 `/dev/nvidia*` | 当前未向容器暴露 GPU |
| Vulkan | 未发现标准目录内的 ICD 配置，`vulkaninfo` 不可用 | 未具备已验证的 Vulkan 渲染环境 |
| 显示 | `DISPLAY` / `WAYLAND_DISPLAY` 均未设置 | 未配置窗口显示通路 |
| 引擎 | PATH 中无 UnrealEditor，未设置 UE_ROOT，`/opt` 与 `/workspace` 为空 | 未发现可直接使用的 UE 安装；未扫描整个文件系统 |
| Git | 初次检查时 Git 可用，Git LFS 不可用 | 独立 demo 的稀疏克隆不需要 LFS |
| 仓库访问 | 初次无交互 `git ls-remote` 返回 128，要求 GitHub 用户名认证 | 用户负责通过已有授权方式配置读取权限 |

`df` 显示的 overlay 可用空间约 956 GiB 也不能视为平台对该容器承诺的存储配额。

## UE 运行边界

- **UE/Lyra 图形 demo**：当前容器不足以直接运行。需要可用的 GPU/Vulkan 环境、显示或浏览器串流通路，以及 Linux 打包产物。`-RenderOffScreen` 仍使用 Vulkan；仅增加这个参数不能解决缺少 GPU/驱动的问题。
- **UE 无图形逻辑 demo**：可以评估 Linux dedicated server 或 `-nullrhi` 路线，但必须实际验证 4 GiB 限额下的启动与业务行为。这不能用来证明游戏画面可运行。
- **本次独立命令行 / Web demo**：已由用户选择；运行和测试通过只能证明该 Python 样例有效，不能证明完整 Lyra 可运行。

构建应优先考虑在具备引擎和资源的机器上完成，再将 Linux 产物交付容器。本地 UE 5.8.3 的 Linux SDK 配置要求 `v26_clang-20.1.8-rockylinux8`，当前尚未验证本地交叉编译工具链可用。

## 如需同步完整 Unreal 工程

仓库：`https://github.com/faith30/ModelTest.git`。源代码与资源已在同一个仓库中；`.uasset` / `.umap` 等通过 Git LFS 管理，LFS 资产约 2.31 GiB。普通 Git clone 完成不代表这些资源已下载。

先在容器内按平台允许的方式配置仓库读取权限。不要把令牌写入 clone URL、脚本、提交或文档；无需将私有仓库改成公开。

以下是完整工程的可选步骤，**运行本次 demo 无需执行**。先确认确实需要原始资产以及足够存储空间：

```bash
apt-get update
apt-get install -y git-lfs
# 在已有仓库内恢复完整工作树
git sparse-checkout disable
git lfs install --local
git lfs pull
git lfs ls-files
git rev-parse HEAD
```

上述 `apt-get` 按本次 root 环境编写；其他容器使用其已授权的软件安装方式。UE 游戏启动应切换到普通用户。仓库只有源码和原始 Content，不包含 UE 引擎或 Linux 打包程序，因此这段命令只完成完整工程同步。

后续更新使用 `git pull --ff-only` 和 `git lfs pull`，并记录两端的 `git rev-parse HEAD`。验收时除提交号一致外，还需确认 LFS 文件已展开为真实资产。

若最终通过 Git 交付打包产物，需要单独安排产物目录或分支，并让 `.pak`、`.ucas`、`.utoc`、Linux 可执行文件等大文件使用 LFS。现有 `.gitattributes` 只配置了 Unreal 原始资产类型；不要直接把整个引擎、缓存、Intermediate 或 Windows Binaries 加入提交。

## 验收边界

完成部署需要同时满足：

1. 容器能读取指定 Git 提交，稀疏工作树包含 Demo/Combat、Tools 和 Docs。
2. Python 测试全部通过，内置 normal / immunity / lethal / max_health 场景能执行。
3. normal 演示伤害/治疗限制，immunity 演示免疫与自毁标记，lethal 演示零血及独立死亡阶段，max_health 演示上限变化。
4. 若使用 Web，验证页面加载、操作和事件回放；保存提交号和启动命令。

环境检查、Windows 编译成功、菜单启动或无图形日志都不能单独替代最终功能验收。

参考：[Epic Linux 开发要求](https://dev.epicgames.com/documentation/en-us/unreal-engine/linux-development-requirements-for-unreal-engine)、[Pixel Streaming 参考](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-pixel-streaming-reference)。版本选择以本地 UE 5.8.3 的 `Engine/Config/Linux/Linux_SDK.json` 为准。
