# ModelTest

Lyra Starter Game 官方 C++ 工程，来自 Epic Games 的 Unreal Engine **5.8.3** 发布版本。

## 当前内容

- 包含上游 `Samples/Games/Lyra` 的完整 Git 文件：`Source`、`Plugins`、`Config`、`Build`、`Platforms` 和 `Lyra.uproject`。
- 包含 354 个 `.cpp`、353 个 `.h`、19 个 `.Build.cs`、10 个 `.Target.cs` 和 20 个 `.uplugin`。
- **尚未包含 Content 资源，当前不能直接运行游戏。** Epic 官方 Git 仓库不提供地图、蓝图、角色、动画等 `.uasset` / `.umap` 文件；这些资源需要另外从 Fab / Epic Games Launcher 获取。
- 未执行编译、编辑器启动或运行测试。

## 上游来源

- 仓库：<https://github.com/EpicGames/UnrealEngine>
- 分支：`release`
- 提交：`396c9f059903aed5fec78ecd3d437a40c6415368`（`5.8.3 release`）
- 项目目录：`Samples/Games/Lyra`
- 导入日期：2026-10-17
- 原始说明：[README-Lyra-Upstream.md](README-Lyra-Upstream.md)
- 许可：[LICENSE.md](LICENSE.md) 和 [Unreal Engine EULA](https://www.unrealengine.com/eula/unreal)

除将上游 README 保存为 `README-Lyra-Upstream.md` 外，Lyra 工程文件按原样导入。此仓库不包含 Unreal Engine 引擎源码。

## 补齐本地可运行项目

1. 安装与源码匹配的 Unreal Engine 5.8.3 和对应 C++ 开发工具。
2. 登录 Epic 账号，在 [Fab 的 Lyra Starter Game 页面](https://www.fab.com/listings/93faede1-4434-47c0-85f1-bf27c0820ad0)领取项目，并通过 Epic Games Launcher 创建匹配版本的 Lyra 示例。
3. 将下载项目中的主 `Content` 文件夹，以及插件等子目录中的所有 `Content` 文件夹，按原有相对路径复制到此项目。
4. 将 `Lyra.uproject` 关联到对应引擎版本，生成项目文件后构建 `LyraEditor`。

操作步骤以 [Epic 官方 Lyra 文档](https://dev.epicgames.com/documentation/unreal-engine/lyra-sample-game-in-unreal-engine) 为准。下载资源的共享与分发须遵守其附带许可。
