<#
.SYNOPSIS
  Local live traversal companion for the Phase 25 crawl-seed link-graph.

.DESCRIPTION
  crawl_seed.py --list expands the seed roots in canonical-sources/crawl_seeds.json
  into candidate child URLs deterministically and OFFLINE. This script performs the
  network-heavy part LOCALLY (where the managed proxy blocks a host): it fetches each
  candidate, extracts child document / link URLs, and writes a JSON result set that
  crawl_seed.py --import merges back. Nothing is auto-ingested — the output is a
  review stub.

  Run from the repo root (the dbz working copy). Requires PowerShell 5+.

.EXAMPLE
  # 1) produce the deterministic candidate list
  python3 tools/crawl_seed.py --list --format json > candidates.json
  # 2) live-crawl locally and write discovered.json
  pwsh -File tools/crawl_seed.ps1 -Candidates candidates.json -Out discovered.json
  # 3) merge back
  python3 tools/crawl_seed.py --import discovered.json
#>
[CmdletBinding()]
param(
  [string]$Candidates = "candidates.json",
  [string]$Out = "discovered.json",
  [int]$DelayMs = 500,
  [int]$MaxLinksPerPage = 40
)

$ErrorActionPreference = "Stop"
$UA = "dbz-crawl-seed/1.0 (+standards currency; contact repo maintainer)"

if (-not (Test-Path $Candidates)) {
  Write-Error "candidate file not found: $Candidates (run: python3 tools/crawl_seed.py --list --format json > $Candidates)"
  exit 1
}

$cand = Get-Content -Raw -Path $Candidates | ConvertFrom-Json
$discovered = New-Object System.Collections.Generic.List[object]

foreach ($c in $cand.candidates) {
  $url = $c.url
  try {
    $resp = Invoke-WebRequest -Uri $url -Headers @{ "User-Agent" = $UA } -TimeoutSec 30 -UseBasicParsing
    $status = $resp.StatusCode
    # extract absolute http(s) links
    $links = @()
    if ($resp.Links) {
      $links = $resp.Links | ForEach-Object { $_.href } |
        Where-Object { $_ -match '^https?://' } | Select-Object -First $MaxLinksPerPage
    }
    # also harvest document links from raw content (pdf/xlsx/json/xml/zip)
    $docs = [regex]::Matches($resp.Content, 'https?://[^\s"''<>]+\.(?:pdf|xlsx|xlsm|csv|json|xml|zip)') |
      ForEach-Object { $_.Value } | Select-Object -Unique -First $MaxLinksPerPage
    $discovered.Add([pscustomobject]@{
      seed = $c.seed; parent = $url; status = $status;
      links = @($links); documents = @($docs)
    })
    # emit each doc link as a top-level discovered url too (for --import)
    foreach ($d in $docs) {
      $discovered.Add([pscustomobject]@{ seed = $c.seed; url = $d; parent = $url; kind = "document" })
    }
    Write-Host ("[{0}] {1}  ->  {2} links / {3} docs" -f $status, $url, $links.Count, $docs.Count)
  }
  catch {
    $discovered.Add([pscustomobject]@{ seed = $c.seed; parent = $url; status = "error"; error = $_.Exception.Message })
    Write-Warning ("error {0}: {1}" -f $url, $_.Exception.Message)
  }
  Start-Sleep -Milliseconds $DelayMs
}

# deterministic-ish: sort by url/parent before writing
$sorted = $discovered | Sort-Object { $_.url }, { $_.parent }
[pscustomobject]@{ tool = "crawl-seed-ps1"; discovered = @($sorted) } |
  ConvertTo-Json -Depth 6 | Set-Content -Path $Out -Encoding UTF8

Write-Host ("`nWrote {0} discovered records -> {1}" -f $discovered.Count, $Out)
Write-Host "Merge with: python3 tools/crawl_seed.py --import $Out"
