# astrbot-plugin-zhihu-open

Zhihu Open Platform plugin for AstrBot.

This plugin adds Zhihu-related LLM tools to AstrBot through the current Zhihu Open Platform APIs.

## Features

- Zhihu site search
- Global search via Zhihu Open Platform
- Zhihu hot list
- Zhida direct-answer API
- Manual command entry points for setup and debugging

## Repository

- GitHub: `https://github.com/miaoxutao123/astrbot-plugin-zhihu-open`

## Requirements

- AstrBot 4.x
- A Zhihu Open Platform `Access Secret`
- Network access from your AstrBot runtime to `https://developer.zhihu.com`

## Install

### Option 1: Copy into an existing AstrBot instance

Create this directory inside your AstrBot plugin path:

```text
data/plugins/astrbot_plugin_zhihu_open/
```

Then place these files into that directory:

```text
__init__.py
_conf_schema.json
main.py
metadata.yaml
```

### Option 2: Clone this repository and copy the files

```bash
git clone https://github.com/miaoxutao123/astrbot-plugin-zhihu-open.git
```

Then copy the repository files into:

```text
data/plugins/astrbot_plugin_zhihu_open/
```

### Recommended folder name

Use this exact folder name:

```text
astrbot_plugin_zhihu_open
```

It matches the plugin metadata and avoids loader inconsistencies.

## Configuration

This plugin uses the current Zhihu Open Platform `Access Secret` bearer authentication.

Get your secret from:

- `https://developer.zhihu.com/profile`

You can configure it in either of these ways.

### Configure from chat

```text
/zhihu set-secret <your_access_secret>
```

### Configure from AstrBot plugin settings

Fill these fields in the plugin config UI:

- `access_secret`
- `proxy_url`
- `timeout_seconds`
- `default_search_count`
- `default_hot_limit`
- `default_zhida_model`
- `show_reasoning`

## Commands

- `/zhihu status`
- `/zhihu set-secret <access_secret>`
- `/zhihu clear-secret`
- `/zhihu search <query>`
- `/zhihu global <query>`
- `/zhihu hot [limit]`
- `/zhihu ask <question>`

## LLM Tools

These tools are registered as AstrBot LLM tools and are intended for automatic AI invocation.

- `zhihu_search_tool`
  Searches content inside Zhihu.
- `zhihu_global_search_tool`
  Searches the broader web through Zhihu Open Platform.
- `zhihu_hot_list_tool`
  Fetches the current Zhihu hot list.
- `zhihu_zhida_tool`
  Calls Zhida for direct answers.

## Supported Zhihu Open APIs

- `https://developer.zhihu.com/api/v1/content/zhihu_search`
- `https://developer.zhihu.com/api/v1/content/global_search`
- `https://developer.zhihu.com/api/v1/content/hot_list`
- `https://developer.zhihu.com/v1/chat/completions`

## Behavior

- If `access_secret` is not configured, Zhihu tools are removed from the current LLM request tool set.
- The plugin stores the secret through AstrBot plugin config and plugin KV persistence.
- The Zhida tool supports:
  - `zhida-fast-1p5`
  - `zhida-thinking-1p5`
  - `zhida-agent`

## Validation

In this publish flow, the plugin source passed:

- `python3 -m py_compile main.py __init__.py`

The full AstrBot-recommended `uv run ruff format .` and `uv run ruff check .` were not run in this environment because `uv` and `ruff` were unavailable.

## License

This repository follows AstrBot core licensing:

- `AGPL-3.0-or-later`

See [LICENSE](LICENSE).

## Notes

- This plugin is implemented against Zhihu Open Platform documentation verified on 2026-05-18.
- Current Zhihu Open Platform authentication is `Authorization: Bearer <access_secret>` plus `X-Request-Timestamp`.
- It does not implement legacy OAuth code flow because that is not the current official auth mode exposed in Zhihu's open platform docs.
