# Win11 少云近景 Houdini 单样本 — 2026-10-19

本轮真实完成一个隔离的 Houdini / Mantra 体积实验。**可复查，尚未美术通过，不替换已验收轻量云或应用少云近景。** 城市、应用源码、正式云资源及启动入口均未改动。

## 打开与查看

- 最终场景：`few-near-fractal01-protected.hip`。同目录保留 `sample06-control.bgeo.sc`、`sample06-density.bgeo.sc`；两条 File SOP 都用 `$HIP` 相对路径。
- 原生开关：`/obj/cloud_density/BASELINE_0_EXPERIMENT_1`，0 为原密度，1 为本轮实验。非渲染控制 mesh 完整保留。
- 最终对照：`final-reference-baseline-candidate.png`；独立候选：`final-candidate.png`。
- 原始真实渲染：`baseline.exr`、`protected-candidate.exr`。
- `few-near-fractal01.hip`、`candidate.exr`、`initial-diagnostic-*` 是保护范围不足的第一轮诊断，不作为最终候选。

## 继承和修改

继承 `.runtime/resume-20261014/cloud-candidate/houdini-cloud01-20261016/cloud01-sample06-review.hip`。该基线延续 sample01 的不等主冠、次冠与低右肩大形，包含 sample06 的 B 云瓣连接曲率修复。参考仍是原 WMO 页面的固定裁切，没有增加参考或扩展云库。

在一个原生 128³ density volume 上，增加固定种子、多尺度的连续坐标位移及不规则内部密度凹区；没有复制独立云朵，没有整体拉伸，没有烘焙光照、统一增亮或后期锐化。最终噪声尺度为 145/71/52 个原场景单位，位移长度限幅 42。体素间距为 15.625/12.5/7.8125，52 仍只是低分辨率结构试验，不是精细分形完成证据。

第一轮保护区没有完整覆盖 B 修复涉及的浅层连接皮，经独立复核后修正同一样本。最终完全保护 `abs(U)<=330, H=200..680, D<=65`，外接平滑过渡；213,439 个保护体素与原始密度逐值完全一致，最大差 0。第一轮该区最大差为 0.68198，保留为诊断，未暗中覆盖。其他部位的真实密度仍可能改变跨区阴影，因此不声称保护区像素相同。

## 控制、资源及实测

Houdini 20.5.332 / Commercial 实际启动、保存、重新加载、回滚密度哈希核验及 Mantra CPU 渲染均成功。普通沙箱启动遇到 Windows DLL 重定位错误；经过平台正式提升审核后执行成功，没有调整许可服务或安全配置。

相机位置、旋转、FOV、原世界 Z 反射修复、太阳、材质及曝光均沿用原生基线。基线和候选重新使用相同 AA 3×3、体积/阴影步长率 2、关闭随机透明的设置。与旧 10/16 渲染的采样不同，故只比较本轮重新渲染的基线。名义相机画幅 2560×1440，实际 EXR data window 为 x100/y190/350×125，仅 43,750 像素；没有通过移动相机或拉伸图像放大云。展示为相同 3 倍最近邻放大、标准线性合成与 sRGB 编码。

- 单 Houdini/Mantra 渲染树，基线与候选串行，未运行 UE/GPU。
- 2 个逻辑 CPU、BelowNormal、进程树硬内存上限 2 GiB、180 秒超时；物理可用内存及 GetPerformanceInfo 精确 commit 余量均保留至少 4 GiB。
- 首轮构建与两张渲染共 68.58 秒，峰值 758.35 MiB；保护修正版构建与单次复核 35.56 秒，峰值 892.16 MiB，全部 exit 0，渲染槽已释放。
- 最终总密度积分相对基线 -3.7973%；未用补偿增益抵消这个变化。
- 密度阈值 0.0001 和 0.02 下，基线及最终候选均恰好一个 6 邻接连通体；最外两层体素密度均为 0。
- 图像 alpha>0.02 的轮廓 IoU 为 0.96748；边界从 `[198,214,355,284]` 到 `[197,214,356,284]`，左右各增加 1 原生像素，上下不变。
- alpha>0.8 的像素从 2667 降为 2414。内部密度修改也改变了厚实程度，不能把所有画面差异归因于新增形体。
- 三项基线源文件 SHA256 重新核对完全不变。最终 Git 正常 LFS 状态无 tracked modification，只有新增记录及预览文件。

## 实际视觉结论

原来的不等三冠关系仍然保留，边缘和前部明暗有轻微不规则变化；未见体积盒裁切硬边。**变化幅度较小，宽滑云冠和简化内部仍明显，远未达到参考图细碎、不重复的云瓣及内部遮挡层次。** 本轮不能宣称方角问题全面消失、分形细节或照片自然度验收通过；保护的是已有 B 修复，未完成其他所有曲面缺陷的消除。

这次实验说明：保持旧 65 单位宽密度过渡、在低分辨率场中做有限坐标扰动，视觉收益不足；继续增大噪声或侵蚀有损厚实结构的风险。下一步应单独验证更紧的局部体积域、可分辨的中尺度表面结构和内部真实遮挡，并在同一物理步长下比较。暂不扩大云群，不以堆叠相同云或整体拉伸补复杂度。

## 证据与同步边界

`native-result.json`、`protected-native-result.json`、`volume-audit.json`、`final-image-audit.json`、两份 `*-budget.json` 和日志可复核原生结果。`edge_internal_protected.vfl` 是最终可编辑代码，已嵌入 HIP。

轻量云同步详情在 `docs/cloud-win11-sync-20261019.md`：10/18 的 `80793d1` 源码及三项 LFS 资产已到位，但启动器仍指向 10/17 旧构建，少云远景轻量云距离分流也尚未实现。未尝试重新构建/部署或改动已验收路线。该运行缺口不是 Houdini 许可阻塞。

技术参考仅用于 API 语义核对：[Volume Wrangle](https://www.sidefx.com/docs/houdini/nodes/sop/volumewrangle.html)、[volumesample](https://www.sidefx.com/docs/houdini/vex/functions/volumesample.html)。本机实际执行输出是能力依据。
