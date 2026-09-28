# 后巷砖瓦真实起伏：技术取舍

本轮选择离线生成真实三角网格、写入 GLB，再导入为普通 Nanite StaticMesh。
两处屋顶与 `09_10` 近墙已完成 CPU 几何检查、UE 导入及成品打包验证。实际 GPU 截图检查了精确 16:30 晴天与 23:00 夜晚；性能记录仅作冒烟检查，不作为独立基准。

## 为什么采用离线几何

- 固定相机中的静态砖瓦不需要逐帧改变几何；生成后的网格直接参与遮挡、VSM 和光追几何构建。
- UE 5.7 官方仍将运行时 Nanite Tessellation、内置 Nanite Static Displacement 标为实验性，前者还明确存在 UV/硬法线接缝裂缝限制；本轮不启用两者或新增全局开关。[Epic 5.7](https://dev.epicgames.com/documentation/unreal-engine/working-with-naniteenabled-content?application_version=5.7)
- POM 改变材质采样与表面深度表现，不能提供需要的真实不齐轮廓，故不是本轮主方案。
- Nanite 负责已有几何的细节调度，不会自动补出缺失砖瓦；普通 Nanite StaticMesh 支持 Lumen 与 VSM。[Nanite 文档](https://dev.epicgames.com/documentation/en-us/unreal-engine/nanite-virtualized-geometry-in-unreal-engine?application_version=5.7)

## 素材与边界

现有 `scripts/generate-bistro-pbr.mjs` 的 Bistro 砖墙 Height 由 BaseColor 灰度、归一化和锐化派生，不能视为扫描高度；原屋瓦没有匹配 Height。
本轮局部几何起伏属于程序化美术近似，不宣称恢复真实建筑尺寸或扫描细节。
屋檐外轮廓需要真实顶点与厚度，不能用法线贴图替代；墙体接缝避免产生开口、悬浮层或重叠薄面。

## 已核验实现

- 两处屋顶各 3,972 三角形，瓦列进退幅度上限 2.7 cm、瓦唇 9 mm；保留原 UV 图表，受影响法线按原硬边分组重算。编码 GLB 的 float32 数据经 UE 厘米转换检查，新增裂缝、非流形边、退化三角形均为零，另无翻面。[屋顶报告](roof-geometry-repair.json)
- 单个 `09_10` 近墙为 31,042 三角形：仅细分 220 个朝相机的源三角面，另 254 个背面/水平面保持；凹缝 8 mm、块面变化 ±2 mm，边界 8 cm 衰减。灰缝坐标来自原 normal map，保留/插值原顶点法线并沿用原 normal map，避免同尺度凹凸叠加。[墙面报告](masonry-relief.json)
- 两个生成脚本均已在真实 UE commandlet 完成，日志报告 0 errors；`Run-Unreal.ps1 -Mode Import` 已包含 `build_masonry_relief.py`。这些事实不等于整条 Import 已重新执行。
- 默认导入曾把三个网格的 fallback 各减到 251 三角形，现已应用下述完整策略；UE 实读分别为 3,972 / 3,972 / 31,042，与生成值一致，三个资产的独立 RT proxy 均为 `false`。

## 这三个新网格的 fallback 策略

仅在新增起伏的派生资产上使用以下设置，保留其他资产及项目渲染配置：

```python
nanite.fallback_target = unreal.NaniteFallbackTarget.PERCENT_TRIANGLES
nanite.fallback_percent_triangles = 1.0
nanite.fallback_relative_error = 0.0
nanite.keep_percent_triangles = 1.0
nanite.trim_relative_error = 0.0
```

字段和枚举已核对 [MeshNaniteSettings](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/MeshNaniteSettings?application_version=5.7) 与 [NaniteFallbackTarget](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/NaniteFallbackTarget?application_version=5.7)。
本机 `MeshBuilderCommon/Private/NaniteHelper.cpp` 会重算 `AUTO` 的误差；`PERCENT_TRIANGLES` 明确将误差设为零。
`NaniteBuilder.cpp` 的 fallback 简化判断还包括 `KeepPercentTriangles` 和 `TrimRelativeError`，因此这两项也要检查，不能盲目继承旧资产。
幂等复用已有派生网格时也需核对该策略；仅新导入分支设置不够。

UE 5.7 另有 `ray_tracing_proxy_settings`；其资产 `enabled` 与项目 `r.RayTracing.RayTracingProxies.ProjectEnabled` 默认关闭，本项目源配置未显式开启，实际资产值已记录，未新增代理系统。
保留完整 fallback 是避免硬件光追丢失新增形状的局部措施，不保证所有 Lumen 缓存、VSM 采样或远处细节完全一致，仍需实机观察。[Lumen 技术细节](https://dev.epicgames.com/documentation/en-us/unreal-engine/lumen-technical-details-in-unreal-engine?application_version=5.7)

## 复用与验证边界

复用现有离线 GLB 生成、来源哈希和定向替换流程；不同场景只提供目标网格、表面参数及边界约束，不增加运行时子系统。
本次打包由同仓库桌面任务协调执行，日志 `.runtime/ue-wallpaper/package.log` 成功；随后本任务实际运行 `validate.ps1 -Packaged -Cases 'alley-afternoon,alley-night' -CaptureSeconds 15`，两例通过，时间读回分别为 16.5 与 23。Lumen GI、反射、硬件光追保持启用，66 对前后窗玻璃保留，日间室内灯为零、夜间正常开启。[验收记录](surface-relief-verification.json)

实机检查确认轮廓随瓦行微小参差、灰缝与原纹理对齐，没有新增开口。查看 [16:30 成品](../Art/Lookdev/alley-afternoon-surface-relief.png)、[夜间成品](../Art/Lookdev/alley-night-surface-relief.png)、[瓦边局部](../Art/Lookdev/alley-slate-edge-detail.png) 和 [石墙局部](../Art/Lookdev/alley-masonry-joint-detail.png)。两张局部图来自 16:00 的 2560×1640 Editor GPU 截图；最初裸浮点命令行被 PowerShell 分词，审计已识别，最终成品另以字符串参数验证精确 16:30，未将错误时间作为同条件对照。

本次未做受控的性能前后基准或新增雨夜专项检查；并行开发和 GPU 工作会影响帧间隔，报告中的 P95 不归因于这三个网格。远处砖墙、抹灰、细混凝土继续采用已有法线贴图，避免在当前机位不可辨认的细节上批量加面。
