# 夜窗方格与室内重复修复

日期：2026-09-23。本轮优先处理后巷夜窗出现方格黑块、同一扇窗内部亮灭不连续及室内图案重复的问题。它是此前迁移交付后的独立修复，不修改 [packaged-verification.json](packaged-verification.json) 中历史构建的哈希或性能成绩。

下方四例验证及性能表属于 **v4 柔化前**的室内图版本。此后 v5 首轮轻度柔化使用 1.25 / 0.62；当前增强阶段使用 Blur2 与实例覆盖 2.0 / 1.8。各阶段实现和验证分别记录，不把之前的通过记录当作后续参数的新包验证。

**v4 阶段已完成 UE 资产审计、窗 UV 重复执行、打包和四例独立程序回归。** 该阶段截图中未再观察到整窗内部的方格亮灭切割，家具细节方向正常、双扇图像连续；六种室内图减少了重复。完整状态、包文件哈希与逐例截图审查结论见 [night-window-verification.json](night-window-verification.json)。

## 实现边界（v4 柔化前）

窗玻璃按整窗分组，为组内玻璃提供连续 UV1，并令 UV2=`(seed,1)` 在整窗恒定。整窗的室内图、亮灯状态和色调共用这一种子，避免逐像素随机分块。只有带 `OOWWindowInterior` 标签的窗进入材质 v4 的六图室内分支；其他窗继续使用 v3，非窗表面保留 v2。

六张原始 1024×1536 图片由内置 `image_gen` 生成，源文件、主题和完整提示词见 [素材说明](../Art/WindowInteriors/README.md)与 [prompts.json](../Art/WindowInteriors/prompts.json)。没有新增第三方室内图。它们是 2D 近似，不是摄影扫描或真实室内几何，不具备真实视差；本轮也不把六张变体称为完全消除重复。

导入顺序现在为：`import_scenes.py` → `build_window_interiors.py` → `build_surface_materials.py` → `build_precipitation.py` → `build_foam.py` → `build_coast_shoreline.py`。先生成玻璃 UV/标签，再生成对应材质。

## 已落盘的几何和纹理

[window-interiors-geometry.json](window-interiors-geometry.json) 的 `appliedToUnreal=true`：检查了 82 个源玻璃 Actor，修改 68 个，生成 415 个整窗组，其中 143 个为多片合并组，没有跨 Actor 分组。原始 583 个连通岛拆成 689 个平面岛，560 个适合室内映射。`09_8` 的 76 个连通岛形成 59 个整窗组；`08_1` 的 14 个连通岛形成 11 个整窗组。组数描述资产处理结果，不等于当前机位实际可见或亮灯窗数。

六个纹理资产已在 `/Game/Materials/OOW/WindowInteriors/` 落盘，名称为 `T_Room_01`、`T_Room_02`、`room-03`、`room-04`、`room-05`、`room-06`，分别对应六张原始 PNG。当前脚本使用原生 Interchange；真实 UE 材质构建进程已以退出码 0 完成。

v4 阶段只读 UE 审计为 `passed=true`：68 个标记 Actor、4 个叶级材质实例、1 个主材质、6 个纹理、0 个失败，快照计数保存在 `night-window-verification.json`。审计核对 3 个 UV 通道、全精度 UV、材质绑定和纹理配置；[window-interiors-audit.json](window-interiors-audit.json) 保存最近一次审计，目前已更新为 v5，不能把最新文件误当成 v4 原始快照。

## 验证状态（v4 柔化前）

- [x] 六张 PNG 与 `prompts.json` 已存在，PNG 头尺寸均为 1024×1536。
- [x] 材质脚本的静态接口已核对：标记窗使用 v4 / UV1 / UV2，房间选择与亮灯按整窗种子，其他窗使用 v3 回退。
- [x] 窗分组与新增 UV 已在真实 UE 中执行，68 个 Actor、415 个整窗组和 143 个多片组合落盘，报告 `appliedToUnreal=true`。
- [x] 六张室内图已导入为 UE 纹理资产，名称与上述实际路径一致；源 PNG 未修改。
- [x] 窗 UV 生成脚本已在真实 UE 中重复执行通过，几何哈希不变，复用已有资产而未重复导入，v4 材质绑定保留；日志为 `.runtime/ue-night-window/geometry-repeat.log`。
- [x] 真实 UE 材质构建完成且退出码 0；只读审计通过，68 个标记 Actor / 4 个叶级材质实例 / 1 个主材质 / 6 个纹理 / 0 个失败。
- [x] 已检查本轮新鲜 GPU 截图：后巷夜间未见方格亮灭切割，室内家具朝向正常且可辨认，双扇画面连续；雨夜室内图在雨与湿反射下保持连续；白天室内发光关闭，玻璃与几何正常；都市夜景沿用既有回退材质，没有出现编译失败材质替代。
- [x] `.runtime/ue-night-window/package.log` 为 `BUILD SUCCESSFUL`，AutomationTool 退出码 0；新包的后巷夜间、雨夜、白天及都市夜间四例均通过自动检查。
- [x] 本轮结束时已正常打开后巷 23:00 晴天，保留可见窗口运行；`normalLaunch` 记录 `testMode=false`、`cameraBound=true`，不是测试模式截图进程。

## 打包与性能记录（v4 柔化前）

[night-window-verification.json](night-window-verification.json) 保存实际运行 exe、`.ucas`、`.utoc` 和素材总账的 SHA-256。本轮改动进入资产包，运行 exe 的哈希与上一轮相同；不能仅用 exe 哈希区分本次室内图和 UV 内容。四例来自本轮打包产物，之前的 15 例矩阵及岸线/单实例成绩继续独立保留。

条件：RTX 5060 8 GB、UE 5.7.4 Windows Development、1280×820、均衡档（85% 内部渲染比例）、60 FPS 上限，每例 30 秒。数据为应用帧间隔，不是 GPU timer。

| 用例 | 平均帧间隔（ms） | P95（ms） | 样本数 |
| --- | ---: | ---: | ---: |
| alley-night | 22.49 | 30.03 | 1,252 |
| alley-rainnight | 22.49 | 37.21 | 1,247 |
| alley-clear | 21.77 | 29.83 | 1,287 |
| city-night | 62.61 | 76.13 | 448 |

都市夜景这轮平均约 16 FPS，性能成本明显偏高；四例的“通过”指状态与材质检查通过，不代表达到 60 FPS。短测没有隔离 GPU、CPU、场景负载或六图采样成本，不能把帧时差异直接归因于室内贴图。都市仍使用既有窗材质回退分支。

本轮是四例定向回归，没有重跑历史 15 例矩阵，也没有从零重跑完整六步 Import；重复执行验证只覆盖窗 UV 生成步骤。六张室内图仍是有限的 2D 变体，没有真实室内几何或视差，远近所有窗口、全部光照时段和长期性能不在这次短测结论内。

## v5 首轮：轻微玻璃柔化（历史）

首轮按轻微模糊要求将标记窗材质升级为 v5，六个纹理采样共用 `OOWInteriorMipBias=1.25`，室内增益为 `0.62`，采样模式为 UE 原生 `TextureMipValueMode.TMVM_MIP_BIAS`。该阶段通过更粗的 mip 级别降低图像锐度，保留整窗坐标和灯光状态；没有新增采样，也没有修改原图、窗几何或灯光参数。这是固定机位的视觉近似，不增加真实玻璃散射或室内视差。

- [x] `.runtime/ue-night-window/build-soft-interiors.log` 的真实 UE 材质构建成功，退出码 0。
- [x] `.runtime/ue-night-window/audit-soft.log` 的只读 UE 审计成功，该阶段为 68 个 Actor / 4 个叶级实例 / 1 个主材质 / 6 个纹理 / 0 个失败；`window-interiors-audit.json` 随后已更新为增强阶段，不作为首轮参数快照。
- [x] `.runtime/ue-night-window/package-soft.log` 打包成功；v5 的后巷夜间、雨夜、白天三例独立程序回归全部通过。
- [x] 已检查三张本轮新截图：室内高频细节轻微柔化，桌椅轮廓仍可辨，外窗框保持清晰；整窗亮灭及双扇图像连续，雨夜可读，白天室内发光关闭且玻璃正常。

柔化阶段的包哈希、三例完整状态和图像审查见 [soft-window-verification.json](soft-window-verification.json)，其中 `priorVerification` 链接上述 v4 历史证据。每例 30 秒，1280×820、均衡档，应用帧间隔如下：

| v5 用例 | 平均帧间隔（ms） | P95（ms） | 样本数 |
| --- | ---: | ---: | ---: |
| alley-night | 17.14 | 19.85 | 1,634 |
| alley-rainnight | 17.26 | 16.82 | 1,624 |
| alley-clear | 20.80 | 34.79 | 1,347 |

这些是短时应用帧间隔，不是独立 GPU 耗时，也不能据与 v4 的数值差异声称柔化带来了性能提升。轻度柔化阶段只重测上述三例，v4 都市夜景和更早的完整矩阵仍保留各自的版本边界。

## v5 当前：进一步柔化并增强暖光

针对“不够柔和且暖光/光晕减弱”的反馈，六张 UE 纹理改用原生 `TMGS_BLUR2`，v5 窗材质实例覆盖 `OOWInteriorMipBias=2.0`、`OOWInteriorGain=1.8`。主材质的 1.25 / 0.62 默认值保留，有效值由实例提供。六个采样和材质图结构不变，原始 PNG、窗几何及场景灯具不变；室内材质发光增强，玻璃柔化仍是视觉近似。

- [x] `.runtime/ue-night-window/build-glow-interiors.log` 构建和 `audit-glow.log` 只读审计均退出码 0；最新审计回读 Bias 2.0、Gain 约 1.8、纹理 `TMGS_BLUR2`，68 个 Actor / 4 个叶级实例 / 1 个主材质 / 6 个纹理 / 0 个失败。
- [x] 新鲜 Editor 预览确认室内更柔和、暖光与光晕更明显，房间明暗结构可辨，外框清晰，没有整窗内部的硬切块。
- [x] `.runtime/ue-night-window/package-glow.log` 为 `BUILD SUCCESSFUL`，退出码 0；最终包夜间/雨夜两例独立程序回归均通过。
- [x] 已检查两张最终包新截图：室内细节融合成更柔和的暖光，亮部与窗边光晕增强，房间明暗结构保留；外部窗框清晰，没有整窗内部硬切块，雨夜仍保持连续。

增强阶段的包哈希、运行状态和截图审查独立保存在 [glow-window-verification.json](glow-window-verification.json)，并链接此前的轻度柔化记录。每例 30 秒、1280×820、均衡档，应用帧间隔如下：

| 最终增强版用例 | 平均帧间隔（ms） | P95（ms） | 样本数 |
| --- | ---: | ---: | ---: |
| alley-night | 22.02 | 30.00 | 1,273 |
| alley-rainnight | 21.96 | 32.29 | 1,275 |

本阶段只复测夜间和雨夜；白天检查保留在此前 v5 记录中，没有把它当作最终参数的新测结果。短时应用帧间隔不是 GPU 基准或长期帧率保证，暖光柔化仍是 2D 视觉近似。
