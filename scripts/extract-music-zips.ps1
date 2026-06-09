# extract-music-zips.ps1
# ============================================================
# Walks Y:\ and extracts every .zip file in place, then deletes
# the original zip once extraction has succeeded.
#
# Each zip is extracted to a sibling folder named after the zip
# (without the .zip extension). So:
#   Y:\downloads\Beatles - Revolver.zip
#     becomes
#   Y:\downloads\Beatles - Revolver\
#
# Safety order:
#   1. Pick a target folder. If it already exists, skip the zip
#      entirely. Never overwrites existing work.
#   2. Extract with Expand-Archive.
#   3. Verify the target folder has at least one file in it.
#   4. Only then delete the zip.
#
# A failed extraction leaves the zip in place. The partial
# target folder is removed so a re-run can try again cleanly.
#
# Logs every action to extract-music-zips.log on Desktop.
#
# Usage:
#   Open PowerShell, cd to wherever this file is, run:
#     Unblock-File .\extract-music-zips.ps1
#     .\extract-music-zips.ps1
#
#   To target a different drive, edit $Root below.
# ============================================================

$Root    = 'Y:\'
$LogFile = "$env:USERPROFILE\OneDrive\Apps\Desktop\extract-music-zips.log"

# Header
"=== Zip extraction run: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" |
    Out-File -FilePath $LogFile -Encoding UTF8
"Root: $Root" | Add-Content -Path $LogFile -Encoding UTF8
"" | Add-Content -Path $LogFile -Encoding UTF8

Write-Host "Scanning $Root for .zip files..." -ForegroundColor Cyan

$zips = Get-ChildItem -LiteralPath $Root -Recurse -File -Force -Filter '*.zip' -ErrorAction SilentlyContinue

$total      = $zips.Count
$extracted  = 0
$skipped    = 0
$failed     = 0
$counter    = 0

Write-Host "Found $total zip file(s)." -ForegroundColor Cyan

if ($total -eq 0) {
    "Nothing to do. No zip files found." | Add-Content -Path $LogFile -Encoding UTF8
    Write-Host "Nothing to do." -ForegroundColor Green
    return
}

foreach ($zip in $zips) {
    $counter++
    Write-Host "[$counter/$total] $($zip.FullName)" -ForegroundColor Gray

    $parent     = Split-Path -Parent $zip.FullName
    $baseName   = [System.IO.Path]::GetFileNameWithoutExtension($zip.Name)
    $targetDir  = Join-Path $parent $baseName

    if (Test-Path -LiteralPath $targetDir) {
        "SKIPPED:  $($zip.FullName) (target folder already exists: $targetDir)" |
            Add-Content -Path $LogFile -Encoding UTF8
        Write-Host "    skipped: target folder already exists" -ForegroundColor Yellow
        $skipped++
        continue
    }

    try {
        # Extract
        Expand-Archive -LiteralPath $zip.FullName -DestinationPath $targetDir -Force -ErrorAction Stop

        # Verify: target folder must exist and contain at least one file at any depth
        $hasContent = Get-ChildItem -LiteralPath $targetDir -Recurse -File -Force -ErrorAction SilentlyContinue |
                      Select-Object -First 1
        if (-not $hasContent) {
            throw "extraction produced no files"
        }

        # Success. Delete the zip.
        Remove-Item -LiteralPath $zip.FullName -Force -ErrorAction Stop

        "EXTRACTED: $($zip.FullName) -> $targetDir (zip deleted)" |
            Add-Content -Path $LogFile -Encoding UTF8
        Write-Host "    extracted, zip deleted" -ForegroundColor Green
        $extracted++
    }
    catch {
        "FAILED:   $($zip.FullName) - $($_.Exception.Message)" |
            Add-Content -Path $LogFile -Encoding UTF8
        Write-Host "    FAILED: $($_.Exception.Message)" -ForegroundColor Red

        # Clean up any partial target so a re-run can try again
        if (Test-Path -LiteralPath $targetDir) {
            try {
                Remove-Item -LiteralPath $targetDir -Recurse -Force -ErrorAction Stop
                "          partial target folder removed: $targetDir" |
                    Add-Content -Path $LogFile -Encoding UTF8
            }
            catch {
                "          could not remove partial target: $targetDir - $($_.Exception.Message)" |
                    Add-Content -Path $LogFile -Encoding UTF8
            }
        }
        $failed++
    }
}

$summary = @"

=== Summary ===
Zip files found:     $total
Extracted + deleted: $extracted
Skipped (existed):   $skipped
Failed:              $failed
Log:                 $LogFile
"@

$summary | Add-Content -Path $LogFile -Encoding UTF8
Write-Host $summary -ForegroundColor Green
