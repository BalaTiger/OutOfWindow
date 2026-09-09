# 后巷运行时 LOD

后巷现在同时加载两个同尺寸、同节点命名的 Bistro 包：

- `bistro-exterior-near-768.glb`：恢复固定机位近景建筑几何；
- `bistro-exterior-lod-safe-768.glb`：远景减面几何。

`ScreenSpaceLodManager` 不使用 `THREE.LOD.position`，而是在模型最终缩放和摆放后，为每个建筑簇计算世界空间 `Box3`。它用相机视锥和包围球投影到屏幕后的像素半径决定档位，并设置 80/110 px 的迟滞，避免边界抖动。建筑簇按完整楼体节点一起切换，窗蓬、植物和运行时生成的窗框不参与降级。

近景变体由 `scripts/restore-bistro-near-geometry.mjs` 生成，配置清单写入 `near-geometry.json` 和 `src/alley-lod-config.js`。如果未来调整后巷机位，需要重新生成 near 包和节点清单；运行时不会根据父节点原点推断建筑距离。
