# Out of Window — UE5 原生工程

工程入口：[OutOfWindow/OutOfWindow.uproject](OutOfWindow/OutOfWindow.uproject)。当前使用本机 **Unreal Engine 5.7.4**，都市、后巷、村庄、山林、海滨分别导入五张关卡。原 Electron/Three.js 工程保留，作为资产来源与行为对照。

本次选择 UE5，是为了直接采用成熟的 **Lumen 动态 GI/反射、Nanite、Virtual Shadow Maps、TSR、DX12/SM6**；硬件支持时使用 Lumen 硬件光追。固定机位的缓存优化建立在这些公共系统上。Lumen 本身支持光照缓存及更新速度控制，Nanite 管理已有几何的细节与流送。[Lumen 官方说明](https://dev.epicgames.com/documentation/en-us/unreal-engine/lumen-global-illumination-and-reflections-in-unreal-engine)、[Nanite 官方说明](https://dev.epicgames.com/documentation/en-us/unreal-engine/nanite-virtualized-geometry-in-unreal-engine)

**Windows Development 成品已成功打包，首轮 15 个独立程序用例全部通过自动检查。** 入口为 `D:\OutOfWindowBuild\Windows\OutOfWindow.exe`。完整矩阵在 Cook 完成后串行运行，每例 30 秒，覆盖五景、天气、三档画质与桌面接口。岸线和单实例启动逻辑修正后的最终包也通过海滨、桌面、正常联网与第二实例补测。精细档后巷平均约 24.5 FPS，尚不适合作为本机 60 FPS 档位；山林地形素材与完整人工交互仍有待完善。证据和边界见 [迁移验收清单](Migration/acceptance.md)。

## 启动与构建

在仓库根目录的 PowerShell 中执行：

```powershell
# 编译 Editor 和独立 Game 的 Development 目标
.\unreal\Run-Unreal.ps1 -Mode Build

# 运行后巷，也可选择 City、Village、Forest、Coast
.\unreal\Run-Unreal.ps1 -Mode Game -Scene Alley

# 打开编辑器
.\unreal\Run-Unreal.ps1 -Mode Editor -Scene Alley

# Cook、打包并归档 Windows Development 程序
.\unreal\Run-Unreal.ps1 -Mode Package

# 固定条件的离屏渲染检查
.\unreal\Run-Unreal.ps1 -Mode Validate
```

脚本先读取 `UE_ROOT`，否则从 Epic Launcher 安装记录查找 `UE_5.7`。本机引擎为 `D:\Epic\Epic Games\UE_5.7`，也可明确传入：

```powershell
.\unreal\Run-Unreal.ps1 -Mode Build -EngineRoot 'D:\Epic\Epic Games\UE_5.7'
```

`Game` 优先运行已经打包的程序；没有打包产物时使用 `UnrealEditor.exe -game`。磁盘上若有旧包，修改源码后须重新 `Package`，或用 `Editor` 打开最新工程。当前独立程序已成功运行，不依赖 Node、Vite、Electron；请保留整个 `Windows` 目录，不能只拷贝顶层启动 exe。

打包只包含 DX12/SM6 目标，使用完整关卡路径 `/Game/Maps/Alley` 等，避免与 Engine 中同名 Reverb 资产混淆；`-skipeditorcontent` 排除编辑器专用资源。加入夜窗素材后的归档约 1.44 GB（1.34 GiB），包含 `THIRD_PARTY_ASSETS.md` 和 `ASSET_INVENTORY.md`；两份文件已与仓库原件核对哈希。首轮 `.runtime/ue-package.log`、岸线/单实例修正后的 `.runtime/ue-package-revalidation.log` 与本轮 `.runtime/ue-night-window/package.log` 均记录 `BUILD SUCCESSFUL` / AutomationTool ExitCode 0。

本机已安装 VS2022 Build Tools 17.14.41、MSVC 14.44.35229、Windows SDK 10.0.22621.0，以及 UE Editor 所需 .NET Framework 4.8 SDK/Targeting Pack。Build Tools 位于 `D:\Microsoft Visual Studio\2022\BuildTools`，安装记录在 `.runtime/ue-toolchain/receipt.json`。UE 使用引擎附带的 .NET 8 SDK。构建入口限制为单任务编译，因为本机曾在并行 PCH 编译时出现虚拟内存不足。

## 磁盘与首次准备

缓存/归档目录跟随引擎所在盘；本机为：

| 内容 | 路径 |
| --- | --- |
| 派生数据缓存 DDC | `D:\OutOfWindowBuildCache` |
| Cook 输出 | `D:\OutOfWindowBuildCache\Cooked\Windows` |
| 打包临时目录 | `D:\OutOfWindowBuildCache\Staged` |
| 打包归档 | `D:\OutOfWindowBuild` |
| 已生成的打包程序入口 | `D:\OutOfWindowBuild\Windows\OutOfWindow.exe` |
| 本仓库 Git LFS 缓存 | `D:\OutOfWindowBuildCache\GitLfsCache` |
| 源素材缓存归档 | `D:\OutOfWindowBuildCache\SourceArchives` |
| 项目原生资产 | `unreal/OutOfWindow/Content` |
| Editor/Game 构建产物 | `unreal/OutOfWindow/Binaries`、`Intermediate` |
| 验证截图、审计 JSON 与日志 | `.runtime/ue-validation` |

DDC、Cook、归档放到 D 盘，不代表仓库里的 `Content`、`Intermediate`、`Saved` 都已移出 C 盘。首次打开和修改材质后会准备着色器、Nanite 与距离场数据；首次准备时间不能作为稳定帧率。验证模式会等 Editor 着色器编译完成后，再开始完整截图等待窗口。

本次 C 盘空间事故来自 `.git/lfs/tmp` 中 314 个失败写入残留，合计约 31.5 GB，并非 UE 缓存。已仅清理该临时目录，保留 LFS 对象和 Git 索引；本仓库的本地 `lfs.storage` 已改为 `D:/OutOfWindowBuildCache/GitLfsCache`，已有缓存对象已复制。该设置不修改全局 Git 配置，也不会随 clone 自动应用。排查期间的只读 Git 命令使用 `git -c filter.lfs.process= -c filter.lfs.required=false status --short`，避免再次触发过滤器的失败写入。

`.runtime/emerald-square-source` 和 `.runtime/helsinki-periphery` 的源缓存已移到上述 `SourceArchives` 下的同名目录，原路径保留为目录 junction，现有脚本仍可使用原路径。这些机器本地缓存不代表将研究用资产纳入 UE 打包内容。

## 资源导入与重建

导出内容是原应用已经组装的五个世界，包括程序生成道路、建筑组合及实例位置。GLB 保存世界变换，JSON 保存相机、车流、水面、风动及灯光语义。实际坐标转换为 `UE(X,Y,Z)=(Three.x,Three.z,Three.y)*100`，单位由米变厘米，只转换一次。运行时依据窗口宽高比，将源垂直 FOV 换算为 UE 水平 FOV。

Bistro 只使用 near GLB 作为街区载体；far GLB 不再重叠导入。画外建筑保留给反射、阴影与 GI。已生成的源文件在 `Migration/Exported`。需要重新导出时，先运行开发服务器，再在另一个终端执行导出和导入：

```powershell
npm run dev -- --configLoader native
```

```powershell
.\node_modules\.bin\electron.cmd .\unreal\Scripts\export-scenes.cjs
.\unreal\Run-Unreal.ps1 -Mode Import
.\unreal\Run-Unreal.ps1 -Mode Build
```

`Import` 使用已编译的 `OutOfWindow.uproject`，依次运行 `import_scenes.py`、`build_window_interiors.py`、`build_surface_materials.py`、`build_precipitation.py`、`build_foam.py`、`build_coast_shoreline.py` 六个步骤，会重建生成区域内的关卡和材质。整窗分组与 UV 必须在表面材质生成前完成。手工修改应放在独立资产，或回写生成脚本。导入器已包含各景太阳方位标签与雾参数；`configure_maps.py` 是给现有地图应用同一配置的维护脚本。

`build_foam.py` 恢复海滨岸边动态泡沫，在保持近岸 Y 边界的前提下把海面扩展至约 2 km 宽、X 中心设为 3,200 cm，向两侧延伸以隐藏侧边界；同时为山林/村庄的六个针叶网格启用 Nanite Preserve Area。实际资产路径和尺寸见 `Migration/foam-repair.json`。这些处理保留原素材，不会增加源贴图分辨率或补出地形细节。

`build_coast_shoreline.py` 随后只修复海滨的程序生成沙地网格：沿东侧 18 m、远侧 24 m 过渡带逐渐把暴露边缘降到海面下，消除矩形沙地的硬切边。它从原 `buildCoast/addTerrain` 的固定种子高度场确定性重建，保留 10,914 个内部顶点、原 UV、材质和 Actor 变换，并重算法线；海面、道路和其他地形不移动。最外边世界高度不高于 −1.40 m，比海面低 0.35 m。相同修正已同步到 `src/main.js`，重复导入不叠加压低。该修正使用工程现有程序几何，没有新增外部素材；两次 UE NullRHI 执行、资产落盘及幂等结果见 [coast-shoreline-repair.json](Migration/coast-shoreline-repair.json)。`Migration/Generated` 中的中间 GLB 可重建并已忽略跟踪。

导入报告如下，表示资产落盘情况，不是性能结果：

| 关卡 | Actor | 独立 Mesh | Nanite Mesh | 传统 LOD Mesh |
| --- | ---: | ---: | ---: | ---: |
| Alley | 1,735 | 1,595 | 1,550 | 45 |
| City | 10,797 | 2,070 | 2,055 | 15 |
| Village | 373 | 46 | 41 | 5 |
| Forest | 131 | 15 | 14 | 1 |
| Coast | 9 | 6 | 6 | 0 |

详细记录为 `Migration/import-*.json`、[资产清单](Migration/asset-inventory.md)及 `Migration/material-probe.json`。不兼容 Nanite 的导入网格使用 100%/50%/20% 三档几何，并按屏幕尺寸选档；兼容网格使用 Nanite 自动细节管理。

## 可复用架构

| 部分 | 职责 |
| --- | --- |
| `WindowGameMode` | 禁用自由移动 Pawn，为任意窗景启动统一 Director。 |
| `WindowDirector` | 相机、时间天气、太阳天空、雾、画质、Slate UI、声音、车流及验证输出；通过 `OOWCamera`、`OOWSun`、`OOWSky` 等标签绑定场景。 |
| `WindowPrecipitation` | 世界空间雨雪及落地飞溅；固定 ISM 由 GPU 材质移动，水花在切景时向下复杂碰撞采样，不做每帧逐粒子碰撞。 |
| `build_window_interiors.py` | 给后巷玻璃生成整窗 UV1 与恒定种子 UV2，标记 `OOWWindowInterior`，为同窗多片玻璃提供连续的室内图坐标；本轮执行和画面验证见独立夜窗记录。 |
| `build_surface_materials.py` | 生成项目内天气材质，保留原纹理/UV，通过材质实例接收湿润、积水、夜灯、风及雨量；仅对已标注叶片/布篷施加风动。 |
| `WindowDesktop` | 独立游戏窗口的 Windows 托盘、显隐、置顶、任务栏、穿透、紧凑模式和单实例；不接管编辑器窗口。 |
| 公共渲染配置 | 五景共用 Lumen、VSM、TSR、Nanite 与纹理流送；禁用静态烘焙光照。 |

固定机位优化使用 Lumen 自身历史和表面缓存。平稳阶段 GI 更新速度为 `0.5`，时间/天气调整后的短暂窗口提高到 `4`，SkyLight 实时捕获启用时间切片。材质天气参数约 10 Hz 更新，太阳、雨雪继续平滑运动；没有把整个 SSR 画面冻结数帧。

三档均保留 Lumen GI/反射，内部渲染比例依次为 70% / 85% / 100%。节能关闭高质量首层透明反射，均衡和精细开启；精细档另启用硬件光追反射 Hit Lighting（`LightingMode=2`），其余使用表面缓存模式（`0`）。三档均已在独立程序中运行，并由 `packaged-alley-eco/clear/fine.json` 回读到对应配置。精细档成本明显增加，实测见下方表格。

新场景提供关卡、相机与光照标签即可复用运行入口；新资产仍须添加语义映射。当前材质分类包含 Bistro/Poly Haven 名称适配，都市车流有既定轨迹，因此不是任意资产零配置适配的 SDK。

## 来源和实际限制

许可总账：[THIRD_PARTY_ASSETS.md](../THIRD_PARTY_ASSETS.md)。ORCA Bistro、Helsinki 远景为 CC BY 4.0，Poly Haven、ambientCG 为 CC0，继承使用的 Three.js 水面法线按原记录保留 MIT 署名。再分发 Content 或打包程序时须附带许可记录和必要署名。研究用 Emerald Square 不在迁移范围内。

夜窗追加了 [六张 AI 生成室内图](Art/WindowInteriors/README.md)，原图均为 1024×1536，提示词完整保留。415 个整窗组消除了已检查夜景中的方格亮灭切割，双扇图像连续。当前 **v5** 使用纹理 `TMGS_BLUR2`、实例有效 `OOWInteriorMipBias=2.0` 和 `OOWInteriorGain=1.8`；UE 构建、审计及最终包夜间/雨夜两例均通过，截图确认更柔和、更明亮的暖光与窗边光晕，外框保持清晰。原图、窗几何和六个采样数量保持不变，仍是没有真实室内几何或视差的 2D 近似。最终证据见 [glow-window-verification.json](Migration/glow-window-verification.json)，各阶段边界见 [夜窗修复记录](Migration/night-window-repair.md)；短测不证明性能提升，历史矩阵保持原记录。

**Nanite 不会补出源资产不存在的细节。** Bistro 载体仍有 157 张 768 px 内嵌图，多数 Poly Haven 贴图来自原来的 1K 素材；导出上限 2048 px 不表示已获得真实 2K 细节。部分 roughness/AO/height 来自基色推导，不等价于测量材质。窗户内部、玻璃厚度、近景破损、自然地形接缝和城市重复布景仍需要美术重做。

海滨矩形沙地断边已通过局部几何修正消除，修正后独立包截图已检查，`coast-clear` 自动复测通过。海滨的源素材和布景仍简单，山林地形素材衔接仍需美术处理。海面扩展、泡沫和针叶 Preserve Area 已有打包证据。自动检查通过不等于美术全面验收，更不等于已经达到 PS5 大作素材精度。

- 首层透明反射及精细档 Hit Lighting 已配置；这不代表每种玻璃都具备正确厚度、高质量透射或多次镜面反弹，仍需材质与预算验证。
- 当前以整张地图切换并保留会话状态；尚未完成后台预取、应用级显存淘汰和大规模 Actor 合批。City 一万多个 Actor 仍有 CPU/光追场景维护成本。
- 大部分窗景设置仅在进程内跨关卡保留；没有完整偏好持久化。天气在启动/刷新时请求；跨 DST 变更依赖再次获取服务 UTC offset，没有本地 IANA 历史时区数据库。
- 环境音为程序噪声占位；雪没有积雪。落雨实体飞溅已实现，沿檐滴水未加入。水花只在真实碰撞命中的朝上静态表面生成，不用悬空平面兜底。
- 独立打包程序的桌面检查 12 项通过，覆盖托盘注册、紧凑尺寸、置顶/任务栏样式、穿透、显隐、最小化及恢复；这是程序调用和 Win32 回读，`humanTrayClickTested=false`，不等于真实鼠标点击托盘/穿透操作通过。完整交互、高 DPI 和逐像素桌面合成仍需验收。透明 Slate 控件不自动等于 Windows 逐像素透明窗口。
- 单实例门禁在进程 `StartupModule` 执行。最终包实测第二实例约 2.43 秒以退出码 0 结束，恢复事件已发送，没有加载重复世界，首个进程仍在运行；真实鼠标与窗口聚焦效果仍按人工交互边界记录。
- 三档画质保留 Lumen，调整 Scalability 与内部渲染比例；尚未承诺 RTX 5060 8 GB 的持续帧率、GPU 毫秒、显存峰值或功耗。

## 验证范围

`Validate` 默认覆盖五景晴天、后巷雨/夜/雨夜/雪/雾/UI，以及都市雨景，共 12 个用例，`CaptureSeconds` 默认 30 秒。测试禁用外部天气请求和音频，默认不启用桌面适配，生成 PNG/JSON，检查场景标签、相机、几何、材质、Lumen 配置和都市 16 辆车的记录。加上桌面程序化检查和节能/精细档，本次 15 例独立程序矩阵全部通过；不等价于手工操作 UI/托盘。

```powershell
.\unreal\Scripts\validate.ps1 -EngineRoot 'D:\Epic\Epic Games\UE_5.7' -Cases 'alley-clear,alley-rain'
# 程序化桌面检查及另外两档画质
.\unreal\Scripts\validate.ps1 -EngineRoot 'D:\Epic\Epic Games\UE_5.7' -Cases 'alley-desktop,alley-eco,alley-fine'
# 验证真正的独立程序；结果文件带 packaged- 前缀
.\unreal\Scripts\validate.ps1 -EngineRoot 'D:\Epic\Epic Games\UE_5.7' -Packaged
# 复现完整 15 例矩阵
.\unreal\Scripts\validate.ps1 -EngineRoot 'D:\Epic\Epic Games\UE_5.7' -Packaged -CaptureSeconds 30 -Cases 'alley-clear,alley-rain,alley-night,alley-rainnight,city-clear,city-rain,village-clear,forest-clear,coast-clear,alley-snow,alley-fog,alley-ui,alley-eco,alley-fine,alley-desktop'
```

2026-09-23 的重测在 Windows 11、RTX 5060 8 GB、DX12/SM6、1280×820 窗口下运行，帧率上限 60，每例运行 30 秒，帧间隔统计排除最初 2 秒。长期保留的证据为 [packaged-verification.json](Migration/packaged-verification.json)：顶层保存首轮完整矩阵与 exe 哈希，`postFix` 保存最终包哈希、两例复测、桌面检查、单实例和联网结果；原始截图/日志在 `.runtime/ue-validation`。以下只引用独立程序重测，不沿用此前可能受其他全屏程序影响的 Editor 数字。

完整 15 例来自首轮包；岸线与进程启动修正后的最终包另测海滨和后巷桌面，结果按构建版本分别记录在验收清单。最终包海滨平均/P95 为 16.67/16.67 ms，桌面例为 16.90/16.67 ms，桌面接口仍为 12/12。最终包正常联网启动也记录 `testMode=false`、`liveTime=true`、`fallbackWeather=false`、`fetchingWeather=false`；第二实例约 2.43 秒退出且未加载重复世界。这些结果不覆盖断网/超时或全部人工交互。

| 后巷用例 | 内部渲染比例 | 平均帧间隔（ms） | P95（ms） |
| --- | ---: | ---: | ---: |
| 晴天·均衡 | 85% | 17.66 | 23.01 |
| 雨天·均衡 | 85% | 18.33 | 33.26 |
| 晴天·节能 | 70% | 16.67 | 16.67 |
| 晴天·精细 | 100% | 40.83 | 53.32 |

精细档平均帧间隔对应约 **24.5 FPS**，高质量反射与更高渲染预算成本明显；本次不是单独隔离 Hit Lighting 的成本测试。节能档在此短测接近 60 FPS 上限，均衡档存在较慢帧，不能声称所有档位持续 60 FPS。全部 15 例的均值/P95、样本数和验证边界见 [Migration/acceptance.md](Migration/acceptance.md)。JSON 的帧间隔不是 GPU timer，30 秒检查也不替代长期运行、功耗和显存峰值测量。
