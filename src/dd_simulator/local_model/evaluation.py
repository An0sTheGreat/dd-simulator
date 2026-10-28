"""Non-destructive local model evaluation and local report generation."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from dd_simulator.local_model.client import LocalModelClient, LocalModelModelInfo
from dd_simulator.local_model.errors import LocalModelError, LocalModelResponseError


@dataclass(frozen=True, slots=True)
class ModelEvaluation:
    model_id: str
    display_name: str
    samples: int
    valid_responses: int
    strict_first_passes: int
    compatibility_retries: int
    average_latency_ms: int
    prompt_tokens: int
    completion_tokens: int
    tokens_per_second: float
    quality_score: int
    context_length: int | None
    memory_bytes: int | None
    evaluated_at: str
    recommendation: str
    errors: tuple[str, ...] = ()

    @property
    def json_success_rate(self) -> float:
        return self.valid_responses / self.samples if self.samples else 0.0

    def status_line(self) -> str:
        return (
            f"{self.display_name}: {self.valid_responses}/{self.samples} valid, "
            f"{self.average_latency_ms} ms average, {self.tokens_per_second:.1f} tok/s, "
            f"quality {self.quality_score}/100. {self.recommendation}"
        )


class ModelEvaluationService:
    """Probe one selected model without reading or changing campaign state."""

    def __init__(self, client: LocalModelClient, report_directory: Path) -> None:
        self.client = client
        self.report_directory = Path(report_directory)

    def evaluate(self, model_id: str, *, samples: int = 3) -> ModelEvaluation:
        selected = " ".join(model_id.split())
        if not selected:
            raise LocalModelResponseError("Select a loaded model before running evaluation.")
        sample_count = max(1, min(int(samples), 5))
        model = self._model_details(selected)
        valid = strict_valid = retries = prompt_tokens = completion_tokens = 0
        elapsed_values: list[float] = []
        quality_values: list[int] = []
        errors: list[str] = []

        for index in range(sample_count):
            started = perf_counter()
            response: dict[str, Any] | None = None
            parsed: object | None = None
            try:
                response = self.client._json_request(  # noqa: SLF001 - integration boundary
                    "/chat/completions",
                    method="POST",
                    payload=self._payload(selected, index=index, strict=True),
                )
                parsed = self._parse_probe(response, index=index)
                strict_valid += 1
            except LocalModelError as exc:
                retries += 1
                try:
                    response = self.client._json_request(  # noqa: SLF001
                        "/chat/completions",
                        method="POST",
                        payload=self._payload(selected, index=index, strict=False),
                    )
                    parsed = self._parse_probe(response, index=index)
                except LocalModelError as retry_exc:
                    errors.append(str(retry_exc or exc))
            elapsed = max(0.0001, perf_counter() - started)
            elapsed_values.append(elapsed)
            if response is not None:
                usage = response.get("usage")
                if isinstance(usage, dict):
                    prompt_tokens += self._nonnegative_int(usage.get("prompt_tokens"))
                    completion_tokens += self._nonnegative_int(usage.get("completion_tokens"))
            if parsed is not None:
                valid += 1
                quality_values.append(100)

        total_seconds = sum(elapsed_values)
        average_ms = round(total_seconds * 1000 / sample_count)
        token_rate = completion_tokens / total_seconds if total_seconds else 0.0
        quality = round(sum(quality_values) / len(quality_values)) if quality_values else 0
        recommendation = self._recommendation(valid, sample_count, average_ms, quality)
        result = ModelEvaluation(
            model_id=selected,
            display_name=model.display_name,
            samples=sample_count,
            valid_responses=valid,
            strict_first_passes=strict_valid,
            compatibility_retries=retries,
            average_latency_ms=average_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            tokens_per_second=round(token_rate, 2),
            quality_score=quality,
            context_length=model.context_length,
            memory_bytes=model.memory_bytes,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
            recommendation=recommendation,
            errors=tuple(errors[-3:]),
        )
        self.write_report(result)
        return result

    def _model_details(self, model_id: str) -> LocalModelModelInfo:
        details = self.client.discover_model_details()
        for item in details:
            if model_id in {item.model_id, item.instance_id}:
                if not item.loaded:
                    raise LocalModelResponseError(
                        f"{item.display_name} is installed but not loaded on the local model server."
                    )
                return item
        raise LocalModelResponseError(
            "The selected model is no longer available. Refresh the model list."
        )

    @staticmethod
    def _payload(model_id: str, *, index: int, strict: bool) -> dict[str, Any]:
        context = {
            "name": "Aria Vale",
            "ancestry": "Human",
            "class_or_archetype": "Ranger",
            "world_type": "Dark fantasy",
            "tone": "Mysterious",
            "starting_region": "Forest village",
            "starting_location": "Tavern",
            "content_preferences": "No graphic injury",
        }
        contract = index % 3
        if contract < 2:
            section = "body_description" if contract == 0 else "campaign_name"
            return LocalModelClient._option_payload(  # noqa: SLF001
                model=model_id,
                section=section,
                context=context,
                retry=not strict,
            )
        return LocalModelClient._campaign_payload(  # noqa: SLF001
            model=model_id,
            context={"campaign": context, "player": {"name": "Aria Vale"}},
            retry=not strict,
        )

    @staticmethod
    def _parse_probe(response: dict[str, Any], *, index: int) -> object:
        contract = index % 3
        if contract < 2:
            return LocalModelClient._parse_options(  # noqa: SLF001
                response,
                section="body_description" if contract == 0 else "campaign_name",
            )
        return LocalModelClient._parse_campaign_details(response)  # noqa: SLF001

    @staticmethod
    def _nonnegative_int(value: Any) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _recommendation(valid: int, samples: int, latency_ms: int, quality: int) -> str:
        if valid < samples:
            return "Not recommended until Character Creation reliability improves."
        if quality >= 90 and latency_ms <= 8000:
            return "Recommended for primary gameplay generation."
        if quality >= 80:
            return "Usable; compare latency and narration quality with another loaded model."
        return "Use only as a fallback model."

    def write_report(self, result: ModelEvaluation) -> tuple[Path, Path]:
        self.report_directory.mkdir(parents=True, exist_ok=True)
        json_path = self.report_directory / "latest-model-evaluation.json"
        markdown_path = self.report_directory / "latest-model-evaluation.md"
        json_path.write_text(json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")
        memory = (
            f"{result.memory_bytes / (1024 ** 3):.1f} GiB"
            if result.memory_bytes is not None
            else "Not reported by the model server"
        )
        context = str(result.context_length or "Not reported by the model server")
        markdown_path.write_text(
            "# Latest Local Model Evaluation\n\n"
            f"- Model: `{result.model_id}`\n"
            f"- Evaluated: {result.evaluated_at}\n"
            f"- Valid schema responses: {result.valid_responses}/{result.samples}\n"
            f"- Strict first passes: {result.strict_first_passes}/{result.samples}\n"
            f"- Compatibility retries: {result.compatibility_retries}\n"
            f"- Average latency: {result.average_latency_ms} ms\n"
            f"- Completion speed: {result.tokens_per_second:.1f} tokens/second\n"
            f"- Quality score: {result.quality_score}/100\n"
            f"- Reported context limit: {context}\n"
            f"- Reported loaded memory: {memory}\n\n"
            f"## Recommendation\n\n{result.recommendation}\n",
            encoding="utf-8",
        )
        return json_path, markdown_path
