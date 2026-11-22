<#
.SYNOPSIS
  Builds KANAT's Windows installers: KANAT-Setup-<version>-threads.exe and
  KANAT-Setup-<version>-processes.exe, in WebApp\deploy\windows\build\output.

.DESCRIPTION
  Run it on the Windows PC that has the repository, the development
  environments (WebApp\backend\.venv is not needed, but ImageRecognitionService\.venv
  is: it is the tested PyTorch build that ships) and Inno Setup 6. It stages
  everything the PC needs into build\stage:

    app\        the KANAT app (Electron, packaged by electron-builder)
    backend\    its own Python 3.12, the backend's packages from uv.lock, the
                backend's code, and the GTK3 runtime WeasyPrint draws PDFs with
    detection\  its own Python 3.14, the tested PyTorch (CUDA) environment,
                the Detection Service's code, the model and the Target template
    video\      MediaMTX and its production config
    scripts\    what installs, runs and removes the background tasks

  then compiles kanat.iss once per run mode. The development scripts, tests,
  tools, docs, other models and every database are left out: the installer
  carries only what runs on the range, and its database starts empty.

.PARAMETER Variant
  threads, processes, or both (default).

.PARAMETER Spanning
  Split the installer into Setup.exe and .bin files. Needed only if a single
  file would pass Inno Setup's 2 GB limit (the build says so).
#>
param(
    [ValidateSet("threads", "processes", "both")][string]$Variant = "both",
    [switch]$Spanning
)
$ErrorActionPreference = "Stop"

$Here = $PSScriptRoot
$Repo = (Resolve-Path (Join-Path $Here "..\..\..")).Path
$Build = Join-Path $Here "build"
$Stage = Join-Path $Build "stage"
$OutDir = Join-Path $Build "output"
$Frontend = Join-Path $Repo "WebApp\frontend"
$BackendSrc = Join-Path $Repo "WebApp\backend"
$DetectionSrc = Join-Path $Repo "ImageRecognitionService"

# Pinned: the MediaMTX release the installer carries (VideoService\mediamtx.exe
# is git-ignored, so each build checks it is this one). Changing the version
# means changing its hash.
$MediaMtxVersion = "v1.21.3"
$MediaMtxSha256 = "13a0bfaa852d83ce976c94342a1af130941bd79fac2c1e95a2175879c92304c0"
$ModelFolder = "kanat_yolo26x_v1"

function Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Ok($text) { Write-Host "    $text" -ForegroundColor Green }
function Note($text) { Write-Host "    $text" -ForegroundColor Yellow }
function Fail($text) { Write-Host ""; Write-Host "FAILED: $text" -ForegroundColor Red; exit 1 }

# A native program's exit code, failing the build on anything but 0
function Run($file, [string[]]$arguments, $cwd = $null) {
    if ($cwd) { Push-Location $cwd }
    try { & $file @arguments } finally { if ($cwd) { Pop-Location } }
    if ($LASTEXITCODE -ne 0) { Fail "$file $($arguments -join ' ') exited with $LASTEXITCODE" }
}

# robocopy's codes below 8 are success
function Copy-Tree($from, $to, [string[]]$excludeDirs = @(), [string[]]$excludeFiles = @()) {
    $arguments = @($from, $to, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/R:2", "/W:1")
    if ($excludeDirs) { $arguments += "/XD"; $arguments += $excludeDirs }
    if ($excludeFiles) { $arguments += "/XF"; $arguments += $excludeFiles }
    & robocopy.exe @arguments | Out-Null
    if ($LASTEXITCODE -ge 8) { Fail "copying $from to $to (robocopy exit $LASTEXITCODE)" }
    $global:LASTEXITCODE = 0
}

# --- 0. Checks ---------------------------------------------------------------

Step "Checking what the build needs"
foreach ($tool in @("node", "npm", "uv", "robocopy")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { Fail "$tool is not on the PATH (install it, then run this again)" }
}
$iscc = @($env:KANAT_ISCC, (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
          (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"), (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")) |
    Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $iscc) { Fail "Inno Setup 6 is not installed (winget install JRSoftware.InnoSetup, or set KANAT_ISCC to ISCC.exe)" }

$mediamtx = Join-Path $Repo "VideoService\mediamtx.exe"
if (-not (Test-Path $mediamtx)) { Fail "VideoService\mediamtx.exe is missing (download MediaMTX $MediaMtxVersion into VideoService)" }
if ((Get-FileHash $mediamtx -Algorithm SHA256).Hash.ToLower() -ne $MediaMtxSha256) {
    Fail "VideoService\mediamtx.exe is not MediaMTX $MediaMtxVersion (its SHA-256 differs from the pinned one; if it was changed on purpose, change both in this script)"
}

$gtk = if ($env:KANAT_GTK) { $env:KANAT_GTK } else { Join-Path $env:ProgramFiles "GTK3-Runtime Win64" }
if (-not (Test-Path (Join-Path $gtk "bin\libpango-1.0-0.dll"))) {
    Fail "the GTK3 runtime (WeasyPrint's Pango) is not in $gtk (install GTK3-Runtime Win64, or set KANAT_GTK to its folder)"
}

$model = Join-Path $DetectionSrc "trained_models\$ModelFolder\weights\best.pt"
if (-not (Test-Path $model)) { Fail "the detection model is missing: $model (it is git-ignored: copy it from where it was trained)" }

# The detection environment that ships is the tested one: the venv's packages and
# the interpreter it was made from. It has to be PyTorch with CUDA, or the range's GPU is not used.
$venvCfg = Join-Path $DetectionSrc ".venv\pyvenv.cfg"
if (-not (Test-Path $venvCfg)) { Fail "ImageRecognitionService\.venv is missing (build it as ImageRecognitionService\HANDOVER.md says)" }
$detectionPython = ((Get-Content $venvCfg | Where-Object { $_ -match "^home\s*=" }) -replace "^home\s*=\s*", "").Trim()
if (-not (Test-Path (Join-Path $detectionPython "python.exe"))) { Fail "the interpreter of ImageRecognitionService\.venv is gone: $detectionPython (rebuild the venv)" }
$detectionSite = Join-Path $DetectionSrc ".venv\Lib\site-packages"
$torchVersion = (Get-Content (Join-Path $detectionSite "torch\version.py") | Where-Object { $_ -match "^__version__" }) -replace "^__version__\s*=\s*", "" -replace "[`"']", ""
if ($torchVersion -notmatch "\+cu\d+") { Fail "ImageRecognitionService\.venv has PyTorch $torchVersion, which has no CUDA: install the CUDA build (see Dockerfile's TORCH_INDEX)" }
Ok "PyTorch $torchVersion, Python from $detectionPython"

$backendPython = (& uv python find 3.12 2>$null | Select-Object -First 1)
if (-not $backendPython -or -not (Test-Path $backendPython)) { Fail "Python 3.12 is not available to uv (uv python install 3.12)" }
$backendPython = Split-Path $backendPython -Parent
Ok "backend Python from $backendPython; MediaMTX $MediaMtxVersion; GTK3 from $gtk"

Step "Parsing the scripts"
$scripts = @(Get-ChildItem (Join-Path $Here "scripts") -Filter "*.ps1") + (Get-Item $MyInvocation.MyCommand.Path)
foreach ($script in $scripts) {
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile($script.FullName, [ref]$null, [ref]$errors) | Out-Null
    if ($errors -and $errors.Count -gt 0) { Fail "$($script.Name) does not parse: $($errors[0].Message) (line $($errors[0].Extent.StartLineNumber))" }
}
if (Get-Module -ListAvailable PSScriptAnalyzer) {
    $findings = $scripts | ForEach-Object { Invoke-ScriptAnalyzer -Path $_.FullName -Severity Error }
    if ($findings) { $findings | Format-List | Out-String | Write-Host; Fail "PSScriptAnalyzer found errors in the scripts (above)" }
    Ok "parse and PSScriptAnalyzer: clean"
} else {
    Note "PSScriptAnalyzer is not installed: only the parse was checked (Install-Module PSScriptAnalyzer)"
    Ok "parse: clean"
}

$Version = (Get-Content (Join-Path $Frontend "package.json") -Raw | ConvertFrom-Json).version
Write-Host "KANAT ${Version}: building the $Variant installer(s) into $OutDir"

# --- 1. Stage ------------------------------------------------------------------

Step "Staging into $Stage"
if (Test-Path $Stage) { Remove-Item -Recurse -Force $Stage }
New-Item -ItemType Directory -Force -Path $Stage, $OutDir | Out-Null

# The app: electron-builder's unpacked folder (the installer is Inno Setup's, not NSIS)
Step "The app"
Run "npm" @("run", "build") $Frontend
$env:CSC_IDENTITY_AUTO_DISCOVERY = "false"   # not code-signed: no certificate here
Run "npx" @("electron-builder", "--win", "--x64", "--dir") $Frontend
$unpacked = Join-Path $Frontend "release\win-unpacked"
if (-not (Test-Path (Join-Path $unpacked "KANAT.exe"))) { Fail "electron-builder did not produce release\win-unpacked\KANAT.exe" }
Copy-Tree $unpacked (Join-Path $Stage "app")
Ok "app packaged"

# A Python to run from a folder of its own: the interpreter, its standard library and DLLs,
# without what only a developer uses (docs, tests, Tk, headers, its own packages)
function Copy-Python($from, $to) {
    $skip = @("Doc", "Tools", "include", "libs", "tcl", "Scripts", "Lib\test", "Lib\idlelib", "Lib\turtledemo", "Lib\site-packages") |
        ForEach-Object { Join-Path $from $_ }
    Copy-Tree $from $to $skip @("*.pdb", "_tkinter.pyd", "tcl*.dll", "tk*.dll")
    New-Item -ItemType Directory -Force -Path (Join-Path $to "Lib\site-packages") | Out-Null
}

Step "The backend"
$backend = Join-Path $Stage "backend"
Copy-Python $backendPython (Join-Path $backend "python")
$requirements = Join-Path $Build "backend-requirements.txt"
Run "uv" @("export", "--frozen", "--no-dev", "--no-hashes", "--no-emit-project", "--project", $BackendSrc, "-o", $requirements)
Run "uv" @("pip", "install", "--python", (Join-Path $backend "python\python.exe"), "--target", (Join-Path $backend "python\Lib\site-packages"),
           "--link-mode", "copy", "--quiet", "-r", $requirements)
Copy-Tree (Join-Path $BackendSrc "app") (Join-Path $backend "service\app") @("__pycache__")
Copy-Tree (Join-Path $BackendSrc "alembic") (Join-Path $backend "service\alembic") @("__pycache__")
Copy-Item (Join-Path $BackendSrc "alembic.ini") (Join-Path $backend "service")
# WeasyPrint draws its PDFs with Pango, which is not a Python package: carried here,
# and found through WEASYPRINT_DLL_DIRECTORIES (scripts\run.ps1)
Copy-Tree $gtk (Join-Path $backend "gtk") @((Join-Path $gtk "gtk3-runtime"), (Join-Path $gtk "share\icons"), (Join-Path $gtk "share\themes"),
    (Join-Path $gtk "share\doc"), (Join-Path $gtk "share\man")) @("gtk3_runtime_uninst.exe")
Ok "backend staged"

Step "The Detection Service"
$detection = Join-Path $Stage "detection"
Copy-Python $detectionPython (Join-Path $detection "python")
# What only tests and installs need stays out: pytest and pip
$devPackages = @("pytest", "_pytest", "pluggy", "iniconfig", "pip") | ForEach-Object { Join-Path $detectionSite $_ }
$devPackages += (Get-ChildItem $detectionSite -Directory | Where-Object { $_.Name -match "^(pytest|pluggy|iniconfig|pip)-[\d.]+\.dist-info$" }).FullName
Copy-Tree $detectionSite (Join-Path $detection "python\Lib\site-packages") $devPackages
$service = Join-Path $detection "service"
Copy-Tree (Join-Path $DetectionSrc "detection") (Join-Path $service "detection") @("__pycache__")
# detection imports tools.manifest; the rest of tools is for evaluating and labelling recordings
New-Item -ItemType Directory -Force -Path (Join-Path $service "tools") | Out-Null
Copy-Item (Join-Path $DetectionSrc "tools\__init__.py"), (Join-Path $DetectionSrc "tools\manifest.py") (Join-Path $service "tools")
Copy-Tree (Join-Path $DetectionSrc "config") (Join-Path $service "config")
Copy-Tree (Join-Path $DetectionSrc "data\targets") (Join-Path $service "data\targets")
New-Item -ItemType Directory -Force -Path (Join-Path $service "trained_models\$ModelFolder\weights") | Out-Null
Copy-Item $model (Join-Path $service "trained_models\$ModelFolder\weights")
Ok "detection staged ($ModelFolder only)"

Step "MediaMTX, the scripts"
New-Item -ItemType Directory -Force -Path (Join-Path $Stage "video") | Out-Null
Copy-Item $mediamtx (Join-Path $Stage "video")
Copy-Item (Join-Path $Here "mediamtx.yml") (Join-Path $Stage "video")
Copy-Tree (Join-Path $Here "scripts") (Join-Path $Stage "scripts")
Set-Content -Path (Join-Path $Stage "VERSION") -Value $Version -Encoding ASCII
$sizeGb = [math]::Round((Get-ChildItem $Stage -Recurse -File | Measure-Object Length -Sum).Sum / 1GB, 2)
Ok "staged: $sizeGb GB"

# --- 2. Compile ------------------------------------------------------------------

$modes = if ($Variant -eq "both") { @("threads", "processes") } else { @($Variant) }
foreach ($mode in $modes) {
    Step "Compiling the $mode installer (several minutes)"
    $arguments = @("/Q", "/DAppVersion=$Version", "/DRunMode=$mode", "/DStageDir=$Stage", "/DOutDir=$OutDir")
    if ($Spanning) { $arguments += "/DSpanning" }
    $arguments += (Join-Path $Here "kanat.iss")
    & $iscc @arguments
    if ($LASTEXITCODE -ne 0) {
        Fail "Inno Setup failed on the $mode installer (above). If it says the installer is over 2 GB, run this again with -Spanning"
    }
    Ok "KANAT-Setup-$Version-$mode.exe"
}

Step "Checksums"
$sums = Get-ChildItem $OutDir -File | Where-Object { $_.Name -ne "SHA256SUMS.txt" } |
    ForEach-Object { "{0}  {1}" -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower(), $_.Name }
Set-Content -Path (Join-Path $OutDir "SHA256SUMS.txt") -Value $sums -Encoding ASCII
Get-ChildItem $OutDir -File | ForEach-Object { Ok ("{0}  {1:N2} GB" -f $_.Name, ($_.Length / 1GB)) }
Write-Host ""
Write-Host "Built into $OutDir. Not verifiable here: the firewall, the multicast route, the scheduled tasks and the" -ForegroundColor Green
Write-Host "cameras: run an installer on a Windows PC, and say so before claiming they work." -ForegroundColor Green
