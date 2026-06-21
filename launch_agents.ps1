<#
  launch_agents.ps1 — arranca el loop multi-agente Pulse (LOCAL).
  PoC de 2 agentes:  A1 = LIVE (opera, Sonnet)  ·  A4 = SHADOW (read-only, Haiku).
  A2 (/pre-market) y A3 (/post-close) son 1x/dia -> a mano (no van aqui).

  USO:
    cd C:\Users\inaki\Code\Trading\Claude
    git checkout feat/multiagent-a1-lean
    .\launch_agents.ps1
    .\launch_agents.ps1 -ShadowModel sonnet     # si sobran tokens, sube A4 a Sonnet

  Lanzar a mano (alternativa): abre 2 terminales y en cada una:
    A1:  claude --model sonnet "@strategies/cycle_prompt.md"
    A4:  claude --model haiku  "@strategies/shadow_prompt.md"
  Parar un agente: Ctrl+C en su ventana.
#>
param(
  [string]$LiveModel   = "sonnet",
  [string]$ShadowModel = "haiku"
)

$proj = $PSScriptRoot

# --- Pre-flight checks ---
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
  Write-Host "ERROR: no encuentro 'claude' en el PATH. Abre/instala el CLI de Claude Code primero." -ForegroundColor Red
  return
}
foreach ($f in @("strategies\cycle_prompt.md", "strategies\shadow_prompt.md")) {
  if (-not (Test-Path (Join-Path $proj $f))) {
    Write-Host "ERROR: falta $f. Cambia a la rama:  git checkout feat/multiagent-a1-lean" -ForegroundColor Red
    return
  }
}
$branch = & git -C $proj branch --show-current
if ($branch -ne "feat/multiagent-a1-lean") {
  Write-Host "AVISO: rama actual = '$branch'. El cycle_prompt LEAN vive en feat/multiagent-a1-lean." -ForegroundColor Yellow
  Write-Host "       En otra rama, A1 podria correr el monolitico (shadows in-cycle)." -ForegroundColor Yellow
}

# --- Aislamiento capa 2: el agente shadow NO puede llamar tools de ordenes ---
# (Capa 1 = shadow_prompt.md lo prohibe; capa 3 = key read-only de Alpaca, NO disponible en paper.)
# Si tu CLI no acepta --disallowedTools, quita ese argumento de la linea de A4 (capa 1 ya protege).
$denyOrders = @(
  "mcp__alpaca__place_stock_order", "mcp__alpaca__place_option_order", "mcp__alpaca__place_crypto_order",
  "mcp__alpaca__cancel_order_by_id", "mcp__alpaca__cancel_all_orders", "mcp__alpaca__close_position",
  "mcp__alpaca__close_all_positions", "mcp__alpaca__replace_order_by_id", "mcp__alpaca__exercise_options_position"
) -join ","

Write-Host "Lanzando agentes Pulse desde $proj" -ForegroundColor Green

# A1 — LIVE (Sonnet)
$a1 = "Set-Location '$proj'; `$host.UI.RawUI.WindowTitle='A1-live ($LiveModel)'; " +
      "Write-Host '=== A1 LIVE -- opera ordenes (cycle_prompt.md lean) ===' -ForegroundColor Cyan; " +
      "claude --model $LiveModel '@strategies/cycle_prompt.md'"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $a1
Start-Sleep -Milliseconds 700

# A4 — SHADOW (Haiku, read-only, tools de ordenes denegadas)
$a4 = "Set-Location '$proj'; `$host.UI.RawUI.WindowTitle='A4-shadow ($ShadowModel)'; " +
      "Write-Host '=== A4 SHADOW -- read-only, SIN ordenes (shadow_prompt.md) ===' -ForegroundColor Magenta; " +
      "claude --model $ShadowModel --disallowedTools '$denyOrders' '@strategies/shadow_prompt.md'"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $a4

Write-Host ""
Write-Host "2 ventanas abiertas:" -ForegroundColor Green
Write-Host "  A1-live   ($LiveModel)   -> opera ordenes" -ForegroundColor Cyan
Write-Host "  A4-shadow ($ShadowModel) -> read-only, solo loggea shadow_signals" -ForegroundColor Magenta
Write-Host ""
Write-Host "ANTES de lanzar: corre /pre-market (A2) en otra terminal para sembrar el estado del dia." -ForegroundColor Yellow
Write-Host "Al cierre (>=16:00 ET): /post-close (A3). Tokens por agente: escribe /cost. Parar: Ctrl+C." -ForegroundColor Yellow
