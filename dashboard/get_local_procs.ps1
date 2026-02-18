$procs = Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python|Prismata' }
foreach ($p in $procs) {
    $cmd = if ($p.CommandLine) { $p.CommandLine.Substring(0, [Math]::Min(200, $p.CommandLine.Length)) } else { '(no cmdline)' }
    Write-Output "$($p.ProcessId)|$($p.Name)|$cmd"
}
