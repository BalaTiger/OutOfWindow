# 后巷墙面风化素材

使用内置 image_gen 生成，完整提示词见 [generation-prompts.json](generation-prompts.json)。两张原图均为 1254×1254 RGB，保留生成原文件；UE 以线性遮罩导入并生成二次幂纹理与 mip。

- `plaster-relief-height.png`：浅色为完整抹灰，较暗区域为裸露砂浆与小孔。用于露底遮罩、独立粗糙度及高度梯度法线，不直接作为墙面固有色。它是美术制作的高度近似，不是扫描或测量数据，不改变模型轮廓。
- `runoff-mask.png`：黑底灰白旧流痕遮罩。仅在三处窗台下薄投射，生成低强度颜色沉积；不覆盖接收墙体的法线和粗糙度，因此保留动态雨湿响应。

生成脚本是 `unreal/Scripts/build_alley_weathering.py` 和 `build_alley_weathering_decals.py`，均已加入 `Run-Unreal.ps1 -Mode Import`，位于基础表面材质生成之后。素材哈希参与派生资产路径，避免修改 PNG 后继续引用旧导入纹理。

干墙保留原有色斑，以较低对比混入暖灰砂浆；剥落边缘由高度法线表现。原 v9 湿润链继续驱动变暗、粗糙度和湿痕，强湿痕仅平顺新增细颗粒，保留宏观边缘。

v2 将露底阈值从 0.55 降至 0.49，复用高度图做 900 cm 大尺度分布遮罩，给完整抹灰留出连续区域。颜色、粗糙度和宏观凹凸共用最终露底遮罩，宏观高度为 `-exposure × relief`；细颗粒独立保留。未新增图片或修改百叶窗材质。

验证范围为两面主墙、三处原有局部贴花。首版记录见 [alley-weathering-verification.json](../../Migration/alley-weathering-verification.json)，稀疏版记录见 [alley-weathering-sparse-verification.json](../../Migration/alley-weathering-sparse-verification.json)。
