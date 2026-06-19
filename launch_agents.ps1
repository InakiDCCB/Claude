<#
  launch_agents.ps1 — arranca el loop multi-agente Pulse (LOCAL).

  Por defecto lanza el PoC de 2 agentes:
    A1 = LIVE  (opera órdenes en paper)      — modelo Sonnet
    A4 = SHADOW (read-only, NO opera nunca)  — modelo Haiku

  A2 (/pre-market) y A3 (/post-close) son 1x/día → se corren a mano cuando toca (no van aquí).

  USO:
    cd C:\Users\inaki\Code\Trading\Claude
    git checkout feat/multiagent-a1-lean          # rama con cycle_prompt lean + shadow_prompt
    .\launch_agents.ps1                            # abre 2 ventanas: A1 (Sonnet) y A4 (Haiku)
    .\launch_agents.ps1 -ShadowModel sonnet        # si sobran tokens, sube A4 a Sonnet

  Cada ventana abre una sesión `claude` con su prompt inicial. Si prefieres lanzarlas a mano,
  abre 2 terminales y en cada una:
    A1:  claude --model sonnet "@strategies/cycle_prompt.md"
    A4:  claude --model haiku  "@strategies/shadow_prompt.md"

  Para PARAR un agente: Ctrl+C en su ventana.
#>
param(
  [string]$LiveModel   = "sonnet",
  [string]$ShadowModel = "haiku"
)

$proj = $PSScriptRoot

# --- Aislamiento capa 2: el agente shadow NO debe poder llamar tools de órdenes ---
# (Capa 1 = el propio shadow_prompt.md lo prohíbe; capa 3 = key read-only de Alpaca, NO disponible en
#  esta cuenta paper.) Si tu versión de Claude CLI no acepta --disallowedTools, quita ese argumento
#  de la línea de A4 más abajo — el spec de A4 ya prohíbe operar.
$denyOrders = "mcp__alpaca__place_stock_order mcp__alpaca__place_option_order mcp__alpaca__place_crypto_order mcp__alpaca__cancel_order_by_id mcp__alpaca__cancel_all_orders mcp__alpaca__close_position mcp__alpaca__close_all_positions mcp__alpaca__replace_order_by_id mcp__alpaca__exercise_options_position"

Write-Host "Lanzando agentes Pulse desde $proj" -ForegroundColor Green

# A1 — LIVE (Sonnet)
$a1 = "Set-Location '$proj'; `$host.UI.RawUI.WindowTitle='A1-live ($LiveModel)'; " +
      "Write-Host '=== A1 LIVE — opera ordenes (cycle_prompt.md lean) ===' -ForegroundColor Cyan; " +
      "claude --model $LiveModel '@strategies/cycle_prompt.md'"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $a1
Start-Sleep -Milliseconds 700

# A4 — SHADOW (Haiku, read-only, tools de ordenes denegadas)
$a4 = "Set-Location '$proj'; `$host.UI.RawUI.WindowTitle='A4-shadow ($ShadowModel)'; " +
      "Write-Host '=== A4 SHADOW — read-only, SIN ordenes (shadow_prompt.md) ===' -ForegroundColor Magenta; " +
      "claude --model $ShadowModel --disallowedTools `"$denyOrders`" '@strategies/shadow_prompt.md'"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $a4

Write-Host ""
Write-Host "2 ventanas abiertas:" -ForegroundColor Green
Write-Host "  A1-live   ($LiveModel)   -> opera ordenes" -ForegroundColor Cyan
Write-Host "  A4-shadow ($ShadowModel) -> read-only, solo loggea shadow_signals" -ForegroundColor Magenta
Write-Host ""
Write-Host "A2 (/pre-market) y A3 (/post-close): a mano en otra terminal cuando toque." -ForegroundColor Yellow
Write-Host "Medir tokens de cada agente: /cost dentro de cada sesion claude. Parar: Ctrl+C." -ForegroundColor Yellow
