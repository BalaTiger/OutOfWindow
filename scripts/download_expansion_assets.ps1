$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$headers = @{ 'User-Agent' = 'OutOfWindow-Demo/0.5' }
$publicRoot = Join-Path $PSScriptRoot '..\public\assets'
$modelRoot = Join-Path $publicRoot 'polyhaven\models'
$modelIds = @(
  'grass_bermuda_01',
  'grass_medium_02',
  'mountainside',
  'rock_moss_set_01',
  'coast_line_01',
  'sand_rocks_small_01'
)

foreach ($assetId in $modelIds) {
  $manifest = Invoke-RestMethod -Headers $headers -Uri "https://api.polyhaven.com/files/$assetId"
  $entry = $manifest.gltf.'1k'.gltf
  if (-not $entry) { throw "No 1K glTF entry for $assetId" }
  $target = Join-Path $modelRoot $assetId
  New-Item -ItemType Directory -Force -Path $target | Out-Null
  foreach ($file in @(@{ Name = (Split-Path $entry.url -Leaf); Value = $entry }) + @($entry.include.PSObject.Properties)) {
    $name = if ($file.Name -is [string]) { $file.Name } else { [string]$file.Name }
    $value = $file.Value
    $localPath = Join-Path $target $name
    New-Item -ItemType Directory -Force -Path (Split-Path $localPath -Parent) | Out-Null
    Invoke-WebRequest -Headers $headers -Uri $value.url -OutFile $localPath
  }
  Write-Host "Downloaded $assetId"
}

$textureIds = @('withered_grass', 'forest_ground_04', 'coast_sand_02')
$textureRoot = Join-Path $publicRoot 'polyhaven\materials'
foreach ($assetId in $textureIds) {
  $manifest = Invoke-RestMethod -Headers $headers -Uri "https://api.polyhaven.com/files/$assetId"
  $target = Join-Path $textureRoot $assetId
  New-Item -ItemType Directory -Force -Path $target | Out-Null
  $channels = @{
    'diffuse.jpg' = $manifest.Diffuse.'1k'.jpg.url
    'normal.jpg' = $manifest.nor_gl.'1k'.jpg.url
    'roughness.jpg' = $manifest.Rough.'1k'.jpg.url
    'displacement.jpg' = $manifest.Displacement.'1k'.jpg.url
  }
  foreach ($channel in $channels.GetEnumerator()) {
    Invoke-WebRequest -Headers $headers -Uri $channel.Value -OutFile (Join-Path $target $channel.Name)
  }
  Write-Host "Downloaded texture $assetId"
}

$sourceRoot = Join-Path $PSScriptRoot '..\.runtime\bistro-source'
$bistroZip = Join-Path $sourceRoot 'Exterior.zip'
New-Item -ItemType Directory -Force -Path $sourceRoot | Out-Null
if (-not (Test-Path $bistroZip)) {
  Invoke-WebRequest -Headers $headers -Uri 'https://casual-effects.com/g3d/data10/research/model/bistro/Exterior.zip' -OutFile $bistroZip
}
if (-not (Test-Path (Join-Path $sourceRoot 'exterior.obj'))) {
  Expand-Archive -LiteralPath $bistroZip -DestinationPath $sourceRoot
}
Write-Host 'Downloaded and extracted Amazon Lumberyard Bistro Exterior'
