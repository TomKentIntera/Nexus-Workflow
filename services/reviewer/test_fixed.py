#!/usr/bin/env python3
"""Test with HTTP directly."""
import asyncio
import httpx
import sys

async def test():
    # Use HTTP directly to avoid redirect path loss
    print("Testing HTTP directly: http://rule34.nexus/api/tags/search", file=sys.stderr)
    async with httpx.AsyncClient(base_url='http://rule34.nexus', timeout=15.0, follow_redirects=True) as client:
        try:
            res = await client.get('/api/tags/search', params={'limit': 12, 'include_zero_posts': False})
            print(f"Status: {res.status_code}", file=sys.stderr)
            print(f"URL: {res.url}", file=sys.stderr)
            if res.status_code == 200:
                print(f"SUCCESS! Response: {res.text[:300]}", file=sys.stderr)
                return True
            else:
                print(f"Error: {res.text[:500]}", file=sys.stderr)
                return False
        except Exception as e:
            print(f"Error: {type(e).__name__}: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            return False

if __name__ == "__main__":
    success = asyncio.run(test())
    sys.exit(0 if success else 1)

