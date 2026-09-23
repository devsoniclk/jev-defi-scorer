"""Jev OpenRouter client for typed DeFi risk decisions."""

import os
import requests
from typing import Any, Dict, Optional


class JevClient:
    """Client for Jev typed-decision API via OpenRouter."""

    ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
    MODEL = "typesafe/jev-1.13"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        self.model = model or os.getenv("JEV_MODEL", self.MODEL)
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY required (env var or pass directly)")

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def decide(self, state: str, questions: Dict[str, Any]) -> Dict[str, Any]:
        """Send a decision request to Jev. Returns full response dict."""
        payload = {
            "model": self.model,
            "state": state,
            "questions": questions,
        }
        resp = requests.post(
            self.ENDPOINT,
            headers=self._headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def build_pool_state(pool: Dict[str, Any]) -> str:
        """Build a concise state string for a DeFi pool."""
        parts = [
            f"Chain: {pool['chain']}",
            f"Project: {pool['project']}",
            f"Token: {pool['symbol']}",
            f"TVL: ${pool['tvl_usd']:,.0f}",
            f"APY: {pool['apy']:.2f}% (base: {pool['apy_base']:.2f}%, reward: {pool['apy_reward']:.2f}%)",
            f"Stablecoin pool: {'yes' if pool.get('stablecoin') else 'no'}",
            f"IL risk (DeFiLlama): {pool.get('il_risk', 'unknown')}",
        ]
        if pool.get("pool_meta"):
            parts.append(f"Pool type: {pool['pool_meta']}")
        if pool.get("exposure"):
            parts.append(f"Exposure: {pool['exposure']}")
        return " | ".join(parts)

    @staticmethod
    def defi_risk_questions() -> Dict[str, Any]:
        """Standard DeFi risk questions for Jev."""
        return {
            "risk_tier": {
                "type": "choice",
                "instructions": "What is the risk tier for this DeFi yield pool?",
                "criteria": {
                    "blue-chip": "Established protocol, audited, high TVL, low risk",
                    "moderate": "Known protocol with some risk factors",
                    "high": "Smaller protocol, high APY, notable risk factors",
                    "degen": "Very high risk, unproven protocol, extreme APY",
                    "avoid": "Likely scam, exploit risk, or fundamentally broken",
                },
            },
            "deposit_score": {
                "type": "score",
                "instructions": "Rate the deposit attractiveness from 1 (terrible) to 10 (excellent). Consider APY vs risk, TVL, and protocol reputation.",
                "criteria": [
                    "1-terrible",
                    "2-very-poor",
                    "3-poor",
                    "4-below-average",
                    "5-average",
                    "6-above-average",
                    "7-good",
                    "8-very-good",
                    "9-excellent",
                    "10-outstanding",
                ],
            },
            "rug_probability": {
                "type": "noul",
                "instructions": "Is this pool likely to suffer a rug pull, exploit, or hack within 30 days?",
            },
            "il_risk": {
                "type": "score",
                "instructions": "Rate the impermanent loss risk for this pool.",
                "criteria": [
                    "very-low",
                    "low",
                    "medium",
                    "high",
                    "very-high",
                ],
            },
        }

    def score_pool(self, pool: Dict[str, Any]) -> Dict[str, Any]:
        """Score a single pool through Jev. Returns raw Jev response."""
        state = self.build_pool_state(pool)
        questions = self.defi_risk_questions()
        return self.decide(state, questions)
