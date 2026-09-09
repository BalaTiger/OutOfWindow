# 都市与后巷场景资产组织

2026-09-09：原城市场景拆为两个独立场景，避免街内机位与外围素材争夺同一构图。相机配置集中在 `src/scene-pack.js` 的 `SCENE_VIEWS`。

## 后巷：保留当前街内机位

- 主场景：Amazon Lumberyard / NVIDIA ORCA Bistro Exterior（CC BY 4.0）
- 运行范围：约 `179 × 190 × 52.6 m`
- 当前固定相机：`(-20, 23, -208)`，目标点 `(-46, 23, -246)`，垂直视场角 `55°`
- 射线测得附近石板路高度约 `7.05–7.17 m`，因此相机离路面约 `16 m`。构图优先显示真实街内立面、栏杆和道路，避免资产背墙与外围空地。
- 后巷仅显示 Bistro 与座椅道具；公寓、工厂、Helsinki 远景和都市车流归属独立的都市场景。

## 都市：展示原先不可见的街区素材

- 相机 `(10,26,34)`，目标 `(-4,19,-110)`，垂直视场角 `50°`。
- 道路沿 Z 轴延伸，公寓位于两侧 `x=±35 m`，以真实 3×3 m 模块构成宽 21 m、5–8 层的闭合建筑；保留原始 PBR 通道。
- 重复模块按建筑实例化；道路三角形朝上，UV 按米制平铺；工业立面在街尾，车库使用 6 m 宽模块。
- Helsinki 按世界包围盒约束最前端 `z≤-290 m`、最高点 `y≤46 m`，避免源文件偏移导致扫描地形进入前景街道。
- 每个场景独立设置太阳目标和天空捕获原点；所有场景沿用同一时间、天气和画质。
- 按需串行加载并缓存模型；都市启动不读取 Bistro，两个场景共享座椅只解码一次。

## 研发候选：NVIDIA Emerald Square

- 官方来源：https://developer.nvidia.com/orca/nvidia-emerald-square
- 内容：四个完整、可平铺城市街区；2,695,054 个独立三角形，实例展开后共 10,046,405 个三角形。
- 格式：日景/暮景 FBX、Falcor 场景、351 张 DDS PBR 贴图和两张 HDR；需离线转换为 glTF/GLB。
- 官方压缩包：617,345,248 bytes；解压后约 1.54 GB。
- 材质通道：BaseColor Alpha 为透明度；Specular DDS 的 R/G/B 分别为 AO、Roughness、Metalness；法线为 DirectX，需要在 glTF 转换时翻转绿色通道。
- 许可证：CC BY-NC-SA 3.0。
- 本地隔离目录：`.runtime/emerald-square-source/`（不进入 Git、Vite 构建或发布包）。
- 用途：验证 Bistro 外围街区的尺度、遮挡关系、LOD 和批处理转换流程。

Emerald Square 的非商业、相同方式共享条款不适合直接作为未来商业版默认资源。因此它只作为研发构图候选；在许可证问题解决之前，运行时代码不得引用该目录。

## 可发布远景：Helsinki 3D Reality Mesh

- 官方来源：https://www.hel.fi/en/decision-making/information-on-helsinki/maps-and-geospatial-data/helsinki-3d
- 下载索引：https://3d.hel.ninja/data/mesh/Helsinki3D-MESH_2017_OBJ_2km-250m_ZIP/
- 许可证：CC BY 4.0，允许商用并要求署名。
- 内容：由航拍照片重建的带纹理真实城市网格，包含建筑、树木、停放车辆和小型构筑物；官方说明位置精度约 20 cm。
- 选定来源瓦片：`Helsinki3D_2017_OBJ_668494x2.zip`。运行版只保留与固定窗景构图相关的子瓦片，并输出为 `public/assets/helsinki/helsinki-periphery-lod2.glb`。
- 限制：摄影测量贴图包含采集时光照，不适合作为近景 PBR 资产，因此只用于 180 m 以外的 LOD2/天际线层，并通过色彩去光照和实时雾弱化烘焙阴影。

## 集成结构

两个场景采用不同的资产组织：

1. 后巷：Bistro 完整街景与当前机位。
2. 都市近中景：Poly Haven 公寓、工业立面、座椅，以及 ambientCG 道路。
3. 都市远景：Helsinki 城市网格 LOD2，使用实时雾衔接天空。

不得使用无纹理方盒、静态城市背景图或随机生成建筑填补边界。外围街区需要在 DCC 转换阶段完成：

- 统一米制比例与 Y-up 坐标；
- 删除相机不可见的室内和重复底面；
- 合并同材质静态网格，生成 LOD1/LOD2；
- 将贴图转为 1K/2K KTX2，并保留 BaseColor、Normal、Roughness、Metalness 与 Alpha；
- 按街区拆分 GLB，使应用能按距离加载；
- 对最终候选执行许可证复核并登记到 `THIRD_PARTY_ASSETS.md`。

## 验收条件

- 后巷原机位与目标点保持不变；都市显示连续立面、屋顶与道路纵深；
- 五个场景可独立选择，切换不串场、不重复加载，也不重置时间、天气或画质；
- 正午近景保留明确的受光面和阴影面，外围 LOD 不产生亮度跳变；
- 城市场景在目标桌面分辨率下维持 45 FPS 以上，外围资源按需加载且不阻塞首屏。
