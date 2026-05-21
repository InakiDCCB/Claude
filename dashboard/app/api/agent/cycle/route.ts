import { NextRequest, NextResponse } from 'next/server'
import Anthropic from '@anthropic-ai/sdk'
import { checkSecret, BASE, alpacaHeaders } from '../../alpaca/_shared'
import { createSupabase } from '../../../../lib/supabase'

export const maxDuration = 300
export const revalidate = 0

const DATA_BASE = 'https://data.alpaca.markets/v2'
const BLOCKED = new Set(['BA', 'LMT', 'TXN', 'NOC', 'RTX', 'GD', 'HII', 'MRNA', 'PFE'])

const TOOLS: Anthropic.Tool[] = [
  {
    name: 'alpaca_clock',
    description: 'Get market clock: is_open, timestamp, next_open, next_close',
    input_schema: { type: 'object', properties: {}, required: [] },
  },
  {
    name: 'alpaca_account',
    description: 'Get account equity and cash for position sizing',
    input_schema: { type: 'object', properties: {}, required: [] },
  },
  {
    name: 'alpaca_positions',
    description: 'Get all open positions',
    input_schema: { type: 'object', properties: {}, required: [] },
  },
  {
    name: 'alpaca_bars',
    description: 'Get OHLCV bars for a symbol',
    input_schema: {
      type: 'object',
      properties: {
        symbol:    { type: 'string' },
        timeframe: { type: 'string', description: '1Min or 5Min' },
        limit:     { type: 'number' },
        feed:      { type: 'string', description: 'iex (real-time 1-min) or sip (5-min)' },
      },
      required: ['symbol', 'timeframe', 'limit'],
    },
  },
  {
    name: 'alpaca_order',
    description: 'Place a market day order. buy = new entry (long only). sell = close existing position.',
    input_schema: {
      type: 'object',
      properties: {
        symbol: { type: 'string' },
        qty:    { type: 'number' },
        side:   { type: 'string', enum: ['buy', 'sell'] },
      },
      required: ['symbol', 'qty', 'side'],
    },
  },
  {
    name: 'alpaca_get_order',
    description: 'Get order status and fill price by order ID',
    input_schema: {
      type: 'object',
      properties: { order_id: { type: 'string' } },
      required: ['order_id'],
    },
  },
  {
    name: 'db_heartbeat',
    description: 'Upsert agent heartbeat in agent_status table',
    input_schema: {
      type: 'object',
      properties: {
        status:      { type: 'string', enum: ['running', 'idle', 'error'] },
        description: { type: 'string' },
        metadata:    { type: 'object', description: '{"regime":"RANGE","positions":1,"daily_pnl":23.5}' },
      },
      required: ['status', 'description'],
    },
  },
  {
    name: 'db_log',
    description: 'Insert a cycle analysis entry into analysis_log',
    input_schema: {
      type: 'object',
      properties: {
        asset:      { type: 'string' },
        timeframe:  { type: 'string' },
        signal:     { type: 'string', enum: ['bullish', 'bearish', 'neutral', 'watching'] },
        confidence: { type: 'number', description: '0–100' },
        indicators: { type: 'object', description: '{"ema9":X,"ema21":Y,"vwap":Z,"rsi":R,"atr":A}' },
        thesis:     { type: 'string' },
      },
      required: ['asset', 'timeframe', 'signal', 'confidence', 'thesis'],
    },
  },
  {
    name: 'db_trade',
    description: 'Record a new trade entry in the trades table',
    input_schema: {
      type: 'object',
      properties: {
        asset:    { type: 'string' },
        side:     { type: 'string', enum: ['buy', 'sell'] },
        qty:      { type: 'number' },
        price:    { type: 'number', description: 'Fill price rounded to 2 decimals' },
        order_id: { type: 'string' },
        notes:    { type: 'string', description: 'SL=X.XX TP1=Y.YY TP2=Z.ZZ ATR=A.AA' },
      },
      required: ['asset', 'side', 'qty', 'price', 'order_id'],
    },
  },
  {
    name: 'db_trade_exit',
    description: 'Update a trade with exit price and P&L',
    input_schema: {
      type: 'object',
      properties: {
        order_id:   { type: 'string' },
        exit_price: { type: 'number' },
        pnl:        { type: 'number' },
        exit_type:  { type: 'string', enum: ['TP1', 'TP2', 'SL', 'TIME', 'MANUAL'] },
      },
      required: ['order_id', 'exit_price', 'pnl', 'exit_type'],
    },
  },
  {
    name: 'db_read',
    description: 'Read data from Supabase',
    input_schema: {
      type: 'object',
      properties: {
        table: { type: 'string', enum: ['session_memory', 'trades_today', 'agent_status'] },
        limit: { type: 'number', description: 'Max rows (default 10)' },
      },
      required: ['table'],
    },
  },
  {
    name: 'db_memory',
    description: 'Write end-of-session learning to session_memory table',
    input_schema: {
      type: 'object',
      properties: {
        regime:       { type: 'string', description: 'TREND or RANGE' },
        assets:       { type: 'array', items: { type: 'string' } },
        total_pnl:    { type: 'number' },
        win_rate:     { type: 'number', description: 'Percentage 0–100' },
        trade_count:  { type: 'number' },
        observations: { type: 'object', description: '{"worked":[],"failed":[],"patterns":[]}' },
        parameters:   { type: 'object', description: '{"notes":"suggestions for next session"}' },
        summary:      { type: 'string' },
      },
      required: ['regime', 'total_pnl', 'summary'],
    },
  },
]

async function runTool(name: string, input: Record<string, unknown>): Promise<unknown> {
  const db = createSupabase()

  switch (name) {
    case 'alpaca_clock': {
      const r = await fetch(`${BASE}/clock`, { headers: alpacaHeaders(), cache: 'no-store' })
      if (!r.ok) return { error: `Clock ${r.status}` }
      return r.json()
    }

    case 'alpaca_account': {
      const r = await fetch(`${BASE}/account`, { headers: alpacaHeaders(), cache: 'no-store' })
      if (!r.ok) return { error: `Account ${r.status}` }
      const d = await r.json()
      return { equity: d.equity, cash: d.cash, buying_power: d.buying_power }
    }

    case 'alpaca_positions': {
      const r = await fetch(`${BASE}/positions`, { headers: alpacaHeaders(), cache: 'no-store' })
      if (!r.ok) return { error: `Positions ${r.status}` }
      return r.json()
    }

    case 'alpaca_bars': {
      const { symbol, timeframe, limit, feed = 'sip' } = input as {
        symbol: string; timeframe: string; limit: number; feed?: string
      }
      const url = `${DATA_BASE}/stocks/${encodeURIComponent(symbol)}/bars`
        + `?timeframe=${timeframe}&limit=${limit}&feed=${feed}&adjustment=raw`
      const r = await fetch(url, { headers: alpacaHeaders(), cache: 'no-store' })
      if (!r.ok) return { error: `Bars ${r.status} ${await r.text()}` }
      return r.json()
    }

    case 'alpaca_order': {
      const { symbol, qty, side } = input as { symbol: string; qty: number; side: string }
      if (side === 'buy' && BLOCKED.has(symbol.toUpperCase())) {
        return { error: `${symbol} is in the blocked universe` }
      }
      if (side === 'sell') {
        const check = await fetch(`${BASE}/positions/${symbol}`, { headers: alpacaHeaders(), cache: 'no-store' })
        if (!check.ok) return { error: `No open position for ${symbol}` }
      }
      const r = await fetch(`${BASE}/orders`, {
        method: 'POST',
        headers: alpacaHeaders(),
        body: JSON.stringify({ symbol, qty: String(qty), side, type: 'market', time_in_force: 'day' }),
        cache: 'no-store',
      })
      if (!r.ok) return { error: `Order ${r.status} ${await r.text()}` }
      return r.json()
    }

    case 'alpaca_get_order': {
      const { order_id } = input as { order_id: string }
      const r = await fetch(`${BASE}/orders/${order_id}`, { headers: alpacaHeaders(), cache: 'no-store' })
      if (!r.ok) return { error: `GetOrder ${r.status}` }
      return r.json()
    }

    case 'db_heartbeat': {
      const { status, description, metadata } = input as {
        status: string; description: string; metadata?: Record<string, unknown>
      }
      const { error } = await db.from('agent_status').upsert(
        { name: 'pulse-v2', status, description, updated_at: new Date().toISOString(), metadata: metadata ?? null },
        { onConflict: 'name' }
      )
      return error ? { error: error.message } : { ok: true }
    }

    case 'db_log': {
      const { asset, timeframe, signal, confidence, indicators, thesis } = input as {
        asset: string; timeframe: string; signal: string; confidence: number;
        indicators?: Record<string, unknown>; thesis: string
      }
      const { error } = await db.from('analysis_log').insert({
        asset, timeframe, signal, confidence, indicators: indicators ?? null, thesis,
      })
      return error ? { error: error.message } : { ok: true }
    }

    case 'db_trade': {
      const { asset, side, qty, price, order_id, notes } = input as {
        asset: string; side: string; qty: number; price: number; order_id: string; notes?: string
      }
      const { data, error } = await db.from('trades').insert({
        asset, side, quantity: qty, price,
        filled_at: new Date().toISOString(),
        order_id, status: 'filled', strategy: 'Pulse-v2.4',
        notes: notes ?? null,
      }).select('id').single()
      return error ? { error: error.message } : { ok: true, id: data?.id }
    }

    case 'db_trade_exit': {
      const { order_id, exit_price, pnl, exit_type } = input as {
        order_id: string; exit_price: number; pnl: number; exit_type: string
      }
      const { error } = await db.from('trades')
        .update({ exit_price, pnl, exit_type, status: 'filled' })
        .eq('order_id', order_id)
      return error ? { error: error.message } : { ok: true }
    }

    case 'db_read': {
      const { table, limit = 10 } = input as { table: string; limit?: number }
      if (table === 'session_memory') {
        const { data, error } = await db.from('session_memory')
          .select('session_date,regime,total_pnl,win_rate,observations,parameters,summary')
          .order('session_date', { ascending: false }).limit(limit)
        return error ? { error: error.message } : data
      }
      if (table === 'trades_today') {
        const today = new Date().toISOString().split('T')[0]
        const { data, error } = await db.from('trades')
          .select('id,asset,side,quantity,price,exit_price,pnl,status,order_id,notes,created_at')
          .gte('created_at', `${today}T00:00:00Z`)
          .order('created_at', { ascending: true })
        return error ? { error: error.message } : data
      }
      if (table === 'agent_status') {
        const { data, error } = await db.from('agent_status')
          .select('*').eq('name', 'pulse-v2').limit(1)
        return error ? { error: error.message } : data
      }
      return { error: 'unknown table' }
    }

    case 'db_memory': {
      const { regime, assets, total_pnl, win_rate, trade_count, observations, parameters, summary } = input as {
        regime: string; assets?: string[]; total_pnl: number; win_rate?: number;
        trade_count?: number; observations?: Record<string, unknown>;
        parameters?: Record<string, unknown>; summary: string
      }
      const today = new Date().toISOString().split('T')[0]
      const { error } = await db.from('session_memory').insert({
        session_date: today, regime, assets: assets ?? null,
        total_pnl, win_rate: win_rate ?? null,
        trade_count: trade_count ?? null,
        observations: observations ?? null,
        parameters: parameters ?? null,
        summary,
      })
      return error ? { error: error.message } : { ok: true }
    }

    default:
      return { error: `Unknown tool: ${name}` }
  }
}

const SYSTEM = `You are the Pulse v2.4 autonomous trading agent operating a paper account on Alpaca. Execute one complete trading cycle using the available tools.

## PHASE DETECTION
Call alpaca_clock first. Parse timestamp to get current ET (UTC-4 in EDT, UTC-5 in EST).
- Market closed (is_open=false) → db_heartbeat(idle, "Market closed") → DONE
- ET < 10:00 → db_heartbeat(idle, "Pre-market") → DONE
- ET 10:00–15:00 → ACTIVE TRADING CYCLE
- ET 15:00–15:55 → PASSIVE: manage open positions only, no new entries
- ET ≥ 15:55 → close ALL positions (exit_type=TIME), write db_memory, heartbeat idle → DONE

## ACTIVE CYCLE

### 1. CONTEXT
alpaca_account → equity for sizing
db_read(session_memory, 3) → apply prior learnings
db_read(trades_today) → sum pnl. If total ≤ -500 → heartbeat(idle, "Daily loss limit") → DONE

### 2. MARKET DATA
For QQQ, TSLA, RIVN:
  alpaca_bars(symbol, "5Min", 100, "sip") — regime + VWAP/EMA/RSI
  alpaca_bars(symbol, "1Min", 30, "iex") — ATR14 + 1-min confirmation

### 3. COMPUTE (from bars)
5-min: VWAP = Σ((H+L+C)/3 × vol) / Σvol from 9:30 ET. EMA9, EMA21, RSI14 on close.
1-min: ATR14 = mean of 14 periods of max(H−L, |H−prevC|, |L−prevC|).

### 4. REGIME (first cycle, if no trades today)
TREND: last_close > VWAP×1.008 AND |last_close−open| > open×0.015
RANGE: default. QQQ/TSLA disagree → RANGE.
TREND DOWN: last_close < open + volume accelerating → restrict longs.

### 5. MANAGE POSITIONS
alpaca_positions. For each, find trade in trades_today by asset.
Parse notes: "SL=X TP1=Y TP2=Z ATR=A". Use latest 1-min close:
  ≤ SL → alpaca_order(sell, qty) → db_trade_exit(order_id, exit_price, pnl, "SL")
  ≥ TP1 → sell 50% → db_trade_exit exit_type="TP1"
  ≥ TP2 → sell rest → db_trade_exit exit_type="TP2"

### 6. ENTRY (skip if ≥2 positions)
EMA filter: <11:15 ET → EMA9; ≥11:15 ET → EMA21. Reject if price < filter. Buffer ±$0.25 → require +$0.20.

RANGE VWAP Pullback (all 5):
  1. price within ±0.15% of VWAP
  2. volume decreasing last 2 bars
  3. 2 consecutive green 1-min bars
  4. RSI14 45–65
  5. not new session low

RANGE Volume Absorption (all 4):
  1. bar vol > 3× avg of prior 5 bars
  2. close within ±0.15% VWAP or support
  3. not new session low
  4. EMA21 < price

TREND ORB (≤11:00 ET):
  1. ORB_HIGH = max(H) first 3 five-min bars since 9:30 ET
  2. last bar closes above ORB_HIGH
  3. breakout vol > ORB avg vol

TREND DOWN: no long until price ≥1.5% above session_low AND 3 consecutive 5-min bars above EMA21.

Post-stop-hunt: SL swept <$0.25 + reversal ≤2 bars + vol ≥ avg + <3 bars since sweep → re-entry valid.

### 7. ORDER
shares = floor(equity × 0.10 / price). Skip if < 2.
Round ALL prices to 2 decimals.
alpaca_order(symbol, shares, "buy") → alpaca_get_order(id) → confirm fill
SL = round(fill − 2×ATR, 2). TP1 = round(fill + 2×ATR, 2). TP2 = resistance or round(fill + 4×ATR, 2).
db_trade(asset, "buy", shares, fill, order_id, "SL=X TP1=Y TP2=Z ATR=A")

### 8. LOG
db_log(asset, "5m", signal, confidence, {ema9,ema21,vwap,rsi,atr}, summary)
db_heartbeat("running", "Active HH:MM ET", {regime, positions, daily_pnl})

## PERMANENT CONSTRAINTS
Long only. No shorts. Universe: QQQ, TSLA, RIVN, OKLO, COST.
Never trade: BA, LMT, TXN, NOC, RTX, GD, HII, MRNA, PFE.
Max 2 simultaneous positions. SL after fill only. All prices to 2 decimal places.
On tool error: log in db_log and continue.`

export async function GET(req: NextRequest) {
  const p = req.nextUrl.searchParams
  const denied = checkSecret(p.get('secret'))
  if (denied) return denied

  const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY })

  const messages: Anthropic.MessageParam[] = [{
    role: 'user',
    content: 'Execute one Pulse v2.4 trading cycle now. Start with alpaca_clock.',
  }]

  let toolCalls = 0
  const MAX_CALLS = 60

  try {
    while (toolCalls < MAX_CALLS) {
      const response = await anthropic.messages.create({
        model: 'claude-sonnet-4-6',
        max_tokens: 4096,
        system: SYSTEM,
        tools: TOOLS,
        messages,
      })

      messages.push({ role: 'assistant', content: response.content })

      if (response.stop_reason === 'end_turn') {
        const textBlock = response.content.find(b => b.type === 'text')
        const summary = textBlock && 'text' in textBlock ? textBlock.text : 'Cycle complete'
        return NextResponse.json({ ok: true, summary, tool_calls: toolCalls })
      }

      if (response.stop_reason !== 'tool_use') {
        return NextResponse.json({ ok: false, error: `Unexpected stop: ${response.stop_reason}`, tool_calls: toolCalls })
      }

      const results: Anthropic.ToolResultBlockParam[] = []
      for (const block of response.content) {
        if (block.type !== 'tool_use') continue
        toolCalls++
        const result = await runTool(block.name, block.input as Record<string, unknown>)
        results.push({ type: 'tool_result', tool_use_id: block.id, content: JSON.stringify(result) })
      }
      messages.push({ role: 'user', content: results })
    }

    return NextResponse.json({ ok: false, error: 'Max tool calls reached', tool_calls: toolCalls })
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ ok: false, error: msg, tool_calls: toolCalls }, { status: 500 })
  }
}
