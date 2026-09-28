# 后巷屋顶午后受光修复

本页记录原始法线恢复阶段。后续两个同款屋顶又增加了瓦片轮廓起伏，当前生成报告包含该增强；新增几何及成品验收见 [surface-relief.md](surface-relief.md)。下文 60 三角面等数值指原始恢复基准。

日期：2026-09-24。中央楼缝内的三角屋顶在午后出现不符合坡面朝向的明暗。**源几何修复、真实 UE 导入与重复执行、新包 GPU 对照和三例回归均已完成。** 相同测试条件下，异常的整坡明暗渐变消失，瓦片方向与建筑轮廓保留。

## 根因与排除项

目标 Actor 为 `OOW_00487_paris_building_03_mirrored_6`，材质为 `MASTER_Roofing_Shingle_Grey`。原始 `bistro-exterior.gltf` 的 mesh 448 及同类 mesh 458 保留了硬边法线，safe 简化结果破坏了这些法线。主屋顶由原始 60 个三角面简化至 41 个；其中两个共面主坡三角面的顶点法线与几何面法线点积分别约为 `[0.004,0.430,1]`、`[0.430,1,1]`，部分顶点偏转约 64°–90°。原始对应面的点积均大于 0.999，适合直接恢复源数据。

这些数据证明简化结果的着色法线异常，**没有证明某个位置焊接（weld）操作是根因**；修复不进行位置焊接或统一平滑法线。

材质链路不是本次已定位异常的原因：

- near GLB 与迁移导出 GLB 的底色、法线贴图解码像素哈希一致。底色确有瓦缝局部明暗，但没有整屋顶或邻楼投影。
- 材质为非金属、粗糙度 0.9，法线强度默认 1，没有额外 AO/ORM 或自发光贴图。
- UE 5.7 的 `InterchangeGltfTranslator.cpp` 自动转换法线绿通道，`InterchangeGLTFMaterial.cpp` 保留 NormalScale；项目的石材天气适配没有改写此法线输入。无需额外翻绿或改 normal scale。

## 修复范围

[repair_roof_geometry.py](../Scripts/repair_roof_geometry.py) 仅恢复白名单内 **9 个受损屋顶**，原始 mesh 索引为 303、312、317、318、324、448、458、554、624。三角面总数 **537 → 794**，恢复后共 1,022 个顶点；主屋顶 448 为 41 → 60，镜像屋顶 458 为 43 → 60。源 NORMAL 和 UV0 按字节保留，UE 构建不重算法线，仅重新生成与 UV 相符的切线。不重新导入贴图，不移动整栋建筑。

[restore-bistro-near-geometry.mjs](../../scripts/restore-bistro-near-geometry.mjs) 的建筑材质白名单增加 `roof`，让后续 near 资产重建也能恢复符合距离、视锥等既有条件的屋顶，避免只修当前 UE 地图而下次导出又丢失。

主屋顶面积加权法线夹角由 14.00° 降至 0.88°。这是恢复源硬边及原有合理平滑的结果，并非强制所有顶点法线等于面法线；不能把源模型局部平滑面的非零夹角再次判为损坏。

## 已完成的 UE 证据

[roof-geometry-repair.json](roof-geometry-repair.json) 已为 `appliedToUnreal=true`，最新重跑中 9 个 Actor 均为 `reused=true`，没有重复生成修复资产。首次与重复 commandlet 均成功、0 error；各有一条 Editor subsystem 构造方式的弃用警告。日志为 `.runtime/ue-roof-check/repair.log` 和 `repair-repeat.log`。

报告读回 **1,801 个 Actor 变换未改、1,792 个非目标 Actor 网格未改**。9 个修复屋顶全部 `naniteEnabled=true`，仍绑定原有 `MI_stone___v2` 天气材质。报告同时保存每个 Actor 的源索引、前后三角数、法线/UV 哈希和边界误差；后续生成会更新该报告。

## 重建与最终验收

源资产后续重建使用 `node scripts/restore-bistro-near-geometry.mjs`。[Run-Unreal.ps1](../Run-Unreal.ps1) 的 `-Mode Import` 已将屋顶修复接在 `import_scenes.py` 后、窗几何与天气材质前。已有地图也可通过 `UnrealEditor-Cmd -run=pythonscript -script=...repair_roof_geometry.py -NullRHI` 定向执行；所有资产写入串行运行。

[validate.ps1](../Scripts/validate.ps1) 已支持 `-Cases alley-afternoon`，固定时间为 **16.5（16:30）**、天气为晴。`.runtime/ue-roof-check/package.log` 记录 BuildCookRun `BUILD SUCCESSFUL`、AutomationTool ExitCode 0；`validate.log` 中新包的 `alley-afternoon`（16:30）、`alley-clear`（12:00）、`alley-night`（23:00）三例全部通过。完整结果见 [roof-lighting-verification.json](roof-lighting-verification.json)。

主线程已查看新包真实 GPU 截图，并与同机位、同晴天、同曝光设置的修复前画面对照：[修复前](../Art/Lookdev/alley-afternoon-roof-before.png)、[修复后](../Art/Lookdev/alley-afternoon-roof-fixed.png)。测试固定上海、2026-09-23、16:30，**不代表严格复现用户当时的实际地理位置与日期**。对照确认原先异常的整坡渐变消失，正常瓦片细节与建筑轮廓保留。

9 个修复屋顶保留 Nanite，运行读回 Lumen GI、Lumen 反射及硬件光追仍开启。三例应用帧间隔 P95 约 16.7 ms，仅作为本次冒烟回归记录，不作性能基准；本轮未复用此前夜窗修复的通过结论。
