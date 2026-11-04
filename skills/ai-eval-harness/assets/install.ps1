<#
.SYNOPSIS
    Install this skill bundle from the repo copy to the user-level skill root.

.DESCRIPTION
    Why a script instead of a manual Copy-Item: the bundle exists twice --
    project-level .dsh/skills/ (versioned, reviewable) and user-level
    ~/.dsh/skills/ (available to every project). Hand copying lets the two
    drift silently; then which copy you run depends on luck. This script
    always installs from the repo copy and can verify both are identical.

    Kept ASCII-only on purpose: Windows PowerShell 5.1 reads no-BOM files as
    ANSI, so non-ASCII comments here would become mojibake and break parsing.
    Docs stay in Chinese; this file is executable plumbing.
#>
[CmdletBinding()]
param(
    [string]$Target = (Join-Path $env:USERPROFILE ".dsh\skills"),
    [switch]$VerifyOnly
)

$ErrorActionPreference = "Stop"

# Source = skill bundle root (assets/ lives one level below it).
$SkillRoot = Split-Path -Parent $PSScriptRoot
$Name = Split-Path -Leaf $SkillRoot
$Dst = Join-Path $Target $Name

# Guard: install.ps1 ships inside the bundle, so it also lands in the install
# target. Running it *from the installed copy* would set $Dst == $SkillRoot and
# the "clean install" step below would delete the skill we just installed.
$RootFull = (Get-Item $SkillRoot).FullName.TrimEnd('\')
$DstFull = $Dst.TrimEnd('\')
if ($RootFull -ieq $DstFull) {
    Write-Host "Refusing to run: source and target are the same directory." -ForegroundColor Red
    Write-Host "  $SkillRoot"
    Write-Host "This script must be run from the repo copy (.dsh/skills/$Name/assets)," -ForegroundColor Red
    Write-Host "not from the installed user-level copy." -ForegroundColor Red
    exit 1
}

# Run leftovers must never ship inside a skill bundle.
$JunkPattern = '(\\|/)(__pycache__|_eval_smoke|_selftest|eval-results|jtest|build)(\\|/)|\.pyc$'

function Get-BundleFileList([string]$root) {
    Get-ChildItem $root -Recurse -File |
        Where-Object { $_.FullName -notmatch $JunkPattern }
}

function Get-RelativePath([string]$root, [string]$full) {
    $full.Substring($root.Length + 1)
}

$srcFiles = @(Get-BundleFileList $SkillRoot)

if ($VerifyOnly) {
    if (-not (Test-Path $Dst)) {
        Write-Host "NOT INSTALLED: $Dst" -ForegroundColor Yellow
        exit 1
    }
    $drift = @()
    foreach ($f in $srcFiles) {
        $rel = Get-RelativePath $SkillRoot $f.FullName
        $d = Join-Path $Dst $rel
        if (-not (Test-Path $d)) { $drift += "$rel (missing)"; continue }
        $a = (Get-FileHash $f.FullName -Algorithm SHA256).Hash
        $b = (Get-FileHash $d -Algorithm SHA256).Hash
        if ($a -ne $b) { $drift += $rel }
    }
    $dstExtra = @(Get-BundleFileList $Dst |
        Where-Object { -not (Test-Path (Join-Path $SkillRoot (Get-RelativePath $Dst $_.FullName))) })
    foreach ($x in $dstExtra) { $drift += ((Get-RelativePath $Dst $x.FullName) + " (extra)") }

    if ($drift.Count -gt 0) {
        Write-Host "OUT OF SYNC:" -ForegroundColor Yellow
        $drift | ForEach-Object { Write-Host "  - $_" }
        exit 1
    }
    Write-Host "In sync ($($srcFiles.Count) files)." -ForegroundColor Green
    exit 0
}

if (Test-Path $Dst) { Remove-Item $Dst -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Dst | Out-Null

foreach ($f in $srcFiles) {
    $rel = Get-RelativePath $SkillRoot $f.FullName
    $out = Join-Path $Dst $rel
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $out) | Out-Null
    Copy-Item $f.FullName $out -Force
}

Write-Host "Installed $($srcFiles.Count) files -> $Dst" -ForegroundColor Green
