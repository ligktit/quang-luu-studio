# Enable CDP flag on all Edge/Chrome/Brave shortcuts
$CDP_PORT = 9222
$FLAG_DEBUG = "--remote-debugging-port=$CDP_PORT"
$FLAG_ORIGINS = "--remote-allow-origins=*"

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
$skipped = 0
$errors = 0

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

            if ($sc.Arguments -like '*remote-debugging-port*') {
                $skipped++
                Write-Host "[SKIP] $($lnk.Name) - da co flag" -ForegroundColor DarkGray
                continue
            }

            $newArgs = "$FLAG_ORIGINS $FLAG_DEBUG"
            if ($sc.Arguments) { $newArgs = "$newArgs $($sc.Arguments)" }
            $sc.Arguments = $newArgs
            $sc.Save()
            $modified++
            Write-Host "[OK]   $($lnk.FullName)" -ForegroundColor Green
            Write-Host "       Args: $newArgs" -ForegroundColor Gray
        } catch {
            $errors++
            Write-Host "[ERR]  $($lnk.Name): $_" -ForegroundColor Red
        }
    }
}

Write-Host ""
Write-Host "Da sua: $modified shortcut(s) | Bo qua: $skipped | Loi: $errors" -ForegroundColor Cyan
if ($modified -gt 0) {
    Write-Host ""
    Write-Host "=> TAT HOAN TOAN trinh duyet roi mo lai de flag co hieu luc." -ForegroundColor Yellow
}
