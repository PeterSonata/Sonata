# report-music-empty-folders.ps1
# ============================================================
# Walks Y:\ and produces a report of every folder that contains
# no music files at any depth. These are "ghost albums" left
# behind from the megaboon to NAS transfer.
#
# Read-only. Does not delete or move anything.
#
# Companion to delete-music-empty-folders.ps1. Run this first
# to review the list. If happy, run the delete script.
#
# A folder is "empty" if no file under it (recursively, at any
# depth) has a recognised audio file extension. A folder with
# only cover.jpg, readme.txt and extraction.log gets flagged.
# A folder with a single MP3 anywhere inside is treated as
# real and ignored.
#
# The report shows only the TOPMOST empty folders. If an entire
# Artist folder is empty because all of its albums are ghosts,
# you see "Y:\Artist" once, not every nested subfolder under it.
# This matches what the delete script would actually remove.
#
# Output:
#   - Console summary plus first 50 ghosts inline
#   - Full list written to ghost-album-report.log on Desktop
#
# Usage:
#   Open PowerShell, cd to wherever this file is, run:
#     .\report-music-empty-folders.ps1
#
#   To target a different drive, edit $Root below.
# ============================================================

$Root    = 'Y:\'
$LogFile = "$env:USERPROFILE\OneDrive\Apps\Desktop\ghost-album-report.log"

# Recognised music file extensions. Must match the delete
# script so the two stay in lockstep.
$MusicExt = @(
    '.mp3', '.flac', '.m4a', '.aac', '.ogg', '.oga',
    '.wav', '.opus', '.ape', '.alac', '.aiff', '.aif'
)

# Top-level folders to exclude from the report (these are the
# reorganise script's targets and can be legitimately empty
# during a working state).
$Protected = @('Compilations', '_Untagged')

$RootResolved = (Resolve-Path $Root).Path.TrimEnd('\')

function Test-FolderHasMusic {
    param([string]$Path)
    # Walk every file beneath $Path, return true on first music hit.
    # -Force picks up hidden files. SilentlyContinue handles long paths.
    $hit = Get-ChildItem -LiteralPath $Path -Recurse -File -Force -ErrorAction SilentlyContinue |
           Where-Object { $MusicExt -contains $_.Extension.ToLower() } |
           Select-Object -First 1
    return [bool]$hit
}

Write-Host "Scanning $Root for ghost folders (no music files at any depth)..." -ForegroundColor Cyan

$allFolders = Get-ChildItem -LiteralPath $Root -Directory -Recurse -Force -ErrorAction SilentlyContinue
$total      = $allFolders.Count

Write-Host "Found $total folders to check." -ForegroundColor Cyan

# Pass 1: classify every folder as has-music or empty.
# Store in a dictionary keyed by full path for fast parent lookups
# in pass 2. PowerShell hashtables are case-insensitive for string
# keys, which matches Windows path semantics.
$emptyMap = @{}
$counter  = 0

foreach ($folder in $allFolders) {
    $counter++
    if ($counter % 500 -eq 0) {
        Write-Host "  ...checked $counter / $total" -ForegroundColor DarkGray
    }
    $emptyMap[$folder.FullName] = -not (Test-FolderHasMusic -Path $folder.FullName)
}

# Pass 2: reduce to the topmost empty folders. A folder is
# topmost-empty if it is itself empty AND its parent either is
# the root or contains music somewhere outside this subtree.
# This is the equivalent of what the delete script removes in a
# single deepest-first sweep.
$topmost = New-Object System.Collections.Generic.List[string]

foreach ($path in $emptyMap.Keys) {
    if (-not $emptyMap[$path]) { continue }

    $parent         = Split-Path -Parent $path
    $parentResolved = $parent.TrimEnd('\')

    if ($parentResolved -eq $RootResolved) {
        # Top-level empty folder. Skip if protected.
        $name = Split-Path -Leaf $path
        if ($Protected -contains $name) { continue }
        $topmost.Add($path)
    }
    elseif ($emptyMap.ContainsKey($parent) -and -not $emptyMap[$parent]) {
        # Parent has music elsewhere, so this folder is an outermost ghost.
        $topmost.Add($path)
    }
    # If parent is also empty, this folder is a nested ghost and
    # will be covered when its topmost ancestor is reported.
}

$topmostSorted = $topmost | Sort-Object

# Write log
"=== Ghost folder report: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" |
    Out-File -FilePath $LogFile -Encoding UTF8
"Root scanned: $Root" | Add-Content -Path $LogFile -Encoding UTF8
"Music extensions counted as real: $($MusicExt -join ', ')" |
    Add-Content -Path $LogFile -Encoding UTF8
"Protected top-level folders (excluded from report): $($Protected -join ', ')" |
    Add-Content -Path $LogFile -Encoding UTF8
"" | Add-Content -Path $LogFile -Encoding UTF8
"Topmost ghost folders ($($topmostSorted.Count)):" |
    Add-Content -Path $LogFile -Encoding UTF8
"" | Add-Content -Path $LogFile -Encoding UTF8

foreach ($p in $topmostSorted) {
    $p | Add-Content -Path $LogFile -Encoding UTF8
}

$totalEmpty = ($emptyMap.Values | Where-Object { $_ }).Count

$summary = @"

=== Summary ===
Total folders scanned:        $total
Empty (no music anywhere):    $totalEmpty
Topmost ghost folders listed: $($topmostSorted.Count)
Log file:                     $LogFile
"@

$summary | Add-Content -Path $LogFile -Encoding UTF8
Write-Host $summary -ForegroundColor Green

# Echo first 50 to console for a quick eyeball check.
if ($topmostSorted.Count -gt 0) {
    Write-Host ""
    $preview = [Math]::Min(50, $topmostSorted.Count)
    Write-Host "First $preview ghost folders:" -ForegroundColor Yellow
    $topmostSorted | Select-Object -First 50 | ForEach-Object { Write-Host "  $_" }
    if ($topmostSorted.Count -gt 50) {
        $remaining = $topmostSorted.Count - 50
        Write-Host "  ... ($remaining more in log file)" -ForegroundColor DarkGray
    }
}
