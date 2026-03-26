from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from dataclasses import dataclass

import redis.asyncio as redis

from .config import AppConfig
from .indexing import create_embeddings, open_vectorstore, validate_runtime_readiness


@dataclass(frozen=True, slots=True)
class HealthCheck:
    name: str
    ok: bool
    details: str


@dataclass(frozen=True, slots=True)
class HealthReport:
    ok: bool
    checks: list[HealthCheck]

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "checks": [
                {"name": check.name, "ok": check.ok, "details": check.details}
                for check in self.checks
            ],
        }


def format_health_report(report: HealthReport) -> str:
    lines = ["Status systeme:"]
    for check in report.checks:
        lines.append(f"- {check.name}: {'OK' if check.ok else 'FAIL'} ({check.details})")
    return "\n".join(lines)


def _check_ollama(base_url: str) -> HealthCheck:
    url = base_url.rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        models = payload.get("models", [])
        return HealthCheck("ollama", True, f"{len(models)} model(s) visible")
    except urllib.error.URLError as exc:
        return HealthCheck("ollama", False, str(exc.reason))
    except Exception as exc:
        return HealthCheck("ollama", False, str(exc))


async def build_health_report(config: AppConfig) -> HealthReport:
    checks: list[HealthCheck] = []

    prompt_ok = config.prompt_path.exists() and bool(config.prompt_text.strip())
    checks.append(HealthCheck("prompt", prompt_ok, str(config.prompt_path)))

    docs_ok = config.docs_dir.exists()
    checks.append(HealthCheck("documents", docs_ok, str(config.docs_dir)))

    validation = validate_runtime_readiness(config)
    checks.append(HealthCheck("index", validation.is_ready, validation.status))

    try:
        embeddings = create_embeddings(config)
        open_vectorstore(config, embeddings)
        checks.append(HealthCheck("chroma", True, str(config.chroma_dir)))
    except Exception as exc:
        checks.append(HealthCheck("chroma", False, str(exc)))

    redis_client = None
    try:
        redis_client = redis.from_url(config.redis_url, decode_responses=True)
        await redis_client.ping()
        checks.append(HealthCheck("redis", True, config.redis_url))
    except Exception as exc:
        checks.append(HealthCheck("redis", False, str(exc)))
    finally:
        if redis_client is not None:
            close_method = getattr(redis_client, "aclose", None)
            if close_method is None:
                close_method = getattr(redis_client, "close", None)
            if close_method is not None:
                result = close_method()
                if hasattr(result, "__await__"):
                    await result

    checks.append(await asyncio.to_thread(_check_ollama, config.ollama_base_url))

    return HealthReport(ok=all(check.ok for check in checks), checks=checks)
