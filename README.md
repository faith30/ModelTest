# ModelTest

四模型 Lyra 功能开发实测报告（DeepSeek、GPT-6 Astra、Claude Opus 5.5、GPT-5.6 Sol）：[Markdown 正文](Reports/LyraFeatureSuite/2026-10-25/MODEL-EVALUATION-REPORT.zh-CN.md) · [PDF 完整版](Reports/LyraFeatureSuite/2026-10-25/MODEL-EVALUATION-REPORT.zh-CN.pdf)。包含三项任务完成情况、评分与排序原因、未验证来源区分，以及完整评分矩阵；本版整理于 2026-10-25。

独立于 UE 的走跑动画、动画图和控制逻辑评测工程已收录在 **[Standalone/LyraLocomotionBench](Standalone/LyraLocomotionBench/README.md)**。包含候选题包、姿态数据、40 项审查清单、评分工具和三路已完成的作答结果；使用该子目录无需安装或启动 Unreal Engine。

Lyra Starter Game 官方 C++ 工程：使用 Unreal Engine **5.8.3** 发布版源码，并包含通过 Fab / Epic Games Launcher 获取的 **5.8 系列完整 Content 资源**。

## 当前内容

- 包含上游 `Samples/Games/Lyra` 的完整 Git 文件：`Source`、`Plugins`、`Config`、`Build`、`Platforms` 和 `Lyra.uproject`。
- 包含 354 个 `.cpp`、353 个 `.h`、19 个 `.Build.cs`、10 个 `.Target.cs` 和 20 个 `.uplugin`。
- 包含官方资源包全部 11 个 `Content` 目录，共 8,816 个文件、2,498,397,660 字节；其中有 8,667 个 `.uasset` 和 22 个 `.umap`，其余为本地化、字体及附带许可等文件。
- `.uasset`、`.umap` 等二进制资产使用 Git LFS。克隆后需要拉取 LFS 文件。
- 引擎本体、预编译二进制、Intermediate、Saved 和缓存不纳入版本管理。
- 已使用 UE 5.8.3 源码引擎通过 `LyraEditor` 和 `ShaderCompileWorker` 的 Win64 Development 编译；未执行编辑器启动、PIE 或打包测试。

## 上游来源

- 仓库：<https://github.com/EpicGames/UnrealEngine>
- 分支：`release`
- 提交：`396c9f059903aed5fec78ecd3d437a40c6415368`（`5.8.3 release`）
- 项目目录：`Samples/Games/Lyra`
- 导入日期：2026-10-17
- 原始说明：[README-Lyra-Upstream.md](README-Lyra-Upstream.md)
- 许可：[LICENSE.md](LICENSE.md) 和 [Unreal Engine EULA](https://www.unrealengine.com/eula/unreal)
- 资源包：[Fab Lyra Starter Game](https://www.fab.com/listings/93faede1-4434-47c0-85f1-bf27c0820ad0)，通过 Launcher 选择 `5.8`，下载于 2026-10-17。

保留 Git 上游的 C++ 源码与配置；上游 README 保存为 `README-Lyra-Upstream.md`，`Lyra.uproject` 的 `EngineAssociation` 设置为 `5.8`。资源包内的构建版本标记为 5.8.0，未用它覆盖 5.8.3 源码或复制其预编译二进制。

## 使用

1. 安装 Unreal Engine 5.8.3、对应 C++ 开发工具和 Git LFS。
2. 克隆仓库后运行 `git lfs install` 和 `git lfs pull`。
3. 将 `Lyra.uproject` 关联到对应引擎安装，生成项目文件并构建 `LyraEditor`，再打开项目。

使用源码引擎时，先将引擎同步到上述 5.8.3 发布提交并运行 `Setup.bat`，完成 VC++ 和 GameInput 运行库安装，再生成工程文件。项目使用 `BuildSettingsVersion.V7`，UE 5.7 的构建工具无法解析该配置。

2026-10-17 构建验证：使用 MSVC 14.44.35222、Windows SDK 10.0.22621.0 和引擎自带 .NET SDK 10.0.203，工程文件生成、`LyraEditor Win64 Development`（4,359 项任务）及 `ShaderCompileWorker Win64 Development`（281 项任务）全部成功。编辑器和 Lyra DLL 的产物版本均为 5.8.3。

资源已从官方包按原有相对路径合入，包含主项目以及所有插件中的 Content。全部 8,816 个资源文件与官方下载安装包的 SHA256 一致，无缺失或多余文件；已确认启动地图、GameMode、GameInstance、DefaultGameData 和默认 PawnData 等关键资源文件存在。资源完整性和 C++ 编译已验证，资产加载、PIE 及打包运行尚未验证。

## 资源许可

Git 源码沿用 Unreal Engine EULA。Fab 资源按领取时的标准许可证及其 UE-Only 标记使用，另保留资源包中的第三方许可。完整原始资源通过私有仓库用于同项目协作；公开源码版本可让使用者自行从 Fab 获取 Content。

参阅 [Fab 标准许可](https://www.fab.com/eula) 和 [Epic 官方 Lyra 文档](https://dev.epicgames.com/documentation/unreal-engine/lyra-sample-game-in-unreal-engine)。
