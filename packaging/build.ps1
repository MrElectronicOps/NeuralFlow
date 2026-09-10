param([switch]$SkipPublish, [switch]$SkipZip, [switch]$BuildInstaller, [switch]$Public, [string]$ReleaseFolder)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$dist = Join-Path $root 'dist'
if ($ReleaseFolder) {
    $releasePath = [IO.Path]::GetFullPath((Join-Path $dist $ReleaseFolder))
    if (-not $releasePath.StartsWith($dist+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Release folder must be inside dist.' }
    $dist = $releasePath
}
$output = Join-Path $dist $(if ($Public) { 'NeuralFlow-Public' } else { 'NeuralFlow' })
$product = Get-Content -LiteralPath (Join-Path $root 'product.json') -Raw | ConvertFrom-Json
$version = $product.version
if (-not (Test-Path -LiteralPath (Join-Path $root 'python/python.exe'))) { throw 'Run packaging/stage-dependencies.ps1 first.' }
New-Item -ItemType Directory -Force -Path $output | Out-Null
if (-not $SkipPublish) {
    & dotnet publish (Join-Path $root 'app/NeuralFlow.csproj') -c Release -r win-x64 --self-contained true -o $output -p:DebugType=None -p:DebugSymbols=false "-p:PathMap=$root=/_/NeuralFlow"
    if ($LASTEXITCODE -ne 0) { throw 'NeuralFlow application publish failed.' }
    & dotnet publish (Join-Path $root 'native/NeuralFlow.Capture.csproj') -c Release -r win-x64 --self-contained true -o (Join-Path $output 'capture') -p:DebugType=None -p:DebugSymbols=false "-p:PathMap=$root=/_/NeuralFlow"
    if ($LASTEXITCODE -ne 0) { throw 'NeuralFlow capture helper publish failed.' }
}
function Copy-Tree([string]$Source, [string]$Destination) {
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    foreach ($item in Get-ChildItem -LiteralPath $Source) {
        if ($item.Name -in @('__pycache__','tests','logs','compatibility','runtime','bin')) { continue }
        if ($Public -and ($item.Name -in @('av','av.libs','av-18.1.0.dist-info','ffmpeg.exe') -or $item.Name -like 'opencv_videoio_ffmpeg*.dll')) { continue }
        if ($item.Name -like '*.whl' -or $item.Name -like '*.pyc' -or $item.Name -like 'test_*' -or $item.Name -like 'test-*') { continue }
        if ($item.Name -match '^(nvngx|_nvngx|nvcuda).*\.dll$') { throw ('NVIDIA runtime found in distribution staging: '+$item.FullName) }
        $target = Join-Path $Destination $item.Name
        if ($item.PSIsContainer) { Copy-Tree $item.FullName $target }
        else { Copy-Item -LiteralPath $item.FullName -Destination $target -Force }
    }
}
Copy-Tree (Join-Path $root 'engine') (Join-Path $output 'engine')
Copy-Tree (Join-Path $root 'python') (Join-Path $output 'python')
$licenseSource = Join-Path $PSScriptRoot 'licenses'
# Self-contained .NET publishing does not copy the runtime package notices.
# Refuse a future runtime update until its matching notices are staged, too.
foreach ($configName in @('NeuralFlow.runtimeconfig.json','capture/NeuralFlow.Capture.runtimeconfig.json')) {
    $config = Get-Content -LiteralPath (Join-Path $output $configName) -Raw | ConvertFrom-Json
    foreach ($framework in $config.runtimeOptions.includedFrameworks) {
        $noticePrefix = switch ($framework.name) {
            'Microsoft.NETCore.App' { 'dotnet-runtime' }
            'Microsoft.WindowsDesktop.App' { 'dotnet-desktop' }
            default { throw ('Review license notices for new runtime framework: '+$framework.name) }
        }
        $license = Join-Path $licenseSource ($noticePrefix+'-'+$framework.version+'-LICENSE.txt')
        if (-not (Test-Path -LiteralPath $license)) { throw ('Stage matching upstream runtime notices before packaging: '+$license) }
    }
}
Copy-Tree $licenseSource (Join-Path $output 'licenses')
Copy-Item -LiteralPath (Join-Path $root 'product.json') -Destination $output -Force
if (-not $Public) { Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'LOCAL-ONLY.txt') -Destination $output -Force }
foreach ($name in @('README.md','VIDEO-PIPELINE.md','THIRD-PARTY-NOTICES.md','COMPATIBILITY.md','LICENSE.txt')) {
    $source = Join-Path $root $name
    if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination $output -Force }
}
foreach ($file in Get-ChildItem -LiteralPath $output -Recurse -File) {
    if ($file.Name -match '^(nvngx|_nvngx|nvcuda).*\.dll$') { throw ('Forbidden NVIDIA runtime in finished package: '+$file.FullName) }
    if ($Public -and ($file.Name -eq 'ffmpeg.exe' -or $file.Name -like 'opencv_videoio_ffmpeg*.dll' -or $file.FullName -like '*\engine\vendor\av\*' -or $file.FullName -like '*\engine\vendor\av.libs\*')) { throw ('Media binary must be user-installed, not bundled in public package: '+$file.FullName) }
    if ($file.Extension -in @('.py','.json','.md','._pth')) {
        if (Select-String -LiteralPath $file.FullName -Pattern 'C:[\\/]Users[\\/]jaimu' -Quiet) { throw ('Personal path found in distribution: '+$file.FullName) }
    }
}
& (Join-Path $output 'python/python.exe') -B -c "import cv2,numpy,PIL,video,backend,media_tools; print('Packaged engine imports OK; optional video dependencies:',video.av is not None)"
if ($LASTEXITCODE -ne 0) { throw 'Finished package import test failed.' }
if ($Public) {
    foreach ($debugFile in Get-ChildItem -LiteralPath $output -Recurse -File | Where-Object { $_.Extension -in @('.pdb','.pyc') }) {
        if (-not $debugFile.FullName.StartsWith($output+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Debug artifact was outside package boundary.' }
        Remove-Item -LiteralPath $debugFile.FullName
    }
}
$hashes = foreach ($file in Get-ChildItem -LiteralPath $output -Recurse -File | Where-Object { $_.Name -ne 'SHA256SUMS.txt' -and $_.Extension -ne '.pyc' }) {
    $relative = $file.FullName.Substring($output.Length).TrimStart('\','/').Replace('\','/')
    ((Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant() + '  ' + $relative)
}
$hashes | Set-Content -LiteralPath (Join-Path $output 'SHA256SUMS.txt') -Encoding ascii
if (-not $SkipZip) {
    $archive = Join-Path $dist $(if ($Public) { 'NeuralFlow-Preview.zip' } else { 'NeuralFlow-LocalPreview.zip' })
    if (Test-Path -LiteralPath $archive) { throw 'This ZIP already exists. Preserve it under a versioned filename before building a replacement.' }
    Compress-Archive -LiteralPath $output -DestinationPath $archive -CompressionLevel Optimal
    ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()+'  '+[IO.Path]::GetFileName($archive)) | Set-Content -LiteralPath ($archive+'.sha256') -Encoding ascii
    Write-Output $archive
}
if ($BuildInstaller) {
    if (-not $Public) { throw 'The redistributable installer must be built from the public package.' }
    if ($SkipZip) { throw 'Installer publishing requires the package ZIP.' }
    & dotnet publish (Join-Path $root 'installer/NeuralFlow.Setup.csproj') -c Release -r win-x64 --self-contained true -o (Join-Path $dist 'installer') "-p:PayloadZipPath=$archive" -p:DebugType=None -p:DebugSymbols=false "-p:PathMap=$root=/_/NeuralFlow"
    if ($LASTEXITCODE -ne 0) { throw 'Installer publish failed.' }
}
Write-Output $output
