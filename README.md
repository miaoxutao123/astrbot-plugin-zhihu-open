# astrbot-plugin-zhihu-open

Zhihu Open Platform plugin for AstrBot.

## Features

- Zhihu site search
- Global search via Zhihu Open Platform
- Zhihu hot list
- Zhida direct-answer API

## LLM Tools

- `zhihu_search_tool`
- `zhihu_global_search_tool`
- `zhihu_hot_list_tool`
- `zhihu_zhida_tool`

## Commands

- `/zhihu status`
- `/zhihu set-secret <access_secret>`
- `/zhihu clear-secret`
- `/zhihu search <query>`
- `/zhihu global <query>`
- `/zhihu hot [limit]`
- `/zhihu ask <question>`

## Installation

Copy these files into an AstrBot plugin directory, for example:

- `main.py`
- `metadata.yaml`
- `_conf_schema.json`
- `__init__.py`

Recommended plugin folder name:

- `astrbot_plugin_zhihu_open`

## Configuration

This plugin uses the current Zhihu Open Platform `Access Secret` bearer authentication.

Get your secret from:

- `https://developer.zhihu.com/profile`

Then configure it with:

```text
/zhihu set-secret <your_access_secret>
```

Or fill `access_secret` in the plugin config UI.

## Supported Zhihu Open APIs

- `https://developer.zhihu.com/api/v1/content/zhihu_search`
- `https://developer.zhihu.com/api/v1/content/global_search`
- `https://developer.zhihu.com/api/v1/content/hot_list`
- `https://developer.zhihu.com/v1/chat/completions`

## Notes

- This plugin is implemented against the Zhihu Open Platform docs available on 2026-05-18.
- Current Zhihu Open Platform auth is `Authorization: Bearer <access_secret>` with `X-Request-Timestamp`, not legacy OAuth code flow.
