import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

CACHE_PATH = Path(__file__).resolve().parent / "cache_github_search.json"


def buscar_repos_github(query: str, max_resultados: int = 8, ttl_segundos: int = 3600) -> list[dict]:
    clave = f"{query.strip().lower()}::{max_resultados}"
    cache = {}
    if CACHE_PATH.exists():
        try:
            cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            cache = {}

    ahora = time.time()
    if clave in cache and (ahora - cache[clave].get("ts", 0)) < ttl_segundos:
        return cache[clave].get("items", [])

    q_enc = urllib.parse.quote(query)
    url = f"https://api.github.com/search/repositories?q={q_enc}&sort=stars&order=desc&per_page={max_resultados}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "videos-ia-local-agent/1.0",
            "Accept": "application/vnd.github+json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            items = []
            for r in data.get("items", []):
                items.append({
                    "full_name": r.get("full_name", ""),
                    "html_url": r.get("html_url", ""),
                    "description": (r.get("description") or "")[:200],
                    "language": r.get("language") or "",
                    "stars": r.get("stargazers_count", 0),
                    "license": (r.get("license") or {}).get("spdx_id") or "",
                })
            cache[clave] = {"ts": ahora, "items": items}
            CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
            return items
    except Exception:
        return cache.get(clave, {}).get("items", [])
