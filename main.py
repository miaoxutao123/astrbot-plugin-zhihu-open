"""AstrBot Zhihu Open Platform plugin.

Provides Zhihu Open Platform LLM tools for:
- Zhihu site search
- Global web search
- Zhihu hot list
- Zhida chat completion
"""

from __future__ import annotations

import html
import json
import re
import time
from typing import Any

import httpx

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star, register
from astrbot.core.star.filter.command import GreedyStr


PLUGIN_NAME = "astrbot_plugin_zhihu_open"
ZHIHU_API_BASE = "https://developer.zhihu.com"
ZHIHU_SEARCH_PATH = "/api/v1/content/zhihu_search"
GLOBAL_SEARCH_PATH = "/api/v1/content/global_search"
HOT_LIST_PATH = "/api/v1/content/hot_list"
ZHIDA_CHAT_PATH = "/v1/chat/completions"
ZHIDA_MODELS = {
    "zhida-fast-1p5",
    "zhida-thinking-1p5",
    "zhida-agent",
}
ZHIHU_TOOL_NAMES = {
    "zhihu_search_tool",
    "zhihu_global_search_tool",
    "zhihu_hot_list_tool",
    "zhihu_zhida_tool",
}


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _strip_html(value: str) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _truncate(value: str, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


class ZhihuOpenClient:
    """Thin async client for Zhihu Open Platform."""

    def __init__(
        self,
        *,
        access_secret: str,
        timeout_seconds: int = 30,
        proxy_url: str | None = None,
    ) -> None:
        self.access_secret = access_secret.strip()
        self.timeout_seconds = _clamp(int(timeout_seconds), 5, 120)
        self.proxy_url = proxy_url.strip() if proxy_url else None
        self._client: httpx.AsyncClient | None = None

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            kwargs: dict[str, Any] = {
                "base_url": ZHIHU_API_BASE,
                "timeout": self.timeout_seconds,
                "follow_redirects": True,
            }
            if self.proxy_url:
                kwargs["proxy"] = self.proxy_url
            self._client = httpx.AsyncClient(**kwargs)
        return self._client

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_secret}",
            "X-Request-Timestamp": str(int(time.time())),
            "Content-Type": "application/json",
        }

    async def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        client = await self._get_client()
        response = await client.get(path, params=params, headers=self._headers())
        return await self._parse_response(response)

    async def post_json(
        self,
        path: str,
        *,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        client = await self._get_client()
        response = await client.post(path, json=body, headers=self._headers())
        return await self._parse_response(response)

    async def _parse_response(self, response: httpx.Response) -> dict[str, Any]:
        content_type = response.headers.get("content-type", "")
        try:
            payload = response.json()
        except Exception:
            payload = None

        if response.status_code >= 400:
            detail = ""
            if isinstance(payload, dict):
                if "error" in payload and isinstance(payload["error"], dict):
                    err = payload["error"]
                    detail = (
                        err.get("message")
                        or err.get("code")
                        or json.dumps(err, ensure_ascii=False)
                    )
                else:
                    detail = payload.get("Message") or payload.get("msg") or ""
            if not detail:
                detail = _truncate(response.text, 300)
            raise RuntimeError(
                f"Zhihu API request failed: HTTP {response.status_code}, {detail or content_type}"
            )

        if isinstance(payload, dict):
            return payload

        raise RuntimeError(
            f"Zhihu API returned non-JSON payload: {content_type or 'unknown content-type'}"
        )


@register(
    PLUGIN_NAME,
    "OpenAI",
    "知乎开放平台插件，提供知乎搜索、全网搜索、热榜与直答 LLM Tools",
    "0.1.0",
)
class ZhihuOpenPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.config = config
        self._client: ZhihuOpenClient | None = None

    async def initialize(self) -> None:
        saved_secret = await self.get_kv_data("access_secret", "")
        if saved_secret:
            self.config["access_secret"] = saved_secret
            logger.info("[%s] restored access_secret from plugin KV store", PLUGIN_NAME)

    async def terminate(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    def _has_access_secret(self) -> bool:
        return bool(str(self.config.get("access_secret", "") or "").strip())

    async def _save_access_secret(self, secret: str) -> None:
        cleaned = secret.strip()
        self.config["access_secret"] = cleaned
        self.config.save_config()
        await self.put_kv_data("access_secret", cleaned)
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def _clear_access_secret(self) -> None:
        self.config["access_secret"] = ""
        self.config.save_config()
        await self.delete_kv_data("access_secret")
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def _get_client(self) -> ZhihuOpenClient:
        secret = str(self.config.get("access_secret", "") or "").strip()
        if not secret:
            raise RuntimeError(
                "Zhihu Access Secret is not configured. Use /zhihu set-secret <secret> first."
            )
        if self._client is None or self._client.access_secret != secret:
            if self._client is not None:
                await self._client.close()
            self._client = ZhihuOpenClient(
                access_secret=secret,
                timeout_seconds=int(self.config.get("timeout_seconds", 30) or 30),
                proxy_url=str(self.config.get("proxy_url", "") or "").strip() or None,
            )
        return self._client

    async def _zhihu_search(self, query: str, count: int) -> dict[str, Any]:
        client = await self._get_client()
        return await client.get_json(
            ZHIHU_SEARCH_PATH,
            params={
                "Query": query,
                "Count": _clamp(count, 1, 10),
            },
        )

    async def _global_search(self, query: str, count: int) -> dict[str, Any]:
        client = await self._get_client()
        return await client.get_json(
            GLOBAL_SEARCH_PATH,
            params={
                "Query": query,
                "Count": _clamp(count, 1, 20),
            },
        )

    async def _hot_list(self, limit: int) -> dict[str, Any]:
        client = await self._get_client()
        return await client.get_json(
            HOT_LIST_PATH,
            params={
                "Limit": _clamp(limit, 1, 30),
            },
        )

    async def _zhida(self, query: str, model: str, stream: bool = False) -> dict[str, Any]:
        client = await self._get_client()
        selected_model = model.strip() if model.strip() in ZHIDA_MODELS else ""
        if not selected_model:
            selected_model = str(
                self.config.get("default_zhida_model", "zhida-fast-1p5")
            ).strip()
        if selected_model not in ZHIDA_MODELS:
            selected_model = "zhida-fast-1p5"

        return await client.post_json(
            ZHIDA_CHAT_PATH,
            body={
                "model": selected_model,
                "messages": [{"role": "user", "content": query}],
                "stream": stream,
            },
        )

    @staticmethod
    def _format_search_items(
        query: str,
        payload: dict[str, Any],
        *,
        title: str,
    ) -> str:
        code = payload.get("Code", payload.get("code", 0))
        message = payload.get("Message", payload.get("msg", "success"))
        data = payload.get("Data") or payload.get("data") or {}
        items = data.get("Items") or data.get("items") or []
        if code != 0:
            return f"{title} failed: {message} (code={code})"
        if not items:
            empty_reason = data.get("EmptyReason") or data.get("empty_reason") or "No result"
            return f"{title} for \"{query}\": no result. {empty_reason}"

        lines = [f"{title} for \"{query}\" ({len(items)} results):"]
        for idx, item in enumerate(items, 1):
            item_title = _strip_html(item.get("Title", "Untitled"))
            content_type = item.get("ContentType", "")
            content_text = _truncate(_strip_html(item.get("ContentText", "")), 220)
            url = item.get("Url", "")
            author = item.get("AuthorName", "")
            vote = item.get("VoteUpCount", 0)
            comments = item.get("CommentCount", 0)
            lines.append(
                f"{idx}. [{content_type}] {item_title} | author={author} | votes={vote} | comments={comments}"
            )
            if content_text:
                lines.append(f"   {content_text}")
            if url:
                lines.append(f"   {url}")
        return "\n".join(lines)

    @staticmethod
    def _format_hot_list(payload: dict[str, Any], limit: int) -> str:
        code = payload.get("Code", payload.get("code", 0))
        message = payload.get("Message", payload.get("msg", "success"))
        data = payload.get("Data") or payload.get("data") or {}
        items = data.get("Items") or data.get("items") or []
        total = data.get("Total", len(items))
        if code != 0:
            return f"Zhihu hot list failed: {message} (code={code})"
        if not items:
            return "Zhihu hot list returned no items."

        lines = [f"Zhihu hot list (requested={limit}, total={total}, returned={len(items)}):"]
        for idx, item in enumerate(items, 1):
            title = _strip_html(item.get("Title", "Untitled"))
            summary = _truncate(_strip_html(item.get("Summary", "")), 180)
            url = item.get("Url", "")
            lines.append(f"{idx}. {title}")
            if summary:
                lines.append(f"   {summary}")
            if url:
                lines.append(f"   {url}")
        return "\n".join(lines)

    def _format_zhida_result(self, payload: dict[str, Any], model: str) -> str:
        if "error" in payload and isinstance(payload["error"], dict):
            err = payload["error"]
            message = err.get("message") or err.get("code") or json.dumps(
                err, ensure_ascii=False
            )
            return f"Zhida failed: {message}"

        choices = payload.get("choices") or []
        if not choices:
            return f"Zhida returned no choices for model {model}."

        choice = choices[0] or {}
        message = choice.get("message") or {}
        content = str(message.get("content", "") or "").strip()
        reasoning = str(message.get("reasoning_content", "") or "").strip()
        if not content and not reasoning:
            return f"Zhida returned an empty result for model {model}."

        parts = [f"Zhida result ({model}):"]
        if reasoning and bool(self.config.get("show_reasoning", False)):
            parts.append("Reasoning:")
            parts.append(reasoning)
        if content:
            parts.append("Answer:")
            parts.append(content)
        return "\n".join(parts)

    def _help_text(self) -> str:
        status = "configured" if self._has_access_secret() else "not configured"
        return (
            "Zhihu Open plugin\n"
            f"status: {status}\n"
            "commands:\n"
            "  /zhihu status\n"
            "  /zhihu set-secret <access_secret>\n"
            "  /zhihu clear-secret\n"
            "  /zhihu search <query>\n"
            "  /zhihu global <query>\n"
            "  /zhihu hot [limit]\n"
            "  /zhihu ask <question>\n"
            "llm tools:\n"
            "  zhihu_search_tool\n"
            "  zhihu_global_search_tool\n"
            "  zhihu_hot_list_tool\n"
            "  zhihu_zhida_tool"
        )

    @filter.on_llm_request()
    async def on_llm_request_hook(
        self,
        event: AstrMessageEvent,
        request: ProviderRequest,
    ) -> None:
        if not request.func_tool:
            return
        if self._has_access_secret():
            return
        for tool_name in ZHIHU_TOOL_NAMES:
            request.func_tool.remove_tool(tool_name)

    @filter.command_group("zhihu")
    def zhihu_group(self) -> None:
        """Zhihu Open plugin commands."""

    @zhihu_group.command("status")
    async def zhihu_status(self, event: AstrMessageEvent) -> None:
        """Show plugin config status."""
        secret = str(self.config.get("access_secret", "") or "").strip()
        proxy_url = str(self.config.get("proxy_url", "") or "").strip()
        masked = f"{secret[:4]}...{secret[-4:]}" if len(secret) >= 8 else ""
        event.set_result(
            event.plain_result(
                "\n".join(
                    [
                        "Zhihu Open status:",
                        f"  access_secret: {'configured' if secret else 'not configured'}",
                        f"  masked_secret: {masked or 'N/A'}",
                        f"  proxy_url: {proxy_url or 'N/A'}",
                        f"  timeout_seconds: {self.config.get('timeout_seconds', 30)}",
                        f"  default_zhida_model: {self.config.get('default_zhida_model', 'zhida-fast-1p5')}",
                    ]
                )
            )
        )

    @zhihu_group.command("set-secret")
    async def zhihu_set_secret(self, event: AstrMessageEvent, secret: GreedyStr) -> None:
        """Set Zhihu Access Secret."""
        cleaned = str(secret or "").strip()
        if not cleaned:
            event.set_result(event.plain_result("Usage: /zhihu set-secret <access_secret>"))
            return
        await self._save_access_secret(cleaned)
        event.set_result(event.plain_result("Zhihu Access Secret saved. LLM tools are now available."))

    @zhihu_group.command("clear-secret")
    async def zhihu_clear_secret(self, event: AstrMessageEvent) -> None:
        """Clear Zhihu Access Secret."""
        await self._clear_access_secret()
        event.set_result(event.plain_result("Zhihu Access Secret cleared."))

    @zhihu_group.command("search")
    async def zhihu_search_command(self, event: AstrMessageEvent, query: GreedyStr = "") -> None:
        """Run Zhihu search manually."""
        text = str(query or "").strip()
        if not text:
            event.set_result(event.plain_result(self._help_text()))
            return
        try:
            payload = await self._zhihu_search(
                text,
                int(self.config.get("default_search_count", 5) or 5),
            )
            event.set_result(
                event.plain_result(
                    self._format_search_items(
                        text,
                        payload,
                        title="Zhihu search",
                    )
                )
            )
        except Exception as exc:
            event.set_result(event.plain_result(f"Zhihu search failed: {exc}"))

    @zhihu_group.command("global")
    async def zhihu_global_command(self, event: AstrMessageEvent, query: GreedyStr = "") -> None:
        """Run global search manually."""
        text = str(query or "").strip()
        if not text:
            event.set_result(event.plain_result(self._help_text()))
            return
        try:
            payload = await self._global_search(
                text,
                int(self.config.get("default_search_count", 5) or 5),
            )
            event.set_result(
                event.plain_result(
                    self._format_search_items(
                        text,
                        payload,
                        title="Zhihu global search",
                    )
                )
            )
        except Exception as exc:
            event.set_result(event.plain_result(f"Zhihu global search failed: {exc}"))

    @zhihu_group.command("hot")
    async def zhihu_hot_command(self, event: AstrMessageEvent, limit: int = 10) -> None:
        """Get hot list manually."""
        try:
            payload = await self._hot_list(limit)
            event.set_result(event.plain_result(self._format_hot_list(payload, limit)))
        except Exception as exc:
            event.set_result(event.plain_result(f"Zhihu hot list failed: {exc}"))

    @zhihu_group.command("ask")
    async def zhihu_ask_command(self, event: AstrMessageEvent, question: GreedyStr = "") -> None:
        """Ask Zhida manually."""
        text = str(question or "").strip()
        if not text:
            event.set_result(event.plain_result(self._help_text()))
            return
        model = str(self.config.get("default_zhida_model", "zhida-fast-1p5") or "zhida-fast-1p5")
        try:
            payload = await self._zhida(text, model=model)
            event.set_result(event.plain_result(self._format_zhida_result(payload, model)))
        except Exception as exc:
            event.set_result(event.plain_result(f"Zhida request failed: {exc}"))

    @filter.llm_tool(name="zhihu_search_tool")
    async def zhihu_search_tool(
        self,
        event: AstrMessageEvent,
        query: str,
        count: int = 5,
    ) -> str:
        """Search content inside Zhihu.

        Use this tool when the user explicitly wants Zhihu results, Zhihu answers,
        Zhihu articles, or China-community discussions from Zhihu.

        Args:
            query(string): Search query.
            count(number): Number of results, 1-10.
        """
        query = str(query or "").strip()
        if not query:
            return "Zhihu search failed: query is required."
        try:
            payload = await self._zhihu_search(query, count)
            return self._format_search_items(query, payload, title="Zhihu search")
        except Exception as exc:
            logger.warning("[%s] zhihu_search_tool failed: %s", PLUGIN_NAME, exc)
            return f"Zhihu search failed: {exc}"

    @filter.llm_tool(name="zhihu_global_search_tool")
    async def zhihu_global_search_tool(
        self,
        event: AstrMessageEvent,
        query: str,
        count: int = 5,
    ) -> str:
        """Search the broader web through Zhihu Open Platform.

        Use this when the user wants broader search results rather than Zhihu-only results.

        Args:
            query(string): Search query.
            count(number): Number of results, 1-20.
        """
        query = str(query or "").strip()
        if not query:
            return "Zhihu global search failed: query is required."
        try:
            payload = await self._global_search(query, count)
            return self._format_search_items(
                query,
                payload,
                title="Zhihu global search",
            )
        except Exception as exc:
            logger.warning("[%s] zhihu_global_search_tool failed: %s", PLUGIN_NAME, exc)
            return f"Zhihu global search failed: {exc}"

    @filter.llm_tool(name="zhihu_hot_list_tool")
    async def zhihu_hot_list_tool(
        self,
        event: AstrMessageEvent,
        limit: int = 10,
    ) -> str:
        """Get the current Zhihu hot list.

        Use this when the user asks for Zhihu trending topics or the current hot list.

        Args:
            limit(number): Number of results, 1-30.
        """
        try:
            payload = await self._hot_list(limit)
            return self._format_hot_list(payload, limit)
        except Exception as exc:
            logger.warning("[%s] zhihu_hot_list_tool failed: %s", PLUGIN_NAME, exc)
            return f"Zhihu hot list failed: {exc}"

    @filter.llm_tool(name="zhihu_zhida_tool")
    async def zhihu_zhida_tool(
        self,
        event: AstrMessageEvent,
        query: str,
        model: str = "",
    ) -> str:
        """Ask Zhida, Zhihu's direct-answer model.

        Use this when the user wants a synthesized answer from Zhihu's direct-answer API.

        Args:
            query(string): User question.
            model(string): Optional model, one of zhida-fast-1p5, zhida-thinking-1p5, zhida-agent.
        """
        query = str(query or "").strip()
        if not query:
            return "Zhida failed: query is required."
        selected_model = model.strip() or str(
            self.config.get("default_zhida_model", "zhida-fast-1p5")
        )
        try:
            payload = await self._zhida(query, selected_model)
            return self._format_zhida_result(payload, selected_model)
        except Exception as exc:
            logger.warning("[%s] zhihu_zhida_tool failed: %s", PLUGIN_NAME, exc)
            return f"Zhida failed: {exc}"
