# ModelTest

Lyra Starter Game 官方 C++ 工程：使用 Unreal Engine **5.8.3** 发布版源码，并包含通过 Fab / Epic Games Launcher 获取的 **5.8 系列完整 Content 资源**。

## 当前内容

- 包含上游 `Samples/Games/Lyra` 的完整 Git 文件：`Source`、`Plugins`、`Config`、`Build`、`Platforms` 和 `Lyra.uproject`。
- 包含 354 个 `.cpp`、353 个 `.h`、19 个 `.Build.cs`、10 个 `.Target.cs` 和 20 个 `.uplugin`。
- 包含官方资源包全部 11 个 `Content` 目录，共 8,816 个文件、2,498,397,660 字节；其中有 8,667 个 `.uasset` 和 22 个 `.umap`，其余为本地化、字体及附带许可等文件。
- `.uasset`、`.umap` 等二进制资产使用 Git LFS。克隆后需要拉取 LFS 文件。
- 引擎本体、预编译二进制、Intermediate、Saved 和缓存不纳入版本管理。
- 未执行编译、编辑器启动或运行测试。

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

资源已从官方包按原有相对路径合入，包含主项目以及所有插件中的 Content。全部 8,816 个资源文件与官方下载安装包的 SHA256 一致，无缺失或多余文件；已确认启动地图、GameMode、GameInstance、DefaultGameData 和默认 PawnData 等关键资源文件存在。文件完整性检查不代表已通过编译或运行测试。

## 资源许可

Git 源码沿用 Unreal Engine EULA。Fab 资源按领取时的标准许可证及其 UE-Only 标记使用，另保留资源包中的第三方许可。完整原始资源通过私有仓库用于同项目协作；公开源码版本可让使用者自行从 Fab 获取 Content。

参阅 [Fab 标准许可](https://www.fab.com/eula) 和 [Epic 官方 Lyra 文档](https://dev.epicgames.com/documentation/unreal-engine/lyra-sample-game-in-unreal-engine)。
