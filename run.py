"""DeFi Yield Scorer - CLI entry point.

Usage:
    python run.py scan [--min-tvl N] [--min-apy N] [--chains c1,c2]
    python run.py score [--top-n N] [--min-tvl N]
    python run.py rank [--top N] [--by FIELD]
    python run.py stats
"""

import argparse
import json
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from defi_scanner import DeFiScanner
from jev_client import JevClient
from logger import JSONLLogger
from scorer import score_pools, rank_pools


def load_config() -> dict:
    """Load config.yaml from project root."""
    config_path = Path(__file__).parent / "config.yaml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def cmd_scan(args, config):
    """Scan DeFiLlama for yield pools and display top results."""
    scanner_cfg = config.get("scanner", {})
    scanner = DeFiScanner(
        base_url=scanner_cfg.get("base_url", "https://yields.llama.fi"),
        timeout=scanner_cfg.get("timeout", 30),
    )

    scan_kwargs = {
        "min_tvl": args.min_tvl or scanner_cfg.get("min_tvl", 100_000),
        "min_apy": args.min_apy or scanner_cfg.get("min_apy", 0.5),
        "max_apy": scanner_cfg.get("max_apy", 500),
    }
    if args.chains:
        scan_kwargs["chains"] = [c.strip() for c in args.chains.split(",")]
    elif scanner_cfg.get("chains"):
        scan_kwargs["chains"] = scanner_cfg["chains"]

    pools = scanner.scan_and_filter(**scan_kwargs)
    pools.sort(key=lambda p: p["tvl_usd"], reverse=True)

    top_n = args.top or 20
    pools = pools[:top_n]

    print(f"\n{'='*80}")
    print(f"  DeFi Yield Scanner - {len(pools)} pools (top {top_n} by TVL)")
    print(f"{'='*80}")
    print(f"{'Rank':>4} {'Chain':<12} {'Project':<16} {'Symbol':<20} {'TVL ($M)':>10} {'APY%':>8}")
    print(f"{'-'*4} {'-'*12} {'-'*16} {'-'*20} {'-'*10} {'-'*8}")

    for i, p in enumerate(pools, 1):
        tvl_m = p["tvl_usd"] / 1_000_000
        print(f"{i:>4} {p['chain']:<12} {p['project']:<16} {p['symbol']:<20} {tvl_m:>10.2f} {p['apy']:>8.2f}")

    print(f"\nShowing {len(pools)} of {len(pools)} filtered pools")


def cmd_score(args, config):
    """Score pools with Jev and display results."""
    load_dotenv()
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY not set. Copy .env.example to .env and add your key.")
        sys.exit(1)

    scanner_cfg = config.get("scanner", {})
    jev_cfg = config.get("jev", {})
    scoring_cfg = config.get("scoring", {})
    logging_cfg = config.get("logging", {})

    scanner = DeFiScanner(
        base_url=scanner_cfg.get("base_url", "https://yields.llama.fi"),
        timeout=scanner_cfg.get("timeout", 30),
    )
    jev = JevClient(api_key=api_key, model=jev_cfg.get("model"))
    logger = JSONLLogger(path=logging_cfg.get("jsonl_path", "data/scores.jsonl"))

    scan_kwargs = {
        "min_tvl": args.min_tvl or scanner_cfg.get("min_tvl", 100_000),
        "min_apy": scanner_cfg.get("min_apy", 0.5),
        "max_apy": scanner_cfg.get("max_apy", 500),
    }
    if scanner_cfg.get("chains"):
        scan_kwargs["chains"] = scanner_cfg["chains"]

    top_n = args.top_n or scoring_cfg.get("top_n", 20)
    weights = scoring_cfg.get("weights", {})

    scored = score_pools(
        scanner=scanner,
        jev=jev,
        logger=logger,
        top_n=top_n,
        weights=weights,
        scan_kwargs=scan_kwargs,
    )

    if not scored:
        print("No pools scored.")
        return

    # Display results
    print(f"\n{'='*100}")
    print(f"  Jev-DeFi Scorer Results - {len(scored)} pools scored")
    print(f"{'='*100}")
    print(f"{'#':>3} {'Composite':>9} {'Tier':<10} {'Dep':>4} {'Rug%':>6} {'IL':>4} {'Chain':<10} {'Project':<14} {'Symbol':<18} {'APY%':>7} {'TVL($M)':>8}")
    print(f"{'-'*3} {'-'*9} {'-'*10} {'-'*4} {'-'*6} {'-'*4} {'-'*10} {'-'*14} {'-'*18} {'-'*7} {'-'*8}")

    for i, p in enumerate(scored, 1):
        tvl_m = p["tvl_usd"] / 1_000_000
        rug_pct = f"{p.get('rug_probability', 0)*100:.0f}%"
        il_labels = {0: "vlow", 1: "low", 2: "med", 3: "high", 4: "vhigh"}
        il_label = il_labels.get(int(p.get("il_risk_score", 2)), "?")
        print(
            f"{i:>3} {p['composite_score']:>9.1f} "
            f"{p.get('risk_tier', '?'):<10} "
            f"{p.get('deposit_score', 0):>4.0f} "
            f"{rug_pct:>6} "
            f"{il_label:>4} "
            f"{p['chain']:<10} {p['project']:<14} {p['symbol']:<18} "
            f"{p['apy']:>7.2f} {tvl_m:>8.2f}"
        )

    # Summary stats
    avg_composite = sum(p["composite_score"] for p in scored) / len(scored)
    avg_deposit = sum(p.get("deposit_score", 0) for p in scored) / len(scored)
    total_cost = sum(p.get("cost", 0) for p in scored)
    print(f"\nAvg composite: {avg_composite:.1f} | Avg deposit: {avg_deposit:.1f}/10 | Total cost: ${total_cost:.6f}")


def cmd_rank(args, config):
    """Show ranked results from the latest scoring run."""
    logging_cfg = config.get("logging", {})
    logger = JSONLLogger(path=logging_cfg.get("jsonl_path", "data/scores.jsonl"))

    # Get latest batch (unique timestamp)
    records = logger.read_all()
    if not records:
        print("No scoring data found. Run 'python run.py score' first.")
        return

    # Get the latest timestamp
    latest_ts = records[-1]["timestamp"]
    latest = [r for r in records if r["timestamp"] == latest_ts]

    top_n = args.top or 20
    field = args.by or "composite_score"

    latest.sort(key=lambda x: x.get(field, 0), reverse=True)
    latest = latest[:top_n]

    print(f"\nRanked by {field} (from {latest_ts[:19]})")
    print(f"{'#':>3} {'Score':>7} {'Tier':<10} {'Dep':>4} {'Rug%':>6} {'Chain':<10} {'Project':<14} {'Symbol':<18} {'APY%':>7}")
    print(f"{'-'*3} {'-'*7} {'-'*10} {'-'*4} {'-'*6} {'-'*10} {'-'*14} {'-'*18} {'-'*7}")

    for i, p in enumerate(latest, 1):
        rug_pct = f"{p.get('rug_probability', 0)*100:.0f}%"
        print(
            f"{i:>3} {p.get('composite_score', 0):>7.1f} "
            f"{p.get('risk_tier', '?'):<10} "
            f"{p.get('deposit_score', 0):>4.0f} "
            f"{rug_pct:>6} "
            f"{p.get('chain', '?'):<10} "
            f"{p.get('project', '?'):<14} "
            f"{p.get('symbol', '?'):<18} "
            f"{p.get('apy', 0):>7.2f}"
        )


def cmd_stats(args, config):
    """Show aggregate statistics from all scoring runs."""
    logging_cfg = config.get("logging", {})
    logger = JSONLLogger(path=logging_cfg.get("jsonl_path", "data/scores.jsonl"))

    records = logger.read_all()
    if not records:
        print("No scoring data found. Run 'python run.py score' first.")
        return

    print(f"\n{'='*60}")
    print(f"  Scoring Statistics - {len(records)} total records")
    print(f"{'='*60}")

    # Unique pools
    pool_ids = set(r.get("pool_id") for r in records if r.get("pool_id"))
    print(f"Unique pools scored: {len(pool_ids)}")

    # Risk tier distribution
    tiers = {}
    for r in records:
        t = r.get("risk_tier", "unknown")
        tiers[t] = tiers.get(t, 0) + 1
    print(f"\nRisk tier distribution:")
    for tier in ["blue-chip", "moderate", "high", "degen", "avoid", "unknown"]:
        count = tiers.get(tier, 0)
        if count:
            pct = count / len(records) * 100
            bar = "█" * int(pct / 2)
            print(f"  {tier:<10} {count:>4} ({pct:>5.1f}%) {bar}")

    # APY stats
    apys = [r.get("apy", 0) for r in records if r.get("apy")]
    if apys:
        print(f"\nAPY stats:")
        print(f"  Min: {min(apys):.2f}%")
        print(f"  Max: {max(apys):.2f}%")
        print(f"  Avg: {sum(apys)/len(apys):.2f}%")

    # Composite score stats
    composites = [r.get("composite_score", 0) for r in records if r.get("composite_score")]
    if composites:
        print(f"\nComposite score stats:")
        print(f"  Min: {min(composites):.1f}")
        print(f"  Max: {max(composites):.1f}")
        print(f"  Avg: {sum(composites)/len(composites):.1f}")

    # Total cost
    costs = [r.get("cost", 0) for r in records if r.get("cost")]
    if costs:
        print(f"\nTotal Jev API cost: ${sum(costs):.6f}")

    # Chain distribution
    chains = {}
    for r in records:
        c = r.get("chain", "unknown")
        chains[c] = chains.get(c, 0) + 1
    print(f"\nTop chains:")
    for chain, count in sorted(chains.items(), key=lambda x: -x[1])[:10]:
        print(f"  {chain:<16} {count:>4} pools")


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Jev-Powered DeFi Yield Scorer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command")

    # scan
    p_scan = sub.add_parser("scan", help="Scan DeFiLlama for yield pools")
    p_scan.add_argument("--min-tvl", type=float, help="Minimum TVL in USD")
    p_scan.add_argument("--min-apy", type=float, help="Minimum APY %%")
    p_scan.add_argument("--chains", type=str, help="Comma-separated chains")
    p_scan.add_argument("--top", type=int, default=20, help="Show top N pools")

    # score
    p_score = sub.add_parser("score", help="Score pools with Jev AI")
    p_score.add_argument("--top-n", type=int, help="Score top N pools")
    p_score.add_argument("--min-tvl", type=float, help="Minimum TVL filter")

    # rank
    p_rank = sub.add_parser("rank", help="Show ranked results")
    p_rank.add_argument("--top", type=int, default=20, help="Show top N")
    p_rank.add_argument("--by", type=str, default="composite_score", help="Rank field")

    # stats
    sub.add_parser("stats", help="Show aggregate statistics")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    config = load_config()

    commands = {
        "scan": cmd_scan,
        "score": cmd_score,
        "rank": cmd_rank,
        "stats": cmd_stats,
    }
    commands[args.command](args, config)


if __name__ == "__main__":
    main()
