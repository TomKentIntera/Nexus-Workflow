#!/usr/bin/env python3
"""Test HTTP connection to Rule34 API."""
import asyncio
import httpx
import sys

async def test():
    # Test with HTTP directly
    async with httpx.AsyncClient(base_url='http://rule34.nexus', timeout=15.0, follow_redirects=True) as client:
        print("Testing HTTP connection to http://rule34.nexus/api/tags/search", file=sys.stderr)
        try:
            res = await client.get('/api/tags/search', params={'limit': 12, 'include_zero_posts': False})
            print(f"Status: {res.status_code}", file=sys.stderr)
            if res.status_code == 200:
                print(f"Success! Response: {res.text[:200]}", file=sys.stderr)
            else:
                print(f"Error response: {res.text[:500]}", file=sys.stderr)
        except Exception as e:
            print(f"Error: {type(e).__name__}: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)

if __name__ == "__main__":
    asyncio.run(test())



