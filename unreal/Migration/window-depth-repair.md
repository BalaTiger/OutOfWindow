# 后巷窗内景深度修复

日期：2026-09-28。当前材质为 **v14**，窗几何接口为 **window-uv-v4**。目标是消除重点窗的平面贴画感、宽窗图像拉伸及旧布帘遮挡，并为其余适用窗提供有限的房间视差。

**状态：资产复验、编辑器夜景、候选包五例回归、部署及安装后哈希和运行状态核对均通过。** 2026-09-28 21:09 已更新 `D:\OutOfWindowBuild\Windows` 并重启；完整证据索引见 [本轮验收](window-depth-verification.json)。最新 [资产审计](window-interiors-audit.json)记录 68 个窗网格、6 张室内图、4 个真实房间、4 个新透明玻璃、74 个隐藏窗帘、1 个保留的室外雨篷对照及 0 失败。画面验收使用编辑器及候选包截图，安装后另核对 10 个部署文件哈希与正常实时运行状态，没有新增安装版截图。

## 实现范围

| 部分 | 当前实现 |
| --- | --- |
| 四个重点窗 | 中央并排两宽窗、前方红篷下两窗；真实墙面、地板、家具、灯具和静态褶皱窗帘，独立 ThinTranslucent 玻璃。 |
| 其余适用窗 | 材质中求交五面虚拟房间；后墙使用六张既有 AI 图，侧墙、地板和天花板使用简化着色。家具仍是后墙卡片的一部分。 |
| 整窗坐标 | 保留 UV0；UV1 为整窗坐标，UV2 为恒定 `(seed,flag)`，UV3 保存窗宽高（米）。`flag=1` 为普通房间、`2` 为真实房间开孔、`-1` 为禁用发光的非窗面；仍有 393 个房间组。 |
| 图像比例 | 按原始 2:3 做 cover 裁剪；宽窗裁去上下部分，不再横向拉宽家具。六张源 PNG 保持不变。 |
| 反射 | 保留 Lumen 镜面反射和现有局部 HDR 捕获；额外捕获补偿在完全入夜时乘 0.12，避免熄灯窗仅靠暖色补偿就像均匀发光。真实房间开孔处不叠加此补偿。 |
| 灯光预算 | 四个房间各一盏有阴影的 PointLight，窗外 RectLight 从最多 12 盏减为最多 8 盏，局部窗灯合计最多 12 盏。沿用 Director 的夜间渐变。 |

四个房间的稳定 ID 为 `67294f945510fc8a`、`14286f445050f0e5`、`13a26cb6982569b0`、`e8143a4235edd362`，分别采用书房、起居室、起居室、书房布局。移除包围实际点光源的封闭灯泡几何后，当前 [几何报告](hero-rooms.json)合计 20,424 个房间三角面和 8 个玻璃三角面，进深约 3.1–4.185 m；室内灯基准约 135–246 lm，色温 2850–3150 K。这些是当前调校值，不是实测建筑照明。

虚拟房间卡片仍使用六次纹理采样、`TMGS_SHARPEN0`；实例参数为 `OOWInteriorMipBias=0.35`、`OOWInteriorGain=0.8`、`OOWInteriorHighlightGain=2`、`OOWInteriorHighlightThreshold=0.55`。这些值不控制真实房间的照明。原图来源、主题和提示词见 [室内图素材说明](../Art/WindowInteriors/README.md)。

## 开孔与旧几何

原窗材质使用 Masked。初版按四个房间的种子浮点值精确匹配开孔，但 GPU 检查发现 Nanite 的 UV 量化会改变该值，导致图片仍挡在新房间前。`window-uv-v4` 改为在生成几何中显式写入 UV2 `flag=2`，材质按标记开孔，不再要求种子位精确相等。

四个重点窗及右侧窗后约 11.4 cm 的重复玻璃 `2e308641366c36c4` 共五个房间组使用该标记；重复玻璃也必须开孔。普通房间保持 `flag=1`，种子继续用于选择图像和亮灭，非窗面保持 `-1`。66 个旧透明前片保持隐藏，新建的四片透明玻璃单独管理。

三个 `MASTER_Awning_Fabric_Cyan` Actor：`OOW_00728_Paris_Building_08_paris_building_08_9`、`OOW_00739_Paris_Building_08_paris_building_08_9__2_`、`OOW_00751_Paris_Building_08_paris_building_08_9__3_`，实际为室内垂挂布片，之前误走雨篷风动路径。现在与 71 个 `MASTER_Curtains` 一起隐藏，关闭 WPO 和光追可见性，共 74 个；真正的室外 Cyan 雨篷 `OOW_00517_paris_building_04_16` 保留。

`clear_hero_backings.py` 只为 `OOW_00768_paris_building_09_17` 生成副本，移除挡住新房间的两个旧室内组件（20 个三角面），保留其余 228 个面、全部源顶点属性、UV、材质及 Actor 变换。源网格指纹变化时必须重审删除范围；重复构建依据生成哈希识别已应用资产。记录见 [hero-backings.json](hero-backings.json)。源 GLB 和原始 UE 网格保留。

## 重建与验证

完整入口仍为 `unreal/Run-Unreal.ps1 -Mode Import`。窗户相关顺序为：`build_window_interiors.py` → `clear_hero_backings.py` → `build_room_boxes.py` → `build_surface_materials.py`；随后在 UE 中执行 `audit_window_interiors.py`。所有 UE 操作必须串行，已有关卡的局部重建也遵循此顺序。

CPU 检查入口：

```powershell
python unreal/Scripts/build_window_interiors.py --self-test
python unreal/Scripts/clear_hero_backings.py --self-test
python unreal/Scripts/build_room_boxes.py --self-test
python unreal/Scripts/build_surface_materials.py --self-test
python unreal/Scripts/audit_window_interiors.py --self-test
```

资产证据为 [窗几何](window-interiors-geometry.json)、[真实房间](hero-rooms.json)、[旧底板清理](hero-backings.json)、[窗灯](awning-transmission.json)及 [资产审计](window-interiors-audit.json)。这些文件会随重建更新，应核对配方和生成哈希。

| 验证项 | 当前状态 |
| --- | --- |
| UE 资产生成、材质绑定与资产审计 | v4 显式开孔标记修正后通过，0 失败；日志 `apertures.log`。 |
| 编辑器 20:21 夜景 | 通过，四个真实房间已显现；[当前截图](../../.runtime/ue-interior-depth/after-open-2021.png)。 |
| 候选包构建 | 通过；[package.log](../../.runtime/ue-interior-depth/package.log)记录 `BUILD SUCCESSFUL`、ExitCode 0，输出 `D:\OutOfWindowBuildInteriorDepth\Windows`。 |
| 候选包五例回归 | 全部通过：20:21 阴天、16:17 阴天连续 8 帧、12:00 晴天、23:00 晴天及雨天；见 [回归结果](../../.runtime/ue-interior-depth/render-verification.json)。 |
| 窄窗布帘回归 | 16:17 阴天的 [连续 8 帧](../../.runtime/ue-interior-depth/packaged-1617-narrow-window-8frames.png)未见原浅青色布帘穿出。 |
| 部署及安装后复核 | 通过：10 个部署文件哈希全部匹配；正常实时 Alley、非测试模式、12 盏窗灯、约 778.056 lm，见 [安装核对](../../.runtime/ue-interior-depth/installed-verification.json)。 |

候选包均以 1920×1080、Quality 1（内部 ScreenPercentage 85）验证，模拟日期固定为 **2026-09-23**；与 9 月 28 日现场实时天文位置不同。同包级 20:21 阴天对照的平均帧间隔为基准 **16.733 ms**、候选 **16.707 ms**，两者接近 60 FPS 上限，不能据此推断新增几何和灯光的 GPU 成本。宽窗效果见 [同条件打包前后对照](../../.runtime/ue-interior-depth/hero-wide-before-after-crop.png)。

五面虚拟房间没有真实家具几何或完整透射；四个真实房间是简化的固定机位布景，尚非照片级，也未扩展为可进入的整栋建筑。历史实现分别见 [v4/v5 夜窗](night-window-repair.md)、[v6 玻璃与窗灯](window-lookdev-repair.md)、[v13 窗面反射](window-surface-repair.md)，原验收记录保留。
