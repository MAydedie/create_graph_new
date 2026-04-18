$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$reportDir = Join-Path $projectRoot "benchmark_reports"

Write-Host "[benchmark] project: $projectRoot"
Write-Host "[benchmark] report_dir: $reportDir"

python (Join-Path $projectRoot "scripts/fixed_scenario_benchmark.py") --project-path $projectRoot --report-dir $reportDir

Write-Host "[benchmark] done"
