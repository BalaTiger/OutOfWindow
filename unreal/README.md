# Out of Window — UE5 原生工程

工程入口：[OutOfWindow/OutOfWindow.uproject](OutOfWindow/OutOfWindow.uproject)。当前使用本机 **Unreal Engine 5.7.4**，都市、后巷、村庄、山林、海滨分别导入五张关卡。原 Electron/Three.js 工程保留，作为资产来源与行为对照。

本次选择 UE5，是为了直接采用成熟的 **Lumen 动态 GI/反射、Nanite、Virtual Shadow Maps、TSR、DX12/SM6**；硬件支持时使用 Lumen 硬件光追。固定机位的缓存优化建立在这些公共系统上。Lumen 本身支持光照缓存及更新速度控制，Nanite 管理已有几何的细节与流送。[Lumen 官方说明](https://dev.epicgames.com/documentation/en-us/unreal-engine/lumen-global-illumination-and-reflections-in-unreal-engine)、[Nanite 官方说明](https://dev.epicgames.com/documentation/en-us/unreal-engine/nanite-virtualized-geometry-in-unreal-engine)

**Windows Development 成品已成功打包，首轮 15 个独立程序用例全部通过自动检查。** 入口为 `D:\OutOfWindowBuild\Windows\OutOfWindow.exe`。完整矩阵在 Cook 完成后串行运行，每例 30 秒，覆盖五景、天气、三档画质与桌面接口。岸线和单实例启动逻辑修正后的最终包也通过海滨、桌面、正常联网与第二实例补测。精细档后巷平均约 24.5 FPS，尚不适合作为本机 60 FPS 档位；山林地形素材与完整人工交互仍有待完善。证据和边界见 [迁移验收清单](Migration/acceptance.md)。

2026-09-28：后巷夜窗更新为 v14 / `window-uv-v4`。四个重点窗使用带家具、实际灯光与透明玻璃的浅房间，其余适用窗户使用五面虚拟房间和保比例裁剪的后墙图，UV3 保存窗宽高。四个窗及其一片重复玻璃用 UV2 的 `flag=2` 开孔，避免 Nanite UV 量化破坏种子精确匹配。74 个源窗帘与 66 个旧透明叠层隐藏，真正的室外雨篷保留；局部窗灯预算为 4 盏室内 PointLight 加最多 8 盏窗外 RectLight。**资产审计、编辑器夜景、候选包五例回归、部署及安装后哈希和正常运行核对均通过。** 画面验证为 1920×1080、Quality 1、固定 2026-09-23，安装后没有另拍截图；四个真实房间仍是简化布景，尚非照片级。范围和证据见 [窗内景深度修复](Migration/window-depth-repair.md)及 [本轮验收](Migration/window-depth-verification.json)；此前 [v13 窗面反射记录](Migration/window-surface-repair.md)保留为历史。

**2026-09-29 最新后巷覆盖：** v16 / `window-uv-v5` 已部署。15 个物理窗洞使用简化 3D（UE 实际 9,520 面），17 个源组使用校准 cubemap IM，其余背景窗使用基础 IM；停用旧整张透视照片后墙，实时灯保持 12 盏。六组候选回归及安装哈希、正常重启通过；同设置单轮 GPU 中位数为 13.79 → 9.22 ms。详见 [逐窗改造及验收](Migration/window-interior-mapping.md)。上面的 v14 内容保留为历史。

**2026-10-01 后巷雨云修正（Editor 预览）：** 原生简单体积云的 `StormClouds` 参数没有生成积雨云塔体与砧部，密集雨云的阴影又让暗后巷自动曝光抬高天空亮度；原先雨天还比晴天增加 0.6 EV。相同曝光 A/B 中，替换为带云底、塔体与砧部包络的三维风暴云团后，天空明暗恢复；只降低曝光、关闭雾或 Bloom 都没有补出所需形态。当前默认加载项目云材质，风暴权重低时保留原生云分支，并把后巷阴雨曝光从 −0.5 调回 −1.1 EV；夜间参数保持原值。原始色调的三组 [对照图](Art/Lookdev/alley-storm-ab.png)分别展示修正前、同曝光换云形与最终方案。屋顶间约 2.4% 的天空开口能看到云底和体积明暗，尚不能据此声称完整塔状、砧状轮廓在该机位可见。

Editor 构建、晴天原生对照、夜间、小雨／中雨／大雨、四帧风漂移及海滨雨天专项检查通过，材质生成脚本能幂等复用资产。RTX 3060 Ti、2560×1440、均衡档单轮正常步长对照的 GPU 中位耗时为 19.39 → 20.30 ms（约 +0.90 ms）；测试冻结云运动，未完成长期动画性能评估。本轮没有重新打包或部署独立程序。完整回归在既有风动断言停止：原生和新云方案均为 126 个风动组件中有 123 个参与计算。证据、指标口径和测试限制见 [雨云验证记录](Migration/alley-storm-verification.json)。复测使用 `Scripts/cloud-ab.ps1`，原生临时回退入口为 `-OOWNativeClouds`；资产由 `Scripts/build_storm_clouds.py` 生成，已加入 Import。

**同日后续，当前云内层次为 v3（Editor 预览）：** v2 云内核的密度夹紧使两个噪声层均失效，只留下边缘和大范围云底渐变。v3 保留云色、AO、相函数、宏观云团包络及两次体积纹理读取，在内部增加真实密度起伏和低密度孔隙；选用 0.35 km 细节尺度，运行时密度倍率 1.35，以保留较厚的雨云观感。固定 EV8、实际眼适应曝光完全一致且关闭雨玻璃的 [前后对照](Art/Lookdev/alley-storm-details-ab.png)确认云内团块来自材质；正常自适应曝光下天空会因云更透光而比 v2 明亮，不能把这组亮度变化归因于曝光补偿。晴天原生对照、夜间、午后、中雨、八帧移动和海滨检查通过。v2→v3 的单轮 2560×1440 GPU 中位耗时为 20.20 → 20.89 ms（约 +0.69 ms）；仍未重新打包，原有 123/126 风动断言保留。新资产生成入口 `Scripts/build_storm_details.py` 已加入 Import，v2 作为诊断基线保留；复测可加 `-NoRainGlass -FixedExposureEV 8`，`Scripts/cloud-detail-report.py` 提供统一天空区域的去线性渐变指标，但该指标不代替画面评估。[本轮验证记录](Migration/alley-storm-details-verification.json)保存候选取舍、GPU CSV 来源和限制。

## 启动与构建

应用默认嵌入 Windows 桌面图标后方，作为动态桌面启动。右上角此时显示「还原」按钮；点击后恢复普通窗口和原来的位置、尺寸，按钮变为「最大化」，再次点击回到动态桌面。动态桌面按显示器完整尺寸铺满，不使用扣除任务栏后的工作区。托盘的显示／隐藏保持当前模式；退出后重新启动仍默认进入动态桌面。

当前桌面模式的实现与验收见 [动态桌面说明](Migration/desktop-mode.md)。下文迁移首轮结果中的置顶、穿透和紧凑模式仅为旧版历史记录。

界面右上角的眼睛按钮可隐藏整套 UI，保留窗景、实体窗框和原窗口尺寸。按 `Esc` 恢复界面；也可将鼠标移回眼睛原来的位置，显示闭眼按钮后点击恢复。鼠标移开时该按钮再次隐藏。原「穿透」「收起／精简尺寸」及对应托盘功能已移除；设置面板自身的折叠按钮仍保留。

前景窗框是独立的 `AWindowFrame` 三维 Actor，不属于 Slate UI，也不烘入地图。默认采用当代住宅石墨灰喷涂铝窗：大块固定玻璃、右侧约 22% 的窄开启扇、分层压条、密封条、竖向执手和浅色窗台，取消 Electron 旧版的中央十字分格。设置仍可选择烟熏橡木、象牙白、石墨灰，选择跨关卡保留。原生 PBR 材质接收自然光与有阴影的夜间室内照明；框体为 1,452 个三角形，位于相机前 81–95.9 cm。仅视口投影改变时重建，相机参考宽高比也同步，避免二次 FOV 换算裁掉窗框。

雨天在框体后 96 cm 的独立玻璃平面上显示局部折射水滴、静止小水珠和短水痕。水滴由材质 Time 沿玻璃向下运动，雨量控制密度，厘米 UV 保持横窄屏的水滴尺寸；晴天关闭透明组件。窗框和雨滴均不受「隐藏 UI」影响，也不参与碰撞。节能档沿用引擎关闭折射的设置，保留水滴着色与高光；均衡及精细档具有局部折射。

窗框安装在带真实窗洞的 30 cm 厚墙体中，侧墙、地板、天花板和后墙包围相机及室内灯。白天关闭室内灯，由场景太阳、天空光及 Lumen 间接光照亮；阴天沿用场景云量响应，不再额外叠加 45,000 lm 补光。夜晚渐亮 4000 K 室内灯，参与真实阴影和间接光，亮度保留 `oow.FrameRoomLumens` 调校入口。[窗框说明与验证](Migration/desktop-frame.md)。

材质生成入口为 `Scripts/build_desktop_frame.py`，输出 `/Game/Materials/OOW/DesktopFrame` 下的 `M_DesktopFrame` 和 `M_WindowRainGlass`，已加入 Import 和 Cook。外观接口为控制台 `OOWFrame oak|ivory|graphite` 或启动参数 `-OOWFrame=ivory`，未知 ID 保持当前选择。仅渲染诊断可在 `-OOWCapture=...` 时加 `-OOWTestNoFrame` 去框；`-OOWTestHideUI -OOWCaptureUI` 则隐藏界面并保留框和雨滴。`validate.ps1 -Cases 'city-rainglass,alley-hiddenui,alley-narrow'` 同时检查连续雨滴截图、晴天和窄屏。设计参考与成品证据见 [窗框验收记录](Migration/desktop-frame.md)。

地理位置可在右下角「地理位置」菜单中设置。默认关闭 IP 跟踪，使用可修改的上海初始位置；输入位置名称、纬度、经度和离线 UTC 时差后点击「保存并更新天气」。只有勾选「跟随 IP 位置」才请求 IP 城市级定位；VPN、代理或运营商出口可能导致定位偏差。手动模式直接按指定坐标查询天气，联网后自动校准当地时区；网络失败保留所选位置并标记天气为离线示例。选择保存在本机 GameUserSettings.ini 的 OutOfWindow.Location 节，跨场景和重启保留。关闭 IP 跟踪后仍会向天气服务发送手动指定的坐标。

右下角设置面板沿用 Electron 版的圆角玻璃背景、时间渐变滑条、天气分段按钮、画质下拉框与五张场景缩略图；缩略图随 UE 成品一起打包。

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

`Import` 使用已编译的 `OutOfWindow.uproject`，按 `Run-Unreal.ps1` 中的脚本顺序重建生成区域内的关卡和材质。窗户部分依次生成整窗 UV、清理真实房间后的旧底板、生成四个真实房间，再生成表面材质；后巷风化层和局部贴花在基础表面材质之后生成。手工修改应放在独立资产，或回写生成脚本。导入器已包含各景太阳方位标签与雾参数；`configure_maps.py` 是给现有地图应用同一配置的维护脚本。

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
| `build_window_interiors.py` | 给后巷玻璃生成整窗 UV1、恒定种子 UV2 和宽高 UV3，保留源 UV0；材质以此提供连续图像、开孔和虚拟房间视差。 |
| `clear_hero_backings.py` / `build_room_boxes.py` | 保留源资产，生成去除必要旧底板的副本，以及十五个带家具和独立玻璃的简化房间。 |
| `build_interior_atlas.py` | 在独立关卡离线烘焙六种室内 HDR cubemap，使用与运行时相同的房间盒体及捕获坐标；此步骤需要真实 RHI。 |
| `build_surface_materials.py` | 生成项目内天气材质，保留原纹理/UV，通过材质实例接收湿润、积水、夜灯、风及雨量；仅对已标注叶片/布篷施加风动。 |
| `WindowDesktop` | 独立游戏窗口的 Windows 动态桌面嵌入、还原／最大化切换、托盘、显隐和单实例；不接管编辑器窗口。 |
| 公共渲染配置 | 五景共用 Lumen、VSM、TSR、Nanite 与纹理流送；禁用静态烘焙光照。 |

固定机位优化使用 Lumen 自身历史和表面缓存。平稳阶段 GI 更新速度为 `0.5`，时间/天气调整后的短暂窗口提高到 `4`，SkyLight 实时捕获启用时间切片。材质天气参数约 10 Hz 更新，太阳、雨雪继续平滑运动；没有把整个 SSR 画面冻结数帧。

三档画质均保留双面材质的独立背面 GI，避免节能／均衡档将后巷红色雨棚照成粉白并放大周围墙面提亮。该设置在每次应用画质后恢复，运行审计和渲染验收会检查实际值；原贴图、透射参数及其他画质选项保留。修改、原生分辨率回归及 GPU 对照见 [雨棚阴天修正](Migration/awning-overcast-repair.md)。

体积云按主画面实际深度估算可见天空面积，包含建筑、Nanite 几何和窗框遮挡。每 2 秒异步读取 128×72 深度缩略图，结合内部渲染像素数平滑分配采样：天空较少时提高精度，开阔天空和高分辨率时按预算降低；节能／均衡／精细分别限制在 0.5–1／1–2／1.5–3 倍。保留 Mode0 时间重建，将云样本分配距离设为 5 km；`oow.CloudSampleBudget` 可调参考像素预算，默认 200000。它是工作量近似，不保证固定 GPU 耗时。

实时标签直接区分气象服务的晴、晴间多云、多云、阴，以及小／中／大雨雪；毛毛雨、冻雨、阵雨、阵雪和雷暴保留具体类型，未知天气码显示「未知」。预览提供实时、晴、多云、阴、雨、雪、雾，选择雨雪后可切换小／中／大并改变粒子强度；旧 `OOWWeather rain|snow` 命令仍表示中等强度。普通多云不再自动混入雨云材质。实现与本机验证见 [自适应天空与天气分级](Migration/adaptive-cloud-weather.md)。

后巷风动采用 v8 材质，恢复原版米到厘米换算后的树冠摆动、叶片轻颤和窗蓬下缘起伏，保留顶部／根部固定点，并随风速、风向与雨量变化。导入材质残留的 WPO `UseConstant` 标记曾使已连接的动画图仍编译为零位移；生成脚本通过 `WindowMaterialLibrary.EnableConnectedWorldPositionOffset` 按 UE-219232 的编辑器处理方式清除该标记，重用旧材质和重新生成时均自动修复。`WindowBirds` 在晴天白昼间歇生成 1–3 只远处飞鸟，复用 9 个组件和两份原创小网格，随后间隔 25–50 秒；夜间、雨雪雾及强风停飞。连续画面检查可在已有 `-OOWCapture=...png` 验证命令后追加 `-OOWCaptureFrames=64 -OOWCaptureInterval=0.1`，中间帧带数字后缀，最后一帧及审计 JSON 保留原路径；`Scripts/inspect_alley_motion.py` 对比叶片、窗蓬边缘和静态墙面，避免把单张截图误当作动画验证。

三档均保留 Lumen GI/反射，内部渲染比例依次为 70% / 85% / 100%。节能关闭高质量首层透明反射，均衡和精细开启；精细档另启用硬件光追反射 Hit Lighting（`LightingMode=2`），其余使用表面缓存模式（`0`）。三档均已在独立程序中运行，并由 `packaged-alley-eco/clear/fine.json` 回读到对应配置。精细档成本明显增加，实测见下方表格。

新场景提供关卡、相机与光照标签即可复用运行入口；新资产仍须添加语义映射。当前材质分类包含 Bistro/Poly Haven 名称适配，都市车流有既定轨迹，因此不是任意资产零配置适配的 SDK。

## 来源和实际限制

后巷地面与石材使用 v9 雨湿材质：浅积水保持平滑水面，雨量控制覆盖范围，墙面增加局部湿痕，并修正带落叶路面的分类。可用 `Scripts/validate.ps1 -EngineRoot 'D:\Epic\Epic Games\UE_5.7' -Packaged -Cases alley-lightrain -CaptureSeconds 60` 复测固定小雨；实现与验证见 [后巷湿表面修复](Migration/wet-surface-repair.md)。

后巷两面可见主墙增加抹灰／裸露砂浆的多通道混合，以及三处窗台旧流痕贴花；原雨湿响应继续保留。素材和完整生成提示词见 [墙面风化素材](Art/AlleyWeathering/README.md)，构建记录为 `Migration/alley-weathering.json`、`Migration/alley-weathering-decals.json`。

许可总账：[THIRD_PARTY_ASSETS.md](../THIRD_PARTY_ASSETS.md)。ORCA Bistro、Helsinki 远景为 CC BY 4.0，Poly Haven、ambientCG 为 CC0，继承使用的 Three.js 水面法线按原记录保留 MIT 署名。再分发 Content 或打包程序时须附带许可记录和必要署名。研究用 Emerald Square 不在迁移范围内。

夜窗 v16 / `window-uv-v5` 按可见面积、角度和遮挡需求分配：15 个物理窗洞使用简化 3D；17 个源组使用从六种真实布局离线烘焙的 HDR cubemap，其余源组使用无家具的基础 Interior Mapping。射线与校准盒体求交后按捕获中心采样，不再把完整透视照片贴在后墙。实体房共约一万个三角形，实时灯总预算仍为 12。素材及边界见 [室内烘焙说明](Art/InteriorMapping/README.md)，实施、验证与部署状态见 [逐窗改造记录](Migration/window-interior-mapping.md)。[旧 AI 图](Art/WindowInteriors/README.md)及 [v14 记录](Migration/window-depth-repair.md)仅保留历史，不作为当前版本结论。

**Nanite 不会补出源资产不存在的细节。** Bistro 载体仍有 157 张 768 px 内嵌图，多数 Poly Haven 贴图来自原来的 1K 素材；导出上限 2048 px 不表示已获得真实 2K 细节。部分 roughness/AO/height 来自基色推导，不等价于测量材质。窗户内部、玻璃厚度、近景破损、自然地形接缝和城市重复布景仍需要美术重做。

海滨矩形沙地断边已通过局部几何修正消除，修正后独立包截图已检查，`coast-clear` 自动复测通过。海滨的源素材和布景仍简单，山林地形素材衔接仍需美术处理。海面扩展、泡沫和针叶 Preserve Area 已有打包证据。自动检查通过不等于美术全面验收，更不等于已经达到 PS5 大作素材精度。

- 首层透明反射及精细档 Hit Lighting 已配置；这不代表每种玻璃都具备正确厚度、高质量透射或多次镜面反弹，仍需材质与预算验证。
- 当前以整张地图切换并保留会话状态；尚未完成后台预取和应用级显存淘汰。2026-09-24 的现代 City 重构及天际线补完后，保存地图为 137 个 Actor，树木使用一个实例组件；当前构图、素材和独立窗框约定见 [现代都市场景](Migration/city-modern.md)。其他场景没有因此完成全局合批。
- 大部分窗景设置仅在进程内跨关卡保留；没有完整偏好持久化。天气在启动/刷新时请求；跨 DST 变更依赖再次获取服务 UTC offset，没有本地 IANA 历史时区数据库。
- 环境音为程序噪声占位；雪没有积雪。落雨实体飞溅已实现，沿檐滴水未加入。水花只在真实碰撞命中的朝上静态表面生成，不用悬空平面兜底。
- 独立打包程序的桌面检查 12 项通过，覆盖托盘注册、紧凑尺寸、置顶/任务栏样式、穿透、显隐、最小化及恢复；这是程序调用和 Win32 回读，`humanTrayClickTested=false`，不等于真实鼠标点击托盘/穿透操作通过。完整交互、高 DPI 和逐像素桌面合成仍需验收。透明 Slate 控件不自动等于 Windows 逐像素透明窗口。
- 单实例门禁在进程 `StartupModule` 执行。最终包实测第二实例约 2.43 秒以退出码 0 结束，恢复事件已发送，没有加载重复世界，首个进程仍在运行；真实鼠标与窗口聚焦效果仍按人工交互边界记录。
- 三档画质保留 Lumen，调整 Scalability 与内部渲染比例；尚未承诺 RTX 5060 8 GB 的持续帧率、GPU 毫秒、显存峰值或功耗。
- 动态体积云已接入天气风、雨层云与云影；City 补齐道路尽头和塔楼根部的中景楼群。最新实机截图、30秒云运动与晴雨性能对照见 [天气天空与城市远景补完](Migration/city-weather.md)。
- 都市车流改为按前车间距减速、留足邻道前后空隙后平滑超车，修复快车直接重叠；动画参数、长期仿真及实机验证见 [都市车流动画修正](Migration/city-traffic.md)。
- 都市幕墙夜灯按楼层内的连续办公区分组，边缘渐暗并保留邻区借光；不再逐窗随机开关。白天基色、建筑几何和独立窗框接口保持原有设计，见 [都市连续办公区夜灯](Migration/city-office-night.md)。
- 都市雨夜修正过长近镜头雨线，扩大道路照明，补上远景楼灯和随车转向的锥形前照灯；见 [都市雨夜与道路照明修正](Migration/city-night-weather.md)。

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
