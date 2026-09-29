# 当代住宅窗框与玻璃雨滴

默认窗型参考当代住宅的喷涂铝窗：大块固定玻璃与右侧约 22% 窄开启扇，配分层型材、EPDM 密封条、竖向执手及浅色窗台。移除 Electron 版中央竖梃加横梃的十字构图。默认外观为 `graphite`，`ivory` 与 `oak` 仍可自由切换；三个外观共用新窗型，选择在会话的场景切换中保留。

[设计参考图](../../docs/desktop-frame/contemporary-reference.png)由内置 image_gen 生成，仅作建筑设计参考，不是 UE 实拍。[完整提示词](../../docs/desktop-frame/contemporary-reference-prompt.txt)保存在项目中；实际运行时不加载此图片。

`AWindowFrame` 是随相机附着的三维 Actor，独立于 Slate。框体含 1,452 个三角形、四种材质槽，全部位于相机前约 81–95.9 cm；独立雨玻璃只有两个三角形，位于 96 cm，由不透明型材自然遮挡。两者均无碰撞。关闭 UI 不会隐藏框体或玻璃雨滴；晴天仅关闭雨玻璃组件。

`Scripts/build_desktop_frame.py` 生成原生 PBR 框材质 `M_DesktopFrame` 与透明雨滴材质 `M_WindowRainGlass`，位于 `/Game/Materials/OOW/DesktopFrame`，随五景统一 Cook。未引入贴图素材或运行依赖。石墨灰表层是非金属喷涂层，金属执手、橡胶与窗台各自使用独立参数。窗框、房间墙体和室内灯使用场景正常光照通道 0；雨玻璃不接收室内灯的直接光。

2026-09-28：删除与云量无关的 `45000 * Daylight` 人工白天补光。白天室内灯为零，窗框直接接收场景太阳、天空光和 Lumen 间接光；阴天亮度由现有天气系统和真实墙体遮挡决定。夜灯使用与街景室内灯一致的黄昏渐变，4000 K，默认 30 lm（沿用现有场景曝光下的亮度校准），支持 `oow.FrameRoomLumens` 调整，设为 0 可关闭。灯位于相机后方 2.5 m、左侧 0.9 m、上方 1.1 m，开启真实阴影和间接光。未调整地图曝光。

新增九块 30 cm 厚的封闭实体墙：四块前墙围成窗洞，另有左右墙、地板、天花板和后墙。相机与灯具在房间内部，窗框嵌入前墙靠外侧，墙厚向室内延伸以保留原有窗景构图。墙体复用原生 Cube 的已构建距离场和 Lumen surface cards；运行时 FastBuild 窗框没有这些数据，不能拿来代替房间的遮光墙。墙体和窗框随视口投影同步适配，保持 UI 隐藏独立性。新增 `-OOWTestCloudCover=100` 可在离线截图模式复现无降水的阴天；审计 JSON 输出 `desktopRoomWalls` 和 `desktopRoomLampLumens`。

另修正了框体与玻璃的三角面绕序：UE 使用 `cross(P2-P0, P1-P0)`，旧绕序与已写入的外法线相反，导致外侧正面被剔除，只见内部暗面和异常亮边。现在保留原有法线/UV，仅反转输出索引。回归检查直接读取最终 RenderData，逐三角核对绕序与顶点法线；原来的几何尺寸和材质加载检查无法发现此错误。夜间改进的最新证据单独记录在 [夜景验证](frame-night-verification.json)，下方旧照片保留为此前版本记录。

玻璃材质以厘米 UV 生成疏密不同的水滴和短水痕，`Time` 驱动滴头沿负 V（向下）滑落，8/16 秒错峰循环；`RainIntensity` 来自实际天气雨量并控制密度。每滴有局部法线与 Pixel Normal Offset 折射，滴外透明且无折射偏移，不叠加整面水膜或模糊。晴天直接关闭透明组件，雨量变化与样式切换不重建网格；仅视口投影改变时重建两张网格。UV 流送数据显式初始化，避免 cooked FastBuild ensure。

节能画质沿用引擎的 `r.RefractionQuality=0`，保留水滴着色与高光；均衡及精细画质具有局部折射。本次不是流体模拟，滴头在小片玻璃内错峰下滑并淡出，未模拟水滴合并或雨停后残留水膜。

自动化用例 `OutOfWindow.Frame.ProjectionAndUIIndependence` 覆盖默认样式、样式切换、雨量限幅、雨晴显隐、玻璃深度、宽窄投影、无碰撞、网格/MID 复用，以及隐藏/恢复 UI 时保留框体和雨玻璃。2026-09-28 新增九面墙体的围合、窗洞与窗框安装交叠、相机与灯位包含、六方向遮挡、实际距离场/Lumen cards、白天关灯、黄昏渐亮及夜灯调校检查。Editor/Game 编译及带渲染的 Frame + UI 两项自动化通过，五项 Editor 实拍（后巷阴天、晴天、夜晚、窄窗及都市雨夜）通过；日志在 `.runtime/ue-frame-room`，原始截图在 `.runtime/ue-validation`。

最终 Windows 成品重新编译并打包成功，后巷阴天与夜间复测通过：阴天云量约 100%，9 块墙体，室内灯 0 lm；夜晚室内灯 30 lm。同一夜景的关灯对照确认实际照明生效，窗框上沿与窗台平均显示亮度分别由约 29 / 20 升至 104 / 186（8 位截图亮度，仅作开关对照，不是物理照度）。对照脚本、读数及关灯截图在 `.runtime/ue-frame-room`；成品截图为 `.runtime/ue-validation/packaged-alley-overcast.png` 和 `packaged-alley-night.png`。

象牙白暗部闪烁复查：材质无动画，切换不重建几何，也未发现可见面的共面冲突。均衡/节能档使用的 UE High GI 预设将屏幕探针间距设为 32 像素，窄窗框暗面的间接光采样不稳定，浅色无纹理表面更容易显露波动。增加探针射线数、关闭短程 AO/反射或缩小上采样抖动均无同等改善；16 像素与更昂贵的 8 像素间距效果接近。因此仅在 `DefaultEngine.ini` 将间距固定为 16 像素，保留自然光、真实遮挡和材质参数。

最终成品在固定阴天、预热 30 秒、同负载的 32 帧对照中，右侧暗框相邻帧亮度差均值由约 1.09 降至 0.17，减少约 85%（0–255 显示亮度），该区域平均亮度为 45.02 / 44.80。这验证了时序稳定性的改善，而非靠压暗材质隐藏闪烁。雨天连续帧、象牙白夜景也通过检查，启动日志确认实际为 `DownsampleFactor=16`、来源 `SystemSettingsIni`。区域统计与消融对照保存在 `.runtime/ue-frame-flicker/final-comparison.json` 等文件；短序列指标不代表所有动态场景均完全无噪声。

以下为加入实体房间前的历史成品实拍，使用旧的室内补光模型：[后巷夜晚](../../docs/desktop-frame/night-room-lit-alley.png)、[都市雨夜](../../docs/desktop-frame/night-room-lit-city.png)、[海岸夜晚](../../docs/desktop-frame/night-room-lit-coast.png)、[后巷白天](../../docs/desktop-frame/day-corrected-frame.png)。旧版验证见 [夜景验证](frame-night-verification.json) 和 [窗型与雨滴验证](desktop-frame-verification.json)。

成品实拍：[都市雨天，UI 已隐藏](../../docs/desktop-frame/contemporary-rain.png)、[连续雨滴动画](../../docs/desktop-frame/contemporary-rain-motion.mp4)。动画由 8 张成品原始截图按 0.5 秒间隔编码，未插帧、未合成雨滴。场景几何、照明仍以 UE 实拍为准，不等同于生成参考图中的建筑。

渲染检查示例：`Scripts/validate.ps1 -EngineRoot 'D:/Epic/Epic Games/UE_5.7' -Packaged -Cases 'city-rainglass,alley-hiddenui,alley-narrow,city-rainnight' -CaptureSeconds 15`。`rainglass` 在雨天隐藏 UI，并连续保存 8 张相隔 0.5 秒的截图；验证脚本还检查雨量、窗框状态、截图时效、材质回退和运行时 ensure。

旧十字窗框的首轮证据保留于 [历史验证记录](desktop-frame-v1-verification.json)，其中图片与尺寸不代表当前默认设计。
