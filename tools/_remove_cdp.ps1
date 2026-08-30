# Quang Luu Studio — Remove CDP flags from browser shortcuts
$browsers = @(
    @{ Name='Microsoft Edge';   Exe='msedge.exe' },
    @{ Name='Google Chrome';    Exe='chrome.exe' },
    @{ Name='Brave';            Exe='brave.exe' }
)

$searchPaths = @(
    [Environment]::GetFolderPath('Desktop'),
    [Environment]::GetFolderPath('CommonDesktopDirectory'),
    (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'),
    (Join-Path $env:PROGRAMDATA 'Microsoft\Windows\Start Menu\Programs'),
    (Join-Path $env:APPDATA 'Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar'),
    (Join-Path $env:APPDATA 'Microsoft\Internet Explorer\Quick Launch')
)

$shell = New-Object -ComObject WScript.Shell
$modified = 0

foreach ($sp in $searchPaths) {
    if (-not (Test-Path $sp)) { continue }
    $lnks = Get-ChildItem -Path $sp -Filter '*.lnk' -Recurse -ErrorAction SilentlyContinue

    foreach ($lnk in $lnks) {
        try {
            $sc = $shell.CreateShortcut($lnk.FullName)
            $target = $sc.TargetPath

            $matched = $false
            foreach ($b in $browsers) {
                if ($target -like "*$($b.Exe)*") { $matched = $true; break }
            }
            if (-not $matched) { continue }
            if ($sc.Arguments -notlike '*remote-debugging-port*' -and $sc.Arguments -notlike '*remote-allow-origins*') { continue }

            $cleanArgs = $sc.Arguments -replace '--remote-debugging-port=\d+', '' -replace '--remote-allow-origins=\S*', ''
            $cleanArgs = ($cleanArgs -replace '\s+', ' ').Trim()
            $sc.Arguments = $cleanArgs
            $sc.Save()
            $modified++
            Write-Host "[OK] $($lnk.FullName) -> da go flag" -ForegroundColor Green
        } catch {
            Write-Host "[ERR] $($lnk.Name): $_" -ForegroundColor Red
        }
    }
}

Write-Host ""
Write-Host "Da go flag khoi $modified shortcut(s)" -ForegroundColor Cyan
if ($modified -gt 0) {
    Write-Host "=> Tat trinh duyet roi mo lai de ap dung." -ForegroundColor Yellow
}
