"""Grounded explanation: context -> provider -> verification.

The dependency direction that matters: this module consumes the engine's output
and can never influence it.  Remove the AI entirely and the platform loses an
explanation panel and nothing else.

The retry-on-contradiction loop is the interesting part.  When the verifier
finds a claim that contradicts the recording, the answer is regenerated once
with the contradiction quoted back.  That is condition A4 in the RQ3 protocol,
and it is only possible because the execution is a queryable typed record rather
than a rendering.
"""

from __future__ import annotations

import json
import time
from typing import Any

from ..ai import modes, template
from ..ai.clients import LLMClient, LLMResponse, NullClient, build as build_client
from ..ai.context import AIContext, ContextBuilder
from ..ai.verifier import ClaimVerifier, GroundingReport
from ..config import SETTINGS, Settings
from ..plugins.registry import REGISTRY as PLUGINS
from .execution_service import ExecutionService


class AIService:
    def __init__(self, executions: ExecutionService,
                 settings: Settings | None = None,
                 client: LLMClient | None = None) -> None:
        self.executions = executions
        self.settings = settings or SETTINGS
        self.client = client or (
            build_client(self.settings.ai_provider, self.settings.ai_model)
            if self.settings.ai_enabled else NullClient()
        )

    # ------------------------------------------------------------------
    def ask(self, execution_id: str, step: int, mode: str = "explain_line",
            question: str = "", focus: dict[str, Any] | None = None,
            use_cache: bool = True) -> dict[str, Any]:
        db = self.executions.db
        mode = mode if mode in modes.MODES else modes.DEFAULT_MODE
        question = (question or modes.get(mode).instruction).strip()[:1000]

        if use_cache:
            cached = db.find_ai_answer(execution_id, step, mode, question)
            if cached and cached.get("answer"):
                return {
                    "answer": cached["answer"],
                    "provider": cached["provider"],
                    "model": cached["model"],
                    "grounding": json.loads(cached["grounding_json"] or "{}"),
                    "cached": True,
                    "mode": mode,
                    "step": step,
                }

        ctx = self.build_context(execution_id, step, mode, question, focus)
        state = self.executions.state_at(execution_id, step)
        analytics = self.executions.analytics(execution_id)
        summary = self.executions.summary(execution_id)
        verifier = ClaimVerifier(
            state, analytics, source_lines=len(summary["source"].splitlines())
        )

        started = time.perf_counter()
        answer, provider, model, tokens, notice = self._generate(ctx, verifier)
        report = verifier.verify(answer)
        latency_ms = (time.perf_counter() - started) * 1000.0

        db.save_ai_answer(
            execution_id=execution_id,
            step=step,
            mode=mode,
            question=question,
            answer=answer,
            provider=provider,
            model=model,
            grounding_json=json.dumps(report.to_dict()),
            tokens_in=tokens[0],
            tokens_out=tokens[1],
            latency_ms=latency_ms,
        )
        return {
            "answer": answer,
            "provider": provider,
            "model": model,
            "grounding": report.to_dict(),
            "context_summary": {
                "events_used": len(ctx.recent_events),
                "causal_chain_length": len(ctx.causal_chain),
                "tokens_in": tokens[0],
                "tokens_out": tokens[1],
            },
            "notice": notice,
            "cached": False,
            "mode": mode,
            "step": step,
            "latency_ms": round(latency_ms, 2),
        }

    # ------------------------------------------------------------------
    def build_context(self, execution_id: str, step: int, mode: str,
                      question: str, focus: dict[str, Any] | None) -> AIContext:
        summary = self.executions.summary(execution_id)
        timeline = self.executions.timeline(execution_id)
        algorithm = None
        if summary.get("algorithm_id"):
            try:
                algorithm = PLUGINS.get(summary["algorithm_id"]).to_dict()
            except Exception:
                algorithm = None
        builder = ContextBuilder(
            timeline, summary["source"], summary.get("structure"), algorithm
        )
        return builder.build(
            step, question, mode, focus,
            analytics=self.executions.analytics(execution_id),
        )

    def _generate(self, ctx: AIContext,
                  verifier: ClaimVerifier) -> tuple[str, str, str, tuple[int, int], str]:
        fallback = template.explain(ctx)
        if not self.settings.ai_enabled or not self.client.available():
            reason = (
                "AI is disabled for this deployment"
                if not self.settings.ai_enabled
                else "no LLM provider is configured"
            )
            return (
                fallback, "template", "",
                (0, 0),
                f"{reason}; this explanation was generated deterministically "
                f"from the recorded execution.",
            )

        system, user = modes.build_prompt(ctx.mode, ctx.render(), ctx.question)
        response: LLMResponse = self.client.complete(
            system, user, self.settings.ai_max_output_tokens
        )
        if response.error or not response.text.strip():
            return (
                fallback, "template", "",
                (0, 0),
                f"the AI provider was unavailable ({response.error or 'empty response'}); "
                f"this explanation was generated deterministically from the trace.",
            )

        report = verifier.verify(response.text)
        if report.contradicted:
            # One retry, with the contradiction quoted back verbatim.
            retry_user = (
                user
                + "\n\nYOUR PREVIOUS ANSWER CONTRADICTED THE TRACE: "
                + report.contradiction_summary()
                + "\nRewrite the answer using only values from the context above."
            )
            retry = self.client.complete(
                system, retry_user, self.settings.ai_max_output_tokens
            )
            if retry.text.strip() and not retry.error:
                retry_report = verifier.verify(retry.text)
                if retry_report.contradicted <= report.contradicted:
                    return (
                        retry.text.strip(), response.provider, response.model,
                        (response.tokens_in + retry.tokens_in,
                         response.tokens_out + retry.tokens_out),
                        "the first answer contradicted the recorded state and was "
                        "regenerated.",
                    )
        return (
            response.text.strip(), response.provider, response.model,
            (response.tokens_in, response.tokens_out), "",
        )

    # ------------------------------------------------------------------
    def provider_status(self) -> dict[str, Any]:
        return {
            "enabled": self.settings.ai_enabled,
            "provider": getattr(self.client, "name", "null"),
            "model": getattr(self.client, "model", ""),
            "available": self.client.available(),
            "fallback": "template",
            "modes": modes.catalog(),
        }
