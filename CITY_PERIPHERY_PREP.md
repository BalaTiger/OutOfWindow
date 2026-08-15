# 城市场景外围资产准备

## 当前近景基准

- 主场景：Amazon Lumberyard / NVIDIA ORCA Bistro Exterior（CC BY 4.0）
- 运行范围：约 `179 × 190 × 52.6 m`
- 当前固定相机：`(45, 23, -70)`，目标点 `(0, 29, -105)`，垂直视场角 `43°`
- 相机离地约 `24 m`，画面保留屋顶、立面和约 15%–20% 天空。

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

外围城市不作为近景替代物，而按三个距离层组织：

1. `0–110 m`：保留 Bistro 原始网格、PBR 材质和完整细节。
2. `110–260 m`：使用外围街区的简化网格与 1K PBR 贴图，保留屋顶轮廓、窗洞和主要立面凹凸。
3. `260–450 m`：使用同一资产生成的 LOD2，只保留城市轮廓和少量高层地标，由实时雾和天空散射衔接。

不得使用无纹理方盒、静态城市背景图或随机生成建筑填补边界。外围街区需要在 DCC 转换阶段完成：

- 统一米制比例与 Y-up 坐标；
- 删除相机不可见的室内和重复底面；
- 合并同材质静态网格，生成 LOD1/LOD2；
- 将贴图转为 1K/2K KTX2，并保留 BaseColor、Normal、Roughness、Metalness 与 Alpha；
- 按街区拆分 GLB，使应用能按距离加载；
- 对最终候选执行许可证复核并登记到 `THIRD_PARTY_ASSETS.md`。

## 验收条件

- 24 m 相机高度下，任何可见方向都不出现模型截断、无材质背墙或世界空洞；
- 天空占画面 15%–30%，仍能看到至少一条街道或庭院纵深；
- 正午近景保留明确的受光面和阴影面，外围 LOD 不产生亮度跳变；
- 城市场景在目标桌面分辨率下维持 45 FPS 以上，外围资源按需加载且不阻塞首屏。
