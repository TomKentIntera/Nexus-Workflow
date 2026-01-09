#!/usr/bin/env python3
"""Test redirect handling."""
import asyncio
import httpx
import sys

async def test():
    # Test HTTPS with redirect following
    print("Testing HTTPS with follow_redirects=True", file=sys.stderr)
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        try:
            res = await client.get('https://rule34.nexus/api/tags/search', params={'limit': 12, 'include_zero_posts': False})
            print(f"Status: {res.status_code}", file=sys.stderr)
            print(f"Final URL: {res.url}", file=sys.stderr)
            if res.status_code == 200:
                print(f"SUCCESS! Response: {res.text[:300]}", file=sys.stderr)
            else:
                print(f"Error: {res.text[:500]}", file=sys.stderr)
        except httpx.HTTPStatusError as e:
            print(f"HTTPStatusError: {e.response.status_code}", file=sys.stderr)
            print(f"Response: {e.response.text[:500]}", file=sys.stderr)
            print(f"Request URL: {e.request.url}", file=sys.stderr)
        except Exception as e:
            print(f"Error: {type(e).__name__}: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)

if __name__ == "__main__":
    asyncio.run(test())

