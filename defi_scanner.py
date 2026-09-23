"""DeFiLlama yield pool scanner."""

import requests
from typing import Any, Dict, List, Optional


class DeFiScanner:
    """Fetches and filters yield pools from DeFiLlama API."""

    def __init__(self, base_url: str = "https://yields.llama.fi", timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def fetch_pools(self) -> List[Dict[str, Any]]:
        """Fetch all yield pools from DeFiLlama."""
        url = f"{self.base_url}/pools"
        resp = requests.get(url, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        # DeFiLlama wraps in {"status": "success", "data": [...]}
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        if isinstance(data, list):
            return data
        raise ValueError(f"Unexpected DeFiLlama response format: {type(data)}")

    def filter_pools(
        self,
        pools: List[Dict[str, Any]],
        min_tvl: float = 100_000,
        min_apy: float = 0.5,
        max_apy: float = 500,
        chains: Optional[List[str]] = None,
        exclude_projects: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Filter pools by TVL, APY, chain, and project."""
        exclude = set(p.lower() for p in (exclude_projects or []))
        chain_set = set(c.lower() for c in chains) if chains else None

        filtered = []
        for p in pools:
            tvl = p.get("tvlUsd") or 0
            apy = p.get("apy") or 0
            project = (p.get("project") or "").lower()
            chain = (p.get("chain") or "").lower()

            if tvl < min_tvl:
                continue
            if apy < min_apy or apy > max_apy:
                continue
            if chain_set and chain not in chain_set:
                continue
            if project in exclude:
                continue

            filtered.append(p)

        return filtered

    def normalize_pool(self, pool: Dict[str, Any]) -> Dict[str, Any]:
        """Extract and normalize pool fields for Jev state."""
        return {
            "pool_id": pool.get("pool", ""),
            "chain": pool.get("chain", "unknown"),
            "project": pool.get("project", "unknown"),
            "symbol": pool.get("symbol", "unknown"),
            "tvl_usd": pool.get("tvlUsd") or 0,
            "apy": pool.get("apy") or 0,
            "apy_base": pool.get("apyBase") or 0,
            "apy_reward": pool.get("apyReward") or 0,
            "stablecoin": pool.get("stablecoin", False),
            "il_risk": pool.get("ilRisk", "unknown"),
            "exposure": pool.get("exposure", "unknown"),
            "pool_meta": pool.get("poolMeta", ""),
            "mu": pool.get("mu"),
            "sigma": pool.get("sigma"),
            "count": pool.get("count"),
        }

    def scan_and_filter(self, **kwargs) -> List[Dict[str, Any]]:
        """Fetch, filter, and normalize in one call."""
        raw = self.fetch_pools()
        filtered = self.filter_pools(raw, **kwargs)
        return [self.normalize_pool(p) for p in filtered]
