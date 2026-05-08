# Market Trading Analysis System

A structured framework for studying market behavior and developing trading strategies using Alpaca (paper trading) and Supabase as the central ledger.

---

## Watched Assets

| Asset | Type | Rationale |
|---|---|---|
| SPY | Equity ETF | S&P 500 benchmark — market pulse |
| QQQ | Equity ETF | Nasdaq 100 — tech/growth proxy |
| TSLA | Equity | High volatility, strong retail interest |
| COST | Equity | Defensive, steady compounder |
| BTC/USD | Crypto | Market-leading crypto, 24/7 |
| ETH/USD | Crypto | DeFi/tech crypto, correlated with BTC |

---

## Infrastructure

| Component | Purpose |
|---|---|
| **Alpaca MCP** | Market data + paper trade execution |
| **Supabase** | Central ledger — trades, snapshots, analysis log |
| **GitHub** | Strategy docs, analysis notes, version control |

---

## Repository Structure

```
/
├── .mcp.json                  # Alpaca MCP server config
├── README.md                  # This file
├── analysis/
│   ├── assets/                # Per-asset analysis files
│   └── market-context/        # Macro, sector, correlation notes
├── strategies/                # Documented trading strategies
├── trades/                    # Paper trade journals
└── supabase/
    └── schema.sql             # Ledger schema
```

---

## Ledger (Supabase)

All activity is recorded in three tables:

- **`trades`** — every paper trade: asset, side, qty, price, timestamp, P&L
- **`market_snapshots`** — periodic price/volume captures per asset
- **`analysis_log`** — dated notes, signals, and indicator readings

---

## Workflow

```
1. Observe  → Pull market data via Alpaca MCP
2. Analyze  → Read price action, indicators, context
3. Hypothesize → Form a trade thesis, document it
4. Execute  → Paper trade via Alpaca
5. Record   → Log to Supabase ledger
6. Review   → Evaluate outcome, update strategy
7. Iterate
```

---

> **Security note:** `.mcp.json` contains paper-trading API keys (no real funds at risk).  
> Never commit live/production keys to version control.
