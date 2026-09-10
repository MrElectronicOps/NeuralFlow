param([string]$FfmpegSource, [switch]$SkipDownload)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$downloads = Join-Path $PSScriptRoot 'downloads'
$python = Join-Path $root 'python'
$tools = Join-Path $root 'engine/tools'
New-Item -ItemType Directory -Force -Path $downloads,$python,$tools | Out-Null
$pythonName = 'python-3.12.10-embed-amd64.zip'
$pythonZip = Join-Path $downloads $pythonName
$pythonUrl = 'https://www.python.org/ftp/python/3.12.10/' + $pythonName
$expectedPython = '4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3'
if (-not (Test-Path -LiteralPath $pythonZip)) {
    if ($SkipDownload) { throw 'The pinned Python archive is missing.' }
    Invoke-WebRequest -Uri $pythonUrl -OutFile $pythonZip
}
if ((Get-FileHash -LiteralPath $pythonZip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedPython) {
    throw 'Python archive does not match the SHA-256 published in its official SPDX document.'
}
Expand-Archive -LiteralPath $pythonZip -DestinationPath $python -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'python312._pth') -Destination (Join-Path $python 'python312._pth') -Force
if ($FfmpegSource) {
    $ffmpeg = (Resolve-Path -LiteralPath $FfmpegSource).Path
    Copy-Item -LiteralPath $ffmpeg -Destination (Join-Path $tools 'ffmpeg.exe') -Force
}
$vendor = Join-Path $root 'engine/vendor'
New-Item -ItemType Directory -Force -Path $vendor | Out-Null
$packages = @(
    @{name='numpy';version='2.2.6';pattern='*-cp312-cp312-win_amd64.whl'},
    @{name='Pillow';version='11.3.0';pattern='*-cp312-cp312-win_amd64.whl'},
    @{name='opencv-python-headless';version='4.12.0.88';pattern='*-cp37-abi3-win_amd64.whl'}
)
$packageRecords = foreach ($package in $packages) {
    $metadata = Invoke-RestMethod -Uri ('https://pypi.org/pypi/'+$package.name+'/'+$package.version+'/json')
    $assets = @($metadata.urls | Where-Object { $_.filename -like $package.pattern })
    if ($assets.Count -ne 1) { throw ('Expected one pinned Windows wheel for '+$package.name) }
    $asset = $assets[0]
    if (([Uri]$asset.url).Host -ne 'files.pythonhosted.org') { throw 'Unexpected wheel download host.' }
    $wheel = Join-Path $downloads $asset.filename
    if (-not (Test-Path -LiteralPath $wheel)) {
        if ($SkipDownload) { throw ('Pinned dependency is missing: '+$asset.filename) }
        Invoke-WebRequest -Uri $asset.url -OutFile $wheel
    }
    if ((Get-FileHash -LiteralPath $wheel -Algorithm SHA256).Hash.ToLowerInvariant() -ne $asset.digests.sha256) { throw ('Dependency hash mismatch: '+$asset.filename) }
    $zip = $wheel+'.zip'
    Copy-Item -LiteralPath $wheel -Destination $zip -Force
    Expand-Archive -LiteralPath $zip -DestinationPath $vendor -Force
    [ordered]@{name=$package.name;version=$package.version;url=$asset.url;sha256=$asset.digests.sha256}
}
$manifest = [ordered]@{
    python = [ordered]@{version='3.12.10';url=$pythonUrl;sha256=$expectedPython;publishedHashSource=($pythonUrl+'.spdx.json')}
    pythonPackages = @($packageRecords)
    videoTools = 'Fetched separately through Complete setup or Download video tools; not required to build the public app.'
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $tools 'dependency-manifest.json') -Encoding utf8
& (Join-Path $python 'python.exe') -c "import sys,cv2,numpy,PIL,video,backend; print('Portable imports OK:',sys.version.split()[0],cv2.__version__,numpy.__version__,PIL.__version__)"
if ($LASTEXITCODE -ne 0) { throw 'Portable Python import smoke test failed.' }
Write-Output 'Portable Python and image dependencies are staged. The public app installs optional components through Complete setup.'
