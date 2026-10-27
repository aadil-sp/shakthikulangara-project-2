# MarkerPilot installer for Windows (PowerShell).
#   irm https://raw.githubusercontent.com/aadil-sp/shakthikulangara-project-2/main/install/install.ps1 | iex
# Installs the ready-made app from the latest release when available, otherwise
# installs from source with pip (installs Python with winget if needed).
$ErrorActionPreference = "Stop"
$Repo      = "aadil-sp/shakthikulangara-project-2"
$Url       = "https://github.com/$Repo/releases/latest/download/markerpilot-windows-x86_64.exe"
$SourceZip = "https://github.com/$Repo/archive/refs/heads/main.zip#subdirectory=robotics"
$Dir       = Join-Path $env:LOCALAPPDATA "MarkerPilot"
$Exe       = Join-Path $Dir "markerpilot.exe"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Add-UserPath($p) {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not ($userPath -split ";" | Where-Object { $_ -eq $p })) {
        [Environment]::SetEnvironmentVariable("Path", "$userPath;$p", "User")
        $env:Path = "$env:Path;$p"
    }
}

function New-StartMenuShortcut($target) {
    $lnk = Join-Path ([Environment]::GetFolderPath("Programs")) "MarkerPilot.lnk"
    $s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
    $s.TargetPath = $target
    $s.Description = "MarkerPilot - ArUco robot navigation"
    $s.Save()
}

New-Item -ItemType Directory -Force -Path $Dir | Out-Null
$haveBinary = $false
try {
    Write-Host "==> Downloading MarkerPilot (latest release)" -ForegroundColor Cyan
    Invoke-WebRequest -Uri $Url -OutFile $Exe -UseBasicParsing
    Unblock-File -Path $Exe
    $haveBinary = $true
} catch {
    Write-Host "!! No ready-made Windows app in the latest release yet - installing from source" -ForegroundColor Yellow
}

if ($haveBinary) {
    Add-UserPath $Dir
    New-StartMenuShortcut $Exe
    Write-Host "==> Installed to $Exe" -ForegroundColor Green
} else {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py -or (& python -c "import sys;print(sys.version_info>=(3,9))") -ne "True") {
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            Write-Host "==> Installing Python 3.12 with winget" -ForegroundColor Cyan
            winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
            $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
        } else {
            Write-Host "!! Please install Python 3.9+ from https://www.python.org (tick 'Add to PATH') and run this again." -ForegroundColor Red
            exit 1
        }
    }
    Write-Host "==> pip install MarkerPilot" -ForegroundColor Cyan
    python -m pip install --user --upgrade $SourceZip
    $scripts = python -c "import sysconfig;print(sysconfig.get_path('scripts','nt_user'))"
    Add-UserPath $scripts
    New-StartMenuShortcut (Join-Path $scripts "markerpilot.exe")
    Write-Host "==> Installed (Python package). Scripts folder: $scripts" -ForegroundColor Green
}
Write-Host "    Start menu: MarkerPilot"
Write-Host "    In a NEW terminal:  markerpilot   |   markerpilot --sim   |   markerpilot cameras"
