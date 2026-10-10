param([string]$OutputDirectory = $PSScriptRoot)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$bmp = [System.Drawing.Bitmap]::new(1400, 1040)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
$g.Clear([System.Drawing.ColorTranslator]::FromHtml('#f7f8fa'))
$svg = [System.Text.StringBuilder]::new()
[void]$svg.AppendLine('<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="1040" viewBox="0 0 1400 1040"><rect width="1400" height="1040" fill="#f7f8fa"/>')
function Pt([double[]]$P) { return [System.Drawing.PointF]::new([single](80 + ($P[0]+72)*5), [single](180+($P[1]+112)*5)) }
function Box($X,$Y,$W,$H,$Color,$Stroke='#d4dce3') {
  $brush=[System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml($Color)); $pen=[System.Drawing.Pen]::new([System.Drawing.ColorTranslator]::FromHtml($Stroke),1)
  $g.FillRectangle($brush,[single]$X,[single]$Y,[single]$W,[single]$H); $g.DrawRectangle($pen,[single]$X,[single]$Y,[single]$W,[single]$H); $brush.Dispose(); $pen.Dispose()
  [void]$svg.AppendLine("<rect x='$X' y='$Y' width='$W' height='$H' fill='$Color' stroke='$Stroke'/>")
}
function Txt($S,$X,$Y,$Size=20,$Color='#243d4e') {
  $font=[System.Drawing.Font]::new('Microsoft YaHei',[single]$Size,[System.Drawing.FontStyle]::Regular,[System.Drawing.GraphicsUnit]::Pixel); $brush=[System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml($Color))
  $g.DrawString($S,$font,$brush,[single]$X,[single]$Y); $brush.Dispose(); $font.Dispose()
  $esc=[System.Security.SecurityElement]::Escape($S); $base=$Y+$Size
  [void]$svg.AppendLine("<text x='$X' y='$base' font-family='Microsoft YaHei,Segoe UI,sans-serif' font-size='$Size' fill='$Color'>$esc</text>")
}
function Line($X1,$Y1,$X2,$Y2,$Color='#667e8b',$Width=2,$Dashed=$false) {
  $pen=[System.Drawing.Pen]::new([System.Drawing.ColorTranslator]::FromHtml($Color),[single]$Width); if($Dashed){$pen.DashStyle=[System.Drawing.Drawing2D.DashStyle]::Dash}
  $g.DrawLine($pen,[single]$X1,[single]$Y1,[single]$X2,[single]$Y2); $pen.Dispose()
  $dash=if($Dashed){"stroke-dasharray='7 5'"}else{''}; [void]$svg.AppendLine("<line x1='$X1' y1='$Y1' x2='$X2' y2='$Y2' stroke='$Color' stroke-width='$Width' $dash/>")
}
function Curve($Points,$Color,$Closed=$true,$Width=2,$Stroke='#304f5f') {
  $path=[System.Drawing.Drawing2D.GraphicsPath]::new(); $start=Pt ($Points[0]); $d="M $($start.X) $($start.Y)"
  for($i=1;$i -lt $Points.Count;$i+=3){$a=Pt ($Points[$i]);$b=Pt ($Points[$i+1]);$c=Pt ($Points[$i+2]);$path.AddBezier($start,$a,$b,$c);$d+=" C $($a.X) $($a.Y) $($b.X) $($b.Y) $($c.X) $($c.Y)";$start=$c}
  if($Closed){$path.CloseFigure();$d+=' Z';$brush=[System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml($Color));$g.FillPath($brush,$path);$brush.Dispose()}
  $pen=[System.Drawing.Pen]::new([System.Drawing.ColorTranslator]::FromHtml($Stroke),[single]$Width);$pen.LineJoin=[System.Drawing.Drawing2D.LineJoin]::Round;$g.DrawPath($pen,$path);$pen.Dispose();$path.Dispose()
  $fill=if($Closed){$Color}else{'none'};[void]$svg.AppendLine("<path d='$d' fill='$fill' stroke='$Stroke' stroke-width='$Width' stroke-linejoin='round'/>")
}
Txt '三座曲面商业体量：组织方向草图' 60 34 32
Txt '概念平面；未建模，非建筑渲染。位置为UE米，曲线为示意。' 62 84 20 '#667e8b'
Box 60 148 670 846 '#ffffff'
Box 760 148 580 260 '#ffffff'
Box 760 428 580 218 '#ffffff'
Box 760 666 580 250 '#ffffff'

# Existing road and right foreground are context diagrams, not a survey.
Box 350 174 180 670 '#e7edf1' '#e7edf1'
Line 440 180 440 838 '#ffffff' 3 $true
Txt '现有主路' 386 268 19 '#748b99'
Txt '保持相机 / 道路' 378 297 14 '#748b99'
Box 555 615 150 170 '#eef1f4'
Txt 'B07' 590 665 23 '#708695'
Txt '办公楼基础' 568 701 17 '#708695'
Txt '先做转角试片' 568 729 15 '#708695'
Line 100 190 330 190 '#ac7765' 2 $true
Line 330 190 330 790 '#ac7765' 2 $true
Line 330 790 100 790 '#ac7765' 2 $true
Line 100 790 100 190 '#ac7765' 2 $true
Txt '研究包络 46×120m' 92 163 17 '#996451'

$A=@(@(-53,-12),@(-53,-23),@(-45,-26),@(-39,-26),@(-34,-26),@(-32,-25),@(-32,-23),@(-31,-19),@(-25,-14),@(-25,-5),@(-25,2),@(-35,2),@(-43,1),@(-50,0),@(-53,-5),@(-53,-12))
$B=@(@(-67,-52),@(-67,-62),@(-59,-68),@(-49,-68),@(-39,-68),@(-29,-60),@(-29,-51),@(-29,-42),@(-36,-34),@(-44,-34),@(-50,-34),@(-67,-37),@(-67,-52))
$C=@(@(-52,-92),@(-52,-101),@(-43,-106),@(-35,-106),@(-27,-106),@(-24,-98),@(-24,-91),@(-24,-81),@(-28,-76),@(-39,-76),@(-48,-76),@(-52,-83),@(-52,-92))
Curve $A '#ead6b4'
Curve $B '#bfd9d5'
Curve $C '#e1e7ee'
$court=@(@(-53,-51),@(-53,-55),@(-50,-57),@(-47,-56),@(-42,-55),@(-40,-49),@(-44,-46),@(-48,-43),@(-53,-46),@(-53,-51))
Curve $court '#ffffff' $true 1 '#789e98'
Txt '天窗' 187 489 13 '#5b8278'
Txt 'A' 222 675 26
Txt '22m' 212 710 19
Txt 'B' 178 465 26
Txt '28m' 157 533 19
Txt 'C' 237 270 26 '#708695'
Txt '36m 占位' 207 308 16 '#708695'

# One curved bridge, with an actual gap and a recessed street-facing corner.
$bridge=@(@(-34,-24),@(-26,-27),@(-27,-32),@(-40,-35))
Curve $bridge '#ffffff' $false 29 '#d9ae73'
Curve $bridge '#ffffff' $false 17 '#fff4df'
Line 304 590 365 572 '#b57539' 2
Txt '桥向街侧偏出' 368 546 17 '#996451'
Line 280 625 164 602 '#be6455' 2
Txt 'A 退角' 91 567 17 '#b15347'
Txt '约5–7m' 91 590 16 '#b15347'
Txt '入口庭院' 295 642 17 '#547b67'
Txt '体量间约8m留白' 102 375 16 '#667e8b'

# Fixed camera rays are planning guidance only; no occlusion result is claimed.
$cam=Pt @(26,42)
Line $cam.X $cam.Y 292 603 '#b67578' 1 $true
Line $cam.X $cam.Y 314 725 '#b67578' 1 $true
Box ($cam.X-5) ($cam.Y-5) 10 10 '#a55a63' '#a55a63'
Txt '固定相机 (26,42,37)' 407 963 17 '#965b64'
Line 104 850 204 850 '#304f5f' 3
Line 104 844 104 856 '#304f5f' 2
Line 204 844 204 856 '#304f5f' 2
Txt '20m' 132 861 16
Txt '包络是设计范围，不是地籍红线。' 94 900 17 '#667e8b'
Txt '虚线视线只提示风险，须由模型实渲复核。' 94 928 15 '#667e8b'

Txt '一组可见商圈街区' 787 171 24
Txt 'A：近端低，入口抬起，远端收角。' 787 217 19
Txt 'B：主力商业楼板，局部中庭与退台。' 787 253 19
Txt 'C：后端较高，第一轮仅轮廓占位。' 787 289 19
Txt '22 / 28 / 36m 均为基底以上最高点。' 787 325 19
Txt '原案例规模不缩小照搬，三座不是圆柱复制。' 787 362 17 '#667e8b'

Txt '连续性来自空间与曲率' 787 452 24
Txt '桥与楼层相切，入口/围带/退台共同组织。' 787 498 19
Txt '桥宽5–6m；初始桥下净空约8m。' 787 534 19
Txt '实际桥跨可能12–18m，落点仍需设计。' 787 570 19
Txt '少数主围带；玻璃、百叶、实体面有分区。' 787 606 18

Txt '下一最小样板' 787 690 24
Txt 'A+B完整外部、一个桥、一个入口庭院。' 787 736 19
Txt 'B07：3层转角幕墙试片，约9×10.8m。' 787 772 19
Txt '固定窗景＋桥下街景＋侧光幕墙真实CPU图。' 787 808 18
Txt '评价厚度、反射和空隙，不用面数代替成品。' 787 844 18
Txt '旧Mall01保留；本轮无新模型/UE/GPU。' 787 881 17 '#667e8b'
Txt '参考：Galaxy SOHO / ZHA；Westfield Mall of the Netherlands / MVSA。详见proposal-zh.md与原图来源。' 65 1007 15 '#667e8b'

[void]$svg.AppendLine('</svg>')
$utf8=[System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText((Join-Path $OutputDirectory 'concept-plan.svg'),$svg.ToString(),$utf8)
$bmp.Save((Join-Path $OutputDirectory 'concept-plan.png'),[System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose();$bmp.Dispose()
Get-Item -LiteralPath (Join-Path $OutputDirectory 'concept-plan.png'),(Join-Path $OutputDirectory 'concept-plan.svg') | Select-Object Name,Length
