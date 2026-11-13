param([Parameter(Mandatory=$true)][string]$Bundle)
$ErrorActionPreference = 'Stop'
$Bundle = (Resolve-Path $Bundle).Path
$manifest = Get-Content (Join-Path $Bundle 'manifest.json') -Raw | ConvertFrom-Json
function NativePath([string]$unix) { return $env:SystemDrive + $unix.Replace('/', '\') }
$source = NativePath $manifest.source_root_linux
New-Item -ItemType Directory -Force $source | Out-Null
& tar -xf (Join-Path $Bundle 'source.tar') -C $source
if ($LASTEXITCODE -ne 0) { throw 'Source archive extraction failed' }
foreach ($file in $manifest.files) {
    $destination = NativePath $file.source_linux
    New-Item -ItemType Directory -Force (Split-Path $destination -Parent) | Out-Null
    Copy-Item (Join-Path $Bundle $file.artifact) $destination
}
$results = Join-Path $Bundle 'native-results'
New-Item -ItemType Directory -Force $results | Out-Null
$failed = $false
$records = @()
foreach ($test in $manifest.tests) {
    $info = [System.Diagnostics.ProcessStartInfo]::new()
    $info.FileName = NativePath $test.source_linux
    $info.WorkingDirectory = $source
    $info.Arguments = '--test-threads=1'
    $info.UseShellExecute = $false
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $info
    if (-not $process.Start()) { throw "Failed to start $($test.name)" }
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    $completed = $process.WaitForExit(300000)
    if (-not $completed) {
        & taskkill.exe /PID $process.Id /T /F | Out-Null
        $process.WaitForExit()
    }
    $code = if ($completed) { $process.ExitCode } else { 124 }
    $name = [System.IO.Path]::GetFileNameWithoutExtension($info.FileName)
    $text = $stdout.GetAwaiter().GetResult()
    $errorText = $stderr.GetAwaiter().GetResult()
    [System.IO.File]::WriteAllText((Join-Path $results "$name.stdout.txt"), $text)
    [System.IO.File]::WriteAllText((Join-Path $results "$name.stderr.txt"), $errorText)
    [Console]::Write($text)
    [Console]::Error.Write($errorText)
    $records += [ordered]@{name=$test.name; exe=$info.FileName; exit_code=$code; timeout=(-not $completed)}
    $failed = $failed -or ($code -ne 0)
    $process.Dispose()
}
$records | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $results 'results.json')
if ($failed) { exit 1 }
