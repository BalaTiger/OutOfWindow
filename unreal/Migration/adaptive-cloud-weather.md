# 自适应云采样与天气分级

2026-09-28。承接 [后巷云层诊断](cloud-lighting-diagnosis.md)，实现按实际可见天空面积分配云采样，并细化天气标签和预览档位。

## 天空面积与采样

`WindowSkySampling` 复用 UE 主视图 Base Pass 的深度缓冲，经引擎原生点采样复制为 128×72 R32_FLOAT 纹理，每 2 秒异步读回。只在 GPU 数据就绪后读取，排除 SceneCapture、反射视图和非主视图；没有额外渲染一次场景，也没有同步等待 GPU。深度为远平面的采样点计为天空，因此会包含真实建筑、Nanite 网格及前景窗框的遮挡。该网格估算三维主画面天空覆盖率，不是逐像素全量计数，细小轮廓可能存在误差。

用实际内部渲染尺寸计算可见天空像素数，避免只按窗口宽高或固定场景名决定。采样倍率为参考像素预算除以天空像素数，并限制在画质档范围内：

| 画质 | 最低倍率 | 最高倍率 | 参考天空像素预算 |
| --- | ---: | ---: | ---: |
| 节能 | 0.5 | 1 | 100000 |
| 均衡 | 1 | 2 | 200000 |
| 精细 | 1.5 | 3 | 300000 |

无有效测量或完全看不到天空时使用最低倍率，保留云对反射和光照的影响。倍率平滑过渡，仅当差值超过 0.02 时更新组件。画面尺寸变化最多约 2 秒后取得新测量；预算是像素乘样本的工作量近似，不是 GPU 计时反馈。

保留 `r.VolumetricRenderTarget.Mode=0` 时间重建；`r.VolumetricCloud.DistanceToSampleMaxCount=5` 提高视线积分密度。控制台 `oow.CloudSampleBudget` 调整均衡档参考预算，范围保护为 20000–1000000。其余档位按比例计算；不增加第三方依赖或自定义着色器。

## 标签和预览

按 [Open-Meteo WMO 天气码](https://open-meteo.com/en/docs#weathervariables) 直接映射：0 晴、1 晴间多云、2 多云、3 阴；61/63/65 为小／中／大雨，71/73/75 为小／中／大雪。毛毛雨、冻毛毛雨、冻雨、阵雨、阵雪、米雪、雾、雾凇、雷暴和伴冰雹雷暴保留具体标签。缺失、无效和未识别代码显示「未知」，不再回退成晴天。

天气预览新增多云和阴；雨、雪下方各显示小、中、大。相应命令为 `cloudy`、`overcast`、`light_rain`、`moderate_rain`、`heavy_rain`、`light_snow`、`moderate_snow`、`heavy_snow`。旧 `rain`、`snow` 为中等强度别名，`live` 仍等同 `real`。

雨雪预览粒子强度为 0.3／0.65／1；实时雪强度按天气码变化，实时雨继续使用已有降水字段响应，不把该累计量当作每小时雨量或用它猜测标签等级。普通云量与雨云类型分开：只在雨雪天气平滑加入 StormClouds，多云仍通过云覆盖、密度、太阳和大气散射响应。

## 验证

Editor 与 Game Development 编译、独立 Windows 打包成功。`OutOfWindow.SkySampling.DepthCoverage` 和 `OutOfWindow.Weather.Classification` 自动化测试通过，覆盖深度行跨度、遮挡／天空、空测量、采样上下限、面积变化、WMO 标签和旧命令别名。

独立成品完成六项 1280×820 渲染检查：后巷多云、海滨多云、后巷小雨、大雪、阴天及节能档。验证脚本检查天气文字与代码、预览选择、真实天空测量、采样范围、云重建配置、雨雪／材质响应、场景完整性和日志错误。后巷天空约占 2%，均衡采样接近 2；海滨约占 24%，目标采样约 1.12。数据在 `.runtime/ue-validation/packaged-summary.json`，本轮过程日志在 `.runtime/ue-cloud-adaptive/`。

另在 2560×1440 检查大雨 UI 和分辨率响应：天空占比约 2.09%，内部天空像素约 55777，约为同构图半尺寸画面的 4 倍。最初与旧桌面实例并行时触发显存超预算，因此不采用该次性能数据；关闭旧实例后单独复测再恢复实时桌面。截图、状态和日志分别保存为 `.runtime/ue-cloud-adaptive/native-rain-single.*`。

单实例复测没有显存告警，30 秒大雨用例的应用帧间隔平均 16.76 ms、P95 17.49 ms（60 FPS 上限，非独立 GPU 计时）。可见天空占比 2.116%，内部天空像素 56355，云采样倍率 1.989；截图已确认小／中／大雨选项及选中状态。

已安装至原 `D:/OutOfWindowBuild/Windows` 启动目录，旧文件备份在 `D:/OutOfWindowBuildBackups/cloud-weather-before-20260928-152327`。部署逐文件校验 SHA256，保留 Saved 中的用户设置。15:24:24 的重启审计确认后巷、象牙白、均衡、实时钟及联网天气恢复，桌面尺寸 2560×1440；服务天气码 3 正确显示「阴」，天空占比 2.094%，采样倍率 1.982。部署与运行证据为 `.runtime/ue-cloud-adaptive/deployment.json`、`live-state.json` 和 `restarted.log`。

可复测新成品目录：

```powershell
.\unreal\Scripts\validate.ps1 -EngineRoot 'D:\Epic\Epic Games\UE_5.7' -Packaged -PackagedRoot 'D:\OutOfWindowBuildCloudWeather\Windows' -Cases 'alley-cloudy,coast-cloudy,alley-light_rain,alley-heavy_snow,alley-overcast,alley-eco' -CaptureSeconds 20 -FrameStyle ivory
```

`-OOWTestWeatherCode=2` 可在已有离线截图模式中验证实时代码路径。审计新增原始／预览天气码、精确标签、服务云量、可见天空比例与像素数、目标云采样倍率及样本分配距离。
