# Jev-Powered DeFi Yield Scorer

AI-scored DeFi yield opportunities using [Jev](https://openrouter.ai/alpha/jev) typed decisions via OpenRouter. Fetches live yield data from [DeFiLlama](https://defillama.com/) and scores each pool on risk, deposit attractiveness, rug probability, and impermanent loss.

## Architecture

```
DeFiLlama API  →  Scanner (fetch + filter)
                          ↓
              Jev Client (typed decisions, ~30ms, ~$0.00003/pool)
                          ↓
              Scorer (composite ranking)
                          ↓
              JSONL Logger (audit trail)
```

## Setup

```bash
cd ~/Projects/jev-defi-scorer
cp .env.example .env
# Edit .env and add your OpenRouter API key
source .venv/bin/activate
```

## Usage

### Scan DeFiLlama for yield pools
```bash
python run.py scan
python run.py scan --min-tvl 1000000 --chains Ethereum,Arbitrum
python run.py scan --top 50
```

### Score pools with Jev AI
```bash
python run.py score
python run.py score --top-n 10 --min-tvl 500000
```

### View ranked results
```bash
python run.py rank
python run.py rank --top 30 --by apy
```

### View statistics
```bash
python run.py stats
```

## Scoring Dimensions

| Dimension | Type | Scale | Weight |
|-----------|------|-------|--------|
| Risk Tier | choice | blue-chip / moderate / high / degen / avoid | 30% |
| Deposit Score | score | 1-10 | 35% |
| Rug Probability | noul | 0.0-1.0 (30-day horizon) | 20% |
| IL Risk | score | very-low / low / medium / high / very-high | 15% |

## Composite Score

Weighted 0-100 score combining all dimensions:
- **80-100**: Strong opportunity, likely blue-chip
- **60-79**: Moderate opportunity, verify risk factors
- **40-59**: Higher risk, proceed with caution
- **0-39**: High risk or avoid

## Cost

~$0.00003 per pool scored. A full 20-pool scan costs ~$0.0006.

## Configuration

Edit `config.yaml` to adjust:
- TVL/APY filters
- Chain/project filters
- Scoring weights
- Top N pools to score
- JSONL log path

## Files

| File | Purpose |
|------|---------|
| `run.py` | CLI entry point (scan, score, rank, stats) |
| `defi_scanner.py` | DeFiLlama API client + filters |
| `jev_client.py` | OpenRouter Jev decision client |
| `scorer.py` | Scoring pipeline + composite ranking |
| `logger.py` | JSONL audit logger |
| `config.yaml` | Configuration |
| `.env.example` | Environment template |
