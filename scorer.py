"""Scorer: orchestrates scanning + Jev scoring + ranking."""

import time
from typing import Any, Dict, List, Optional

from defi_scanner import DeFiScanner
from jev_client import JevClient
from logger import JSONLLogger


# Risk tier ordering (lower index = lower risk)
RISK_TIER_ORDER = {
    "blue-chip": 0,
    "moderate": 1,
    "high": 2,
    "degen": 3,
    "avoid": 4,
}

# IL risk ordering
IL_RISK_ORDER = {
    "very-low": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "very-high": 4,
}


def extract_score(response: Dict[str, Any]) -> Dict[str, Any]:
    """Extract scored fields from Jev response into flat dict."""
    answers = response.get("answers", {})

    risk_tier = answers.get("risk_tier", {})
    deposit = answers.get("deposit_score", {})
    rug = answers.get("rug_probability", {})
    il = answers.get("il_risk", {})

    return {
        "risk_tier": risk_tier.get("choice", "unknown"),
        "risk_tier_confidence": risk_tier.get("confidence", 0),
        "deposit_score": deposit.get("score", 0),
        "deposit_confidence": deposit.get("confidence", 0),
        "rug_probability": rug.get("noul", 0),
        "il_risk_score": il.get("score", 0),
        "il_risk_confidence": il.get("confidence", 0),
        "cost": response.get("usage", {}).get("cost", 0),
    }


def compute_composite_score(scored: Dict[str, Any], weights: Dict[str, float]) -> float:
    """Compute a 0-100 composite score from Jev scores."""
    # Deposit score: already 0-10, normalize to 0-100
    deposit_norm = (scored.get("deposit_score", 5)) * 10

    # Risk tier: invert (blue-chip=100, avoid=0)
    tier = scored.get("risk_tier", "moderate")
    tier_idx = RISK_TIER_ORDER.get(tier, 2)
    risk_norm = max(0, 100 - (tier_idx * 25))

    # Rug probability: invert (0% = 100, 100% = 0)
    rug_prob = scored.get("rug_probability", 0.5)
    rug_norm = max(0, (1 - rug_prob) * 100)

    # IL risk: invert
    il_score = scored.get("il_risk_score", 2)
    il_norm = max(0, 100 - (il_score * 25))

    composite = (
        weights.get("deposit_score", 0.35) * deposit_norm
        + weights.get("risk_tier", 0.30) * risk_norm
        + weights.get("rug_probability", 0.20) * rug_norm
        + weights.get("il_risk", 0.15) * il_norm
    )
    return round(composite, 2)


def rank_pools(scored_pools: List[Dict[str, Any]], weights: Dict[str, float]) -> List[Dict[str, Any]]:
    """Add composite_score and sort descending."""
    for p in scored_pools:
        p["composite_score"] = compute_composite_score(p, weights)
    scored_pools.sort(key=lambda x: x["composite_score"], reverse=True)
    return scored_pools


def score_pools(
    scanner: DeFiScanner,
    jev: JevClient,
    logger: JSONLLogger,
    top_n: int = 20,
    weights: Optional[Dict[str, float]] = None,
    scan_kwargs: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Full pipeline: scan -> filter -> score with Jev -> rank -> log."""
    if weights is None:
        weights = {
            "deposit_score": 0.35,
            "risk_tier": 0.30,
            "rug_probability": 0.20,
            "il_risk": 0.15,
        }
    if scan_kwargs is None:
        scan_kwargs = {}

    # 1. Scan and filter pools
    pools = scanner.scan_and_filter(**scan_kwargs)
    print(f"Fetched {len(pools)} pools after filtering")

    # 2. Take top N by TVL (best proxies first)
    pools.sort(key=lambda p: p["tvl_usd"], reverse=True)
    if top_n > 0:
        pools = pools[:top_n]
    print(f"Scoring top {len(pools)} pools...")

    # 3. Score each pool with Jev
    scored = []
    for i, pool in enumerate(pools):
        pool_label = f"{pool['chain']}:{pool['project']}:{pool['symbol']}"
        print(f"  [{i+1}/{len(pools)}] {pool_label}...", end=" ", flush=True)
        try:
            resp = jev.score_pool(pool)
            scores = extract_score(resp)
            pool.update(scores)
            pool["composite_score"] = 0  # computed after ranking
            scored.append(pool)
            tier = scores["risk_tier"]
            deposit = scores["deposit_score"]
            print(f"tier={tier} deposit={deposit}/10")
        except Exception as e:
            print(f"FAILED: {e}")
            continue
        # Rate limit courtesy
        time.sleep(0.1)

    # 4. Rank by composite
    scored = rank_pools(scored, weights)

    # 5. Log results
    if scored:
        log_records = []
        for p in scored:
            log_records.append({
                "pool_id": p.get("pool_id"),
                "chain": p["chain"],
                "project": p["project"],
                "symbol": p["symbol"],
                "tvl_usd": p["tvl_usd"],
                "apy": p["apy"],
                "risk_tier": p.get("risk_tier"),
                "deposit_score": p.get("deposit_score"),
                "rug_probability": p.get("rug_probability"),
                "il_risk_score": p.get("il_risk_score"),
                "composite_score": p.get("composite_score"),
                "cost": p.get("cost", 0),
            })
        logger.log_batch(log_records)
        print(f"\nLogged {len(log_records)} scored pools")

    return scored
