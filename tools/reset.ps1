<#
.SYNOPSIS
    Wipe every ArchVM artefact and recreate a clean starting state.

.DESCRIPTION
    Removes the virtual disk, UEFI variables, saved settings, build output and
    logs, then recreates an empty disk, fresh firmware and a current seed.iso,
    and repairs the Desktop and Start Menu shortcuts.

    The Arch ISO is kept by default because it is 1.5 GB and its checksum was
    already verified. Pass -All to remove it too.

    Nothing outside the ArchVM folder, %APPDATA%\ArchVM and the two shortcuts is
    touched.

.PARAMETER Root
    VM data directory. Defaults to D:\ArchVM.

.PARAMETER All
    Also delete the downloaded Arch ISO.

.PARAMETER KeepBuild
    Leave dist/ and build/ alone (skips rebuilding the executable).

.PARAMETER ResetGuestConfig
    Also reset seed\vm.conf to defaults. Without this the guest username,
    password, hostname and timezone from the previous install are kept, since
    retyping them is usually not what you want.

.PARAMETER Force
    Do not ask for confirmation.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\reset.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\reset.ps1 -All -Force
#>
[CmdletBinding()]
param(
    [string]$Root = 'D:\ArchVM',
    [switch]$All,
    [switch]$KeepBuild,
    [switch]$ResetGuestConfig,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

function Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Note($msg) { Write-Host "    $msg" -ForegroundColor DarkGray }
function Warn($msg) { Write-Host "    $msg" -ForegroundColor Yellow }

$qemuDir = 'C:\Program Files\qemu'
$qemuImg = Join-Path $qemuDir 'qemu-img.exe'
$appData = Join-Path $env:APPDATA 'ArchVM'

if (-not (Test-Path $Root)) { throw "VM directory not found: $Root" }

# ---------------------------------------------------------------- summary
Write-Host ""
Write-Host "ArchVM reset" -ForegroundColor White
Write-Host "------------"
$size = 0
if (Test-Path $Root) {
    $size = (Get-ChildItem $Root -Recurse -File -EA SilentlyContinue |
             Measure-Object Length -Sum).Sum / 1GB
}
Note "VM directory : $Root  ($('{0:N1}' -f $size) GB)"
Note "Settings     : $appData"
Note "Arch ISO     : $(if ($All) { 'DELETED' } else { 'kept' })"
Note "Build output : $(if ($KeepBuild) { 'kept' } else { 'removed and rebuilt' })"
Note "Guest config : $(if ($ResetGuestConfig) { 'reset to defaults' } else { 'kept (username, password, timezone)' })"
Write-Host ""
Write-Host "This permanently deletes the virtual disk and everything installed" -ForegroundColor Yellow
Write-Host "inside the VM. Windows files outside these folders are untouched." -ForegroundColor Yellow
Write-Host ""

if (-not $Force) {
    $ans = Read-Host "Type RESET to continue"
    if ($ans -ne 'RESET') { Write-Host "Cancelled."; exit 1 }
}

# ------------------------------------------------------------ 1. processes
Step "Stopping anything that holds these files open"
foreach ($n in 'ArchVM', 'qemu-system-x86_64', 'qemu-system-x86_64w', 'pythonw') {
    $procs = Get-Process $n -EA SilentlyContinue
    if ($procs) {
        $procs | Stop-Process -Force -EA SilentlyContinue
        Note "stopped $n ($($procs.Count))"
    }
}
Start-Sleep -Seconds 2

# --------------------------------------------------------------- 2. delete
Step "Removing VM state"
$targets = @(
    (Join-Path $Root 'disks\arch-hyprland.qcow2'),
    (Join-Path $Root 'disks\OVMF_VARS.fd'),
    (Join-Path $Root 'iso\seed.iso'),
    (Join-Path $appData 'vm.json'),
    (Join-Path $appData 'settings.json'),
    (Join-Path $appData 'elevated-task.ps1'),
    (Join-Path $appData 'elevated-result.txt')
)
if ($All) { $targets += (Join-Path $Root 'iso\archlinux-x86_64.iso') }

foreach ($t in $targets) {
    if (Test-Path $t) {
        try { Remove-Item $t -Force; Note "deleted $(Split-Path $t -Leaf)" }
        catch { Warn "could not delete $t : $($_.Exception.Message)" }
    }
}

Step "Clearing logs and caches"
foreach ($d in @((Join-Path $Root 'logs'))) {
    if (Test-Path $d) {
        Get-ChildItem $d -File -EA SilentlyContinue | Remove-Item -Force -EA SilentlyContinue
        Note "emptied $d"
    }
}
Get-ChildItem $Root -Recurse -Directory -Filter '__pycache__' -EA SilentlyContinue |
    ForEach-Object { Remove-Item $_.FullName -Recurse -Force -EA SilentlyContinue }
Note "removed __pycache__ directories"

if (-not $KeepBuild) {
    Step "Removing build output"
    foreach ($d in @((Join-Path $Root 'app\dist'), (Join-Path $Root 'app\build'))) {
        if (Test-Path $d) {
            Remove-Item $d -Recurse -Force -EA SilentlyContinue
            if (Test-Path $d) { Warn "could not fully remove $d - close anything using it" }
            else { Note "deleted $d" }
        }
    }
}

# ------------------------------------------------------------- 3. recreate
if ($ResetGuestConfig) {
    Step "Resetting the guest configuration"
    $conf = Join-Path $Root 'seed\vm.conf'
    @(
        '# defaults - edit here or in the Guest page of the app',
        'USERNAME=arch',
        'USERPASS=arch',
        'ROOTPASS=arch',
        'HOSTNAME=arch-hypr',
        'TIMEZONE=UTC',
        'LOCALE=en_US.UTF-8',
        'KEYMAP=us',
        'FORK_REPO=https://github.com/pctrade/end4-pc.git',
        'FORK_NAME=end4-pC',
        'AUTO_CONFIRM=no'
    ) -join "`n" | ForEach-Object {
        # LF only: CRLF breaks these values inside the guest shell scripts
        [IO.File]::WriteAllText($conf, $_ + "`n")
    }
    Note "seed\vm.conf reset (the app rewrites it from your answers on setup)"
}

Step "Recreating a clean VM"
foreach ($d in 'disks', 'iso', 'logs', 'seed') {
    New-Item -ItemType Directory -Force -Path (Join-Path $Root $d) | Out-Null
}

if (-not (Test-Path $qemuImg)) { throw "qemu-img not found at $qemuImg" }
& $qemuImg create -f qcow2 (Join-Path $Root 'disks\arch-hyprland.qcow2') 120G | Out-Null
Note "created a fresh 120 GB disk (sparse)"

$code = Join-Path $qemuDir 'share\edk2-x86_64-code.fd'
$vars = Join-Path $qemuDir 'share\edk2-i386-vars.fd'
if (Test-Path $code) {
    Copy-Item $code (Join-Path $Root 'disks\OVMF_CODE.fd') -Force
    Copy-Item $vars (Join-Path $Root 'disks\OVMF_VARS.fd') -Force
    Note "reset UEFI firmware and variables"
} else {
    Warn "UEFI firmware not found in the QEMU install"
}

$py = (Get-Command python -EA SilentlyContinue).Source
$builder = Join-Path $Root 'manager\build_seed.py'
if ($py -and (Test-Path $builder)) {
    & $py $builder | ForEach-Object { Note $_ }
} else {
    Warn "could not rebuild seed.iso (python or build_seed.py missing)"
}

# ---------------------------------------------------------------- 4. build
if (-not $KeepBuild) {
    $buildPy = Join-Path $Root 'app\build.py'
    if ($py -and (Test-Path $buildPy)) {
        Step "Rebuilding the application"
        Push-Location (Split-Path $buildPy)
        try { & $py $buildPy | ForEach-Object { Note $_ } } finally { Pop-Location }
    }
}

# ------------------------------------------------------------ 5. shortcuts
Step "Restoring shortcuts"
$exe = Join-Path $Root 'app\dist\ArchVM\ArchVM.exe'
$ico = Join-Path $Root 'app\assets\archvm.ico'
if (Test-Path $exe) {
    $ws = New-Object -ComObject WScript.Shell
    foreach ($lnk in @((Join-Path ([Environment]::GetFolderPath('Desktop')) 'ArchVM Manager.lnk'),
                       (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\ArchVM Manager.lnk'))) {
        $sc = $ws.CreateShortcut($lnk)
        $sc.TargetPath = $exe
        $sc.WorkingDirectory = (Split-Path $exe)
        if (Test-Path $ico) { $sc.IconLocation = $ico }
        $sc.Description = 'Arch Linux + Hyprland VM (QEMU)'
        $sc.WindowStyle = 1
        $sc.Save()
        Note "shortcut -> $lnk"
    }
} else {
    Warn "executable not built; shortcuts left alone"
}

# ------------------------------------------------------------------ done
Write-Host ""
Write-Host "Reset complete." -ForegroundColor Green
$now = (Get-ChildItem $Root -Recurse -File -EA SilentlyContinue | Measure-Object Length -Sum).Sum / 1GB
Note ("VM directory now {0:N1} GB" -f $now)
Write-Host ""
Write-Host "Next: open ArchVM Manager and press Install Arch." -ForegroundColor White
Write-Host ""
