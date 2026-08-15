$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$headers = @{ 'User-Agent' = 'OutOfWindow-Demo/0.4' }
$assetRoot = Join-Path $PSScriptRoot '..\public\assets\polyhaven\models'
$assetIds = @(
  'modular_urban_apartments_facade',
  'modular_factory_facade',
  'modular_street_seating',
  'modular_fort_01',
  'wine_barrel_01',
  'wooden_crate_02',
  'boulder_01',
  'coastal_cliff_01'
)

foreach ($assetId in $assetIds) {
  $manifest = Invoke-RestMethod -Headers $headers -Uri "https://api.polyhaven.com/files/$assetId"
  $entry = $manifest.gltf.'1k'.gltf
  if (-not $entry) { throw "No 1K glTF entry for $assetId" }

  $target = Join-Path $assetRoot $assetId
  New-Item -ItemType Directory -Force -Path $target | Out-Null
  New-Item -ItemType Directory -Force -Path (Join-Path $target 'textures') | Out-Null

  $mainName = Split-Path $entry.url -Leaf
  Invoke-WebRequest -Headers $headers -Uri $entry.url -OutFile (Join-Path $target $mainName)
  foreach ($file in $entry.include.PSObject.Properties) {
    $localPath = Join-Path $target $file.Name
    $localDirectory = Split-Path $localPath -Parent
    New-Item -ItemType Directory -Force -Path $localDirectory | Out-Null
    Invoke-WebRequest -Headers $headers -Uri $file.Value.url -OutFile $localPath
  }
  Write-Host "Downloaded $assetId"
}

$waterRoot = Join-Path $PSScriptRoot '..\public\assets\water'
New-Item -ItemType Directory -Force -Path $waterRoot | Out-Null
Invoke-WebRequest -Headers $headers -Uri 'https://raw.githubusercontent.com/mrdoob/three.js/dev/examples/textures/waternormals.jpg' -OutFile (Join-Path $waterRoot 'waternormals.jpg')
Write-Host 'Downloaded Three.js water normals'
