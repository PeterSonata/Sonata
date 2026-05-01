# delete-music-empty-folders.ps1
# ============================================================
# Walks Y:\ and deletes any folder that contains no music
# files at any depth.
#
# A folder is considered empty (and deleted) if nothing under
# it (recursively, at any depth) has a recognised audio file
# extension. So a folder with only cover.jpg, readme.txt and
# extraction.log gets removed. A folder with a single MP3
# anywhere inside it is kept.
#
# Process:
#   1. Walk every folder, deepest first.
#   2. For each folder, check if any descendant file has a
#      music extension. If not, delete the folder and all its
#      contents.
#   3. Log everything to deleted-music-empty-folders.log on
#      Desktop.
#
# Safe by design:
#   - Only deletes folders that contain zero music files.
#   - Does not touch the Y:\ root itself.
#   - Skips protected top-level folders (Compilations,
#     _Untagged) so the reorganise script's targets survive.
#   - Logs every deletion and every protected folder for audit.
#
# Usage:
#   Open PowerShell, cd to wherever this file is, run:
#     .\delete-music-empty-folders.ps1
#
#   To target a different drive, edit $Root below.
# ============================================================

$Root    = 'Y:\'
$LogFile = "$env:USERPROFILE\OneDrive\Apps\Desktop\deleted-music-empty-folders.log"

# Recognised music file extensions. Add to this list if you
# have anything exotic (e.g. .dsf, .dff for DSD).
$MusicExt = @(
    '.mp3', '.flac', '.m4a', '.aac', '.ogg', '.oga',
    '.wav', '.opus', '.ape', '.alac', '.aiff', '.aif'
)

# Top-level folders we never delete, even if they happen to be
# empty during the run (these are the reorganise script's targets).
$Protected = @('Compilations', '_Untagged')

# Resolve the root path once so we can compare against it cleanly.
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

# Header
"=== Music-empty folder cleanup: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" |
    Out-File -FilePath $LogFile -Encoding UTF8
"Music extensions treated as real: $($MusicExt -join ', ')" |
    Add-Content -Path $LogFile -Encoding UTF8
"" | Add-Content -Path $LogFile -Encoding UTF8

Write-Host "Scanning $Root for folders with no music files..." -ForegroundColor Cyan

# Get all folders, sorted by path depth (descending) so we process
# the deepest folders first. This means if Y:\A\B has no music and
# Y:\A only contains B, we delete B first, then A becomes empty
# and gets deleted on the same pass.
$allFolders = Get-ChildItem -LiteralPath $Root -Directory -Recurse -Force -ErrorAction SilentlyContinue |
              Sort-Object { ($_.FullName -split '\\').Count } -Descending

$total     = $allFolders.Count
$deleted   = 0
$protected = 0
$kept      = 0
$errors    = 0
$counter   = 0

Write-Host "Found $total folders to check." -ForegroundColor Cyan

foreach ($folder in $allFolders) {
    $counter++
    if ($counter % 500 -eq 0) {
        Write-Host "  ...checked $counter / $total (deleted: $deleted, kept: $kept)" -ForegroundColor DarkGray
    }

    # Folder may have been deleted already as part of a parent's
    # cleanup. Skip if it's gone.
    if (-not (Test-Path -LiteralPath $folder.FullName)) {
        continue
    }

    # Skip protected top-level folders.
    $isTopLevel = ($folder.Parent.FullName.TrimEnd('\') -eq $RootResolved)
    if ($isTopLevel -and ($Protected -contains $folder.Name)) {
        "PROTECTED: $($folder.FullName)" | Add-Content -Path $LogFile -Encoding UTF8
        $protected++
        continue
    }

    # Skip if any descendant is a music file.
    if (Test-FolderHasMusic -Path $folder.FullName) {
        $kept++
        continue
    }

    # No music anywhere beneath. Delete the folder and everything in it.
    try {
        # Count what's about to go for the log.
        $contentCount = (Get-ChildItem -LiteralPath $folder.FullName -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object).Count
        Remove-Item -LiteralPath $folder.FullName -Recurse -Force -ErrorAction Stop
        "DELETED:  $($folder.FullName)  (contained $contentCount non-music files)" |
            Add-Content -Path $LogFile -Encoding UTF8
        $deleted++
    }
    catch {
        "ERROR:    $($folder.FullName) - $($_.Exception.Message)" |
            Add-Content -Path $LogFile -Encoding UTF8
        $errors++
    }
}

# Summary
$summary = @"

=== Summary ===
Total folders scanned: $total
Deleted:               $deleted
Kept (had music):      $kept
Protected (skipped):   $protected
Errors:                $errors
Log:                   $LogFile
"@

$summary | Add-Content -Path $LogFile -Encoding UTF8
Write-Host $summary -ForegroundColor Green
