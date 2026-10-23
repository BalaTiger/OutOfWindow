# Win11 轻量云同步核查（2026-10-19）

> 后续运行端集成已完成：默认入口已绑定版本 `cloud-runtime-20261019-v2`，少云 4 km 内保留旧云、4–8 km 混合、8 km 外使用轻量云；高层丝缕与多云阴雨沿用验收方案。新旧构建均已通过启动探针，并保留独立旧版入口。详见 [运行端截图和版本证据](../预览/20261019_运行端天气云同步/README.md)。以下正文保留首次同步审计时的状态，其中“尚未重建/远景未分流”已由此次工作解决。

本轮结束补充：正常 Git LFS 状态已通过正式提升后的只读 `git status` 核验，无 tracked modification，仅新增本记录与隔离实验预览。Houdini 单样本真实构建、重新加载、串行渲染已完成；实验结论与本机软件证据见 [实验记录](../预览/20261019_Houdini少云近景单样本/README.md)。本机默认运行入口未重新构建。

结论：**10 月 18 日轻量云源码和资源已拉取到本机；默认运行入口仍指向旧构建，尚不能认定新云已在该入口运行。** 少云近景保留原方案；少云远景轻量云目前没有独立实现，不能写成已经完成。

## Git 与资源证据

- 核查目录：`C:\Users\zhuzi\Documents\OutOfWindow`。本仓库递归查找未发现 `AGENTS.md`；主代理亦核查了根目录及祖先目录。
- `HEAD/main` 与本地 `origin/main` 均为 `80793d16b5aba6d33bd486ed9d4bcd08388b50e6`（`cloud`），提交时间为 `2026-10-18 14:08:02 +08:00`。
- 主代理核实 `git reflog`：本机在 `2026-10-19 09:41 +08:00` 已执行 pull，结果为 fast-forward。此次核查未再次 fetch/pull。
- 该提交增加 3 个云资产、`WindowApprovedClouds.h`、对应测试，并修改 `WindowDirector.cpp/.h`，共 7 个文件。
- 原生 `git status` 受沙箱中的 Git LFS/MSYS 命名对象错误影响。禁用 LFS filter 的只读 status 显示 3 个云资产 modified；下表证明本地资产与提交 LFS 对象完全一致，这些标记不能据此判为用户修改。

资源目录：`unreal/OutOfWindow/Content/Weather/OOW_ApprovedClouds/`。以下本地 SHA256 与提交中的 LFS oid、size 均逐项一致，资产已经实体化，并非只剩 LFS 指针。

| 文件 | 字节数 | SHA256 |
| --- | ---: | --- |
| `MI_RuntimeMix.uasset` | 8,213 | `ae2e41391ae8e095892454d960f0cee22b6a33da82def36bee813062a0a2ddbf` |
| `M_RuntimeMix.uasset` | 281,805 | `585992bdd43e95429dea01cc6485c339b19c808098fa6c5811ad2ce3240aef6d` |
| `T_Ci_LowerAccepted.uasset` | 150,549 | `063fe904e34e0bda42784c52d7dbef59f206aeba3d00831132b7ae58045da099` |

## 实际天气选择与 shader

代码位置均相对于仓库根目录。

- `unreal/OutOfWindow/Source/OutOfWindow/WindowDirector.cpp:1036`：`ActualWeather()` 对普通天气按云量分类，对雨、雪、雾等保留供应商天气语义。`:1422` 取得该结果，`:1645` 传入 `UpdateApprovedClouds`，没有另行解释天气。
- `WindowDirector.cpp:164`：`oow.ApprovedClouds` 默认值为 1；`:595` 在非原生/旧版诊断路由下加载 `MI_RuntimeMix`；`:2409` 起平滑更新混合权重。
- `unreal/OutOfWindow/Source/OutOfWindow/WindowApprovedClouds.h:14` 定义下表。原低云列为路由权重，不表示晴天一定有可见低云。

| 应用天气 | 轻量低云 | 原低云 | 验收卷云 | 阴雨参数 |
| --- | ---: | ---: | ---: | ---: |
| 晴 | 0 | 1 | 1 | 0 |
| 少云 | 0 | 1 | 0.55 | 0 |
| 多云 | 1 | 0 | 0.15 | 0 |
| 阴 / 雨 | 1 | 0 | 0 | 1 |
| 雪 / 雾 / 未知 | 0 | 1 | 0 | 0 |

- **少云没有按距离拆分远近景。** `WindowApprovedClouds.h:17` 的轻量低云目标为 0；近景保留原方案，但“远景可用轻量云”目前只是允许方向，不是已实现功能。
- `WindowDirector.cpp:2419` 起：多云低云层 1.6–2.5 km，阴雨低云层 1.3–2.4 km；覆盖率从 0.48 混到 0.69，侵蚀从 0.25 混到 0.32，密度系数 0.0045。
- 直接读取 `M_RuntimeMix.uasset` 内嵌 Custom 节点 HLSL：轻量低云在 `ApprovedMix.r < .00001` 时返回 0；使用 UE 现有 Perlin-Worley 三维噪声构成覆盖、变化云冠、边缘侵蚀与内部密度变化。
- 同一材质的验收卷云使用 `T_Ci_LowerAccepted` 蓝通道，位于 8.2–8.38 km，仅一个 bundle、固定场景方向，无交叉复制。当前提交没有对应独立文本 shader，以上来自资产内嵌代码，不是猜测资产名称。
- `unreal/OutOfWindow/Source/OutOfWindow/Tests/WindowApprovedCloudsTest.cpp` 已提交天气边界和路由测试；本次只读核查未执行 UE 测试，不能声称本机已测试通过。

## 默认入口与旧构建缺口

- 入口链：`打开UE窗景.cmd` → `unreal/Launch-Unreal.ps1` → `.runtime/launcher/target.json`。`unreal/Run-Unreal.ps1` 的 Game 模式也转到该启动器。
- 当前 manifest 指向 `.runtime/loading-work/project/OutOfWindow/OutOfWindow.uproject` 及其模块，记录构建时间 `2026-10-17T02:29:03.7646652Z`。该副本缺少 `WindowApprovedClouds.h` 和整个 `Content/Weather/OOW_ApprovedClouds`。
- 该副本模块 SHA256 仍与旧 manifest 一致，但正式目录 `WindowDirector.cpp/.h` 已与 manifest 源码哈希不符；新增 `WindowApprovedClouds.h` 和 `Tests/WindowApprovedCloudsTest.cpp` 也未收录。
- `unreal/Launcher/Program.cs:185` 检查源码哈希，`:195` 检查新增源码。因此现有启动器将要求重新构建；没有启动 UE 也能验证这一缺口。
- 正式目录 `unreal/OutOfWindow/Binaries/Win64/UnrealEditor-OutOfWindow.dll` 修改时间为 `2026-10-07 12:41:48 +08:00`，`OutOfWindow.exe` 为 `2026-10-06 14:52:54 +08:00`，均早于云提交；不能用这些二进制证明新路由已运行。
- `unreal/Build-LoadingExperience.ps1:22` 支持新建隔离快照，`:113` 使用单并行编译；新构建和实际运行验收仍待完成。此记录没有执行构建或更换启动目标。

## Houdini 可用性与实验边界

- 主代理对本机 hython 的正式提权探测已成功，输出为 **Houdini 20.5.332 Commercial、Python 3.11.7**，证明解释器和许可可用。
- 普通 sandbox 探测曾遇到 DLL relocation 错误；这是受限环境下的加载问题，不能据此判断 Houdini 未安装。提权探测成功也不等于新体积云已完成生成或渲染。
- 后续授权方向：少云近景隔离实验，先小体积、低分辨率、单样本；保留 sample01 已通过的大形，消除方形边缘，改善边缘分形和内部不重复结构；不得只重复堆叠两朵云或拉伸替代细节。
- 卷积云试验暂停，城市不动，不覆盖已验收云；避免并行多 UE/Houdini 实例，保存隔离版本及对照图。

本记录仅新增此 Markdown 文件；核查期间未修改启动器、业务代码、云资产或城市，未启动 UE。剩余待办为新运行构建及其验收，以及独立 Houdini 样本实验。
