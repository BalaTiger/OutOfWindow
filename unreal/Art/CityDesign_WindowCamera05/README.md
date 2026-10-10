# Camera05：B08窗洞修复已通过几何核验，等待正式窗景恢复

已锁定v04商业尺寸，A眼点(27.5,49,53.2077)m、target(-52,21,26.5)、VFOV52°、俯角17.58°、16:9，新增室内FF51.6077、站立眼高1.6m。位于现有B08顶层空间，不是原浮空机位加边框；水平楼板、侧墙、22cm低窗台、12mm透明闭合玻璃与实际宿主窗洞都在独立blend。

Camera05_A_B08.blend已实际修复原实心核及局部相交的Office_B08_Visible_Planar_Glass_32mm、Secondary_Mullions_52mm、Recessed_Head_Rails_43mm、Opaque_Spandrel_550mm。Corner_Aluminium_Cap的Y约36.5不与开口Y46.7..53.1相交，保留。417源对象检查仅这5个宿主对象改变，412其他源对象包括所有商业和旧相机指纹一致。

15条窗洞射线先碰新增透明West_Glass、之后不再被任何Office_B08_或宿主挡住；aperture-ray-audit-A.json PASS。几何守卫单自有Blender1线程、private上限1GiB，未调用render；PID56252于14:07:08UTC退出，private/commit峰0.573GiB，工作集峰0.491GiB。首次无渲染遍历错误及其退出内部异常记录已保留，按名字重新取对象后修复验证正常退出。

preview-A-low.png仍为13:16那一次全黑旧图，不能当作当前blend的预览。与旧黑图对应blend/机位记录存A-before-aperture-fix。当前没有修复后的新PNG，也没有B.blend/预览。技术几何PASS不能当视觉验收。

主会话优先恢复正式窗景；新GPU诊断暂停，但这不自动开放CPU预览。正式窗景已恢复；当前commit余量不足而暂停，仅未来主会话明确新的资源窗口并重新满足原门槛后，才按2线程640×360/8samples串行修复A、检查像素后才B，不升分辨率、不同时两臂。A下一次用SourceScripts/run_camera05_budget.py --candidate A --render-existing-fixed，从已核验blend低负载渲染到preview-A-repaired-low.png，新监控/日志不会覆盖旧黑图记录；B之后单独用同守卫--candidate B。原预览守卫private4GiB、启动phys8/commit10、运行最低phys4/commit6，只有自有child可停止。未实际执行这两个下一步命令。

PLAN.md保留最初机位方案，camera-design-plan.json记录B设计与Galaxy官方参考；README/RESUME/coordination-status为当前状态。SourceScripts是最新实际源。原v04、City、部署/云诊断相机保留，无UE/GPU、无桌面焦点操作、无提交推送部署。Library上传等有效小预览完成，未将黑图当候选发送。


## 最新资源阻塞：2026-10-07 14:41 UTC

主会话已明确正式窗景恢复稳定，云诊断终止。此后只做一次只读内存采样：物理可用8.0238GiB、系统commit64.6232/66.8795GiB、commit余量2.2563GiB。原启动门槛是phys>=8、commit余量>=10（新增private预算<=4、保留phys4/commit6），故提交容量不满足。本轮没有启动Blender、UE或GPU，也没有修复A/B新预览。不得降低门槛、关闭正式launcher13724/game24648或其他用户程序、修改正式设置、自动轮询等待或排队渲染。当前以resource-blocked-20261007T144130Z.json和coordination-status.json为准。夜间优先ToE，城市预览留在资源阻塞检查点；后续仅在主会话新资源窗口通知和新采样满足门槛时恢复。不是在等待正式窗景恢复，已通过的B08几何无需重做。
