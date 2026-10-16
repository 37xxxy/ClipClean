$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $projectRoot "gui\AdSkipGui.cs"
$output = Join-Path $projectRoot "ClipClean-v0.3.0.exe"
$compilerCandidates = @(
    "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
    "$env:WINDIR\Microsoft.NET\Framework\v4.0.30319\csc.exe"
)
$compiler = $compilerCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $compiler) {
    throw "找不到 Windows C# 编译器。"
}

& $compiler /nologo /target:winexe /optimize+ /codepage:65001 `
    /reference:System.dll `
    /reference:System.Drawing.dll `
    /reference:System.Windows.Forms.dll `
    "/out:$output" `
    $source
if ($LASTEXITCODE -ne 0) {
    throw "GUI 编译失败，退出码 $LASTEXITCODE。"
}

Write-Host "已生成：$output"
