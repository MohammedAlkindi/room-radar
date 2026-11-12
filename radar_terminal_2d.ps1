param([string]$PortName = "COM11")

Clear-Host
[Console]::CursorVisible = $false

Write-Host "==========================================================================" -ForegroundColor Cyan
Write-Host "         ESP32-S3 2D TACTICAL WI-FI RADAR - POWERSHELL CONSOLE           " -ForegroundColor Cyan
Write-Host "==========================================================================" -ForegroundColor Cyan
Write-Host "Connecting to $PortName at 115200 baud..." -ForegroundColor Gray

$port = [System.IO.Ports.SerialPort]::new($PortName, 115200)
$port.DtrEnable = $true
$port.RtsEnable = $false

try {
    $port.Open()
} catch {
    Write-Host "`n[!] Could not open $PortName : $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Make sure Arduino IDE Serial Monitor or other apps are closed!`n" -ForegroundColor Yellow
    [Console]::CursorVisible = $true
    exit 1
}

Write-Host "[+] Connected! Calibrating ambient baseline (please stand still)..." -ForegroundColor Green

$baselineSamples = @()
$baseline = 1.20
$pattern = [regex]"RADAR:([0-9.]+),RSSI:([0-9-]+),CSI_LEN:([0-9]+),PACKETS:([0-9]+)"

while ($baselineSamples.Count -lt 25) {
    try {
        $line = $port.ReadLine().Trim()
        $m = $pattern.Match($line)
        if ($m.Success) {
            $baselineSamples += [float]$m.Groups[1].Value
            $pct = [int]($baselineSamples.Count * 4)
            Write-Host -NoNewline "`r[Calibrating Baseline: $pct%] Please stand still..."
        }
    } catch {}
}

$sum = 0.0
foreach ($s in $baselineSamples) { $sum += $s }
$baseline = $sum / $baselineSamples.Count
Write-Host "`n[+] Baseline Established: $($baseline.ToString('F2'))! Launching 2D Console Map..." -ForegroundColor Green
Start-Sleep -Milliseconds 800

Clear-Host

$gridW = 68
$gridH = 15

$personX = 50
$personY = 11

function Render-2DMap {
    param(
        [float]$Metric,
        [int]$Rssi,
        [int]$Packets,
        [string]$Status
    )

    [Console]::SetCursorPosition(0, 0)

    # Move target if in motion
    if ($Status -eq "MOTION") {
        $stepX = (Get-Random -Minimum -3 -Maximum 4)
        $stepY = (Get-Random -Minimum -2 -Maximum 3)
        $global:personX = [Math]::Max(6, [Math]::Min(60, $global:personX + $stepX))
        $global:personY = [Math]::Max(2, [Math]::Min(13, $global:personY + $stepY))
    } elseif ($Status -eq "PRESENCE") {
        $global:personX = 50
        $global:personY = 11
    }

    $sb = [System.Text.StringBuilder]::new()
    [void]$sb.AppendLine("+------------------------------------------------------------------+")
    [void]$sb.AppendLine("|                 ESP32-S3 2D WI-FI CSI RADAR CONSOLE              |")
    [void]$sb.AppendLine("+------------------------------------------------------------------+")

    for ($y = 0; $y -lt $gridH; $y++) {
        $rowChars = [char[]](" " * $gridW)
        $rowChars[0] = '|'
        $rowChars[$gridW - 1] = '|'

        # 1. Bed (Top Left: x 3..18, y 1..4)
        if ($y -ge 1 -and $y -le 4) {
            for ($x = 3; $x -le 18; $x++) {
                if ($y -eq 1 -or $y -eq 4 -or $x -eq 3 -or $x -eq 18) {
                    $rowChars[$x] = '#'
                } else {
                    $rowChars[$x] = '.'
                }
            }
            if ($y -eq 2) {
                $bedTxt = "[BED:ZONE]"
                for ($k = 0; $k -lt $bedTxt.Length; $k++) { $rowChars[5 + $k] = $bedTxt[$k] }
            }
        }

        # 2. Wardrobe (Top Right: x 46..62, y 1..4)
        if ($y -ge 1 -and $y -le 4) {
            for ($x = 46; $x -le 62; $x++) {
                if ($y -eq 1 -or $y -eq 4 -or $x -eq 46 -or $x -eq 62) {
                    $rowChars[$x] = '#'
                } else {
                    $rowChars[$x] = '.'
                }
            }
            if ($y -eq 2) {
                $closetTxt = "[WARDROBE]"
                for ($k = 0; $k -lt $closetTxt.Length; $k++) { $rowChars[49 + $k] = $closetTxt[$k] }
            }
        }

        # 3. Work Desk & ESP32 (Bottom Right: x 44..62, y 9..13)
        if ($y -ge 9 -and $y -le 13) {
            for ($x = 44; $x -le 62; $x++) {
                if ($y -eq 9 -or $y -eq 13 -or $x -eq 44 -or $x -eq 62) {
                    $rowChars[$x] = '#'
                } else {
                    $rowChars[$x] = '.'
                }
            }
            if ($y -eq 10) {
                $dTxt = "[DESK:WORK]"
                for ($k = 0; $k -lt $dTxt.Length; $k++) { $rowChars[48 + $k] = $dTxt[$k] }
            }
            if ($y -eq 12) {
                $rxTxt = "(ESP32:RX)"
                for ($k = 0; $k -lt $rxTxt.Length; $k++) { $rowChars[48 + $k] = $rxTxt[$k] }
            }
        }

        # 4. Bookshelf (Bottom Left: x 3..18, y 9..13)
        if ($y -ge 9 -and $y -le 13) {
            for ($x = 3; $x -le 18; $x++) {
                if ($y -eq 9 -or $y -eq 13 -or $x -eq 3 -or $x -eq 18) {
                    $rowChars[$x] = '#'
                } else {
                    $rowChars[$x] = '.'
                }
            }
            if ($y -eq 11) {
                $shTxt = "[BOOKSHELF]"
                for ($k = 0; $k -lt $shTxt.Length; $k++) { $rowChars[5 + $k] = $shTxt[$k] }
            }
        }

        # 5. Phone Node (x 10..17, y 6)
        if ($y -eq 6) {
            $phTxt = "T(PHONE)"
            for ($k = 0; $k -lt $phTxt.Length; $k++) { $rowChars[10 + $k] = $phTxt[$k] }
        }

        # 6. Doorway (x 28..37, y 14)
        if ($y -eq 14) {
            $drTxt = "[DOOR:ENTRY]"
            for ($k = 0; $k -lt $drTxt.Length; $k++) { $rowChars[28 + $k] = $drTxt[$k] }
        }

        # 7. Radio Multipath Ray (Phone x=18..44, y line)
        $slope = (11 - 6) / (50 - 10)
        $expY = [int]([Math]::Round(6 + (30 - 10) * $slope))
        if ($y -eq $expY) {
            for ($rx = 19; $rx -lt 44; $rx++) {
                if ($rowChars[$rx] -eq ' ') {
                    if ($Status -eq "MOTION") { $rowChars[$rx] = '~' }
                    elseif ($Status -eq "PRESENCE") { $rowChars[$rx] = '-' }
                    else { $rowChars[$rx] = '.' }
                }
            }
        }

        # 8. Human Target Marker
        if ($y -eq $global:personY -and $Status -ne "STILL") {
            $px = $global:personX
            if ($px -ge 1 -and $px -lt ($gridW - 1)) {
                if ($Status -eq "MOTION") {
                    $rowChars[$px] = 'W'
                    if ($px - 1 -ge 1) { $rowChars[$px - 1] = '*' }
                    if ($px + 1 -lt ($gridW - 1)) { $rowChars[$px + 1] = '*' }
                } else {
                    $rowChars[$px] = 'P'
                }
            }
        }

        [void]$sb.AppendLine([string]::new($rowChars))
    }

    [void]$sb.AppendLine("+------------------------------------------------------------------+")

    # Disturb bar
    $barLen = [Math]::Min(26, [Math]::Max(1, [int]($Metric * 6.5)))
    $bar = ("=" * $barLen) + ("-" * (26 - $barLen))

    $statusMsg = ""
    if ($Status -eq "MOTION") {
        $statusMsg = "[ALERT] MOTION DETECTED (Walking / Physical Movement)"
    } elseif ($Status -eq "PRESENCE") {
        $statusMsg = "[SENSE] HUMAN PRESENCE (Breathing / Subtle Motion)"
    } else {
        $statusMsg = "[QUIET] ROOM EMPTY / STILL"
    }

    [void]$sb.AppendLine("  STATUS: $statusMsg")
    [void]$sb.AppendLine("  RF DISTURBANCE: [$bar] $($Metric.ToString('F2')) (Baseline: $($baseline.ToString('F2')))")
    [void]$sb.AppendLine("  WI-FI RSSI: $Rssi dBm  |  CSI PACKETS: $Packets  |  TARGET: (X: $global:personX, Y: $global:personY)")
    [void]$sb.AppendLine("  Press [Ctrl + C] to exit | Run 'launch_radar_map.bat' for HD Web")

    Write-Host -NoNewline $sb.ToString()
}

try {
    while ($true) {
        $line = $port.ReadLine().Trim()
        if ([string]::IsNullOrWhiteSpace($line)) { continue }

        $m = $pattern.Match($line)
        if (-not $m.Success) { continue }

        $metric = [float]$m.Groups[1].Value
        $rssi = [int]$m.Groups[2].Value
        $pkts = [int]$m.Groups[4].Value

        $status = "STILL"
        if ($metric -ge 1.65) { $status = "MOTION" }
        elseif ($metric -ge 1.28) { $status = "PRESENCE" }
        else { $status = "STILL" }

        Render-2DMap -Metric $metric -Rssi $rssi -Packets $pkts -Status $status
    }
} finally {
    if ($port.IsOpen) { $port.Close() }
    [Console]::CursorVisible = $true
}
