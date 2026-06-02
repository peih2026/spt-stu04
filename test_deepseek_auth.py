#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Simple Deepseek authentication test.

Attempts several common API key header formats against /v1/models
and prints status and a short response preview.
"""

import os
import requests


def main():
    key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        print("ERROR: No DEEPSEEK_API_KEY or OPENAI_API_KEY found in environment.")
        return

    url = "https://api.deepseek.com/v1/models"
    attempts = [
        ("Authorization: Bearer", {"Authorization": f"Bearer {key}"}),
        ("OpenAI-Api-Key", {"OpenAI-Api-Key": key}),
        ("Api-Key", {"Api-Key": key}),
        ("X-API-Key", {"X-API-Key": key}),
    ]

    for label, headers in attempts:
        try:
            headers.update({"User-Agent": "investigation-agent/1.0"})
            print(f"\n== Trying header: {label} ==")
            resp = requests.get(url, headers=headers, timeout=15)
            print(f"Status: {resp.status_code}")
            text = resp.text or ""
            print(text[:1000])
            # If 200 OK or 401, stop early for clarity
            if resp.status_code in (200, 401):
                break
        except Exception as e:
            print(f"Request error for {label}: {e}")


if __name__ == "__main__":
    main()
