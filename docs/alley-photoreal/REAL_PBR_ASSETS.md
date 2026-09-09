# 后巷真实石材 PBR 资产准备

运行时目前继续使用本地派生通道作为默认值，后巷使用按固定机位恢复近景建筑的 ORCA near-768 包，并在可见窗玻璃边界上生成独立窗框条。真实替换包已准备好下载脚本：

```powershell
node scripts/download-real-bistro-pbr.mjs
```

脚本从 Poly Haven 获取两套 CC0 材质并压缩到 1K：

- `plastered_stone_wall`：用于墙体、灰泥和砖石立面。
- `cobblestone_floor_001`：用于石板路和路缘。

每套包括 diffuse、ARM（AO/roughness/metalness）、OpenGL normal 和 displacement。脚本完成后会把 `src/bistro-pbr-config.js` 的开关改为真实通道，启动预加载会自动使用它们；如果下载失败，运行时仍保留派生通道回退。

来源页面：[Plastered Stone Wall](https://polyhaven.com/a/plastered_stone_wall)、[Cobblestone Floor 001](https://polyhaven.com/a/cobblestone_floor_001)。Poly Haven 页面列出了 AO、ARM、位移、OpenGL 法线和 roughness 通道，并标明材质为 CC0。
