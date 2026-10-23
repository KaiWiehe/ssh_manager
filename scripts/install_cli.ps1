param(
    [string]$Directory = (Join-Path $env:LOCALAPPDATA "Programs\SSH-Manager"),
    [switch]$AddToPath
)
$ErrorActionPreference = "Stop"
$Source = Join-Path $PSScriptRoot "..\dist\sshm.exe"
if (!(Test-Path -LiteralPath $Source -PathType Leaf)) {
    throw "Zuerst scripts\build_windows.ps1 ausfuehren; dist\sshm.exe fehlt."
}
$Directory = [IO.Path]::GetFullPath($Directory)
$Target = Join-Path $Directory "sshm.exe"
$Collisions = @(Get-Command sshm -All -ErrorAction SilentlyContinue | Where-Object {
    !$_.Source -or [IO.Path]::GetFullPath($_.Source) -ne $Target
})
if ($Collisions.Count) { throw "Der Name 'sshm' ist bereits anderweitig belegt. Bitte zuerst die Namenskollision klaeren." }
New-Item -ItemType Directory -Force -Path $Directory | Out-Null
Copy-Item -LiteralPath $Source -Destination $Target -Force
& $Target --version
if ($LASTEXITCODE -ne 0) { throw "Der installierte CLI-Starter konnte nicht geprueft werden." }
if ($AddToPath) {
    $EnvironmentKey = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey("Environment", $true)
    try {
        $CurrentPath = [string]$EnvironmentKey.GetValue("Path", "", [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
        $Segments = @($CurrentPath.Split(';') | Where-Object { $_ })
        if (!($Segments | Where-Object { [Environment]::ExpandEnvironmentVariables($_).TrimEnd('\') -ieq $Directory.TrimEnd('\') })) {
            $NewPath = if ($CurrentPath) { $CurrentPath.TrimEnd(';') + ';' + $Directory } else { $Directory }
            $EnvironmentKey.SetValue("Path", $NewPath, [Microsoft.Win32.RegistryValueKind]::ExpandString)
        }
    }
    finally { $EnvironmentKey.Dispose() }
    if (-not ('SshmEnvironment' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class SshmEnvironment {
    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern IntPtr SendMessageTimeout(IntPtr hwnd, uint msg,
        UIntPtr wParam, string lParam, uint flags, uint timeout, out UIntPtr result);
}
'@
    }
    $BroadcastResult = [UIntPtr]::Zero
    [void][SshmEnvironment]::SendMessageTimeout([IntPtr]0xffff, 0x001A, [UIntPtr]::Zero, "Environment", 2, 3000, [ref]$BroadcastResult)
    Write-Host "Benutzer-PATH ergaenzt. Terminalhost ggf. vollstaendig neu starten, dann: sshm"
}
Write-Host "CLI installiert: $Target"
