#!/usr/bin/env python3
"""
GEO Visibility Scanner.

Reads clients.json from the repo root, runs each client's prompts against
OpenAI (gpt-4o-search-preview), Perplexity (sonar), and Anthropic (claude
with web_search tool), scores responses, and writes scan_results.json
in the schema the dashboard's autoLoadFromGitHub() expects.

Environment variables:
  OPENAI_API_KEY       — required for ChatGPT scans
  PERPLEXITY_API_KEY   — required for Perplexity scans
  ANTHROPIC_API_KEY    — required for Claude scans

Any platform without a key is skipped (its mentions count as 0).
The script prints a summary and exits 0 if at least one platform ran.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

# ─────────────────────────────────────────────────────────────────────────────
# Repo paths
# ─────────────────────────────────────────────────────────────────────────────
REPO_ROOT       = Path(__file__).resolve().parent.parent
CLIENTS_PATH    = REPO_ROOT / "clients.json"
RESULTS_PATH    = REPO_ROOT / "scan_results.json"

# ─────────────────────────────────────────────────────────────────────────────
# Prompt templates — mirrors index.html buildPreviewPrompts()
# ─────────────────────────────────────────────────────────────────────────────
def build_prompts(brand: str, industry: str, location: str, services: str, biztype: str) -> list[str]:
    primary_service = (services or industry or "").split(",")[0].strip() or industry or "your service"
    is_national     = not (location or "").strip()
    is_b2b          = (biztype or "").lower() == "b2b"
    is_national_b2b = is_b2b and is_national
    b = brand or "{brand}"

    if is_national_b2b:
        return [
            f"Best {industry} company in the US",
            f"Top {industry} services for businesses",
            f"Who provides {primary_service} for businesses?",
            f"Best {industry} vendor for commercial clients",
            f"Tell me about {b}",
            f"Is {b} a reputable company?",
            f"What do clients say about {b}?",
            f"What is {b} known for?",
            f"Top rated {industry} providers",
            f"Best {primary_service} company — recommendations?",
        ]
    if is_b2b:
        return [
            f"Best {industry} company in {location}",
            f"Top {industry} services for businesses in {location}",
            f"Who provides {primary_service} in {location}?",
            f"Which companies offer {industry} in {location}?",
            f"{industry} companies near {location}",
            f"Tell me about {b}",
            f"Is {b} a reputable company?",
            f"What do clients say about {b}?",
            f"Who should I hire for {primary_service} in {location}?",
            f"Looking for a {industry} company in {location} — any recommendations?",
        ]
    if is_national:
        return [
            f"Where is the best place to buy {primary_service} online?",
            f"Best online {industry} in the US",
            f"Top rated {industry} websites",
            f"Where can I order {primary_service} online?",
            f"Who sells the best {primary_service} online?",
            f"Tell me about {b}",
            f"Is {b} reputable?",
            f"What do people say about {b}?",
            f"Best place to get {primary_service} shipped to my door",
            f"Which online {industry} has the best selection?",
        ]
    return [
        f"What is the best {industry} in {location}?",
        f"Top rated {industry} in {location}",
        f"Best {industry} near {location}",
        f"Can you recommend a good {industry} in {location}?",
        f"Where can I find a great {industry} in {location}?",
        f"Tell me about {b}",
        f"Is {b} worth it?",
        f"What do people say about {b}?",
        f"What are the most popular {industry} options in {location}?",
        f"Which {industry} in {location} is highest rated?",
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Scoring — mirrors index.html scoreScanResponse()
# ─────────────────────────────────────────────────────────────────────────────
def score_response(text: str, client: dict) -> dict:
    lower = (text or "").lower()
    name  = client["name"].lower()
    domain = (client.get("domain") or "").lower().replace("https://", "").replace("http://", "").replace("www.", "")
    alts = [a.strip().lower() for a in (client.get("alts") or "").split(",") if a.strip()]

    mentioned = (name in lower) or any(a in lower for a in alts)
    cited     = bool(domain) and (domain in lower)
    position  = "absent"
    if mentioned:
        idx = lower.find(name)
        pct = idx / max(len(lower), 1)
        position = "first" if pct < 0.15 else ("top_3" if pct < 0.45 else "mentioned_later")
    return {"mentioned": mentioned, "position": position, "cited": cited}


# ─────────────────────────────────────────────────────────────────────────────
# Platform callers
# ─────────────────────────────────────────────────────────────────────────────
def _post_json(url: str, headers: dict, body: dict, timeout: int = 60) -> dict:
    r = requests.post(url, headers=headers, json=body, timeout=timeout)
    if r.status_code >= 400:
        # Surface the API's error message so logs are debuggable
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
    return r.json()


def call_openai(api_key: str, prompt: str) -> str:
    data = _post_json(
        "https://api.openai.com/v1/chat/completions",
        {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        {"model": "gpt-4o-search-preview", "messages": [{"role": "user", "content": prompt}], "max_tokens": 600},
    )
    return data["choices"][0]["message"]["content"] or ""


def call_perplexity(api_key: str, prompt: str) -> str:
    data = _post_json(
        "https://api.perplexity.ai/chat/completions",
        {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        {"model": "sonar", "messages": [{"role": "user", "content": prompt}], "max_tokens": 600},
    )
    return data["choices"][0]["message"]["content"] or ""


def call_claude(api_key: str, prompt: str) -> str:
    data = _post_json(
        "https://api.anthropic.com/v1/messages",
        {"Content-Type": "application/json", "x-api-key": api_key, "anthropic-version": "2023-06-01"},
        {
            "model": "claude-opus-4-5",
            "max_tokens": 600,
            "tools": [{"type": "web_search_20250305", "name": "web_search"}],
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    return " ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Per-client scan
# ─────────────────────────────────────────────────────────────────────────────
def scan_client(client: dict, platforms: list[tuple[str, str, callable]]) -> dict:
    """Returns a result dict in the schema scan_results.json expects."""
    prompts = build_prompts(
        client["name"],
        client.get("industry", ""),
        client.get("location", ""),
        client.get("services", ""),
        client.get("biztype", "local"),
    )

    platform_results: dict[str, dict] = {}
    counts = {"openai": 0, "perplexity": 0, "claude": 0}

    for key, env_key, caller in platforms:
        prompt_log = []
        total = 0
        api_key = os.environ.get(env_key, "")
        for prompt in prompts:
            try:
                text = caller(api_key, prompt)
                scored = score_response(text, client)
                if scored["mentioned"]:
                    total += 1
                prompt_log.append({
                    "prompt": prompt,
                    "response": text,
                    "mention_count": 1 if scored["mentioned"] else 0,
                    "position": scored["position"],
                    "cited": scored["cited"],
                })
                # Be polite — small delay between calls
                time.sleep(0.7)
            except Exception as exc:  # noqa: BLE001
                print(f"    ✗ {key} error on '{prompt[:50]}…': {exc}", file=sys.stderr)
                prompt_log.append({
                    "prompt": prompt, "response": "",
                    "mention_count": 0, "position": "absent", "cited": False,
                    "error": str(exc),
                })
        platform_results[key] = {
            "total_mentions": total,
            "prompts_run": len(prompts),
            "prompt_log": prompt_log,
        }
        counts[key] = total
        mark = "✓" if total else "○"
        print(f"  {mark} {key:>10}: {total}/{len(prompts)} mentions")

    total_mentions = sum(counts.values())
    total_cells    = len(platforms) * len(prompts)
    visibility     = round(100 * total_mentions / total_cells) if total_cells else 0

    return {
        "client_id":   client.get("id"),
        "client_name": client["name"],
        "domain":      client.get("domain", ""),
        "industry":    client.get("industry", ""),
        "location":    client.get("location", ""),
        "alts":        client.get("alts", ""),
        "biztype":     client.get("biztype", "local"),
        "scanned_at":  datetime.now(timezone.utc).isoformat(),
        "total_mentions":   total_mentions,
        "visibility_score": visibility,
        "m_chatgpt": counts["openai"],
        "m_perp":    counts["perplexity"],
        "m_claude":  counts["claude"],
        "m_google":  0,
        "m_bing":    0,
        "platform_results": platform_results,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────────────────────────────────────────
def load_clients() -> list[dict]:
    if not CLIENTS_PATH.exists():
        print(f"clients.json not found at {CLIENTS_PATH}. Push one from the dashboard.", file=sys.stderr)
        sys.exit(1)
    raw = json.loads(CLIENTS_PATH.read_text(encoding="utf-8"))
    # Accept either a bare list or {clients: [...]} from the dashboard's GitHub sync
    return raw["clients"] if isinstance(raw, dict) and "clients" in raw else raw


def main() -> None:
    clients = load_clients()
    if not clients:
        print("No clients in clients.json — nothing to scan.")
        return

    platforms_all = [
        ("openai",     "OPENAI_API_KEY",     call_openai),
        ("perplexity", "PERPLEXITY_API_KEY", call_perplexity),
        ("claude",     "ANTHROPIC_API_KEY",  call_claude),
    ]
    platforms = [p for p in platforms_all if os.environ.get(p[1])]
    if not platforms:
        print("No API keys set. Add OPENAI_API_KEY / PERPLEXITY_API_KEY / ANTHROPIC_API_KEY as repo secrets.", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning {len(clients)} clients across {len(platforms)} platform(s): {[p[0] for p in platforms]}")

    # Optional: subset by SCAN_LIMIT env var (handy for smoke tests)
    limit = int(os.environ.get("SCAN_LIMIT", "0") or 0)
    if limit:
        clients = clients[:limit]
        print(f"  (limiting to first {limit} client(s) per SCAN_LIMIT)")

    results = []
    for i, c in enumerate(clients, 1):
        print(f"\n[{i}/{len(clients)}] {c['name']}")
        results.append(scan_client(c, platforms))

    run_id = "run_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    payload = {
        "scan_run_id":  run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "platforms":    [p[0] for p in platforms],
        "client_count": len(results),
        "results":      results,
    }
    RESULTS_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n✓ Wrote {RESULTS_PATH.relative_to(REPO_ROOT)} — {len(results)} clients, run id {run_id}")


if __name__ == "__main__":
    main()
