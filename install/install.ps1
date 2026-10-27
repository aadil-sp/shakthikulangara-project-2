# MarkerPilot installer for Windows (PowerShell).
#   irm https://raw.githubusercontent.com/aadil-sp/shakthikulangara-project-2/main/install/install.ps1 | iex
$ErrorActionPreference = "Stop"
$Repo  = "aadil-sp/shakthikulangara-project-2"
$Url   = "https://github.com/$Repo/releases/latest/download/markerpilot-windows-x86_64.exe"
$Dir   = Join-Path $env:LOCALAPPDATA "MarkerPilot"
$Exe   = Join-Path $Dir "markerpilot.exe"

Write-Host "==> Downloading MarkerPilot (latest release)" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $Dir | Out-Null
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $Url -OutFile $Exe -UseBasicParsing
Unblock-File -Path $Exe

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not ($userPath -split ";" | Where-Object { $_ -eq $Dir })) {
    Write-Host "==> Adding $Dir to your PATH" -ForegroundColor Cyan
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$Dir", "User")
    $env:Path = "$env:Path;$Dir"
}

$Shortcut = Join-Path ([Environment]::GetFolderPath("Programs")) "MarkerPilot.lnk"
$Shell = New-Object -ComObject WScript.Shell
$Link = $Shell.CreateShortcut($Shortcut)
$Link.TargetPath = $Exe
$Link.WorkingDirectory = $Dir
$Link.Description = "MarkerPilot - ArUco robot navigation"
$Link.Save()

Write-Host "==> Installed to $Exe" -ForegroundColor Green
Write-Host "    Start menu: MarkerPilot"
Write-Host "    In a NEW terminal:  markerpilot   |   markerpilot --sim   |   markerpilot cameras"
