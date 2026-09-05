$audioRuntimeRoot = $env:CODEX_AUDIO_RUNTIME
if (-not $audioRuntimeRoot) {
    $audioRuntimeRoot = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Codex\skill-runtimes\extract-text-audio'
}
$audioPython = Join-Path $audioRuntimeRoot 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $audioPython -PathType Leaf)) {
    throw "Local audio runtime missing at $audioRuntimeRoot. Run setup_audio.py first."
}
& $audioPython -X utf8 (Join-Path $PSScriptRoot 'audio_verify.py') --runtime-root $audioRuntimeRoot @args
exit $LASTEXITCODE
