#!/usr/bin/env python3
"""Test script to check Rule34 API connectivity."""
import asyncio
import httpx
import sys

async def test():
    base_url = "https://rule34.nexus"
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=15.0) as client:
            print(f"Testing connection to {base_url}/api/tags/search", file=sys.stderr)
            res = await client.get("/api/tags/search", params={"limit": 1})
            print(f"Status: {res.status_code}", file=sys.stderr)
            print(f"Response: {res.text[:200]}", file=sys.stderr)
    except httpx.ConnectError as e:
        print(f"Connection Error: {e}", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"HTTP Status Error: {e.response.status_code} - {e.response.text[:200]}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test())


