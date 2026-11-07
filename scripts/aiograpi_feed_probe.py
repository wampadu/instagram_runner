"""Read-only structural probe for Instagram private hashtag responses.

Never prints response data, cookies, IDs, URLs, captions, headers, or tokens.
Shows only counts, selected allowlisted field names, and media age buckets.
"""
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

SESSION = Path.home() / ".instagram_runner" / "aiograpi-session.json"


def classify_response(response):
    if not isinstance(response, dict):
        return {"shape": type(response).__name__}
    sections = response.get("sections", [])
    if not isinstance(sections, list):
        sections = []
    media_nodes = []
    layout_shapes = {}
    for section in sections:
        if not isinstance(section, dict):
            continue
        layout = section.get("layout_content") or {}
        if not isinstance(layout, dict):
            layout = {}
        for key in ("fill_items", "medias", "one_by_two_item", "three_by_three_items", "two_by_two_items"):
            value = layout.get(key)
            if isinstance(value, list):
                layout_shapes[key] = layout_shapes.get(key, 0) + len(value)
                media_nodes.extend(value)
            elif isinstance(value, dict):
                layout_shapes[key] = layout_shapes.get(key, 0) + 1
                for subkey in ("items", "clips", "medias"):
                    nested = value.get(subkey)
                    if isinstance(nested, list):
                        media_nodes.extend(nested)
                    elif isinstance(nested, dict):
                        media_nodes.extend(nested.get("items") or [])
    return {
        "sections": len(sections),
        "layout_counts": layout_shapes,
        "counted_media_nodes": len(media_nodes),
        "has_more": bool(response.get("more_available")),
        "status_ok": response.get("status") == "ok",
        "has_next_cursor": bool(response.get("next_max_id")),
        "top_level_media_fields": {k:len(response[k]) for k in ("items", "media", "ranked_items") if isinstance(response.get(k), list)}
    }


async def main():
    logging.disable(logging.CRITICAL)
    if not SESSION.exists():
        print("Session missing; stopped.")
        return 2
    from aiograpi import Client
    client = Client()
    client.load_settings(SESSION)
    try:
        await client.account_info()
    except Exception as exc:
        print("Auth verification failed:", type(exc).__name__)
        return 2
    print("Authentication: PASS (saved session; no password login)")
    tag="toronto"
    # Compare only two tabs: top as a control, and recent as requested.
    for tab in ("top", "recent"):
        data = {
            "tab":tab,
            "media_recency_filter":"default" if tab=="top" else "top_recent_posts",
            "_uuid":client.uuid,
            "include_persistent":"false",
            "rank_token":client.rank_token
        }
        try:
            response=await asyncio.wait_for(client.private_request(
                f"tags/{tag}/sections/",data=data,with_signature=False
            ),timeout=40)
        except Exception as exc:
            print(tab, "request error:",type(exc).__name__)
            continue
        print(tab,"response summary:",classify_response(response))
    print("No raw responses or session exported. No writes performed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(asyncio.wait_for(main(),timeout=100)))
    except Exception as exc:
        print("Probe error:",type(exc).__name__)
        raise SystemExit(1)
