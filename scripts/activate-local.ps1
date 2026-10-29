param(
    [string]$ConfigPath = "$env:USERPROFILE/.codex/config.toml",
    [Parameter(Mandatory=$true)][string]$ExecutablePath
)
$ErrorActionPreference = 'Stop'
$taskExecutable = (Resolve-Path -LiteralPath $ExecutablePath).Path.Replace('\', '/')
$taskConfigPath = (Resolve-Path -LiteralPath $ConfigPath).Path
$taskConfig = [IO.File]::ReadAllText($taskConfigPath)
$taskPattern = '(?ms)(^\[mcp_servers\.google_ads\]\s*\r?\n)(.*?)(?=^\[|\z)'
$taskMatch = [regex]::Match($taskConfig, $taskPattern)
if (-not $taskMatch.Success) { throw 'google_ads configuration section not found.' }
$taskCommandPattern = '(?m)^command\s*=\s*"[^"\r\n]*"\s*$'
if ([regex]::Matches($taskMatch.Groups[2].Value, $taskCommandPattern).Count -ne 1) {
    throw 'Expected exactly one command in the existing google_ads section.'
}
$taskNewBody = [regex]::Replace($taskMatch.Groups[2].Value, $taskCommandPattern,
    ('command = "' + $taskExecutable + '"'))
$taskReplacement = $taskMatch.Groups[1].Value + $taskNewBody
$taskNewConfig = $taskConfig.Substring(0, $taskMatch.Index) + $taskReplacement +
    $taskConfig.Substring($taskMatch.Index + $taskMatch.Length)
$taskBackup = $taskConfigPath + '.before-search-editing-' + (Get-Date -Format 'yyyyMMddHHmmss') + '.bak'
[IO.File]::Copy($taskConfigPath, $taskBackup, $false)
[IO.File]::WriteAllText($taskConfigPath, $taskNewConfig, [Text.UTF8Encoding]::new($false))
Write-Output 'Updated only the google_ads command; authentication settings preserved.'
Write-Output ('Configuration backup: ' + $taskBackup)
