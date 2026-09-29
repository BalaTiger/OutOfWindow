# 校准室内 cubemap

本目录保存 `v16` 详细 Interior Mapping、`interior-cubes-v3` 的离线烘焙来源和预览证据。六种室内来自本工程的实际简化 3D 模板，不使用旧的整张室内 PNG 作为后墙。**六个 cube 已重新烘焙，资产、GPU 方向、候选包六组回归及性能已核验；2026-09-29 已部署并确认安装版正常运行。**

| 序号 | 实际模板布局 | HDR 导出 | UE 静态资产 |
| --- | --- | --- | --- |
| 01 | 书房 study | `room-cube-01.hdr` | `T_RoomCube_01` |
| 02 | 起居室 sitting | `room-cube-02.hdr` | `T_RoomCube_02` |
| 03 | 厨房 kitchen | `room-cube-03.hdr` | `T_RoomCube_03` |
| 04 | 卧室 bedroom | `room-cube-04.hdr` | `T_RoomCube_04` |
| 05 | 餐室 dining | `room-cube-05.hdr` | `T_RoomCube_05` |
| 06 | 阅读室 reading | `room-cube-06.hdr` | `T_RoomCube_06` |

UE 资产目录为 `/Game/Materials/OOW/InteriorMapping/`，类型为 `TextureCube`，每面 `256×256`，HDR 压缩、`sRGB=false`，使用原生 mip。HDR 文件由原生 cube 导出为经纬展开图，用于复查捕获内容和亮度；运行时采样的是静态 TextureCube，不进行实时室内捕获。

六种模板共用以下校准。单位为米，局部坐标为 **X 向右、Y 向上、Z 向室内**：

- 盒体范围：`min=(-1.8,-0.45,0)`，`max=(1.8,3.05,3.4)`。
- 窗口范围：`min=(-1,0)`，`max=(1,2.75)`，窗口位于 `Z=0`。
- 捕获中心：`(0,1.375,0.20)`，位于窗口中心高度、窗后 20 厘米。UE cube 的坐标为右、向内、上，因此采样方向是 `(hit-captureCenter).xzy`。
- 实际窗宽高为 `W,H` 时，射线各轴按 `(2/W,2.75/H,2.75/H)` 缩放，再求盒体交点。不得直接用反射向量采样，也不得单独移动捕获中心而不更新材质。

生成入口为 [build_interior_atlas.py](../../Scripts/build_interior_atlas.py)，复用 [build_room_boxes.py](../../Scripts/build_room_boxes.py) 的六种家具模板。烘焙在独立关卡通过 UE 原生 SceneCaptureCube 完成，需要真实 RHI；材质编译等待、场景更新及 GPU 读回均在脚本中同步。灯具采用固定光强，独立烘焙材质实例强制 `Night=1`、`Occupied=1`，不依赖生产场景的当前时间。生产室内实时灯预算与这些临时烘焙灯分开。

v16 将探针从房间中部移到窗后，减少近家具投到盒面后的放大及背面误差。`interior-cubes-v3` 将临时主灯设为 `135 lm` 并保留阴影，天花和窗口补光分别设为 `120 lm`、`60 lm`，关闭补光阴影以近似漫反射反弹，降低硬阴影造成的黑亮二分。此补光不是 GI 解算；六个 cube 已按此配方重新烘焙，采样与面分类验证都从同一 `CAPTURE_CENTER` 读取校准。

[interior-atlas.json](../../Migration/interior-atlas.json) 记录几何哈希、校准、纹理路径、HDR 导出哈希及亮度统计。只有六个 cube 均捕获成功，脚本才写入 `bakedInUnreal=true`；这个字段不等于视觉验收或部署通过。

本轮 [资产审计](../../Migration/window-interiors-audit.json) 为零失败；同一窗口、同一厨房 cube 从距窗 12 米的仰视、平视和俯视相机完成 [GPU 方向验证](../../../.runtime/ue-window-rebuild/cube-orientation/verification.json)，20:21 阴天实景见 [候选包验收图](../../../.runtime/ue-window-rebuild/packaged-2021.png)。候选包回归、GPU 帧时间及安装目录哈希与重启证据见 [完整验收](../../Migration/window-interior-mapping-verification.json)。

家具颜色被投影到单一代理盒体，仍没有独立深度、完整的家具遮挡变化或真实室内 GI。大窗与明显需要家具轮廓的窗继续使用实体几何。此版本完成基本 Interior Mapping，没有加入双深度 POM。工程分配、灯光预算与验收见 [window-interior-mapping.md](../../Migration/window-interior-mapping.md)。
