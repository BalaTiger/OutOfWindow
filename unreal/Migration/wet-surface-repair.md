# 后巷湿表面修复

2026-09-28。针对 Unreal 后巷小雨时建筑湿痕和路面水膜不明显的问题，更新 `build_surface_materials.py`，仅 ground、stone 材质采用 v9，其他材质保留既有版本。

- **浅水水膜**：出现强度改为 `smoothstep(.02,.16,Water)`，覆盖阈值为 `lerp(.18,.68,Water)`。积水量主要扩大面积，浅水内部也能形成平滑反射；目标粗糙度为 `.055+.025*RainIntensity`，且不提高原有更光滑表面的粗糙度。原路面法线按积水遮罩混入带雨滴涟漪的水面法线，积水区域额外暗化最多 18%。
- **建筑湿痕**：在原有整体湿润响应上，增加世界坐标控制的竖向湿痕、局部暗化和粗糙度变化。额外效果随 `Wetness` 混入，干态为零；朝上的水平屋顶额外湿痕为零，倾斜表面按朝向渐变。
- **材质分类**：修正名称含 `Leaves` 的石板路面被归入 foliage 的问题；明确标记为 foliage 动画的植物仍走原植物分支。
- **真实雨量**：雨强、湿润和积水累积公式保持不变。新增仅在测试模式生效的 `-OOWTestPrecipitation`，支持确定性的 0.1 小雨；`validate.ps1 -Cases alley-lightrain` 使用该输入。

本次使用 `OOW_MATERIAL_SCENES=alley`、`OOW_MATERIAL_KINDS=ground,stone` 定向重建，更新 378 个材质槽，生成 36 个新资产；已有其他资产哈希保持不变。

已完成 Editor 小雨、晴天、雨天检查及只读审计；最终覆盖范围调校后的 Windows 成品也通过小雨、晴天、雨夜三例。60 秒小雨用例保持雨强 0.325381、积水量 0.485868；晴天湿润度和积水均为零。日志没有材质编译回退、Fatal error 或 Ensure，Lumen 反射保持开启。

验证程序已部署至 `D:\OutOfWindowBuild\Windows`，12 个部署文件逐一核对 SHA256，并按原启动参数恢复后巷、实时天气和象牙白窗框。旧成品备份在 `D:\OutOfWindowBuildBackups\wet-surfaces-before-20260928-145015`。首次复制遇到退出进程尚未释放的资源句柄，待进程退出后重试成功；最终哈希全部一致。

数值与部署记录见 [wet-surface-verification.json](wet-surface-verification.json)。最终小雨、晴天、雨夜截图分别保存在仓库 `.runtime/ue-wetness-repair/packaged-light.png`、`packaged-clear.png`、`packaged-rainnight.png`。当前固定镜头中的路面面积较小，保留 Lumen 原生反射，未增加额外平面反射渲染通道。
