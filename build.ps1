$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8='1'
$buildPython=Join-Path $PSScriptRoot '.venv-build/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $buildPython)) {
    py -3.11 -m venv .venv-build
    if ($LASTEXITCODE -ne 0) {throw 'Python 3.11 is required'}
}
& $buildPython -m pip install -r requirements.txt 'pyinstaller>=6,<7'
if ($LASTEXITCODE -ne 0) {throw 'Build dependency installation failed'}
& $buildPython -m PyInstaller --noconfirm --clean --windowed --onedir --name CourseNotesStudio --add-data 'skills;skills' --add-data 'course_notes;course_notes' desktop.py
if ($LASTEXITCODE -ne 0) {throw 'PyInstaller failed'}
$bundle=Join-Path $PSScriptRoot 'dist/CourseNotesStudio'
foreach ($file in @('README.md','LICENSE','THIRD_PARTY_NOTICES.md','setup-gpu.cmd','setup-gpu.ps1','deploy_local.py','deploy_formula.py','requirements-gpu.txt','settings.example.json')) {Copy-Item -LiteralPath (Join-Path $PSScriptRoot $file) -Destination $bundle}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'course_notes') -Destination $bundle -Recurse -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'LICENSES') -Destination $bundle -Recurse -Force
& $buildPython collect_licenses.py (Join-Path $bundle 'LICENSES/dependencies')
if ($LASTEXITCODE -ne 0) {throw 'Dependency license collection failed'}
& $buildPython package_zip.py $bundle 'dist/CourseNotesStudio-0.2.4-windows-x64.zip'
if ($LASTEXITCODE -ne 0) {throw 'Archive creation failed'}
Write-Host 'Built dist/CourseNotesStudio-0.2.4-windows-x64.zip'
