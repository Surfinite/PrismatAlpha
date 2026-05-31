# Zen Mode patch builder for Prismata.swf
# Requires JPEXS FFDec (https://github.com/jindrapetrik/jpexs-decompiler)
# Targets Steam install of Prismata.

$ErrorActionPreference = "Stop"

$ffdec       = "C:\Program Files (x86)\FFDec\ffdec.bat"
$prismataDir = "C:\Program Files (x86)\Steam\steamapps\common\Prismata"
$swfOrig     = Join-Path $prismataDir "Prismata.swf.ORIG"
$swfTarget   = Join-Path $prismataDir "Prismata.swf"
$swfBackup   = Join-Path $prismataDir "Prismata.swf.PRE_ZEN"
$patchDir    = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Test-Path $ffdec))     { throw "FFDec not found at: $ffdec" }
if (-not (Test-Path $swfOrig))   { throw "Source SWF not found: $swfOrig" }

# Stage one-time backup of the current Prismata.swf
if (-not (Test-Path $swfBackup)) {
    Copy-Item $swfTarget $swfBackup -Force
    Write-Host "Backed up current Prismata.swf -> Prismata.swf.PRE_ZEN"
}

$gamePlayerAS = Join-Path $patchDir "GamePlayer.as"
$gameStubAS   = Join-Path $patchDir "GameStub.as"
$arenaPageAS  = Join-Path $patchDir "UIArenaPage.as"

foreach ($f in @($gamePlayerAS, $gameStubAS, $arenaPageAS)) {
    if (-not (Test-Path $f)) { throw "Missing patch source: $f" }
}

Write-Host "Applying Zen Mode patches to Prismata.swf..."
Write-Host "  Source : $swfOrig"
Write-Host "  Output : $swfTarget"

& $ffdec -replace `
    $swfOrig $swfTarget `
    "client.GamePlayer" $gamePlayerAS `
    "client.GameStub"   $gameStubAS `
    "starlingUI.lobby.lobbyPages.UIArenaPage" $arenaPageAS

if ($LASTEXITCODE -ne 0) { throw "FFDec returned exit code $LASTEXITCODE" }

Write-Host ""
Write-Host "Done. Patched Prismata.swf written."
Write-Host "Roll back at any time with:"
Write-Host "  Copy-Item '$swfBackup' '$swfTarget' -Force"
