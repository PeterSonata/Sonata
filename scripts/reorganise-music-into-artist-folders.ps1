# reorganise-music-into-artist-folders.ps1
# ============================================================
# Walks Y:\ and moves album folders into Artist subfolders.
#
# Expects folders named "Artist - Album (Year)" at the root
# of Y:\. Splits on the first " - " to derive the artist name,
# creates the artist subfolder if needed, and moves the album
# folder into it.
#
# Special cases:
#   - "Various Artists - ..." moves into Y:\Compilations\
#   - Folders already inside a subfolder (not direct children
#     of Y:\) are skipped entirely.
#   - Folders whose names contain no " - " are skipped and
#     logged for manual review.
#
# Safe by design:
#   - Only moves folders, never deletes anything.
#   - Logs every action to Desktop.
#   - Dry-run mode available: set $DryRun = $true below.
# ============================================================

$Root    = 'Y:\'
$LogFile = "$env:USERPROFILE\OneDrive\Apps\Desktop\reorganise-music-into-artist-folders.log"
$DryRun  = $false   # Set to $true to preview without moving anything

$RootResolved = (Resolve-Path $Root).Path.TrimEnd('\')

"=== Music folder reorganisation: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" |
    Out-File -FilePath $LogFile -Encoding UTF8
if ($DryRun) {
    "DRY RUN - no files will be moved" | Add-Content -Path $LogFile -Encoding UTF8
}
"" | Add-Content -Path $LogFile -Encoding UTF8

Write-Host "Scanning $Root for album folders to reorganise..." -ForegroundColor Cyan

# Only process direct children of Y:\ that are folders.
$albumFolders = Get-ChildItem -Path $Root -Directory |
                Where-Object { $_.Parent.FullName.TrimEnd('\') -eq $RootResolved }

$total  = $albumFolders.Count
$moved  = 0
$skipped = 0
$errors = 0

Write-Host "Found $total direct subfolders to check." -ForegroundColor Cyan

foreach ($folder in $albumFolders) {
    $name = $folder.Name

    # Skip if no " - " separator present.
    if ($name -notlike '* - *') {
        "SKIPPED (no separator): $name" | Add-Content -Path $LogFile -Encoding UTF8
        $skipped++
        continue
    }

    # Split on first " - " only.
    $separatorIndex = $name.IndexOf(' - ')
    $artist = $name.Substring(0, $separatorIndex).Trim()

    # Various Artists goes to Compilations.
    if ($artist -eq 'Various Artists') {
        $targetParent = Join-Path $Root 'Compilations'
    } else {
        $targetParent = Join-Path $Root $artist
    }

    $destination = Join-Path $targetParent $name

    # Skip if destination already exists (safety check).
    if (Test-Path -Path $destination) {
        "SKIPPED (destination exists): $name -> $destination" |
            Add-Content -Path $LogFile -Encoding UTF8
        $skipped++
        continue
    }

    if ($DryRun) {
        "DRY RUN: would move [$name] -> [$destination]" |
            Add-Content -Path $LogFile -Encoding UTF8
        $moved++
        continue
    }

    try {
        if (-not (Test-Path -Path $targetParent)) {
            New-Item -ItemType Directory -Path $targetParent | Out-Null
        }
        Move-Item -Path $folder.FullName -Destination $destination -ErrorAction Stop
        "MOVED: $name -> $destination" | Add-Content -Path $LogFile -Encoding UTF8
        $moved++
    }
    catch {
        "ERROR: $name - $($_.Exception.Message)" | Add-Content -Path $LogFile -Encoding UTF8
        $errors++
    }
}

$summary = @"

=== Summary ===
Total folders checked: $total
Moved:                 $moved
Skipped:               $skipped
Errors:                $errors
Log:                   $LogFile
"@

$summary | Add-Content -Path $LogFile -Encoding UTF8
Write-Host $summary -ForegroundColor Green