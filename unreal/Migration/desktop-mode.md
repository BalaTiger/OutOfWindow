# 默认动态桌面（2026-09-24）

应用启动后嵌入 Windows 桌面图标后方；右上角显示还原图标。还原时脱离桌面，恢复原窗口位置和尺寸；窗口中的最大化按钮重新进入动态桌面。托盘显隐保持当前模式，退出再启动默认进入动态桌面。

使用显示器 `rcMonitor`，而非扣除任务栏的工作区。Windows 11 raised desktop 使用 Progman 子窗口并排在图标层之后；旧桌面布局使用图标后方 WorkerW。首次挂接等待初始视口布局完成，避免 UE 启动时重设窗口样式和尺寸。

桌面模式只转发应用控件上的左键事件，空白处保留桌面操作；鼠标移动支持眼睛按钮恢复，桌面聚焦时 Esc 恢复 UI。窗口化时移除桌面输入钩子。

Editor 与 Game Development 均编译成功。Editor `-game -OOWTestDesktop` 的 13 项 Win32 检查全部通过，证据见 [desktop-verification.json](desktop-verification.json)：默认父窗口及图标层级、2560×1440 完整客户区、输入钩子、还原位置、最小化恢复、再次进入桌面、显隐与重复往返。此记录是程序调用和原生状态回读，不代表人工鼠标逐项验收；多显示器、高 DPI 和 Explorer 重启恢复未覆盖。

Development 成品已打包到 `D:/OutOfWindowBuild/Windows/OutOfWindow.exe`，打包版 `alley-desktop` 用例及全部 13 项原生桌面检查再次通过。证据 JSON 同时保存 Editor、成品结果和实际游戏 exe 的 SHA-256；后续场景任务可继续更新同一成品。
