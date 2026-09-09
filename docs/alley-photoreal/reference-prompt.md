# 图像参考生成记录

- 模式：内置 image_gen，编辑现有渲染截图。
- 输入：`docs/weather-response/alley-rain.png`。
- 输出：`reference-generated.png`，为 2D 视觉参考，未作为 3D 背景贴图使用。
- 用途：对照同机位下的干湿对比、积水、窗蓬水迹与湿叶细节。静态图不能验证动画。

## 原始提示词

Use case: style-transfer.
Asset type: photorealistic visual target for improving an existing realtime 3D desktop window scene.
Image 1 is the EDIT TARGET. Transform only the exterior alley scenery inside the window into an ultra-photorealistic rainy midmorning architectural photograph. Preserve exactly the camera position, perspective, framing, building heights, roof silhouettes, locations and count of existing windows and red half-dome fabric awnings, green doors, iron railings and existing plants. Preserve the outer application border, wooden window frame and crossbars. Do not add buildings, people, cars, props, text, lighting fixtures, or new landscaping. Do not change the viewpoint or reveal more road by moving the camera.
The image should establish a realistic rain appearance clearly readable at the original overview size: darker saturated wet stone and pavement separated from matte dry areas beneath awnings; several connected irregular shallow puddles visible on the existing alley floor, with clear yet naturally broken reflections of the bright overcast sky, window frames and nearby facades, wet cobbles and dark joints still visible; rain impact ripple rings and tiny splash crowns with believable scale. Red awnings have woven cloth texture, darker rain-soaked patches, glistening water beads along the lower scalloped edges and small streams/drips falling from existing seams, with slight natural wind tension in their flexible edges. Existing shrubs have deep wet green, individually readable clustered leaves, tiny sharp water highlights and a hint of wind movement in their tips. Walls are real weathered pale stone/plaster, physically straight architectural edges, fine mineral grain, subtle damp streaks below edges, properly shaded recesses and detailed ironwork. Use neutral luminous overcast daylight around 10:47, with gentle sky bounce in shaded facades, rich midtone separation, no orange dusk, no dramatic sun shafts. Rain streaks vary in depth and size, subtle localized splash mist near the ground. Professional natural architectural photography, realistic roughness hierarchy and tactile material detail, no CGI plastic finish, no excessive HDR halos, no uniform glossy mirror road, no added raindrops on the viewing glass. Keep the original scene composition locked. Return one image.

