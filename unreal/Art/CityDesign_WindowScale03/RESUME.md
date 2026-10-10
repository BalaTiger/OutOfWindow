# 恢复说明：WindowScale03 独立候选已完成本轮

原来的关机暂停指令已由主会话明确取消；2026-10-07 已恢复并完成两轮固定窗景修正、导出与技术验证。当前主文件是 `CityDesign_WindowScale03.blend`，不是 `CHECKPOINT_BASE_ONLY`。

先查看 `README.md`、`preview-window.png` 和 `fixed_window_visual_review.json`。正式图2560×1440，仅固定相机；没有新近景。当前是待用户审阅候选，不能宣称审美通过：商场功能分段在该距离弱、中楼偏浅、入口左半仍被树遮挡。

三个技术报告均PASS，商业4网格151,988三角＋办公3网格65,218三角。原文件保护状态看 `protected-after-v3.json`；工具/尺度/完整文件索引见 `README.md` 和 `file-index.json`。

继续编辑直接打开主 `.blend`；C占位隐藏，导出副本隐藏。`SourceScripts` 为实际可复现脚本。base-only 副本原样受保护，勿覆盖；`prepare_window_scale03.py` 勿重跑覆盖哈希基线。

仅在独立城市美术目录修改；保留原City、WindowDirector、云材质、共享脚本和现有工作树改动。单进程CPU低负载；UE导入/地图试摆/GPU之前通知主会话协调时段。没有授权整城扩建、Git提交推送或替换部署。
