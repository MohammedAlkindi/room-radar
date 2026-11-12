param([string]$PortName = "COM11")

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Clear-Host
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "   ESP32-S3 WI-FI CSI RADAR - LIVE PHYSICAL PRESENCE MONITOR   " -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "Connecting to $PortName at 115200 baud..." -ForegroundColor Gray

$port = [System.IO.Ports.SerialPort]::new($PortName, 115200)
$port.DtrEnable = $true
$port.RtsEnable = $false

try {
    $port.Open()
} catch {
    Write-Host "[!] Could not open $PortName : $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Tip: Close the Serial Monitor in Arduino IDE so it doesn't lock the port!" -ForegroundColor Yellow
    exit 1
}

Write-Host "[+] Connected! Calibrating ambient baseline (please stand still)..." -ForegroundColor Green

$baselineSamples = @()
$baseline = 0.50
$sampleCount = 0
$lastStatus = ""

$pattern = [regex]"RADAR:([0-9.]+),RSSI:([0-9-]+),CSI_LEN:([0-9]+),PACKETS:([0-9]+)"

try {
    while ($true) {
        $line = $port.ReadLine().Trim()
        if ([string]::IsNullOrWhiteSpace($line)) { continue }

        $match = $pattern.Match($line)
        if (-not $match.Success) {
            if ($line -match "Wi-Fi Connected|IP:|ACTIVE") {
                Write-Host "    $line" -ForegroundColor Gray
            }
            continue
        }

        $metric = [float]$match.Groups[1].Value
        $rssi = [int]$match.Groups[2].Value
        $packets = [int]$match.Groups[4].Value

        # Calibration
        if ($baselineSamples.Count -lt 20) {
            $baselineSamples += $metric
            $pct = [int]($baselineSamples.Count * 5)
            Write-Host -NoNewline "`r[Calibrating ambient baseline: $pct%] Please stand still..."
            if ($baselineSamples.Count -eq 20) {
                $sum = 0.0
                foreach ($s in $baselineSamples) { $sum += $s }
                $baseline = $sum / 20.0
                Write-Host "`n[+] Baseline Established: $($baseline.ToString('F2')) (Monitoring active!)" -ForegroundColor Green
                Write-Host "-----------------------------------------------------------------" -ForegroundColor Gray
            }
            continue
        }

        $diff = $metric - $baseline
        $ratio = if ($baseline -gt 0.05) { $metric / $baseline } else { $metric / 0.5 }

        # Classify state
        $statusTag = ""
        $statusText = ""
        $statusColor = "Green"

        if ($ratio -gt 1.35 -or $diff -gt 0.30) {
            $statusTag = "[ALERT]"
            $statusText = "MOTION DETECTED (Walking / moving in room)"
            $statusColor = "Red"
        } elseif ($ratio -gt 1.12 -or $diff -gt 0.12) {
            $statusTag = "[SENSE]"
            $statusText = "PRESENCE (Sitting / subtle movement / breathing)"
            $statusColor = "Yellow"
        } else {
            $statusTag = "[QUIET]"
            $statusText = "STILL (Room empty or quiet)"
            $statusColor = "Green"
        }

        $sampleCount++

        # Draw ASCII disturbance bar
        $barLength = [Math]::Min(25, [Math]::Max(1, [int]($ratio * 10)))
        $bar = ("#" * $barLength) + ("-" * (25 - $barLength))
        $ts = (Get-Date).ToString("HH:mm:ss")

        if ($statusText -ne $lastStatus -or ($sampleCount % 8 -eq 0)) {
            $outLine = "[$ts] " + $statusTag + " " + $statusText.PadRight(42) + " | Disturbance: [$bar] ($($metric.ToString('F2')))"
            Write-Host $outLine -ForegroundColor $statusColor
            $lastStatus = $statusText
        }
    }
} finally {
    $port.Close()
    Write-Host "`n[+] Port closed." -ForegroundColor Gray
}
