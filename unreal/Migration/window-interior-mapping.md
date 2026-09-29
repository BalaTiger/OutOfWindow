# 后巷室内映射 v16

本记录对应材质 `v16`、窗格几何 `window-uv-v5`、实体房间 `hero-rooms-v2` 和静态烘焙 `interior-cubes-v3`。**资产审计、编辑器 GPU 验证、候选包六组回归及性能采样已完成；2026-09-29 10:58 更新安装版并通过重启、文件哈希和正常运行核对。**此前的 [v14 深度修复](window-depth-repair.md)及其部署结果保留为历史记录。

## 变更目的

v14 的背景窗将完整室内图贴在后墙，图片自带的地板和桌面透视无法随观察角度变化；当前方案改用真实模板烘焙的校准 cubemap，并按固定机位的屏幕尺寸与角度分配实体室内、详细 IM 和基础 IM。首次 v15 验证出现近家具投影过大和硬阴影黑块，已通过窗后探针位置与 `interior-cubes-v3` 烘焙照明修正。

## 当前工程配置

| 类型 | 数量与用途 |
| --- | --- |
| 实体室内 | 15 间，UE 实际 9,520 个室内三角面（导出源含零面积封口面共 10,032）；每间两个室内材质 section，玻璃另计。13 个源窗组中两个宽窗各拆成两个室内空间。 |
| 详细 IM | 17 个窗组，采样六种烘焙室内变体；保留整窗连续坐标、固定种子与亮灯状态。 |
| 基础 IM | 其余 361 个窗组，当前固定视野可见 14 个；沿用正确盒体求交和面着色，省略家具纹理细节。 |
| 实时灯预算 | 8 盏室内 PointLight 与 4 盏窗外 RectLight，照明预算与房间几何数量分别管理；没有为每间房无条件新增实时灯。 |

393 个源房间组的几何标志中，实体开孔占 15 组：13 个可见源窗组，加两组需要同步开孔的后方重复玻璃。它与“15 间实体室内”的计数口径不同。逐窗选择依据见 [window-technique-allocation.json](window-technique-allocation.json) 和 [重新评估记录](window-allocation-reassessment.md)。

`window-uv-v5` 保留原顶点位置与 UV0；UV1 为整窗连续坐标，V 从下向上；UV2 保存 `(seed,flag)`，`-1` 为排除面、`0.5` 为基础 IM、`1` 为详细 IM、`2` 为实体室内开孔；UV3 为实际整窗宽高（米）。开孔依据整数语义标志，避免再次依赖 Nanite 量化后的种子精确相等。原有 66 个透明前片和 74 个旧室内窗帘保持隐藏，真实室外雨篷继续保留。

全局夜间时序保留 `Night=0.58→0.86` 的渐变，亮灯布局在 `8 PointLight + 4 RectLight` 预算内重新分配。独立审计确认 15 间实体室内中 13 间沿用原有效开关，未发生亮灯改熄灯；新增亮灯为 `4b36e0ec1c9d5fc3`（标号 20）和 `360ea453eb0f5fb6_R`（标号 37 右半）。原本亮灯的 A/B 大窗仍为 occupied，照片发光改为实体照明后视觉更暗，不能将亮度变化视为熄灯，也不能称所有窗的亮灭布局完全不变。

## 素材与采样

六种静态 cube 由书房、起居室、厨房、卧室、餐室和阅读室的实际简化模板烘焙，每面 `256×256`，HDR 压缩、线性采样、原生 mip。运行时不捕获室内，不再使用旧六张完整 PNG 作为背景后墙，也不保留旧照片的人工高光增亮项。

模板与 shader 共用一个局部盒体：`min=(-1.8,-0.45,0)`、`max=(1.8,3.05,3.4)`，窗口为 `(-1,0)` 到 `(1,2.75)`，捕获中心为 `(0,1.375,0.20)`，即窗口中心高度、窗后 20 厘米。局部 X/Y/Z 分别向右、向上、向内。材质先将世界射线按实际窗尺寸缩放到该空间，再求最近盒面交点；从交点减去捕获中心后，以 `.xzy` 对应 UE cube 坐标采样。仰视、平视和俯视必须使用这一套相同校准。主材质与验证材质读取脚本中的同一捕获位置。

素材来源、文件名与重建入口见 [InteriorMapping/README.md](../Art/InteriorMapping/README.md)。[interior-atlas.json](interior-atlas.json) 保存来源几何与 HDR 文件哈希、捕获校准和亮度分布。烘焙使用独立关卡及固定临时灯，不消耗游戏中的实时灯预算。`interior-cubes-v3` 将主灯设为 `135 lm` 并保留阴影，天花补光 `120 lm`、窗口补光 `60 lm` 均关闭阴影，近似漫反射反弹，降低此前明显的黑亮二分；没有烘焙真实 GI。全部六个 cube 已按此配方重新捕获，材质 v16 与捕获校准保持一致。

详细 IM 的家具仍近似投影到单一盒体，不具有实体家具的全部深度和遮挡变化。本轮优先完成空间方向正确的基本方案，没有增加双深度 POM；需要真实家具轮廓、明显仰视或较大屏幕占用的窗采用实体几何。

## 验收与部署结果

- 资产审计已通过：[window-interiors-audit.json](window-interiors-audit.json) 为零失败。直接读取 UE 网格核对 15 间实体室内共 9,520 个有效三角面（源文件 10,032，UE 移除 512 个零面积封口面）、每间两个材质 section；15 个独立玻璃面共 30 三角面；8 盏室内 PointLight 与 4 盏窗外 RectLight；393 个源窗组分为 15 个开孔、17 个详细 IM、361 个基础 IM；74 个旧窗帘和 66 个旧透明前片保持隐藏。
- 静态素材已通过：[interior-atlas.json](interior-atlas.json) 确认六个 `256×256/面` HDR cube 为 `interior-cubes-v3`，位置 `(0,1.375,0.20)`，主灯 `135 lm` 保留阴影，`120/60 lm` 补光关闭阴影；来源几何、导出哈希、纹理类型和校准均已审计。
- 编辑器 GPU 已通过：[三视角验证记录](../../.runtime/ue-window-rebuild/cube-orientation/verification.json) 在同一固定窗面、同一厨房 cube 上，从距窗 12 米的仰视/平视/俯视相机输出实际材质与面分类图，确认天花板、后墙、地板方向及边界。[20:21 阴天实景](../../.runtime/ue-window-rebuild/editor-2021-release.png) 已完成视觉复查，捕获状态见 [对应 JSON](../../.runtime/ue-window-rebuild/editor-2021-release.json)。
- 候选包回归通过：20:21 阴天、12:00 晴天、23:00 晴夜、23:00 雨夜、1280×820 窗口，以及 16:17 阴天的 8 帧连续捕获；其余图为 1920×1080、Quality 1。白天室内灯光通量为 0，夜间共 12 灯；室外雨篷继续参与风动，123 个有效风动组件保留。截图、状态和文件哈希见 [完整验收 JSON](window-interior-mapping-verification.json)。
- GPU 对比：同机、1920×1080、Quality 1（85% screen percentage）、20:21 阴天，关闭帧率限制和 VSync，以原生 `csvGpuStats` 各采 1800 帧，丢弃前 900 帧。GPU 中位数由 **13.79 ms → 9.22 ms**，P95 由 **14.42 ms → 9.62 ms**；DrawCalls 中位数 392 → 413，绘制图元 51,365 → 30,311。此为各一次捕获，存在运行间波动，不能将全部差异归因于单一修改；限帧回归约 16.7 ms 并不是这项 GPU 结论的依据。
- 安装版部署通过：候选来自 `D:\OutOfWindowBuildInteriorMapping\Windows`，部署至 `D:\OutOfWindowBuild\Windows`，10 个发布文件哈希一致。旧版备份为 `D:\OutOfWindowBuildBackups\interior-mapping-before-20260929-105821`。正常启动后 `testMode=false`、`liveTime=true`、12 灯、123 个有效风动组件；见 [部署记录](../../.runtime/ue-window-rebuild/deployment.json)、[安装验证](../../.runtime/ue-window-rebuild/installed-verification.json)和[运行状态](../../.runtime/ue-window-rebuild/installed-state.json)。本页截图来自已验证的同哈希候选包，未另外捕获安装后画面。

本轮证据目录为 `.runtime/ue-window-rebuild/`。最终 [20:21 原生截图](../../.runtime/ue-window-rebuild/packaged-2021.png)与[完整验收 JSON](window-interior-mapping-verification.json)保留测试条件、GPU 原始数据和剩余限制。旧 `.runtime/ue-interior-depth/` 为 v14 历史。
