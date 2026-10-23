# Win11 运行端天气云同步 · 2026-10-19

**默认入口已切换并通过验证。** 现在运行根目录 `打开UE窗景.cmd` 使用 `cloud-runtime-20261019-v2`；`打开云同步前旧版.cmd` 可直接启动保留的旧构建。切换后的默认清单已再次通过正式加载、UE 启动和桌面挂接探针。完整证据见 [runtime-evidence.json](runtime-evidence.json)。

新版本名：`cloud-runtime-20261019-v2`。构建快照位于 `.runtime/loading-builds/20261019-020955-3169f205/OutOfWindow`，构建时间为 `2026-10-19T02:14:02.5378791Z`。模块 SHA256 为 `4486cc7f12aca42a149b5e7ea0d20b723df0883fa3b7f8221209ab493cdb2d72`。

新版本基于已拉取的 `80793d16b5aba6d33bd486ed9d4bcd08388b50e6`，另有本次尚未提交的少云远近分流改动。92 条源码/配置记录与 6516 个内容文件均已逐项核验。`OutOfWindow.Weather.ApprovedCloudRouting` 和 `ApprovedCloudDistanceBlend` 两项 UE 自动化测试实际通过，无警告。

## 天气规则

| 应用天气 | 低云 | 高层卷云 |
| --- | --- | --- |
| 晴 | 保留旧路线 | 已验收单束丝缕，权重 1 |
| 少云 | 4 km 内旧云；4–8 km 平滑过渡；8 km 外轻量云，覆盖参数 0.26 | 已验收单束丝缕，权重 0.55 |
| 多云 | 已验收轻量云，覆盖参数 0.48 | 已验收单束丝缕，权重 0.15 |
| 阴 / 雨 | 已验收阴雨轻量云，覆盖参数 0.69 | 0 |

距离以固定场景相机的水平位置计算。材质图中低云混合完成后才加高层卷云，远景分流不压制卷云；没有交叉复制束。雪、雾与未知天气沿用旧路由。本次没有恢复暂停的卷积云试验。

原 `OOW_ApprovedClouds` 三个验收资产的 SHA256 均保持原值；21 段原 Custom shader 代码也保持一致。仅新增 `OOW_RuntimeClouds_20261019` 派生材质，未改动城市资产或城市逻辑。

## 入口与回退

默认入口仍是仓库根目录 `打开UE窗景.cmd`，目前已切换到 `cloud-runtime-20261019-v2`。本次版本切换更新了 `.runtime/launcher/target.json`，旧清单原文已另行备份。

根目录 `打开云同步前旧版.cmd` 可直接启动冻结的旧构建，不改变默认入口。旧版本名为 `rollback-before-cloud-20261019`，保留 10/17 模块、44 条旧源码记录、6511 个内容文件及原入口；旧快照没有被覆盖。若需把默认入口改回旧版，可在仓库中运行：

```powershell
./unreal/Switch-RuntimeBuild.ps1 -Version rollback-before-cloud-20261019
```

回退后如需恢复本次新版，可使用同一命令，将版本名改为 `cloud-runtime-20261019-v2`。脚本会重新校验版本证据，并原子替换与备份旧清单；本次已完成的激活记录见 [activation-result.json](activation-result.json)。

## 验证边界

有效天气图采用同一 Alley 场景、正午、固定天气与云运动，串行单实例。`-OOWTestQuality=1` 对应 High 材质（`r.MaterialQualityLevel=1`），与旧入口的材质级别一致；输出为 960×540，并以 `-OOWTestScreenPercentage=70` 将内部渲染比例设为 70%。因此这些图应描述为 High 材质、降低渲染分辨率，不能统称“低画质”。截图不会保存场景改动。截图 JSON 的距离权重是 CPU 诊断镜像，另有实际材质连接证据，不把它当作 GPU 像素分类。

最初有效的 `weather-clear-high` 和 `weather-few` 截图保留了 `-UseFixedTimeStep -FPS=10`。它们用于确认画面与路由，固定模拟步长不代表真实运行时每秒只渲染 10 帧；少云命令虽另设 `t.MaxFPS 10`，也不能据此把固定步长运行当作性能基准。从 `weather-cloudy` 开始，后续阴天、雨天命令移除了固定步长，改用真实时间推进与 `t.MaxFPS 10` 限帧。限帧配置不保证稳定达到 10 FPS；各次总耗时还包含加载、编译和截图等待，不能直接比较为云渲染性能。

初期 `-OOWTestQuality=0` 将材质从旧入口的 High 切到了 Medium（`r.MaterialQualityLevel=2`），进入不同的材质变体冷启动路径。早期独立缓存运行在 600 秒截止时停止，峰值提交约 8.23 GiB；随后仅恢复默认 Zen、仍保留 Medium 的一次运行也未完成，已受控取消。该轮日志明确记录了 50 次未预缓存 PSO 创建卡顿及 PSO 等待，因此不能将“已使用旧 Zen”当作 Medium 变体已经全部预热，也不能把全部延迟都归因于 shader 重编译。有效验证最终同时复用原默认 Zen 缓存并采用 `-OOWTestQuality=1`，完成必要预热后，晴天成功生成截图，后续少云、多云复验也成功退出。当前截图流程已避开先前 Medium 变体的冷启动阻塞，未把未完成的 Medium 运行计为通过。

早期两次失败分别触及测试 Job 的 6 GiB、8 GiB 提交量上限，未得到有效截图；提交量上限不等于物理内存使用量。后续采用 12 GiB Job 提交量上限、4 GiB 系统余量保护、4 个逻辑 CPU，以及 `-noshaderworker`，保持单实例串行。已成功的晴天、少云、多云运行峰值 Job 提交量分别约 8.66、8.52、8.80 GiB，均低于新上限，先前限制过小的问题已在这些运行中解决。资源保护只属于验证脚本，没有更改日常启动器的缓存、CPU 或内存设置，也未改动系统或用户环境变量。默认 Zen 复用证据见 `.runtime/cloud-runtime-sync-20261019/cache-reuse-proof.json`；各次命令、成功结果和失败日志均保留在同目录。

Houdini 新样本继续保存在独立实验目录，不接入正式云材质。


## 实际截图与启动证据

| 天气 | 正常场景 | 同方位天空特写 |
| --- | --- | --- |
| 晴 | [实景](01-clear-weather.png) | [天空](01-clear-sky.png) |
| 少云 | [实景](02-few-weather.png) | [天空](02-few-sky.png) |
| 多云 | [实景](03-cloudy-weather.png) | [天空](03-cloudy-sky.png) |
| 阴 | [实景](04-overcast-weather.png) | [天空](04-overcast-sky.png) |
| 雨 | [实景](05-rain-weather.png) | [天空](05-rain-sky.png) |

天空特写仅在测试进程中隐藏场景网格，采用同一方位（face 4），保留固定场景距离原点；没有保存场景修改。图像保留原始 UE 输出，没有修饰云形。

[新版正常启动帧](startup-v2.png)、[旧版回退启动帧](startup-rollback-lowload.png)、[切换后默认入口启动帧](startup-default.png)。旧版首次全负载探针因可用物理内存降至 3.977 GiB 被保护性停止；后续旧版与默认清单使用仅作用于测试进程的 50% 内部渲染、10 FPS，保留 4 GiB 系统余量保护后通过。没有关闭其他应用、修改正式画质或系统设置。

探针调用正式 `LauncherForm.LoadTarget` 和 `LaunchSession`，验证 Ready、窗口已挂接桌面、可见且未 cloaked、截图生成，以及测试自有进程清理。入口 `.cmd` 到 PowerShell 再到清单的解析关系另见 [entry-resolution.json](entry-resolution.json)。没有用探针代替完整的双击与 Launcher UI 交互验收；UE 截图也不是 Windows 桌面合成截图。受控加载耗时不代表默认启动性能。

新旧版本的内容清单分别保存在 `.runtime/launcher-versions/cloud-runtime-20261019-v2/runtime-content-proof.json` 与 `rollback-before-cloud-20261019/runtime-content-proof.json`。激活脚本在哈希验证后备份并原子替换默认清单；[activation-result.json](activation-result.json) 记录准确备份路径。

本轮随后完成的 [Houdini 近景细雕诊断](../20261019_Houdini少云近景细雕诊断/README.md) 未通过连通性和自然度检查，仅保存隔离工程及对照图，没有接入此运行版本。
