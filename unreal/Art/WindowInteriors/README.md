# 夜窗室内图

这六张图用于固定机位后巷的夜间窗户，在同一整窗内显示一幅连续的室内画面，减少重复的亮色块。它们由本工程于 **2026-09-23 使用内置 `image_gen` 生成**，每张原图均为 **1024×1536 PNG，2:3 竖幅**；尺寸已读取 PNG 头核对。

| 文件 | 提示词中的室内主题 | 已落盘的 UE 资产名 |
| --- | --- | --- |
| [room-01.png](room-01.png) | 起居室：赭色沙发、橡木书架、台灯 | `T_Room_01` |
| [room-02.png](room-02.png) | 厨房：灰绿橱柜、瓷砖墙、杯子和水壶 | `T_Room_02` |
| [room-03.png](room-03.png) | 书房：木书桌、皮椅、桌灯、书架 | `room-03` |
| [room-04.png](room-04.png) | 卧室：蓝色被褥、床头柜、台灯、衣柜 | `room-04` |
| [room-05.png](room-05.png) | 餐室：圆桌、不同款椅子、餐边柜、吊灯 | `room-05` |
| [room-06.png](room-06.png) | 另一种起居室：绿色扶手椅、落地灯、立式钢琴、植物 | `room-06` |

完整提示词、生成日期与工具原始输出路径保存在 [prompts.json](prompts.json)。图像来自文字生成，本轮没有下载或添加第三方室内照片；提示词要求摄影风格，**实际来源仍是 AI 生成，不是摄影或扫描素材**，也没有对应的实测 PBR 通道。

当前 **v6** 使用整窗 UV1 与组内恒定的 UV2=`(seed,flag)`：`1` 是房间，`-1` 明确禁用室内和旧窗发光；`0` 仅供旧窗回退。房间选择、亮灭、亮度和色温由同一个整窗种子决定。`window-uv-v2` 保留原顶点位置和 UV0，排除 26 组包边的 259 个三角面及另外 52 个非窗面，留下 393 个房间组。UV1 底部为 0、顶部为 1，采图使用 `1-V`。

纹理仍为六次采样，原生 `TMGS_SHARPEN0` mip 配合材质实例覆盖：`OOWInteriorMipBias=1.5`、`OOWInteriorGain=0.8`、`OOWInteriorHighlightGain=8`、`OOWInteriorHighlightThreshold=0.32`。底图与从同一采样提取的灯具高亮分别控制，避免把家具和灯芯一起均匀提亮；`Night=0` 时室内图发光为零。主材质默认值不代表实例的实际运行值。

66 个独立玻璃前层使用原生 **ThinTranslucent / SurfaceForwardShading**，关闭 Nanite，使用三档原生 LOD；室内图仍留在后方不透明网格上。`OOWWindowGlassFront` / `OOWWindowGlassBacking` 标签将两层分开，避免后层重复施加玻璃衰减。其他未标记窗保留 v3，非窗表面保持 v2；雨篷另有独立 v6 配方。

上表 UE 资产均位于 `/Game/Materials/OOW/WindowInteriors/`，以实际导入名称为准。导入器设置 sRGB、Clamp、`STRETCH_TO_POWER_OF_TWO` 与 mip 生成；不使用产生黑边的 padding，不修改六张源 PNG。v6 已完成打包、资产审计和后巷夜间/雨夜/白天、都市夜间四例回归，资产审计为 0 失败。实现、重建顺序与完整验证见 [v6 修复记录](../../Migration/window-lookdev-repair.md)和 [验证数据](../../Migration/window-lookdev-verification.json)。实机截图：[后巷夜间](../Lookdev/alley-night-implemented-v6.png)、[雨夜](../Lookdev/alley-rainnight-implemented-v6.png)、[白天](../Lookdev/alley-day-implemented-v6.png)。

**历史版本：** v4 原图室内、v5 首轮 1.25 / 0.62 轻度柔化，以及 v5 后续 Blur2 / 2.0 / 1.8 增强阶段的构建、审计和独立程序验证保留在 [夜窗修复记录](../../Migration/night-window-repair.md)。这些成绩属于各自旧包，不能作为当前 v6 的验收结果。

这是 **原生玻璃前层加 2D 室内贴图近似**：家具、墙壁和灯具没有真实室内几何，不提供随视点移动的正确视差或遮挡；六张图也不能完全消除重复。图片中的透视和光照已经烘在图像中，适合本项目的固定机位，不应当作可进入的室内场景。
