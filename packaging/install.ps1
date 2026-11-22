# Installs the mbot2 command-line tool on Windows. In PowerShell, run:
#
#   irm https://github.com/Coletronix/mbot2-ble/releases/latest/download/install.ps1 | iex
#
# It downloads one file, the standalone mbot2.exe from the latest release, to
# %LOCALAPPDATA%\Programs\mbot2 and adds that folder to your user PATH. No administrator
# rights needed. To uninstall, delete that folder. Running it again updates to the newest version.

& {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'  # the progress bar makes downloads very slow in Windows PowerShell 5
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    $repo = 'Coletronix/mbot2-ble'
    $dir = Join-Path $env:LOCALAPPDATA 'Programs\mbot2'
    $exe = Join-Path $dir 'mbot2.exe'
    $url = "https://github.com/$repo/releases/latest/download/mbot2-windows-x64.exe"

    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    Write-Host "Downloading $url"
    Invoke-WebRequest -Uri $url -OutFile "$exe.download" -UseBasicParsing
    try {
        Move-Item -Force "$exe.download" $exe
    } catch {
        Remove-Item -Force "$exe.download" -ErrorAction SilentlyContinue
        throw "Couldn't replace $exe. Is mbot2 still running (a terminal or VS Code)? Close it and try again."
    }

    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    if (-not $userPath) { $userPath = '' }
    if (($userPath -split ';') -notcontains $dir) {
        $newPath = (($userPath.TrimEnd(';')), $dir | Where-Object { $_ }) -join ';'
        [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
        $env:Path = "$env:Path;$dir"
        $note = 'Other terminals that are already open need to be restarted to find it.'
    }

    Write-Host "Installed $(& $exe --version) to $exe"
    Write-Host "Try it:  mbot2 scan"
    if ($note) { Write-Host $note }
}
