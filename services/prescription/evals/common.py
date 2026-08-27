from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import httpx


EVAL_DIR = Path(__file__).resolve().parent
SERVICE_DIR = EVAL_DIR.parent
PROJECT_ROOT = SERVICE_DIR.parents[1]


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_default_env_files(extra_files: Iterable[str]) -> None:
    candidates = [
        EVAL_DIR / ".env",
        SERVICE_DIR / ".env",
        PROJECT_ROOT / ".env.docker",
    ]
    candidates.extend(Path(path) for path in extra_files)
    for path in candidates:
        load_env_file(path)


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line_no, line in enumerate(file, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
    return rows


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]], append: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with path.open(mode, encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def parse_json_object(text: str) -> Optional[Dict[str, Any]]:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if fenced:
        try:
            parsed = json.loads(fenced.group(1))
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(stripped[start:end + 1])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def render_prompt(template: str, **values: Any) -> str:
    rendered = template
    for key, value in values.items():
        replacement = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
        rendered = rendered.replace("{{" + key + "}}", replacement)
    return rendered


def safe_http_error(provider: str, exc: httpx.HTTPStatusError) -> str:
    response = exc.response
    body = response.text[:500] if response is not None else ""
    status = response.status_code if response is not None else "unknown"
    return f"{provider} request failed: status={status}, body={body}"


class LlmJsonClient:
    def __init__(
        self,
        provider: str,
        model: str,
        timeout: float = 180.0,
        temperature: float = 0.0,
    ) -> None:
        self.provider = provider
        self.model = model
        self.timeout = timeout
        self.temperature = temperature

    @property
    def name(self) -> str:
        return f"{self.provider}:{self.model}"

    def complete_json(self, prompt: str) -> Dict[str, Any]:
        if self.provider == "openai":
            return self._complete_openai(prompt)
        if self.provider == "gemini":
            return self._complete_gemini(prompt)
        if self.provider == "anthropic":
            return self._complete_anthropic(prompt)
        raise ValueError(f"Unsupported provider: {self.provider}")

    def _complete_openai(self, prompt: str) -> Dict[str, Any]:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required")
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "Return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(safe_http_error("OpenAI", exc)) from exc
            content = response.json()["choices"][0]["message"]["content"]
        parsed = parse_json_object(content)
        if parsed is None:
            raise RuntimeError(f"OpenAI returned non-JSON content: {content[:500]}")
        return parsed

    def _complete_gemini(self, prompt: str) -> Dict[str, Any]:
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY is required")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": self.temperature,
                "responseMimeType": "application/json",
            },
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, params={"key": api_key}, json=payload)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(safe_http_error("Gemini", exc)) from exc
            parts = response.json()["candidates"][0]["content"]["parts"]
            content = "".join(part.get("text", "") for part in parts)
        parsed = parse_json_object(content)
        if parsed is None:
            raise RuntimeError(f"Gemini returned non-JSON content: {content[:500]}")
        return parsed

    def _complete_anthropic(self, prompt: str) -> Dict[str, Any]:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required")
        payload = {
            "model": self.model,
            "max_tokens": 8192,
            "temperature": self.temperature,
            "system": "Return valid JSON only.",
            "messages": [{"role": "user", "content": prompt}],
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                json=payload,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(safe_http_error("Anthropic", exc)) from exc
            content = "".join(part.get("text", "") for part in response.json().get("content", []))
        parsed = parse_json_object(content)
        if parsed is None:
            raise RuntimeError(f"Anthropic returned non-JSON content: {content[:500]}")
        return parsed
