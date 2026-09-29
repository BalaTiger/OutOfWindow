# 后巷阴天雨棚修正

2026-09-28。已编译、验收并更新正在运行的桌面程序。正式入口仍为 `D:/OutOfWindowBuild/Windows/OutOfWindow.exe`。

针对 [诊断中已复现的路径差异](awning-overcast-diagnosis.md)，`WindowDirector::OOWQuality` 在应用 Scalability 后显式设置 `r.Lumen.ScreenProbeGather.TwoSidedFoliageBackfaceDiffuse=1`。启动、切景后的 BeginPlay 和用户切换画质都经过该入口。节能与均衡的 GI quality 2 不再使用导致粉白雨棚的关闭分支；精细档原本已经开启。设置统一作用于双面材质，包括都市及山林植被。

此次保留雨棚原图、反照率、.2 透射强度、.65 光学厚度及整体曝光。固定曝光诊断中该开关已经恢复红色并减轻墙面过强的间接提亮，因此本轮没有再添加材质调色补偿。夜间透光继续存在；不宣称当前干燥阴天画面与雨天美术目标逐像素一致。

正式代码仅增加此设置及 `OOWAudit` 读回；现有 `Scripts/validate.ps1` 增加对应断言，无新渲染依赖或测试框架。

## 验证

Editor 与 Game Development 均编译成功。候选包复用已验收的 AlleyWeathering 内容容器，只替换新 Game exe/pdb；没有修改序列化结构、材质或 shader 源码，因此不重新 Cook。诊断阶段旧包已实测包含开启背面 GI 所需的着色器排列。

八项独立进程回归全部通过：后巷阴天、晴天、夜晚、雨夜、都市阴天、山林晴天，以及后巷节能／精细档。每项读回背面 GI=1，并完成既有几何、材质、天气、灯光及渲染错误检查。数据：[回归状态汇总](../../.runtime/ue-awning-repair/regression-summary.json)、[验收日志](../../.runtime/ue-awning-repair/validation.log)。前几项与旧桌面实例并行，帧间隔受显存竞争影响，不用这些值评价性能。

安装后再次以单进程运行 **2560×1440、后巷、16:00、阴天、均衡**，使用正常自动曝光。实际执行画质 `0→1→2→0→1`，五次查询均为背面 GI=1；输出截图与完整状态，未见材质回退、Fatal、Ensure 或显存耗尽。该次 30 秒运行的应用帧间隔均值 16.67 ms、P95 16.71 ms，是帧间隔而非 GPU 计时。

[安装后阴天画面](../../.runtime/ue-awning-repair/installed-overcast.png) · [状态与画质读回](../../.runtime/ue-awning-repair/installed-overcast.json) · [夜景](../../.runtime/ue-awning-repair/packaged-alley-night.png) · [雨夜](../../.runtime/ue-awning-repair/packaged-alley-rainnight.png)

## GPU 开销

RTX 5060，单进程、2560×1440、均衡（85% 内部分辨率）、固定 16:00 阴天、云量 100%，关闭 VSync/帧率上限，使用真实时间步长。UE 原生 CSV 连续记录 2000 帧，以同一进程按关闭→开启→开启→关闭顺序取四个窗口；每窗剔除前 150 帧，保留后 250 帧，开启/关闭各 500 帧。

| GPUTime | 关闭背面 GI | 开启背面 GI |
| --- | ---: | ---: |
| 均值 | 13.439 ms | 13.374 ms |
| 中位数 | 13.411 ms | 13.350 ms |
| P95 | 13.928 ms | 13.883 ms |

中位差 −.061 ms，小于关闭组自身前后漂移 .084 ms。结论是**本轮未观察到性能回退**，不能据此声称提速或保证所有场景的性能。`GPUTime` 来自引擎 `RHIGetGPUFrameCycles()`；本机新 GPU profiler 未提供 `GPU/Total`，`GPU/LumenScreenProbeGather` 只覆盖其图形队列独占范围，不将它当作含异步计算的完整 GI 成本。

证据：[GPU 分析](../../.runtime/ue-awning-repair/gpu-summary.json)、[采集脚本](../../.runtime/ue-awning-repair/performance.ps1)、[解析与自检脚本](../../.runtime/ue-awning-repair/analyze-gpu.ps1)。首次用启动参数立即开启 CSV 遇到 UE 在 RHI 初始化前查询光追状态的断言；改为场景加载后的 `csvprofile frames=2000` 后完成采集。这仅影响诊断启动方式，正常运行及全部渲染回归均通过。

## 安装与恢复

只更新 `OutOfWindow/Binaries/Win64/OutOfWindow.exe` 和 `.pdb`；根启动器与内容容器保留。新 exe SHA256 为 `AC5B139879A02DA038707810CF0B06172804EEC408623D3DE8F4E2D38183F8B3`，安装后核对一致。旧文件保存在工作区 `.runtime/ue-awning-repair/backup-20260928-171557`。

[部署记录](../../.runtime/ue-awning-repair/deployment.json)记录前后哈希、备份和五次画质查询。安装后已重启原桌面入口；[实时状态](../../.runtime/ue-awning-repair/live-state.json)确认实际运行版本为后巷、非测试模式，背面 GI=1。
