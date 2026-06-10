"""Benchmark helper for dashboard model testing."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

from pr_agent.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler
from pr_agent.algo.litellm_credentials import temporary_litellm_credentials
from pr_agent.log import get_logger

BENCHMARK_SYSTEM_PROMPT = (
    "You are a senior code reviewer. Respond with valid JSON only, no markdown fences."
)

BENCHMARK_USER_PROMPT = """Review the following pull request diff and produce a structured JSON review.

## File: src/services/payment_processor.py
```diff
@@ -45,12 +45,28 @@ class PaymentProcessor:
-    def charge(self, amount, card_token):
-        response = self.gateway.charge(amount, card_token)
-        return response.status == 'approved'
+    def charge(self, amount: float, card_token: str) -> ChargeResult:
+        if amount <= 0:
+            raise ValueError("amount must be positive")
+        if not card_token or len(card_token) < 8:
+            raise ValueError("invalid card token")
+        response = self.gateway.charge(amount=amount, token=card_token)
+        if response.status != 'approved':
+            self.audit.log_declined(response.transaction_id, amount)
+            return ChargeResult(success=False, transaction_id=response.transaction_id)
+        self.audit.log_approved(response.transaction_id, amount)
+        return ChargeResult(success=True, transaction_id=response.transaction_id)
```

## File: src/services/payment_processor_test.py
```diff
@@ -10,6 +10,18 @@ class TestPaymentProcessor:
         processor = PaymentProcessor(mock_gateway)
         result = processor.charge(100.0, 'tok_valid123')
         assert result.success is True
+
+    def test_charge_rejects_zero_amount(self):
+        processor = PaymentProcessor(mock_gateway)
+        with pytest.raises(ValueError):
+            processor.charge(0, 'tok_valid123')
+
+    def test_charge_rejects_short_token(self):
+        processor = PaymentProcessor(mock_gateway)
+        with pytest.raises(ValueError):
+            processor.charge(50.0, 'short')
```

## File: src/models/charge_result.py
```diff
+from dataclasses import dataclass
+
+@dataclass
+class ChargeResult:
+    success: bool
+    transaction_id: str
```

Return JSON with keys:
- "summary": one paragraph overview
- "key_issues": array of objects with "severity" (low|medium|high), "title", "detail"
- "security_concerns": array of strings
- "test_coverage_assessment": string
- "estimated_review_effort_1_to_5": integer

Be specific and reference the diff. Include at least three key_issues entries."""


@dataclass
class ModelTestResult:
    success: bool
    model: str
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    output_tokens_per_sec: float = 0.0
    total_tokens_per_sec: float = 0.0
    finish_reason: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


async def run_model_benchmark(
    model: str,
    temperature: float = 0.2,
    secrets: Optional[Dict[str, Any]] = None,
) -> ModelTestResult:
    """Run a substantive completion against the given model and measure latency/tokens."""
    if not model or not model.strip():
        return ModelTestResult(success=False, model=model or "", error="Model is required")

    model = model.strip()
    started = time.perf_counter()

    try:
        with temporary_litellm_credentials(secrets):
            handler = LiteLLMAIHandler(use_injected_credentials=True)
            _response, finish_reason, token_usage = await handler.chat_completion(
                model=model,
                system=BENCHMARK_SYSTEM_PROMPT,
                user=BENCHMARK_USER_PROMPT,
                temperature=temperature,
            )
    except Exception as exc:
        get_logger().warning(f"Model benchmark failed for {model}: {exc}")
        latency_ms = (time.perf_counter() - started) * 1000
        return ModelTestResult(
            success=False,
            model=model,
            latency_ms=round(latency_ms, 2),
            error=str(exc),
        )

    latency_ms = (time.perf_counter() - started) * 1000
    input_tokens = int((token_usage or {}).get("input_tokens") or 0)
    output_tokens = int((token_usage or {}).get("output_tokens") or 0)
    seconds = max(latency_ms / 1000.0, 0.001)
    output_tps = round(output_tokens / seconds, 2)
    total_tps = round((input_tokens + output_tokens) / seconds, 2)

    return ModelTestResult(
        success=True,
        model=model,
        latency_ms=round(latency_ms, 2),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        output_tokens_per_sec=output_tps,
        total_tokens_per_sec=total_tps,
        finish_reason=finish_reason,
    )
