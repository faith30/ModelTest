#Requires -Version 7.0
<#
Build and stage a frozen Lyra candidate with real UE tools on Windows.
This script never runs the Linux result and never creates a success manifest
when the build fails or the expected ELF/launcher cannot be verified.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$EngineRoot,
    [Parameter(Mandatory = $true)][string]$ProjectRoot,
    [Parameter(Mandatory = $true)][string]$ToolchainRoot,
    [Parameter(Mandatory = $true)][string]$CandidateSha,
    [Parameter(Mandatory = $true)][string]$OutputRoot
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$resolvedOutput = [System.IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $resolvedOutput) {
    throw "OutputRoot already exists; choose a new directory: $resolvedOutput"
}
# Exclusive creation prevents reusing logs or manifests from another build.
$null = New-Item -ItemType Directory -Path $resolvedOutput -ErrorAction Stop

$buildLog = Join-Path $resolvedOutput 'build.log'
$startedAt = [DateTimeOffset]::UtcNow
$buildWatch = [System.Diagnostics.Stopwatch]::StartNew()
$buildExitCode = $null
$phase = 'preflight'
$previousToolchain = [Environment]::GetEnvironmentVariable('LINUX_MULTIARCH_ROOT', 'Process')
$environmentChanged = $false

function Read-ElfHeader {
    param([Parameter(Mandatory = $true)][string]$Path)
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $header = [byte[]]::new(20)
        $read = $stream.Read($header, 0, $header.Length)
        return ($read -eq 20 -and $header[0] -eq 0x7f -and
            $header[1] -eq 0x45 -and $header[2] -eq 0x4c -and $header[3] -eq 0x46 -and
            $header[4] -eq 2 -and $header[5] -eq 1 -and
            $header[16] -in @(2, 3) -and $header[17] -eq 0 -and
            $header[18] -eq 62 -and $header[19] -eq 0)
    }
    finally {
        $stream.Dispose()
    }
}

function File-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

try {
    if (-not $IsWindows) {
        throw 'This cross-compilation script requires Windows and PowerShell 7.'
    }
    if ($CandidateSha -notmatch '\A[0-9a-fA-F]{40}\z') {
        throw 'CandidateSha must be the complete 40-character frozen Git commit ID.'
    }
    $CandidateSha = $CandidateSha.ToLowerInvariant()
    $resolvedEngine = (Get-Item -LiteralPath $EngineRoot -ErrorAction Stop).FullName
    $resolvedProject = (Get-Item -LiteralPath $ProjectRoot -ErrorAction Stop).FullName
    $resolvedToolchain = (Get-Item -LiteralPath $ToolchainRoot -ErrorAction Stop).FullName
    $projectFile = Join-Path $resolvedProject 'Lyra.uproject'
    $sourceFile = Join-Path $resolvedProject 'Source/LyraGame/Character/LyraHealthComponent.cpp'
    $runUat = Join-Path $resolvedEngine 'Engine/Build/BatchFiles/RunUAT.bat'
    $versionFile = Join-Path $resolvedEngine 'Engine/Build/Build.version'
    $compiler = Join-Path $resolvedToolchain 'x86_64-unknown-linux-gnu/bin/clang++.exe'
    $toolchainVersionFile = Join-Path $resolvedToolchain 'ToolchainVersion.txt'
    foreach ($requiredFile in @($projectFile, $sourceFile, $runUat, $versionFile, $compiler, $toolchainVersionFile)) {
        if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
            throw "Required file is missing: $requiredFile"
        }
    }
    $version = Get-Content -LiteralPath $versionFile -Raw | ConvertFrom-Json
    $engineVersion = '{0}.{1}.{2}' -f $version.MajorVersion, $version.MinorVersion, $version.PatchVersion
    if ($engineVersion -ne '5.8.3') {
        throw "This evaluation requires UE 5.8.3; found $engineVersion."
    }
    $toolchainVersion = (Get-Content -LiteralPath $toolchainVersionFile -Raw).Trim()
    if ($toolchainVersion -ne 'v26_clang-20.1.8-rockylinux8') {
        throw "This evaluation requires v26_clang-20.1.8-rockylinux8; found $toolchainVersion."
    }
    $sourceHash = File-Sha256 $sourceFile
    $archiveRoot = Join-Path $resolvedOutput 'archive'
    $uatArgs = @(
        'BuildCookRun'
        "-project=$projectFile"
        '-target=LyraServer'
        '-nop4'
        '-server'
        '-noclient'
        '-serverplatform=Linux'
        '-serverconfig=Development'
        '-build'
        '-cook'
        '-stage'
        '-pak'
        '-archive'
        "-archivedirectory=$archiveRoot"
        '-MapsToCook=/Engine/Maps/Entry+/Game/DefaultGameData'
        # Keep startup packages: native CDOs request engine assets even with NullRHI.
        # CookSkipRequests omits WorldGridMaterial and crashes before tests start.
        '-AdditionalCookerOptions=-unattended -nullrhi -nosound'
        '-ini:Engine:[/Script/EngineSettings.GameMapsSettings]:GameInstanceClass=/Script/LyraGame.LyraGameInstance'
        '-ini:Engine:[/Script/EngineSettings.GameMapsSettings]:GlobalDefaultGameMode=/Script/Engine.GameModeBase'
        '-ini:Engine:[/Script/EngineSettings.GameMapsSettings]:GlobalDefaultServerGameMode=/Script/Engine.GameModeBase'
        '-ubtargs=-MaxParallelActions=12'
        '-utf8output'
        '-unattended'
    )
    $request = [ordered]@{
        schema_version = 1
        candidate_sha = $CandidateSha
        engine_root = $resolvedEngine
        project_root = $resolvedProject
        toolchain_root = $resolvedToolchain
        engine_version = $engineVersion
        toolchain_version = $toolchainVersion
        source_path = $sourceFile
        source_sha256 = $sourceHash
        executable = $runUat
        arguments = $uatArgs
        started_at = $startedAt.ToString('o')
    }
    $request | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $resolvedOutput 'build-request.json') -Encoding utf8

    [Environment]::SetEnvironmentVariable('LINUX_MULTIARCH_ROOT', $resolvedToolchain, 'Process')
    $environmentChanged = $true
    $phase = 'BuildCookRun'
    & $runUat @uatArgs 2>&1 | Tee-Object -FilePath $buildLog
    $buildExitCode = $LASTEXITCODE
    if ($buildExitCode -ne 0) {
        throw "RunUAT BuildCookRun failed with exit code $buildExitCode."
    }

    $phase = 'verify staged package'
    $launchers = @(Get-ChildItem -LiteralPath $archiveRoot -Filter 'LyraServer.sh' -File -Recurse)
    if ($launchers.Count -ne 1) {
        throw "Expected exactly one staged LyraServer.sh; found $($launchers.Count)."
    }
    $launcher = $launchers[0]
    $packageRoot = $launcher.Directory.FullName
    $elfCandidates = @(Get-ChildItem -LiteralPath $packageRoot -Filter 'LyraServer*' -File -Recurse |
        Where-Object { $_.Name -notmatch '\.(debug|sym|psym)$' -and (Read-ElfHeader $_.FullName) })
    if ($elfCandidates.Count -ne 1) {
        throw "Expected exactly one executable ELF64 x86_64 LyraServer binary; found $($elfCandidates.Count)."
    }
    $binary = $elfCandidates[0]
    $binaryRelativePath = [System.IO.Path]::GetRelativePath($packageRoot, $binary.FullName).Replace('\', '/')
    $launcherText = Get-Content -LiteralPath $launcher.FullName -Raw
    $expectedInvocation = '"$UE_PROJECT_ROOT/' + $binaryRelativePath + '"'
    if (-not $launcherText.Contains($expectedInvocation)) {
        throw 'The staged launcher does not reference the discovered LyraServer ELF.'
    }
    if ((File-Sha256 $sourceFile) -ne $sourceHash) {
        throw 'LyraHealthComponent.cpp changed during the build; no success manifest can be issued.'
    }
    $buildWatch.Stop()
    $manifest = [ordered]@{
        schema_version = 1
        candidate_sha = $CandidateSha
        target_platform = 'Linux'
        build_target = 'LyraServer'
        build_configuration = 'Development'
        build_exit_code = $buildExitCode
        source_sha256 = $sourceHash
        source_path = $sourceFile
        binary_sha256 = File-Sha256 $binary.FullName
        binary_relpath = $binaryRelativePath
        binary_path = $binary.FullName
        launcher_sha256 = File-Sha256 $launcher.FullName
        build_log_sha256 = File-Sha256 $buildLog
        build_log_path = $buildLog
        engine_version = $engineVersion
        engine_root = $resolvedEngine
        toolchain_version = $toolchainVersion
        package_root = $packageRoot
        started_at = $startedAt.ToString('o')
        finished_at = [DateTimeOffset]::UtcNow.ToString('o')
        build_seconds = [Math]::Round($buildWatch.Elapsed.TotalSeconds, 3)
        runtime_validated = $false
        provenance_boundary = 'CandidateSha identifies the evaluator-frozen candidate. Apply and validate candidate scope before this build; this script hashes the actual source and binary but does not independently prove Git provenance or Linux execution.'
    }
    $manifestPath = Join-Path $resolvedOutput 'build-manifest.json'
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding utf8
    Write-Output "Build and stage succeeded. Linux runtime remains unvalidated. Manifest: $manifestPath"
}
catch {
    $buildWatch.Stop()
    $failure = [ordered]@{
        schema_version = 1
        candidate_sha = $CandidateSha
        phase = $phase
        build_exit_code = $buildExitCode
        error = $_.Exception.Message
        started_at = $startedAt.ToString('o')
        finished_at = [DateTimeOffset]::UtcNow.ToString('o')
        elapsed_seconds = [Math]::Round($buildWatch.Elapsed.TotalSeconds, 3)
        build_log_path = $buildLog
        build_log_sha256 = $(if (Test-Path -LiteralPath $buildLog -PathType Leaf) { File-Sha256 $buildLog } else { $null })
        valid_build_manifest = $false
    }
    $failure | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $resolvedOutput 'build-failure.json') -Encoding utf8
    throw
}
finally {
    if ($environmentChanged) {
        [Environment]::SetEnvironmentVariable('LINUX_MULTIARCH_ROOT', $previousToolchain, 'Process')
    }
}
