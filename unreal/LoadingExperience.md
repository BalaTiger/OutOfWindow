# UE 加载体验与验证记录

本次将日常启动接到独立 WinForms 启动器。界面立即显示当前阶段和已等待时间，依次为“启动渲染器、加载场景、连接桌面、就绪”，不提供估算百分比。超过 30 秒仍显示正在加载，可取消；错误、退出码、日志目录与重试入口保留在启动器中。

## 启动与重建

双击仓库根目录 `打开UE窗景.cmd`，或运行：

```powershell
.\unreal\Run-Unreal.ps1 -Mode Game -Scene Alley
```

启动器根据 `.runtime/launcher/target.json` 使用已构建的准确工程和 DLL，并校验模块、Source、Config 和 `.uproject` 的 SHA256；不再优先启动 `D:\OutOfWindowBuild\Windows\OutOfWindow.exe` 的旧包。此次已检查原入口：旧 bootstrap 为 10 月 6 日，内层渲染器为 10 月 5 日；仅更新源码不能让原入口获得新行为。

首次准备、源码/配置更新或清单失效时运行下列命令，成功后重试：

```powershell
.\unreal\Build-LoadingExperience.ps1
```

重建会复制当前源码、配置和 Content 到新的 `.runtime/loading-builds/<时间-ID>/OutOfWindow`，以单编译任务构建 UE Editor 模块，再更新清单。没有 Cook、部署或替换工作工程的 DLL。当前复用的已验证工程位于 `.runtime/loading-work/project/OutOfWindow`；**它是正式清单引用的运行依赖，不可作为临时目录删除**。迁移仓库后需要重新构建，保留活动快照及其 Saved 数据。

关闭就绪后的启动器会保留场景。加载时关闭启动器会取消本次启动。“取消”与“重试”只管理启动前便归入独立 Windows Job 的本次进程树；既有应用实例不会被按名称关闭。重试前最多等两秒确认上次的保留进程句柄已退出、Job 已空；未完成时保留原会话并提示稍后重试。启动器直接启动验证过的 `UnrealEditor.exe -game`，状态中的实际 UE PID 还须与该 Job 对应；包装进程先退出也不能成为错误的就绪证据。

每次启动有新的 GUID 和独立目录，默认在 `.runtime/launcher/sessions/<时间-GUID>/`，包含 `status.json`、`ue.log`、`launcher.log`。准备错误保存在 `.runtime/launcher/launcher-errors.log`。自定义 `-OutputDirectory` 会通过 `--state-dir` 同时隔离清单与日志。旧日志和其他会话/PID 的 ready 标记均不接受。

## 显示与失败处理

UE 模块在创建游戏窗口之前安装本进程显示钩子，对首次显示的游戏 HWND 设置并核对 DWM cloak。资源加载期间窗口保持遮挡。场景、相机、流送、资源/着色器和 PSO 就绪后，等待实际 viewport 绘制对应的 GPU fence；随后挂接桌面，再等待相机适配桌面大小后的新绘制和 GPU fence，最后解除遮挡并发布 ready。

这取代了仅等待两个游戏帧便挂接的判断。仍在正常加载资源时不以固定总时长判作崩溃。无法确认 viewport、场景具备绘制条件后长期没有绘制、或 GPU 提交长期没有完成，会产生明确错误并尝试恢复窗口，提供日志、取消和重试。未进入桌面模式、挂接失败及挂接后的异步失败不会无限隐藏。恢复会核对实际父窗口、窗口样式、可见性和 cloak，不能确认时记录失败。

JSON 状态以临时文件替换发布；遇到短暂共享/访问冲突最多额外重试 200ms，保留系统错误码。发布失败时立即刷出错误日志，仅接受本次唯一 UE 日志中的明确错误协议；日志永远不能建立 ready。日常入口不逐条强制刷新全部引擎日志。UE 提前退出时保留对应退出码；尚未绑定实际 UE 时，入口退出码会明确标为入口退出码。

本次没有修改城市、云材质或 Content 资产，默认云仍为 v7，日常入口不包含 Houdini 或截图测试开关。最初纯天空帧的具体历史原因没有被捕获，本记录不将它归因为崩溃。

## 验证证据

记录时间：2026-10-17。所有重构建和真实场景运行均串行；重构建使用 `MaxParallelActions=1`。最初沙盒内构建被权限阻止，用户随后明确批准沙盒外构建与隔离运行；正式提权机制下构建成功。没有安装软件、改 ACL、提交、推送或部署。

自动化模拟与逻辑检查：

- [21/21 进程生命周期检查](../.runtime/loading-work/tests/Build/results/20261017-022556-636d8dfe/results.json)：正常/慢加载、提前退出、包装器和实际子进程、历史或异会话状态、缺文件、取消、重试、重复实例、错误恢复、退出收尾等待与超时保留等。
- [16/16 清单和状态目录检查](../.runtime/loading-work/tests/Build/target-validation/20261017-022609-ad8925a9/results.json)：模块与完整源文件集合变更、缺场景、自定义清单隔离等。
- [3 种实际 argv 检查](../.runtime/loading-work/tests/state-directory-selfcheck-1a1d9e7f6a2047c89600e650c2587363/results.json)：默认目录、含空格目录、含空格且末尾反斜线目录。
- [6/6 界面布局检查](../.runtime/loading-work/tests/Build/layout/20261017-020826/layout.json)：慢加载、长错误、重复实例及 100%/200%几何缩放。此项是离屏控件绘制，不是物理显示器 DPI 验收。
- [脚本隔离和版本检查](../.runtime/loading-work/evidence/scripts-checks.json)：14 项准备、保留候选、源变更、编译缓存与错误恢复检查；该历史记录里的权限状态以本文件最新状态为准。
- [最终 UE 构建日志](../.runtime/loading-work/evidence/ue-build-final.log) 与 [构建清单](../.runtime/loading-work/evidence/target-built-final.json)。

真实运行与显示中的启动器检查：

- [正常启动与遮挡时序](../.runtime/loading-work/tests/runtime-observation/20261017-021704-c236ce01/summary.json)：首次显示分发前 `visible=0, cloaked=1`；1280×820 场景 GPU 帧完成后挂接，随后完成 2560×1440 桌面 GPU 帧，再解除遮挡并发布 ready。约 89 秒的加载没有误报崩溃；[就绪帧截图](../.runtime/loading-work/tests/runtime-observation/20261017-021704-c236ce01/attempt-1-86847b1ebd1b463f8c4dafe3180ea288-ready.png)包含完整街景。
- [真实加载中取消后重试](../.runtime/loading-work/tests/runtime-observation/20261017-022657-b9c56b69/summary.json)：首次在 scene 阶段取消，旧 PID/互斥量约 264ms 后释放；新 GUID 的第二次启动约 39.8 秒就绪。[重试就绪帧](../.runtime/loading-work/tests/runtime-observation/20261017-022657-b9c56b69/attempt-2-35a0566cabc9444181c6a6e13098d7b5-ready.png)。桌面阶段前无遮挡可见采样为 0，第二次最大采样间隔约 56ms；结束只清理本次 Job。此后仅收口日志刷新策略，最终 DLL 另经下列 GUI/恢复检查。
- [缺清单错误页](../.runtime/loading-work/tests/launcher-gui/20261017-021901-55f59382/summary.json)：真实 LauncherForm 出现约 76ms，保留错误、日志与重试入口，未启动 UE。
- [加载中 UE 退出](../.runtime/loading-work/tests/launcher-gui/20261017-023025-ff58e320/summary.json)：最终版本启动器约 55ms 原生可见；只结束核实属于本次 Job 的实际 UE PID，持续保留 `-1 (0xFFFFFFFF)`、日志和重试按钮。[错误页控件截图](../.runtime/loading-work/tests/launcher-gui/20261017-023025-ff58e320/after-ue-load-exit-form.png)。测试包装脚本最初把 UE 自行删除临时配置报成清理错误，已核实文件不存在并修正包装脚本；此错误未改变 GUI 探针的通过结果。
- [正常 GUI 启动与 UE 退出后保留](../.runtime/loading-work/tests/launcher-gui/20261017-023113-c2115863/summary.json)：最终版本启动器约 51ms 原生可见，约 9.3 秒到 ready；结束本次 UE 后窗口、退出码、日志与重试仍保留。[就绪控件截图](../.runtime/loading-work/tests/launcher-gui/20261017-023113-c2115863/ready-form.png)。耗时受缓存和验证设置影响，不作为性能承诺。
- [挂接后的实际故障注入与恢复](../.runtime/loading-work/tests/startup-recovery/20261017-023200-a5247ce8/summary.json)：只把本次 status 文件以禁止替换的共享方式打开约 1.51 秒；UE 记录 Win32 错误 5、11 次发布尝试及本会话错误。launcher 状态为 Failed，没有 ready。同一实际 HWND 已恢复为父窗口 0、无 WS_CHILD、可见、cloak=0；通过时 UE 仍活着，随后仅清理本次 Job。该检查没有修改权限或项目文件。

Win32/DWM API 观察、UE 生成的帧截图、显示中的 WinForms 控件状态分别记录，不将模拟或离屏测试称为桌面目视验收。重复实例和既有进程不受影响由隔离进程模拟验证；未对用户正在使用的真实实例做破坏性测试。

## 应用范围

共 21 个源码、脚本、测试和说明文件，清单及原文件哈希见 [proposal-manifest.json](../.runtime/loading-work/proposal-manifest.json)，精确备份和逐文件应用记录见 [apply-runs](../.runtime/loading-work/apply-runs/)。应用前校验 42 项原始基线，并逐路径、逐 SHA256 比较完整 44 项 Source/Config/uproject；应用后再比较，正式清单记录候选与工作树各 44 项，共 88 项。复用准确的已验证 DLL，不复制到工作工程。

- 启动：`打开UE窗景.cmd`、`unreal/Run-Unreal.ps1`、`Launch-Unreal.ps1`、`Build-LoadingExperience.ps1`、`Launcher/Program.cs`、`Launcher/LaunchSession.cs`。
- UE：`WindowStartup.cpp/.h`、`WindowDesktop.cpp`、`WindowDirector.cpp/.h`、`OutOfWindow.Build.cs`。
- 测试：`FakeRenderer.cs`、`LaunchSessionTests.cs`、`LauncherTargetTests.cs`、`LauncherLayoutTests.cs`、`Run-Tests.ps1`、`state-directory-selfcheck.ps1`。
- 说明：根 `README.md`、`unreal/README.md`、本记录。

## 验证边界

原生电脑 GUI 自动化在当前工具环境不可用，因此没有人工/鼠标操作的物理桌面逐帧验收。轮询存在采样间隔，不能排除短于该间隔的瞬时呈现；UE 截图也不等于 Windows 合成器最终显示。GPU fence 证明相应 viewport 绘制完成，不保证所有时域效果、后续纹理流送在每个硬件上都已完全收敛。已有实例保护、错误注入与重复启动的模拟测试须与真实场景证据分开解读。

窗口观察器使用额外 `-noshaderworker` 限制 shader 任务、`-OOWStartupCapture=<本次PNG>` 保存就绪帧，以及验证用逐条日志刷新；这些均不在日常入口，其加载耗时不是正式性能基准。最终故障恢复观察器没有逐条日志刷新。真实启动器 GUI 观察器使用日常命令行参数，在隔离快照临时配置禁用并行 shader worker，引擎日志确认使用 1 worker；[配置恢复记录](../.runtime/loading-work/evidence/gui-config-exit-after-ready.json)确认测试配置已移除。所有注入只针对新建测试目录、当前持有的 Job 和核实归属的 UE 进程，未破坏用户工程。
