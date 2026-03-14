# Run eland_sweep_v3.py for each Jamaica parish
# Output saved to parish_data/
# Run from project root: .\scripts\run_parish_sweeps.ps1

$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $projectRoot

$parishes = @(
    "Hanover",
    "St. Elizabeth",
    "St. James",
    "Trelawny",
    "Westmoreland",
    "Clarendon",
    "Manchester",
    "St. Ann",
    "St. Catherine",
    "St. Mary",
    "Kingston",
    "Portland",
    "St. Andrew",
    "St. Thomas"
)

$outDir = "parish_data"
$total = $parishes.Count
$i = 0

foreach ($parish in $parishes) {
    $i++
    $safeName = $parish -replace " ", "_" -replace "\.", "_"
    $outFile = "$outDir\parcels_$safeName.geojson"
    
    Write-Host "`n[$i/$total] Sweeping $parish -> $outFile" -ForegroundColor Cyan
    python "$PSScriptRoot\eland_sweep_v3.py" --parish $parish -o $outFile
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ERROR: Failed for $parish" -ForegroundColor Red
    }
}

Write-Host "`nDone. Files in $outDir\" -ForegroundColor Green
