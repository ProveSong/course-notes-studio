$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8='1'
$env:PYTHONPATH=$PSScriptRoot
function Run-Checked { param([string]$Exe,[string[]]$Arguments) & $Exe @Arguments; if ($LASTEXITCODE -ne 0) {throw "Command failed: $Exe"} }
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {throw 'Install Python 3.11 for Windows from python.org, then run setup again.'}
$studioHome = if ($env:COURSE_NOTES_HOME) {$env:COURSE_NOTES_HOME} else {Join-Path $env:LOCALAPPDATA 'CourseNotesStudio'}
$gpuRoot=Join-Path $studioHome 'DeepRead'
New-Item -ItemType Directory -Force -Path $gpuRoot | Out-Null
Run-Checked 'py' @('-3.11','-m','venv',(Join-Path $gpuRoot '.venv-paddle'))
$gpuPython=Join-Path $gpuRoot '.venv-paddle/Scripts/python.exe'
Run-Checked $gpuPython @('-m','pip','install','--upgrade','pip')
Run-Checked $gpuPython @('-m','pip','install','torch==2.6.0','torchvision==0.21.0','--index-url','https://download.pytorch.org/whl/cu126')
Run-Checked $gpuPython @('-m','pip','install','paddlepaddle-gpu==3.3.1','--index-url','https://www.paddlepaddle.org.cn/packages/stable/cu126/')
Run-Checked $gpuPython @('-m','pip','install','-r',(Join-Path $PSScriptRoot 'requirements-gpu.txt'))
Run-Checked $gpuPython @('-X','utf8',(Join-Path $PSScriptRoot 'deploy_local.py'))
