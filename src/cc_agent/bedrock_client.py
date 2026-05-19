"""Boto3 Bedrock Converse wrapper with retries."""

from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from .config import BedrockConfig


@dataclass
class ConverseResponse:
    content_blocks: list[dict[str, Any]]
    stop_reason: str
    usage: dict[str, Any]
    model_id: str

    def text_blocks(self) -> list[str]:
        return [b["text"] for b in self.content_blocks if "text" in b]

    def tool_uses(self) -> list[dict[str, Any]]:
        return [b["toolUse"] for b in self.content_blocks if "toolUse" in b]


class BedrockClient:
    """Thin wrapper around boto3 bedrock-runtime client.converse."""

    def __init__(self, config: BedrockConfig) -> None:
        self._config = config
        region = self._resolve_region(config.region)
        boto_cfg = BotoConfig(
            connect_timeout=10,
            read_timeout=config.timeout_seconds,
            retries={"max_attempts": 3, "mode": "standard"},
        )
        self._client = boto3.client("bedrock-runtime", region_name=region, config=boto_cfg)

    @staticmethod
    def _resolve_region(configured: str | None) -> str | None:
        if configured:
            return configured
        return (
            os.environ.get("AWS_REGION")
            or os.environ.get("AWS_DEFAULT_REGION")
            or None  # boto3 will fall back to profile
        )

    def converse(
        self,
        model_id: str,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tool_schemas: list[dict[str, Any]],
    ) -> ConverseResponse:
        request: dict[str, Any] = {
            "modelId": model_id,
            "messages": messages,
            "system": [{"text": system_prompt}],
            "inferenceConfig": {
                "maxTokens": self._config.max_tokens,
                "temperature": self._config.temperature,
            },
        }
        if tool_schemas:
            request["toolConfig"] = {"tools": tool_schemas}

        response = self._call_with_retry(request)

        message = response.get("output", {}).get("message", {})
        content = message.get("content", []) or []
        stop_reason = response.get("stopReason", "end_turn")
        usage = response.get("usage", {}) or {}

        return ConverseResponse(
            content_blocks=content,
            stop_reason=stop_reason,
            usage=usage,
            model_id=model_id,
        )

    def _call_with_retry(self, request: dict[str, Any]) -> dict[str, Any]:
        max_retries = 4
        for attempt in range(max_retries):
            try:
                return self._client.converse(**request)
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "")
                if code in {"ThrottlingException", "ServiceUnavailableException", "InternalServerException"} and attempt < max_retries - 1:
                    delay = min(2**attempt + random.random(), 10.0)
                    time.sleep(delay)
                    continue
                raise
        raise RuntimeError("retry loop exited without return")  # unreachable
