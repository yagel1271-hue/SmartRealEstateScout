# Read-only environment check - works even before Python is installed.
# Run: right-click > "Run with PowerShell", or paste into a PowerShell window.
function Check($name, $cmd) {
  $c = Get-Command $cmd -ErrorAction SilentlyContinue
  if ($c) { $v = (& $cmd --version 2>&1 | Select-Object -First 1); "{0,-8}: {1}  [{2}]" -f $name, $v, $c.Source }
  else { "{0,-8}: NOT INSTALLED" -f $name }
}
$os = Get-CimInstance Win32_OperatingSystem
"Windows : $($os.Caption) | $($os.Version) | $($os.OSArchitecture)"
"CPU     : $((Get-CimInstance Win32_Processor).Name)"
"RAM     : $([math]::Round($os.TotalVisibleMemorySize/1MB,1)) GB total, $([math]::Round($os.FreePhysicalMemory/1MB,1)) GB free"
"Disk C: : $([math]::Round((Get-PSDrive C).Free/1GB,1)) GB free"
Get-CimInstance Win32_VideoController | ForEach-Object { "GPU     : $($_.Name)" }
Check "Python" "python"
Check "py" "py"
Check "Git" "git"
Check "VSCode" "code"
Check "Ollama" "ollama"
"ExecPol : $(Get-ExecutionPolicy)"
Read-Host "Press Enter to close"
