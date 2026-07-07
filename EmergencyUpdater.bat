<# :
@echo off
setlocal
:: Ensure admin privileges for stopping services
NET SESSION >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting Administrator privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "iex ((Get-Content '%~f0') -join [Environment]::NewLine)"
exit /b
#>

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$Global:latestVersion = $null
$Global:downloadUrl = $null
$Global:currentVersion = "Unbekannt"

# --- UI Setup ---
$form = New-Object System.Windows.Forms.Form
$form.Text = "EmberCore Emergency Updater"
$form.Size = New-Object System.Drawing.Size(550, 400)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false

$fontBold = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
$fontNormal = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Regular)

$lblPath = New-Object System.Windows.Forms.Label
$lblPath.Text = "EmberCore Installationspfad:"
$lblPath.Location = New-Object System.Drawing.Point(20, 20)
$lblPath.AutoSize = $true
$lblPath.Font = $fontNormal
$form.Controls.Add($lblPath)

$txtPath = New-Object System.Windows.Forms.TextBox
$txtPath.Location = New-Object System.Drawing.Point(20, 45)
$txtPath.Size = New-Object System.Drawing.Size(400, 25)
$txtPath.Text = $PSScriptRoot
$txtPath.Font = $fontNormal
$form.Controls.Add($txtPath)

$btnBrowse = New-Object System.Windows.Forms.Button
$btnBrowse.Text = "Suchen..."
$btnBrowse.Location = New-Object System.Drawing.Point(430, 44)
$btnBrowse.Size = New-Object System.Drawing.Size(80, 27)
$btnBrowse.Font = $fontNormal
$form.Controls.Add($btnBrowse)

$lblCurrent = New-Object System.Windows.Forms.Label
$lblCurrent.Text = "Installierte Version: Wird geprüft..."
$lblCurrent.Location = New-Object System.Drawing.Point(20, 85)
$lblCurrent.Size = New-Object System.Drawing.Size(400, 20)
$lblCurrent.Font = $fontBold
$form.Controls.Add($lblCurrent)

$lblLatest = New-Object System.Windows.Forms.Label
$lblLatest.Text = "Neueste GitHub Version: Wird geprüft..."
$lblLatest.Location = New-Object System.Drawing.Point(20, 110)
$lblLatest.Size = New-Object System.Drawing.Size(400, 20)
$lblLatest.Font = $fontBold
$lblLatest.ForeColor = [System.Drawing.Color]::Blue
$form.Controls.Add($lblLatest)

$txtLog = New-Object System.Windows.Forms.TextBox
$txtLog.Location = New-Object System.Drawing.Point(20, 145)
$txtLog.Size = New-Object System.Drawing.Size(490, 150)
$txtLog.Multiline = $true
$txtLog.ReadOnly = $true
$txtLog.ScrollBars = "Vertical"
$txtLog.Font = New-Object System.Drawing.Font("Consolas", 8)
$form.Controls.Add($txtLog)

$btnUpdate = New-Object System.Windows.Forms.Button
$btnUpdate.Text = "Jetzt Reparieren / Updaten"
$btnUpdate.Location = New-Object System.Drawing.Point(175, 310)
$btnUpdate.Size = New-Object System.Drawing.Size(200, 40)
$btnUpdate.Font = $fontBold
$btnUpdate.BackColor = [System.Drawing.Color]::LightGreen
$btnUpdate.Enabled = $false
$form.Controls.Add($btnUpdate)

# --- Functions ---
function Log($msg) {
    $time = Get-Date -Format "HH:mm:ss"
    $txtLog.AppendText("[$time] $msg`r`n")
    $txtLog.SelectionStart = $txtLog.Text.Length
    $txtLog.ScrollToCaret()
    [System.Windows.Forms.Application]::DoEvents()
}

function Check-LocalVersion {
    $path = $txtPath.Text
    $vFile = Join-Path $path "version.json"
    if (Test-Path $vFile) {
        try {
            $content = Get-Content $vFile | ConvertFrom-Json
            if ($content -is [array]) {
                $Global:currentVersion = $content[0].version
            } else {
                $Global:currentVersion = $content.version
            }
            $lblCurrent.Text = "Installierte Version: " + $Global:currentVersion
            Log "Lokale Version $Global:currentVersion in $path gefunden."
        } catch {
            $lblCurrent.Text = "Installierte Version: Fehler beim Lesen!"
            Log "Konnte version.json nicht lesen."
        }
    } else {
        $lblCurrent.Text = "Installierte Version: Nicht gefunden (Neuinstallation?)"
        Log "Keine version.json im Pfad gefunden."
    }
}

function Check-RemoteVersion {
    Log "Prüfe GitHub auf neue Versionen..."
    try {
        $response = Invoke-RestMethod -Uri "https://api.github.com/repos/MasterBurns/EmberCore/releases/latest" -ErrorAction Stop
        $Global:latestVersion = $response.tag_name
        $lblLatest.Text = "Neueste GitHub Version: " + $Global:latestVersion
        Log "GitHub meldet Version: $Global:latestVersion"
        
        foreach ($asset in $response.assets) {
            if ($asset.name -like "EmberCore_Windows*.zip" -and $asset.name -notmatch "Setup") {
                $Global:downloadUrl = $asset.browser_download_url
                break
            }
        }
        
        if ($Global:downloadUrl) {
            $btnUpdate.Enabled = $true
            Log "Update-Paket verfügbar."
        } else {
            Log "WARNUNG: Kein ZIP-Archiv für Windows im Release gefunden!"
        }
    } catch {
        $lblLatest.Text = "Neueste GitHub Version: API Fehler!"
        $lblLatest.ForeColor = [System.Drawing.Color]::Red
        Log "Fehler bei GitHub Abfrage: $_"
    }
}

# --- Events ---
$btnBrowse.Add_Click({
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.SelectedPath = $txtPath.Text
    if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        $txtPath.Text = $dialog.SelectedPath
        Check-LocalVersion
    }
})

$txtPath.Add_TextChanged({
    Check-LocalVersion
})

$btnUpdate.Add_Click({
    $btnUpdate.Enabled = $false
    $path = $txtPath.Text
    
    Log "Starte Notfall-Update..."
    Log "Beende laufende EmberCore Prozesse und Dienste..."
    Stop-Service -Name "EmberCore" -ErrorAction SilentlyContinue | Out-Null
    Stop-Process -Name "EmberCore" -Force -ErrorAction SilentlyContinue | Out-Null
    Stop-Process -Name "EmberCoreService" -Force -ErrorAction SilentlyContinue | Out-Null
    Start-Sleep -Seconds 2
    
    $tempZip = Join-Path $env:TEMP "EmberCore_Emergency.zip"
    Log "Lade herunter: $($Global:latestVersion) (UI friert kurz ein...)"
    [System.Windows.Forms.Application]::DoEvents()
    
    try {
        Invoke-WebRequest -Uri $Global:downloadUrl -OutFile $tempZip -ErrorAction Stop
        Log "Download erfolgreich!"
    } catch {
        Log "FEHLER beim Download: $_"
        $btnUpdate.Enabled = $true
        return
    }
    
    Log "Entpacke Dateien nach $path ..."
    try {
        Expand-Archive -Path $tempZip -DestinationPath $path -Force -ErrorAction Stop
        Log "Entpacken erfolgreich! (Konfigurationen wurden beibehalten)"
    } catch {
        Log "FEHLER beim Entpacken (Expand-Archive): $_"
        Log "Versuche .NET Fallback..."
        try {
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            [System.IO.Compression.ZipFile]::ExtractToDirectory($tempZip, $path, $true)
            Log "Deep-Fallback Entpacken erfolgreich!"
        } catch {
            Log "FEHLER: Entpacken endgültig gescheitert. Bitte manuell entpacken."
            $btnUpdate.Enabled = $true
            return
        }
    }
    
    Remove-Item -Path $tempZip -Force -ErrorAction SilentlyContinue
    
    Log "Update abgeschlossen! Versuche Dienste zu starten..."
    Check-LocalVersion
    
    $svc = Get-Service -Name "EmberCore" -ErrorAction SilentlyContinue
    if ($svc) {
        Log "Starte Windows Dienst 'EmberCore'..."
        Start-Service -Name "EmberCore" -ErrorAction SilentlyContinue | Out-Null
    } else {
        $exePath = Join-Path $path "EmberCore.exe"
        if (Test-Path $exePath) {
            Log "Starte EmberCore.exe..."
            Start-Process -FilePath $exePath
        }
    }
    
    Log "VORGANG ERFOLGREICH BEENDET."
    [System.Windows.Forms.MessageBox]::Show("EmberCore wurde erfolgreich auf $($Global:latestVersion) repariert/aktualisiert!", "Erfolg", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Information)
    $btnUpdate.Enabled = $true
})

$form.Add_Shown({
    Check-LocalVersion
    Check-RemoteVersion
})

[System.Windows.Forms.Application]::EnableVisualStyles()
$form.ShowDialog() | Out-Null
