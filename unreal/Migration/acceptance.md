# Out of Window → UE5 迁移验收清单

审查日期：2026-09-23。原行为基线来自 `index.html`、`src/main.js`、`src/solar-time.js`、`src/rain-response.js`、`src/scene-pack.js`、`src/render-pipeline.js`、`src/styles.css`、`electron/main.cjs`、`electron/preload.cjs` 及测试源码；本轮工程证据来自 `unreal` 内源码、资产、迁移报告及实际构建日志。只有已经核实的条目才勾选；生成项目、导入模型、编辑器里出现一张后巷画面，都不等于产品迁移完成。

## 本轮已经核实的工程证据

- [x] 已创建 `OutOfWindow/OutOfWindow.uproject`，引擎关联为 5.7，本机实际使用 UE 5.7.4；原 Electron/Three.js 工程保留。
- [x] 五景 GLB/语义 JSON 已导出，`Content/Maps` 中五个 `.umap` 已生成；`Migration/import-*.json` 记录 Actor、独立 Mesh、Nanite 与传统 LOD 数量。这只验证资源与导入流程，不替代五景画面验收。
- [x] 公共配置已设置 DX12/SM6、Lumen GI/反射、硬件光追、VSM、TSR，并关闭静态光照。已有运行 JSON 回读 Lumen、硬件光追与 TSR 状态，详见末尾记录；不能据此声称性能达标。
- [x] 表面材质生成脚本已在真实 UE 中完成五景处理，`Migration/material-probe.json` 当前 `failures` 为 0；雨、雪和 `M_RainSplash` 生成记录见 `.runtime/ue-precipitation.log`。
- [x] VS2022 Build Tools、MSVC 14.44.35229、SDK 10.0.22621.0、.NET Framework 4.8 SDK/Targeting Pack 均已安装并核实；Windows C++ 编译、链接和运行 smoke test 通过。
- [x] Development Editor 和 Game 目标已有实际成功构建记录，分别见 `.runtime/ue-build-editor.log`、`.runtime/ue-build-game.log`；中间重编译见 `.runtime/ue-build-final.log`，岸线/单实例修正后的最终构建见 `.runtime/ue-build-revalidation.log`。构建与运行证据按版本分别记录。
- [x] 独立打包程序的 15 例、每例 30 秒矩阵全部通过自动检查，包含五景晴天、后巷雨/夜/雨夜/雪/雾/UI、都市雨、后巷三档画质和桌面接口；长期证据为 [packaged-verification.json](packaged-verification.json)，详见末尾实测表。
- [ ] 动画连续性、完整 UI/托盘人工交互、长时间性能和美术全面验收尚未完成，不能由上述自动检查代替。
- [x] Windows Development 已完成 Cook、Stage、IoStore、Archive，`.runtime/ue-package.log` 记录 `BUILD SUCCESSFUL` / ExitCode 0；独立 exe 已多次从退出状态启动并完成矩阵。

下方尚未勾选的交互和画面条目表示尚未逐项完整验收，不表示相关源码一定缺失。自动检查只覆盖明确列出的范围。运行和重建入口见 [UE5 工程说明](../README.md)。

## 范围与当前产品边界

- 完整迁移包含都市、后巷、村庄、山林、海滨五种窗景及桌面外壳。若首阶段仅交付后巷，应明确标为后巷阶段，不把另外四景或桌面功能标记完成。
- 当前没有设置持久化：未使用 `localStorage` / `sessionStorage`，场景、时间、天气、画质、音频、收起状态、穿透和窗口尺寸仅在进程内存在。Electron 的 `.runtime` 用户目录及缓存不等于应用偏好已保存。
- 当前天气仅在启动和点击刷新时联网；每秒更新的是时钟。自动天气轮询、手动城市输入、首次联网授权、季节、空气质量、月相、天气记录均不属于已经实现的功能。
- 当前无自由漫游、鼠标转镜头、缩放或相机呼吸抖动。开发查询参数中的相机覆盖仅用于检查，不是用户功能。
- 环境声目前是循环噪声经低通滤波后的低音量占位，不是独立雨声、交通、鸟鸣音轨；雪只有下落粒子，没有地表积雪；场景文案里的“炊烟”没有对应的活动烟雾实现。
- 原版 Electron README 同时残留按需加载和全场景预加载两种描述；原版源码在启动阶段加载五景并预热 shader。UE 当前使用整张关卡切换；切景无需重新下载资源，但未完成后台预取和切景卡顿验收。

## 必须保留的全部交互

以下控制可使用一个 UMG/Slate 主界面统一实现，并绑定同一份运行状态，避免控件外观与真实状态脱节。[Epic Slate 文档](https://dev.epicgames.com/documentation/en-us/unreal-engine/slate-user-interface-programming-framework-for-unreal-engine)

| 验收 | 现有入口 | 必须可观察的行为 | UE5 对应方式 |
| --- | --- | --- | --- |
| [ ] | 五个场景按钮 `sceneTabs` | 选择都市／后巷／村庄／山林／海滨；标题、说明、编号 01–05、选中态随之变化；时间、天气、画质连续 | 场景数据表与关卡或场景根 Actor；共享状态放 GameInstance/Subsystem |
| [ ] | `weatherModes` 五选一 | 实时、晴、雨、雪、雾均真正改变天空、光照、雾或粒子；实时模式按天气代码驱动 | 枚举与天气控制 Actor；动态材质参数和 Niagara |
| [ ] | `timeSlider` | 00:00–23:59，分钟精度；拖动立即退出“跟随当地”，时刻、太阳、时段更新 | Slider → 分钟数 → 同一太阳计算入口 |
| [ ] | `liveTime` | 可开关；恢复后跟随定位所在地时间，不误用 PC 当前时区；不影响天气模式 | 1 秒 Timer；UTC、所在地时区和日期转换 |
| [ ] | `refreshWeather` | 刷新旋转反馈；更新城市、温度、WMO 中文天气、图标、风速、当地时钟和同步状态 | 异步 HTTP 请求及状态回调 |
| [ ] | `renderQuality` | 节能／均衡／精细，切换不重置场景；视觉成本确实有区别 | `UGameUserSettings` / Scalability + 项目反射、粒子质量参数 |
| [ ] | `ambientToggle` | 初始不播放；点击启停、有状态反馈；切场景连续改变声景音色，淡入淡出无爆音 | AudioComponent 或 MetaSound；低通频率与音量参数 |
| [ ] | `collapsePanel` | 只收起控制面板，仍可再次展开 | UMG 动画与可交互的面板标题 |
| [ ] | `compactMode` | 整体精简 UI，隐藏状态卡、场景说明、面板、声景和页脚；保留可恢复的标题栏；桌面尺寸切 760×510／1040×690 | 独立于面板折叠的 Compact 状态；Slate 窗口 resize |
| [ ] | `dismissPrivacy` | 关闭“城市级近似定位”提示，不误称精确地址；当前只在本次会话隐藏 | UMG 提示与运行态布尔值 |
| [ ] | `clickThrough` | 切换真正的系统鼠标穿透，按钮状态同步；开启后能从托盘恢复 | Windows 原生窗口适配，不能只关闭 UMG Hit Test |
| [ ] | `minimize` | 系统窗口最小化 | Slate/平台窗口调用 |
| [ ] | `maximize` | 最大化／还原切换；图标、提示和尺寸状态同步 | Slate/平台窗口调用及系统事件 |
| [ ] | `close` | 主窗口关闭操作隐藏到托盘，进程继续存在 | 拦截关闭请求；隐藏窗口 |
| [ ] | 标题栏拖动区域 | 可移动无边框窗口；按钮本身可点击 | 原生窗口拖动命中区域 |
| [ ] | 托盘“显示／隐藏窗景”及单击图标 | 隐藏后可恢复，显示不会无故抢夺焦点 | Windows 托盘实现与原生窗口显隐 |
| [ ] | 托盘“鼠标穿透” | 与主界面状态相同，能解锁不可点击的窗口 | 与 UI 共用 Desktop 状态 |
| [ ] | 托盘“桌面挂件模式” | 当前语义是置顶 + 不显示任务栏；关闭后恢复普通窗口行为 | Windows topmost、任务栏样式；不是桌面壁纸 WorkerW 模式 |
| [ ] | 托盘“退出” | 真正结束程序；区别于标题栏关闭 | 主动退出状态与完整资源清理 |

补充显示验收：启动加载阶段与百分比、失败信息、城市/区域去重显示、温度取整、风速 km/h、当地 HH:mm、“实时天空／离线演示数据”、当前时段，以及真实运行 FPS 标签均须保留。中文字体、焦点、按钮可读性和 760×510 紧凑布局必须在打包版检查。旧 HTML 的声景按钮初始视觉为 active，但音频初始关闭，是原 UI 不一致，应修正而非照抄。

## 时间、天气和照明

现有天气链路为 `ipwho.is` 城市级 IP 定位 → Open-Meteo current 数据。UE 可使用原生 [FHttpModule](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/HTTP/FHttpModule) 及 JSON 解析，保留两个服务、错误状态和离线演示；网络不应阻塞游戏线程。

- [ ] 保留经纬度、所在地时区、温度、体感温度、天气代码、昼夜标志、降水、云量、风速、风向和阵风字段；仅内存使用定位与天气，日志不新增 IP 或精确位置持久化。
- [ ] 网络失败/超时仍可进入可用窗景，状态明确显示“离线演示数据”；默认上海（31.23, 121.47, Asia/Shanghai）、22°C、天气代码 1、云量 35%、风速 8 km/h。桌面请求当前各有 8 秒超时。
- [ ] WMO 映射保持：45/48 → 雾；71/73/75/77/85/86 → 雪；51/53/55/61/63/65/80/81/82/95/96/99 → 雨；其余 → 晴类。0–3 的云量差异仍通过实时云量体现。
- [ ] 手动时间与手动天气互相独立；刷新天气不可把用户手动天气或手动时间擅自改回实时；当地状态时钟仍正常显示。
- [ ] 太阳高度依赖所在地经纬度、当地日期、时区、闰年与 DST；不可仅做小时数驱动的固定半圆。可保留现有 NOAA 公式或使用 Sun Position Calculator。[Epic SunSky](https://dev.epicgames.com/documentation/en-us/unreal-engine/sun-and-sky-actor-in-unreal-engine) 支持日期、经纬度、时区和 DST，但 IANA 时区自动解析仍需应用层处理，不能全年固定 UTC offset。
- [ ] “深夜／夜晚／晨曦／暮色／清晨／黄昏／上午／日中／午后”按太阳高度和时刻决定，不能上午 10:47 仍显示清晨。
- [ ] 保留产品原有的构图光向约定：后巷光向随 06–18 时从画面左侧向右侧移动，高度由真实太阳高度决定；其余景使用场景艺术方位。源场景未按真实地理北向建模，不能宣称原版具备完全真实的建筑朝向。
- [ ] 日夜切换同时改变直射光、环境反射、天空、雾色、云层、曝光及夜灯；夜间太阳不从地下照亮场景。UE 使用 Movable DirectionalLight、SkyAtmosphere、SkyLight、动态雾及受控曝光；不能仅修改背景颜色。
- [ ] 后巷暖石材、都市较冷天空基调保留；日间窗玻璃不自发光，不出现白色不透明板；夜灯在暮色逐渐开启。

## 固定机位与场景内容

| 场景 | Three.js position | target | 垂直 FOV |
| --- | --- | --- | --- |
| 都市 | (24, 26, 34) | (-1, 15.5, -116) | 56° |
| 后巷 | (-20, 23, -208) | (-46, 23, -246) | 55° |
| 村庄 | (0, 8, 24) | (0, 2, -30) | 48° |
| 山林 | (0, 7, 20) | (0, 3, -24) | 48° |
| 海滨 | (0, 10, 25) | (7, 2, -31) | 48° |

- [x] 已核实并记录 UE 5.7 glTF Interchange 实际转换：源场景以 Y 向上、米为单位，`UE=(ThreeX, ThreeZ, ThreeY)*100`；导出的场景已包含世界变换，不再重复施加原包装变换。后巷相机对应 `(-2000,-20800,2300)` cm，依据见 `asset-inventory.md` 和 `scene-manifest.json`。
- [ ] 使用固定 CameraActor/ViewTarget 并禁用游戏自由移动。上表是基线构图；Three 垂直 FOV 不可直接照填 UE 默认水平 FOV。适配 viewport aspect，或明确约束垂直 FOV；不同窗口尺寸不得挤压几何。
- [ ] 原窗框、横竖中梃、窗台、玻璃轻反光和边缘阴影继续形成“从室内向外看”的产品形态；3D 画面裁剪在窗洞内，UI 不被透明面错误遮挡。
- [ ] 后巷保留 Bistro 街区、近景高模、远景 LOD、红雨篷、植物、石板路和正确窗框；尤其右侧窗玻璃不得穿进墙体，百叶窗不得误刷成灰泥。既有修复不是可以丢弃的浏览器特效。
- [ ] 都市保留公寓、工业模块、远景 Helsinki、道路功能区、示意车流和夜间窗灯；三个自然场景保留各自地形/扫描资产与溪流或海水。资源缺失必须列项，不能用同一后巷切五个名称代替。
- [ ] 材质须保持基色/法线/粗糙度通道色彩空间正确、叶片/栏杆遮罩和玻璃独立；ORCA 仅派生的 AO/height 不应写成真实扫描通道。保留本次砖石/灰泥分支、积水 Fresnel 和叶片湿润修复意图。
- [x] 仓库内资产署名与许可继续保留在 `THIRD_PARTY_ASSETS.md`，迁移清单也记录 ORCA/Helsinki CC BY 4.0、Poly Haven/ambientCG CC0 及其他文件约定。Windows 归档已附带 `THIRD_PARTY_ASSETS.md` 与 `ASSET_INVENTORY.md`，均与仓库原件核对哈希一致。

## 动画与天气表面

粒子宜使用 [Niagara](https://dev.epicgames.com/documentation/en-us/unreal-engine/overview-of-niagara-effects-for-unreal-engine)，表面使用材质实例、Material Parameter Collection 和 World Position Offset。验收动画结果，不要求照搬 Three.js 的 shader 拼接方法。

- [ ] 云层随时间和风移动，实时云量影响覆盖和光照；使用动态天空/云，不用固定截图冒充时间天气。
- [ ] 雨丝和雪粒子出现在当前机位附近；切到平移很远的后巷也可见，离开该天气停止相应粒子。雨的强度随降水变化；风向按气象 FROM 语义、km/h 转 m/s。
- [ ] 都市/后巷地表随降雨逐步湿润、形成不规则积水，露天地面有水花和涟漪；遮雨处区别于露天；雨停后有持续排水与干燥过程，不能瞬间全干。
- [ ] 积水随视角发生正确 Fresnel 反射，俯视保留受光石板，掠射角保留环境倒影；夜间水膜不凭空发亮，不能把漫反射背景当镜面反射。
- [ ] 后巷雨篷固定上缘、边缘摆动/颤动并有落雨冲击与蓬边滴水；叶片按植株高度约束风摆。湿叶仍有绿色与粗糙度层次，不变成满冠雪白高光。
- [ ] 都市车流沿原道路连续移动；海滨海面动态法线、反射和岸边泡沫持续运动；山林溪流有水面运动。已有动画在暂停时间滑条时仍继续，滑条不是全局动画暂停键。
- [ ] 音频按城市场景/后巷约 650 Hz、海滨约 420 Hz、其余约 850 Hz 的原占位低通差异迁移即可；升级授权音效应单独注明，不能宣称原版已有素材声景。

## 桌面外壳、设置与启动

- [x] 打包 Windows 程序能够独立启动，无需 Electron、Node 或 Vite 服务；15 例矩阵逐例启动/退出，已从完整退出状态重新运行。
- [x] 单实例：最终包第二次启动约 2.43 秒以退出码 0 结束，向现有实例发送恢复事件，不加载重复世界，首个进程继续运行；详见 `postFix.singleInstance`。
- [ ] 人工确认重复启动后的显示/聚焦体验；上述自动检查验证恢复事件已发送，不替代人工窗口交互验收。
- [ ] 无边框窗景、最小尺寸 760×510、正常尺寸 1040×690、首次位于主显示器工作区右下留 26 px；缩放、最大化、还原和高 DPI 可用。
- [ ] 透明外框、置顶、任务栏隐藏、托盘和鼠标穿透必须在实际打包 RHI 路径上验收。UMG 的透明背景不自动等于 Windows 合成器透明；原生窗口适配属于必须单独验证的工作，不把普通 UE 游戏窗口当作桌面挂件完成。
- [ ] 不增加原版没有的桌面 WorkerW 嵌入、开机自启、多显示器配置等功能声明；若另行实现，独立记录验证结果。
- [ ] 启动进度实际对应资源/材质准备；失败可见且能降级进入；五景切换无新网络下载或黑屏/长时间 shader 卡顿。UE 可 Cook 全部资产并用 Asset Manager/流式加载管理，但最终行为要匹配可用性。
- [ ] 画质三档映射到经实机测量的 [Scalability](https://dev.epicgames.com/documentation/unreal-engine/scalability-reference-for-unreal-engine)、分辨率比例、阴影/反射/粒子预算，不能只改下拉框文字。节能档应降低额外反射成本；UI 保持清晰。

设置持久化是原版缺项。如果本轮将其纳入 UE 产品，则使用一个小型 Config 或 [SaveGame](https://dev.epicgames.com/documentation/en-us/unreal-engine/saving-and-loading-your-game-in-unreal-engine) 保存场景、画质、时间/天气模式、手动分钟数、音频开关、收起状态和窗口位置/尺寸；重启恢复并校验无效值。实时天气和 IP 坐标不必写入。鼠标穿透恢复必须保留托盘解锁通道。未实现时清楚写“保持原版会话内设置”，不得勾选成“设置已持久化”。

## 最终证据与不允许替代的验证

- [ ] UE Editor 实际打开项目，所选引擎版本编译成功；项目源码存在不等于构建通过。
- [ ] Cook/打包成功并实际运行 Shipping 或 Development exe；记录 OS、UE 版本、GPU、RHI、分辨率、画质、启动时间、frame/GPU 时间与峰值显存，不能沿用旧 Electron 60 Hz 上限数字。
- [ ] 逐项操作上方全部 UI 与托盘控制并记录结果；另测断网、服务超时、重复启动、关闭到托盘、点击穿透后恢复、紧凑模式和最大化还原。
- [ ] 固定 Singapore、2026-09-09 10:47、本地 UTC+8 场景：太阳高度约 55–57°且标签“上午”；跨 UTC 午夜和 2024-02-29 正确；New York 一月 UTC-5／七月 UTC-4。以 `scripts/solar-weather.test.mjs` 作为既有逻辑基准。
- [ ] 五景晴天；后巷晴/雨/雪/雾/雨夜；都市雨景；后巷近景地面与右侧窗户；两档窗口尺寸。截图记录时间、天气输入、预湿时间、机位与画质，可重复对比。
- [ ] 后巷默认机位连续录像展示叶片/雨篷、滴水、降雨及积水，不用两张静态图代替动画验收；切晴后记录积水逐渐衰减。
- [ ] 资源、玻璃、叶片、近远 LOD、阴影和反射无明显闪烁/错位；每个明确缺项保留未勾选状态。最终交付应分别说明“已实现”“已运行验证”“尚待验证/缺失”。

## Windows 打包与独立程序实测（2026-09-23）

长期证据：[packaged-verification.json](packaged-verification.json)，顶层保存首轮 15 例完整状态、12 项桌面检查、环境及首轮 exe 的 SHA-256；`postFix` 另存最终包的哈希、两例复测、桌面检查、单实例和联网结果。原始 PNG/JSON/日志位于 `.runtime/ue-validation/packaged-*`，完整首轮汇总备份为 `packaged-matrix-summary.json`。此前 Editor 短测可能受其他全屏程序影响，不再引用其帧时作为本次结论。

完整矩阵对应首轮实际运行 exe，SHA-256 为 `79391D7B1BD99CE9D9366CE8C2109BDABCDC09DC93E8F48D8CD87A476C60EDCE`。之后只修改岸线局部网格和进程级单实例启动逻辑，统一重新 Build/Package 已成功（`.runtime/ue-build-revalidation.log`、`.runtime/ue-package-revalidation.log`）。下表保留首轮数据；新包的海滨/桌面复测在后面独立列出，不把旧矩阵说成在新二进制上重新跑过。

- [x] `.runtime/ue-package.log` 确认 Cook、Stage、IoStore 和 Archive 成功，AutomationTool ExitCode 0。入口为 `D:\OutOfWindowBuild\Windows\OutOfWindow.exe`；归档目录约 1.43 GB（1.33 GiB）。需分发整个 `Windows` 目录。
- [x] `Run-Unreal.ps1` 使用完整 `/Game/Maps/X` 关卡路径，避免 Engine 同名 Reverb 资产；Cook 输出为 `D:\OutOfWindowBuildCache\Cooked\Windows`；Windows 只 Cook DX12/SM6，启用 `-skipeditorcontent`。
- [x] 打包归档中的许可证和资产清单与仓库原件 SHA-256 相同。
- [x] Cook 后 15 例矩阵串行完成，验证进程退出码 0；每例运行 30 秒，统计排除最初 2 秒，不与 Cook 并行。全部相机绑定、必要标签、截图、几何/材质及 Lumen 状态检查通过；这些检查没有设置性能合格阈值。

测试环境：Windows 11 25H2、UE 5.7.4 Development、DX12/SM6、Intel Core i5-14600K、32 GB RAM、RTX 5060 8 GB、1280×820 窗口、`t.MaxFPS=60`。场景输入日期 2026-09-23，当地 UTC+8；夜间/雨夜为 23:00，其余 12:00。测试禁用在线天气和音频，除 `alley-desktop` 外均离屏渲染；因此桌面例与离屏例不是完全相同的呈现负载。

| 用例 | 画质 | 平均帧间隔（ms） | P95（ms） | 样本数 |
| --- | --- | ---: | ---: | ---: |
| alley-clear | 均衡 | 17.66 | 23.01 | 1,587 |
| alley-rain | 均衡 | 18.33 | 33.26 | 1,528 |
| alley-night | 均衡 | 16.95 | 16.77 | 1,653 |
| alley-rainnight | 均衡 | 17.69 | 27.75 | 1,584 |
| city-clear | 均衡 | 16.67 | 16.67 | 1,681 |
| city-rain | 均衡 | 16.67 | 16.67 | 1,680 |
| village-clear | 均衡 | 16.67 | 16.67 | 1,681 |
| forest-clear | 均衡 | 16.67 | 16.70 | 1,681 |
| coast-clear | 均衡 | 16.67 | 16.69 | 1,681 |
| alley-snow | 均衡 | 17.64 | 20.17 | 1,588 |
| alley-fog | 均衡 | 17.23 | 16.87 | 1,626 |
| alley-ui | 均衡 | 16.75 | 16.68 | 1,672 |
| alley-eco | 节能 | 16.67 | 16.67 | 1,680 |
| alley-fine | 精细 | 40.83 | 53.32 | 688 |
| alley-desktop | 均衡 | 16.67 | 16.67 | 1,681 |

精细档后巷平均约 **24.5 FPS**（1000 / 40.83），明显低于 60 FPS；均衡后巷雨景 P95 为 33.26 ms，也不能称作稳定 60 FPS。节能档此轮短测接近 60 FPS 上限，上限同时限制了可观察的峰值速度。上述数值是帧间隔，不是 GPU timer；不同档位同时调整分辨率和多个质量参数，不能把差值全部归因于单独一个反射选项。

三档均实际回读 Lumen GI/反射启用、硬件光追启用、TSR；对应差异如下：

| 画质 | 内部比例 | 首层透明反射 Enable/Allow | 硬件光追 LightingMode |
| --- | ---: | --- | --- |
| 节能 | 70% | 0 / 0 | 0（表面缓存） |
| 均衡 | 85% | 1 / 1 | 0（表面缓存） |
| 精细 | 100% | 1 / 1 | 2（Hit Lighting） |

- [x] 后巷打包例回读 4 盏夜灯、125 个天气材质实例和 1,650 个 Nanite 组件；雨景湿润度约 0.999、积水量约 0.910。都市晴/雨均记录 16 辆移动车辆。状态回读不替代连续运动或反射质量的目视验收。
- [x] `.runtime/ue-validation/packaged-alley-desktop.desktop.json` 的 12 项全部 `passed=true`：托盘注册、760×510 紧凑尺寸及恢复、桌面置顶/任务栏样式及恢复、穿透及恢复、隐藏及恢复、最小化及恢复、最终可交互状态。结果来自程序调用和 Win32 回读，明确 `humanTrayClickTested=false`；不是逐项真实点击、托盘菜单或高 DPI 验收。
- [x] `Migration/foam-repair.json` 记录泡沫材质 `/Game/Materials/OOW/M_ShoreFoam_v1`、海面宽 200,000 cm、深约 211,765 cm、X 中心 3,200 cm、近岸 Y 边界 4,200 cm，以及山林/村庄共六个针叶网格的 Preserve Area 处理，已进入本轮打包。
- [x] 首轮验证时 `Run-Unreal.ps1 -Mode Import` 包含关卡、表面材质、雨雪、泡沫、岸线五个生成步骤。此后的夜窗修复在第 2 步加入 `build_window_interiors.py`，当前入口为六步，执行状态见 [night-window-repair.md](night-window-repair.md)；本表历史哈希和成绩保持不变。默认 12 个验证用例加后巷节能、精细、桌面例组成上述 15 例。
- [x] [coast-shoreline-repair.json](coast-shoreline-repair.json) 记录局部沙地修正已通过两次 UE NullRHI 执行并落盘，重复运行不叠加。几何来自原程序高度场（种子 118），14,641 顶点/28,800 三角形中保留 10,914 个内部顶点，沿东/远边过渡到海面下 0.35 m；原 UV、材质、Actor 变换和其他物体位置保留。`src/main.js` 已同步同一算法，无新增外部资产。此项是资产/幂等验证，不是修正后 GPU 画面验收。
- [x] 首轮包正常联网启动记录 `.runtime/ue-validation/packaged-live-weather.json` 为 `testMode=false`、`liveTime=true`、`fallbackWeather=false`，已写入长期证据 `liveWeatherSmoke`。不覆盖断网/超时和所有时区案例。
- [ ] 山林地形素材衔接仍需美术处理，不能将全矩阵自动通过等同于美术全面验收。
- [ ] 长时间运行、GPU timer、显存峰值、功耗、真实鼠标交互、动画连续录像及完整排水过程仍需独立验收；30 秒单例矩阵通过不替代这些项目。

### 局部修正后的新包复测

最终实际运行 exe 的 SHA-256 为 `432C32F3ADF9D3439A38B8FC1424555CC0FA20CA203174F4EBBF086FBC6256C8`，与 `postFix.executableSHA256` 一致。构建/打包成功后按相同 1280×820、均衡档、60 FPS 上限、每例 30 秒条件串行复测；与上述首轮 15 例分别记录。最终归档内许可证和资产清单再次核对哈希，仍与仓库原件一致。

| 用例 | 平均帧间隔（ms） | P95（ms） | 样本数 | 结果 |
| --- | ---: | ---: | ---: | --- |
| coast-clear | 16.67 | 16.67 | 1,680 | 自动检查通过；截图中原矩形沙地断边消失 |
| alley-desktop | 16.90 | 16.67 | 1,678 | 自动检查通过；桌面接口 12/12 |

- [x] 新包海滨和桌面两例正常结束并生成 PNG/JSON，相机绑定、标签、几何、材质和 Lumen 状态完整。海滨源素材和布景仍简单，该局部修正不等于海滨写实度全面达标。
- [x] 新包 `packaged-alley-desktop.desktop.json` 的 12 项全部通过；仍为程序调用/Win32 回读，`humanTrayClickTested=false`。
- [x] 最终包正常联网成功：`postFix.liveWeather` 和 `.runtime/ue-validation/packaged-live-weather-final.json` 记录 `testMode=false`、`liveTime=true`、`fallbackWeather=false`、`fetchingWeather=false`，相机绑定有效；这是一轮成功联网检查，不覆盖断网/超时。
- [x] 最终包单实例检查通过：`postFix.singleInstance` 记录第二实例 2.4278815 秒退出、退出码 0、`restoreEventSent=true`、`duplicateWorldLoaded=false`、`firstStillRunning=true`。旧版超出 30 秒阈值的问题已由进程级 `StartupModule` 门禁解决。验证结束时保留首个主窗口运行供查看；人工聚焦体验仍单独列为未验收。
