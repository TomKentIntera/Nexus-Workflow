#!/usr/bin/env python3
"""Test script to check the reviewer endpoint."""
import asyncio
import httpx
import sys

async def test():
    try:
        async with httpx.AsyncClient(base_url='http://localhost:7860', timeout=10.0) as client:
            print("Testing endpoint: /api/rule34/tags/search?type=general&limit=12", file=sys.stderr)
            res = await client.get('/api/rule34/tags/search', params={'type': 'general', 'limit': 12})
            print(f"Status: {res.status_code}", file=sys.stderr)
            print(f"Response headers: {dict(res.headers)}", file=sys.stderr)
            print(f"Response body: {res.text}", file=sys.stderr)
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test())



