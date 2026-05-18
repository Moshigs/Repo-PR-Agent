#!/usr/bin/env python3
"""
Batch-generate illustrative PNGs via OpenAI Image API (gpt-image-2).

Reads prompts/image_generation_prompts.json, saves under ./image/.

Requirements: pip install -r requirements.txt
Env: OPENAI_API_KEY required; OPENAI_BASE_URL optional.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

PROMPTS_FILE = ROOT / "prompts" / "image_generation_prompts.json"
OUT_DIR = ROOT / "image"
MODEL = "gpt-image-2"

DEFAULT_SIZE = "1536x1024"
DEFAULT_QUALITY = "high"


def main() -> None:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise SystemExit(
            "未设置 OPENAI_API_KEY；复制 .env.example 为 .env 并写入密钥后再运行。"
        )

    base_url = os.environ.get("OPENAI_BASE_URL")

    raw = PROMPTS_FILE.read_text(encoding="utf-8")
    data = json.loads(raw)
    items = data.get("items") or []

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    client = OpenAI(api_key=key, base_url=base_url) if base_url else OpenAI(api_key=key)

    for item in items:
        name = item.get("filename")
        prompt = item.get("prompt_api") or item.get("prompt_zh")
        if not name or not prompt:
            continue
        dest = OUT_DIR / name

        print(f"生成中: {name} ...")

        resp = client.images.generate(
            model=MODEL,
            prompt=prompt,
            size=DEFAULT_SIZE,
            quality=DEFAULT_QUALITY,
            response_format="b64_json",
            n=1,
        )

        b64 = resp.data[0].b64_json
        if not b64:
            raise RuntimeError(f"API 未返回 b64_json: {name}")

        dest.write_bytes(base64.b64decode(b64))
        print(f"已保存: {dest}")

    print("全部完成。")


if __name__ == "__main__":
    main()
