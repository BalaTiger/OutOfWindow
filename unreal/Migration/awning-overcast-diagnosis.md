# 后巷阴天雨棚泛白与墙面间接光诊断

2026-09-28。检查当前已部署的 AlleyWeathering Development 包、地图资产及本机 UE 5.7 源码，并完成独立离屏对照。未修改生产源码、材质、地图、画质配置或正在运行的桌面实例。

主要问题已锁定在 **TwoSidedFoliage 雨棚材质与均衡档 Lumen 关闭独立背面间接采光的组合**。只开启这一项即可显著消除粉白感；关闭镜面、直接光或雨棚透射均不能获得同样结果。雨棚自身的反照率也确实大幅影响周围墙面。尚未定位引擎内部哪一段积分、时域处理或光照反馈放大了关闭分支的差异，不能据此宣称存在 GBuffer 解码错误。

对照画面：[当前均衡路径](../../.runtime/ue-awning-diagnosis/fixed.png)、[只开启独立背面采光](../../.runtime/ue-awning-diagnosis/backface.png)。白天美术参考为 [原效果图](../../docs/alley-photoreal/reference-generated.png)；它是生成的美术目标，天气、机位和几何与当前 UE 画面不同，不将其像素值当作物理标定数据。

## 已确认的资产与运行状态

只读加载地图后，26 个雨棚组件实际使用 4 个 v8 叶实例及 1 个主材质，均为 Opaque、TwoSidedFoliage、双面。BaseColorFactor=(1,1,1,1)，颜色贴图 sRGB=true，亮度、曲线和饱和度参数均为 1，自发光颜色为 0；Roughness=.92、Metallic=0、IOR=1.5。透射强度为 .2，光学厚度为 .65，没有残留旧版 .7 强度。红布原图均值约 sRGB 120/37/36，线性 .190/.019/.018，本身不是粉白色。

完整读回：[probe.json](../../.runtime/ue-awning-diagnosis/probe.json)，摘要：[material-summary.json](../../.runtime/ue-awning-diagnosis/material-summary.json)。旧 v6 审计不能代表当前 v8 资产。

最近部署的 [16:10:41 实时状态](../../.runtime/ue-alley-weathering/live-state.json) 为上海阴天、云量 100%、均衡画质，太阳约 3150 lux、天空光倍率 .85，湿润和积水均为 0，室内灯与窗框房间灯均为 0。曝光补偿 -.5，自动曝光读回 .012104。未在项目代码中发现额外提高 Lumen DiffuseColorBoost 的设置；这不代替对所有后处理属性的完整读回。

## 相同曝光下的实机对照

共同条件：当前已部署包、后巷、16:00、阴天、均衡、1280×820、20 秒模拟预热、固定模拟步长 1/20 秒。测试入口日期为 9 月 23 日，因此不是原封重放 9 月 28 日的桌面画面。`r.EyeAdaptation.MethodOverride=3` 与 `r.ExposureOffset=4` 将曝光固定为 .01178511046，接近上述实时状态；每组实际曝光、太阳、天空光和云量读回一致。桌面程序保持运行，本测试不用于性能评价。

雨棚取样矩形为 x=760、y=567、65×50，避开轮廓；数据是最终显示图像的均值，非 HDR 光能。饱和度为 HSV S，亮度为 RGB 的加权灰度（0–255）。

| 唯一变化 | 雨棚平均 RGB | 饱和度 S | 显示亮度 |
| --- | --- | ---: | ---: |
| 当前均衡路径 | 233.3 / 176.3 / 163.9 | .298 | 187.6 |
| 重复当前路径 | 233.2 / 176.2 / 163.7 | .299 | 187.4 |
| 关闭镜面显示 | 232.5 / 170.0 / 156.7 | .326 | 182.3 |
| 雨棚透射参数设为 0 | 229.2 / 169.0 / 156.6 | .318 | 180.9 |
| 关闭直接光显示 | 232.9 / 175.5 / 163.0 | .301 | 186.8 |
| 独立背面间接采光从 0 改为 1 | 210.6 / 85.5 / 73.4 | **.652** | **111.2** |

决定性控制项为 `r.Lumen.ScreenProbeGather.TwoSidedFoliageBackfaceDiffuse`。基准日志确认均衡档设为 0，实验日志确认覆盖为 1。基准重跑的 RGB 误差小于 .2，远小于该开关带来的变化。镜面反射及透射强度有次要贡献，但不是此次严重泛白的充分解释；直接光的可见贡献很小。固定曝光也仍然泛白，不能只归因于自动曝光。

关闭透射使用原生 KE 调用当前进程 MID 的 `SetScalarParameterValue`，日志为 141/141 调用成功并读回参数；只有雨棚材质使用该参数。没有保存资产。

## 墙面确实受到雨棚反照率影响

另一个实验只对已识别的 4 个雨棚 MID 将 BaseColorFactor 设为 (0,0,0,0)，保留几何、灯光和曝光。日志记录四次指定实例调用成功及实际零值；原材质为 Opaque，不会因为 Alpha=0 消失。此举同时去掉由原 albedo 派生的透射颜色，保留材质镜面项，因此画面里的雨棚仍呈灰色，不代表 setter 失败。

| 墙面区域 | 基准显示亮度 | 雨棚反照率清零后 | 变化 |
| --- | ---: | ---: | ---: |
| 紧邻雨棚的石墙 | 120.34 | 85.68 | −28.8% |
| 上方灰泥墙 | 133.67 | 101.74 | −23.9% |

邻墙的 R−G 从 10.72 降至 7.98，说明除了提亮也包含颜色影响。这个实验确认雨棚材质对墙面有显著贡献，不能将墙面变化解释为单纯曝光变化。百分比是色调映射后显示亮度变化，**不是“29% 的物理光能来自雨棚”**，也不直接量化超过真实世界标准多少。

只开启独立背面采光时，两块墙面的显示亮度分别降至 92.38 / 109.13，伴随雨棚颜色恢复；这一开关作用于全场景的相同着色模型，因此不能把全部墙面改善都单独归给某一块雨棚。

证据：[反照率清零画面](../../.runtime/ue-awning-diagnosis/black-awnings.png)、[全部区域与测量](../../.runtime/ue-awning-diagnosis/metrics.json)、[测量脚本](../../.runtime/ue-awning-diagnosis/measure.cjs)。

## 代码上的原因与边界

[window_lookdev.py:26](../Scripts/window_lookdev.py#L26) 将雨棚设为 TwoSidedFoliage；第 31–39 行将原 albedo × .2 × exp(−.65/NoV) 接入 SubsurfaceColor，日夜都有效。[WindowDirector.cpp:800](../OutOfWindow/Source/OutOfWindow/WindowDirector.cpp#L800) 将均衡设为 GI quality 2。

本机引擎根目录为 `D:/Epic/Epic Games/UE_5.7/Engine`，相关实现：

- `Config/BaseScalability.ini:301`：GI quality 2 把独立背面采光设为 0；不能用 C++ 初始化默认值 1 推断当前运行值。
- `Shaders/Private/DiffuseIndirectComposite.usf:559–576`：关闭时使用正面间接光 × (DiffuseColor + SubsurfaceColor/π)；开启时分别使用正面间接光和背面间接光。
- `Source/Runtime/Renderer/Private/Lumen/LumenScreenProbeGather.cpp:1646,1879,2614`：这个开关还会切换积分、时域重投影的着色器排列及独立背面缓冲。因此它不是单纯的透射强度旋钮。
- `Shaders/Private/Lumen/LumenCardBasePass.ush:124–128`：TwoSidedFoliage 的 SubsurfaceColor 被加进 Lumen 表面缓存的漫反射反照率。透射参数会影响反弹，不只控制看到的背光。

按当前材质公式，缓存附加的 SSS 项正视上限约为原 albedo 的 10.44%；合成关闭分支的 SSS/π 约为 3.32%。**这些公式本身不足以解释实测的巨大退饱和**，尤其透射设为零仍泛白。已检查 SSS 编解码，未发现“关闭分支未解码”的证据；更细的引擎内部原因尚未证实。

Epic 的 [Lumen 官方说明](https://dev.epicgames.com/documentation/unreal-engine/lumen-global-illumination-and-reflections-in-unreal-engine)说明了 TwoSidedFoliage 的背面采光与 SubsurfaceColor 衰减机制。在线页面可能指向较新版本，本次具体分支判断以本机 5.7 源码及上述实测为准。

## 后续处理顺序

优先将当前背面 GI 关闭路径作为修正对象，保留其余均衡参数，以开启独立背面采光的结果做局部验收和 GPU 成本检查；若成本不适合，再考虑雨棚单独改用更合适的表面/透射模型。随后校准布料反照率和透射对周围墙面的贡献。直接把原图涂得更暗、只降透射，或整体压低曝光，均不能代替先解决已复现的路径差异。

本轮到诊断为止。没有将实验开关写入正式配置，也没有重新打包或重启用户桌面程序。
