# 后巷夜窗、玻璃与雨篷修正

日期：2026-09-24。本文记录当前 v6 配方和重建接口。**最终打包、资产审计和四例独立程序回归已通过**：后巷夜间、雨夜、白天及都市夜间。完整数据与产物证据见 [window-lookdev-verification.json](window-lookdev-verification.json)。[AI 全景目标](../Art/Lookdev/README.md)只用于美术参考，不是 UE 实机截图。

实际 v6 截图：[后巷夜间](../Art/Lookdev/alley-night-implemented-v6.png)、[后巷雨夜](../Art/Lookdev/alley-rainnight-implemented-v6.png)、[后巷白天](../Art/Lookdev/alley-day-implemented-v6.png)。

## 根因与几何边界

v5 把部分 U 形窗洞包边及进深侧壁识别成室内面；将其标成普通回退仍会触发旧窗发光。`window-uv-v2` 因此采用明确的负标记，禁用 26 个包边组件的 259 个三角面及另外 52 个非窗面，剩余 393 个房间组。组数不等于固定机位可见或亮灯的窗数。

原室内网格顶点和 UV0 保持不变。UV1 为整窗连续图像坐标，底部 0、顶部 1，材质采样 `1-V`；同窗所有片共用恒定 UV2=`(seed,flag)`，`1` 是房间、`-1` 禁用一切窗发光、`0` 仅供未标记旧窗回退。房间变体、亮灭、色温和亮度依赖整窗种子，不使用逐像素世界坐标随机开关。

68 个 Actor 使用室内接口，其中 66 个有独立玻璃前层及对应后层标签。前层仅复制真窗片，沿源外法线偏移 1 cm，并排除近重合重复片；关闭 Nanite，使用三档原生 LOD，不投射阴影。未把整楼玻璃统一外移或放大。

## 当前材质与照明

| 项目 | 当前配置与作用 |
| --- | --- |
| 室内图 | 六张原始 1024×1536 AI PNG 保留；sRGB、Clamp、`STRETCH_TO_POWER_OF_TWO`、`TMGS_SHARPEN0`，没有 padding 黑边或源图像素修改。 |
| v6 室内实例 | `OOWInteriorEnabled=1`、`OOWInteriorMipBias=1.5`、`OOWInteriorGain=0.8`、`OOWInteriorHighlightGain=8`、`OOWInteriorHighlightThreshold=0.32`。 |
| 室内分层 | 六次纹理采样供底图和亮度曲线共同使用，单独提高灯具高亮；`Night=0` 时室内发光为零。主材质初始 Bias / Gain / Highlight 为 1 / 0.6 / 4，实际值由实例覆盖。 |
| 玻璃前层 | 原生 ThinTranslucent、Translucent、SurfaceForwardShading，双面；无自发光，介电 F0 约 0.04，干燥粗糙度 0.07，湿润时增加至 0.09。透射颜色为 `(0.95,0.97,0.98)`。 |
| 玻璃后层 | 室内图仍在不透明后层；有独立前层时不重复施加 Fresnel 衰减。没有独立前层的室内仍使用视角衰减近似。 |
| 雨篷 | 原生 TwoSidedFoliage / 双面，以原 albedo、视角光程和指数吸收控制 SubsurfaceColor；实例 `OOWAwningTransmission=0.2`、`OOWAwningOpticalDepth=0.65`，不添加自发光。旧主材质可能仍保留 0.7 默认值，应检查叶级实例解析值。 |
| 局部窗灯 | 最多 12 盏 Movable RectLight，当前计划 12 盏；亮度 `2 lm × gain`，gain 由同窗 seed 在 0.8–1.2 间确定，半径 400 cm。有阴影、启用 transmission、体积散射为 0；只选亮灯房间，并与室内共用夜间渐变。 |
| 夜间后处理 | `OOWWindowLookdev` 体积按夜间渐变到 BloomIntensity 1.3、BloomSizeScale 5.5、曝光补偿 -1.15；对应 CVar 为 `oow.NightBloom`、`oow.NightBloomSize`、`oow.NightExposureBias`。 |

雨篷白亮的诊断中，关闭镜面反射仍然偏白，关闭直接光后恢复红色，因此局部窗灯从较高亮度下调至当前值。UE TwoSidedFoliage 的透射分支确实乘以 SubsurfaceColor；透射强度并不同时缩放普通直接漫反射，不能仅靠降低透射参数解决照明过曝。最终颜色与光晕可对照上方实机截图和验证记录。

只有 `OOW_00770_paris_building_09_19` 百叶组件建立独立双面材质实例并开启双面投影，标签为 `OOWThinShadowCaster`，用于修复单面片背面的遮挡。未修改全局阴影 bias；灯光资产实际读回 shadow bias 0.5、slope bias 0.5、contact shadow length 0、光追阴影 `UseProjectSetting`。源叶片仍是带纹理的平面，不能承诺立体叶片或条纹阴影。

## 可复用接口

| 标签 / 接口 | 含义 |
| --- | --- |
| `OOWWindowInterior` | 明确启用整窗 UV1/UV2 室内接口；不能只依赖不存在的 UV2 通道可能回退出的值。 |
| `OOWWindowGlassFront` | 独立原生透明玻璃前层。 |
| `OOWWindowGlassBacking` | 对应室内后层，禁止重复玻璃衰减及非房间回退发光。 |
| `OOWNightLight` + `OOWInteriorLight` | 运行时缓存灯光基准强度，按室内同一 `smoothstep(.58,.86,Night)` 渐变。 |
| `OOWRoom_<id>` | 局部窗灯关联确定的整窗组。 |
| `OOWWindowLookdev` | 仅对标记后处理体积应用本轮夜间校准。 |

`build_surface_materials.py` 只给标记室内、玻璃前层和雨篷使用 v6；旧窗保持 v3，其他表面保持 v2。`window_lookdev.py` 的 `add_awning_transmission()` 接入已有表面材质，保留原粗糙度、法线和风动；`configure_window_lighting()` 按房间报告配置局部灯与标签，`audit_window_lighting()` 读回实际资产。新场景复用时必须先提供正确的整窗分组与标签，不能仅按名称给所有玻璃启用。

纹理柔化、镜头 bloom 和窗台/布篷受光分别由采样、后处理和场景照明负责。原生前层提供玻璃响应，但背后家具、墙和灯仍是 2D 图像，没有室内视差、真实遮挡或可进入空间。

## 重建与验收

在仓库根目录执行，串行运行 UE，避免多个进程同时写同一资产。完整重建入口为 `unreal/Run-Unreal.ps1 -Mode Import`；它先导入源关卡，再运行窗几何与材质等六个生成步骤。已有地图仅重建本轮资产时：

```powershell
$ue = 'D:\Epic\Epic Games\UE_5.7\Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
$project = (Resolve-Path 'unreal\OutOfWindow\OutOfWindow.uproject').Path
$env:OOW_MATERIAL_SCENES = 'alley'
foreach ($name in @('build_window_interiors.py', 'build_surface_materials.py', 'audit_window_interiors.py')) {
    $scriptPath = (Resolve-Path "unreal\Scripts\$name").Path
    & $ue $project -run=pythonscript "-script=$scriptPath" -unattended -nop4 -nosplash -NullRHI
    if ($LASTEXITCODE -ne 0) { throw "Failed: $name" }
}
Remove-Item Env:\OOW_MATERIAL_SCENES
.\unreal\Run-Unreal.ps1 -Mode Build
.\unreal\Run-Unreal.ps1 -Mode Package
```

几何必须先于材质。NullRHI 审计不替代 GPU 验证；旧打包程序也不会自动包含新资产。资产证据使用 [window-interiors-geometry.json](window-interiors-geometry.json)、[window-interiors-audit.json](window-interiors-audit.json)及 [awning-transmission.json](awning-transmission.json)，这些报告会随重新生成更新。

最终资产审计为 0 失败，读回 66 个玻璃前层、68 个室内 Actor、6 张纹理及 12 盏局部灯。四个打包回归用例 `alley-night`、`alley-rainnight`、`alley-clear`、`city-night` 均通过，帧间隔 P95 均约 16.7 ms；这是应用帧间隔，不是 GPU timer，也不是全场景长期性能保证。

固定机位截图用于检查负标记包边、玻璃反射、房间连续性、红篷颜色、百叶遮挡及昼夜变化。`finalViewPostProcess` 记录最终 bloom、曝光补偿和曝光适应读回。打包状态、产物哈希、逐例结果及准确帧时间以 [window-lookdev-verification.json](window-lookdev-verification.json) 为准；没有重跑或覆盖此前全部迁移验收矩阵。

[v4/v5 夜窗记录](night-window-repair.md)与对应旧包验证保留为历史。其 415 房间组、Blur2 / 2.0 / 1.8 等计数或参数属于旧配方，不能混用为当前 393 房间组与 v6 的证据。
