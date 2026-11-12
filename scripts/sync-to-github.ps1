# sync-to-github.ps1
# Commit pending doc changes and try to push to GitHub.
# Safe to run anytime: with no changes it does nothing, without a proxy it
# reports clearly instead of hanging.
#
# Usage:
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\tools\sync-to-github.ps1"
#   ... -File "...\sync-to-github.ps1" -NoPush     # local commit only
#   ... -File "...\sync-to-github.ps1" -Status     # just report, change nothing

param(
    [switch]$NoPush,
    [switch]$Status
)

$ErrorActionPreference = 'Continue'

# ---- locate workspace root (this script lives in <root>\tools) ----
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $Root '.git'))) {
    Write-Host "[FAIL] no .git under $Root" -ForegroundColor Red
    exit 1
}
Set-Location $Root

function Say($msg, $color) {
    if ($color) { Write-Host $msg -ForegroundColor $color } else { Write-Host $msg }
}

Say "===== workspace: $Root =====" Cyan

# ---- 1. stage + inspect ----
git add -A 2>&1 | Out-Null
$pending = @(git status --porcelain)
$localAhead = @(git log --oneline '@{u}..HEAD' 2>$null)

if ($Status) {
    Say "dirty files : $($pending.Count)"
    Say "unpushed    : $($localAhead.Count)"
    if ($pending.Count -gt 0) { $pending | ForEach-Object { Say "  $_" } }
    exit 0
}

# ---- 2. commit if there is anything ----
if ($pending.Count -gt 0) {
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm'
    $msg = "sync: docs snapshot $stamp ($($pending.Count) files)"
    # .git\config has a mojibake author name; override per-command instead of fixing config
    git commit -m $msg 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $sha = (git rev-parse --short HEAD)
        Say "[OK] committed $sha ($($pending.Count) files)" Green
    } else {
        Say "[FAIL] commit failed (pre-commit hook blocked?)" Red
        Say "       run: python memory/check_memory.py" Yellow
        exit 1
    }
} else {
    Say "[--] nothing to commit (working tree clean)" DarkGray
}

if ($NoPush) {
    Say "[--] -NoPush given, stopping before push" DarkGray
    exit 0
}

# ---- 3. anything left to push? ----
# NOTE: with no upstream branch, 'git log @{u}..HEAD' fails and prints nothing -
# which silently looked like "already in sync". Check the upstream explicitly.
$branch = (git rev-parse --abbrev-ref HEAD)
$upstream = (git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>$null)
if (-not $upstream) {
    git rev-parse --verify --quiet "origin/$branch" > $null 2>&1
    if ($LASTEXITCODE -ne 0) {
        Say "[FAIL] branch '$branch' has no upstream, and origin/$branch does not exist." Red
        Say "       push once manually:  git push -u origin $branch" Yellow
        exit 1
    }
    Say "[..] no upstream set - using origin/$branch" Yellow
    git branch --set-upstream-to="origin/$branch" $branch 2>&1 | Out-Null
}
$localAhead = @(git log --oneline '@{u}..HEAD' 2>$null)
if ($localAhead.Count -eq 0) {
    Say "[OK] already in sync with origin - nothing to push" Green
    exit 0
}
Say "[..] $($localAhead.Count) commit(s) waiting to be pushed" Cyan

# ---- 4. find a working proxy (Windows IE settings), else try direct ----
$proxy = $null
try {
    $reg = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction Stop
    if ($reg.ProxyEnable -eq 1 -and $reg.ProxyServer) {
        $server = $reg.ProxyServer
        if ($server -notmatch '://') { $server = "http://$server" }
        $hostPart = ([uri]$server).Host
        $portPart = ([uri]$server).Port
        $alive = Test-NetConnection -ComputerName $hostPart -Port $portPart -InformationLevel Quiet -WarningAction SilentlyContinue
        if ($alive) { $proxy = $server; Say "[..] proxy detected and alive: $proxy" Cyan }
        else { Say "[..] system proxy configured but port closed: $proxy" DarkGray }
    }
} catch {
    Say "[..] could not read proxy settings, will try direct" DarkGray
}

# ---- 5. push, fast-fail instead of hanging for minutes ----
$attempts = @()
if ($proxy) { $attempts += $proxy }
$attempts += 'direct'

$pushed = $false
foreach ($mode in $attempts) {
    if ($mode -eq 'direct') {
        Say "[..] pushing direct (no proxy) ..." Cyan
        $gitArgs = @('-c', 'http.proxy=', '-c', 'http.connectTimeout=15',
                     '-c', 'http.lowSpeedLimit=1000', '-c', 'http.lowSpeedTime=15', 'push')
    } else {
        Say "[..] pushing via $mode ..." Cyan
        $gitArgs = @('-c', "http.proxy=$mode", '-c', "https.proxy=$mode", '-c', 'http.connectTimeout=15',
                     '-c', 'http.lowSpeedLimit=1000', '-c', 'http.lowSpeedTime=15', 'push')
    }
    $out = & git @gitArgs 2>&1
    if ($LASTEXITCODE -eq 0) {
        Say "[OK] pushed to origin/$branch" Green
        $pushed = $true
        break
    } else {
        $tail = ($out | Select-Object -Last 3) -join ' | '
        Say "  -> failed: $tail" DarkGray
    }
}

if (-not $pushed) {
    Say "" 
    Say "[WARN] push failed on every route. Your commits are SAFE locally." Yellow
    Say "       $($localAhead.Count) commit(s) waiting. Turn on the proxy/VPN, then run this again." Yellow
    Say "       Only the upload is pending - nothing is lost." Yellow
    exit 2
}

$remote = (git ls-remote origin "refs/heads/$branch" 2>$null)
if ($remote) {
    $remoteSha = ($remote -split '\s+')[0]
    $localSha = (git rev-parse HEAD)
    if ($remoteSha -eq $localSha) { Say "[OK] remote confirmed at $($localSha.Substring(0,7))" Green }
    else { Say "[??] remote reads $remoteSha, local is $localSha" Yellow }
}

Say "===== done =====" Cyan
exit 0
