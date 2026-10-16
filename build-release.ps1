$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$version = "0.3.0"
$releaseRoot = Join-Path $projectRoot "release\ClipClean-$version"
$distRoot = Join-Path $projectRoot "release\engine-build"
$ffmpegCandidates = @()
if ($env:FFMPEG_BIN) { $ffmpegCandidates += $env:FFMPEG_BIN }
$ffmpegCandidates += @(
    (Join-Path $projectRoot "third_party\ffmpeg\bin"),
    (Join-Path $env:USERPROFILE "Desktop\ffmpeg\ffmpeg\bin"),
    "C:\ffmpeg\bin"
)
$ffmpegBin = $ffmpegCandidates |
    Where-Object {
        (Test-Path (Join-Path $_ "ffmpeg.exe")) -and
        (Test-Path (Join-Path $_ "ffprobe.exe"))
    } |
    Select-Object -First 1
if (-not $ffmpegBin) {
    throw "找不到 FFmpeg。请设置 FFMPEG_BIN 为包含 ffmpeg.exe 和 ffprobe.exe 的 bin 目录。"
}
$pyinstaller = Get-Command pyinstaller -ErrorAction SilentlyContinue
if (-not $pyinstaller) { throw "找不到 PyInstaller。请先运行：python -m pip install pyinstaller" }

Remove-Item -LiteralPath (Join-Path $projectRoot "release") -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null

& $pyinstaller.Source --noconfirm --clean --onefile --name clipclean-engine `
    --paths (Join-Path $projectRoot "src") `
    --distpath $distRoot `
    --workpath (Join-Path $projectRoot "release\pyinstaller-work") `
    --specpath (Join-Path $projectRoot "release") `
    (Join-Path $projectRoot "src\adskip_engine_entry.py")
if ($LASTEXITCODE -ne 0) { throw "处理引擎打包失败。" }

$compiler = @(
    "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
    "$env:WINDIR\Microsoft.NET\Framework\v4.0.30319\csc.exe"
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $compiler) { throw "找不到 Windows C# 编译器。" }
$gui = Join-Path $releaseRoot "ClipClean-v$version.exe"
& $compiler /nologo /target:winexe /optimize+ /codepage:65001 `
    /reference:System.dll /reference:System.Drawing.dll /reference:System.Windows.Forms.dll `
    "/out:$gui" (Join-Path $projectRoot "gui\AdSkipGui.cs")
if ($LASTEXITCODE -ne 0) { throw "GUI 编译失败。" }

Copy-Item (Join-Path $distRoot "clipclean-engine.exe") (Join-Path $releaseRoot "clipclean-engine.exe")
Copy-Item (Join-Path $ffmpegBin "ffmpeg.exe") (Join-Path $releaseRoot "ffmpeg.exe")
Copy-Item (Join-Path $ffmpegBin "ffprobe.exe") (Join-Path $releaseRoot "ffprobe.exe")
Copy-Item (Join-Path $projectRoot "README.md") (Join-Path $releaseRoot "使用说明.md")
Copy-Item (Join-Path $projectRoot "LICENSE") (Join-Path $releaseRoot "LICENSE")
Copy-Item (Join-Path $projectRoot "THIRD_PARTY_NOTICES.md") (Join-Path $releaseRoot "第三方声明.md")
New-Item -ItemType Directory -Path (Join-Path $releaseRoot "licenses") -Force | Out-Null
Copy-Item (Join-Path $projectRoot "licenses\ffmpeg-gpl-3.0.txt") (Join-Path $releaseRoot "licenses\ffmpeg-gpl-3.0.txt")
New-Item -ItemType Directory -Path (Join-Path $releaseRoot "work") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $releaseRoot "outputs") -Force | Out-Null
$launcherText = @'
@echo off
start "" "%~dp0ClipClean-v__VERSION__.exe" %*
'@
$launcherText = $launcherText.Replace("__VERSION__", $version)
[IO.File]::WriteAllText((Join-Path $releaseRoot "启动ClipClean.cmd"), $launcherText, [Text.Encoding]::ASCII)
Write-Host "发布目录已生成：$releaseRoot"
$zipPath = Join-Path $projectRoot "release\ClipClean-$version-windows-x64.zip"
Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $releaseRoot "*") -DestinationPath $zipPath -CompressionLevel Optimal
Write-Host "发布压缩包已生成：$zipPath"
$hashPath = Join-Path $projectRoot "release\SHA256SUMS.txt"
$hash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath $hashPath -Value ($hash + "  " + (Split-Path $zipPath -Leaf)) -Encoding ASCII
Write-Host "校验文件已生成：$hashPath"
