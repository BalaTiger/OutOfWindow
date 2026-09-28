# 当代住宅窗框与玻璃雨滴

默认窗型参考当代住宅的喷涂铝窗：大块固定玻璃与右侧约 22% 窄开启扇，配分层型材、EPDM 密封条、竖向执手及浅色窗台。移除 Electron 版中央竖梃加横梃的十字构图。默认外观为 `graphite`，`ivory` 与 `oak` 仍可自由切换；三个外观共用新窗型，选择在会话的场景切换中保留。

[设计参考图](../../docs/desktop-frame/contemporary-reference.png)由内置 image_gen 生成，仅作建筑设计参考，不是 UE 实拍。[完整提示词](../../docs/desktop-frame/contemporary-reference-prompt.txt)保存在项目中；实际运行时不加载此图片。

`AWindowFrame` 是随相机附着的三维 Actor，独立于 Slate。框体含 1,452 个三角形、四种材质槽，全部位于相机前约 81–95.9 cm；独立雨玻璃只有两个三角形，位于 96 cm，由不透明型材自然遮挡。两者均无碰撞。关闭 UI 不会隐藏框体或玻璃雨滴；晴天仅关闭雨玻璃组件。

`Scripts/build_desktop_frame.py` 生成原生 PBR 框材质 `M_DesktopFrame` 与透明雨滴材质 `M_WindowRainGlass`，位于 `/Game/Materials/OOW/DesktopFrame`，随五景统一 Cook。未引入贴图素材或运行依赖。石墨灰表层是非金属喷涂层，金属执手、橡胶与窗台各自使用独立参数。室内补光仅影响窗框的通道 1，雨玻璃不接收这盏补光。

夜间按室内始终开灯处理：使用原生 4000 K 柔和暖白色温，保留稳定室内补光基线；光源位于相机后方 2.5 m、上方 1.4 m，朝向窗体，白天追加柔和补光。夜间采用 30 lm 的有效窗边填充量，这是未建模房间漫反射的近似，不代表真实室内灯具的总流明。调校入口为 `oow.FrameRoomLumens`。补光只作用于实体框体，关闭间接光、透明物体和体积雾贡献，隐藏 UI 不改变灯光。没有修改地图曝光设置。

另修正了框体与玻璃的三角面绕序：UE 使用 `cross(P2-P0, P1-P0)`，旧绕序与已写入的外法线相反，导致外侧正面被剔除，只见内部暗面和异常亮边。现在保留原有法线/UV，仅反转输出索引。回归检查直接读取最终 RenderData，逐三角核对绕序与顶点法线；原来的几何尺寸和材质加载检查无法发现此错误。夜间改进的最新证据单独记录在 [夜景验证](frame-night-verification.json)，下方旧照片保留为此前版本记录。

玻璃材质以厘米 UV 生成疏密不同的水滴和短水痕，`Time` 驱动滴头沿负 V（向下）滑落，8/16 秒错峰循环；`RainIntensity` 来自实际天气雨量并控制密度。每滴有局部法线与 Pixel Normal Offset 折射，滴外透明且无折射偏移，不叠加整面水膜或模糊。晴天直接关闭透明组件，雨量变化与样式切换不重建网格；仅视口投影改变时重建两张网格。UV 流送数据显式初始化，避免 cooked FastBuild ensure。

节能画质沿用引擎的 `r.RefractionQuality=0`，保留水滴着色与高光；均衡及精细画质具有局部折射。本次不是流体模拟，滴头在小片玻璃内错峰下滑并淡出，未模拟水滴合并或雨停后残留水膜。

自动化用例 `OutOfWindow.Frame.ProjectionAndUIIndependence` 覆盖默认样式、样式切换、雨量限幅、雨晴显隐、玻璃深度、宽窄投影、无碰撞、网格/MID 复用，以及隐藏/恢复 UI 时保留框体和雨玻璃；新增绕序、常亮室内灯和灯光隔离检查。夜间改进已通过 Frame + UI 两项回归及四次成品实拍，见 [夜景验证](frame-night-verification.json)，日志位于 `.runtime/ue-frame-night`。此前窗型与雨滴版本的记录见 [历史验证](desktop-frame-verification.json)。

最新成品实拍均隐藏 UI、使用默认室内灯参数：[后巷夜晚](../../docs/desktop-frame/night-room-lit-alley.png)、[都市雨夜](../../docs/desktop-frame/night-room-lit-city.png)、[海岸夜晚](../../docs/desktop-frame/night-room-lit-coast.png)、[后巷白天](../../docs/desktop-frame/day-corrected-frame.png)。[改进前后巷夜晚](../../docs/desktop-frame/night-before-alley.png)使用同样的 23 时、晴天与 1280×820 视口，可对照框体表面、倒角和窗台。

成品实拍：[都市雨天，UI 已隐藏](../../docs/desktop-frame/contemporary-rain.png)、[连续雨滴动画](../../docs/desktop-frame/contemporary-rain-motion.mp4)。动画由 8 张成品原始截图按 0.5 秒间隔编码，未插帧、未合成雨滴。场景几何、照明仍以 UE 实拍为准，不等同于生成参考图中的建筑。

渲染检查示例：`Scripts/validate.ps1 -EngineRoot 'D:/Epic/Epic Games/UE_5.7' -Packaged -Cases 'city-rainglass,alley-hiddenui,alley-narrow,city-rainnight' -CaptureSeconds 15`。`rainglass` 在雨天隐藏 UI，并连续保存 8 张相隔 0.5 秒的截图；验证脚本还检查雨量、窗框状态、截图时效、材质回退和运行时 ensure。

旧十字窗框的首轮证据保留于 [历史验证记录](desktop-frame-v1-verification.json)，其中图片与尺寸不代表当前默认设计。
