#!/usr/bin/env python3
"""Verify Rule34 API connectivity from container."""
import asyncio
import httpx
import sys
import json

async def test():
    base_url = "https://rule34.nexus"
    
    print("=" * 60, file=sys.stderr)
    print("Test 1: /api/tags/related (top tags, no query)", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=15.0) as client:
            res = await client.get("/api/tags/related", params={"limit": 3})
            print(f"Status: {res.status_code}", file=sys.stderr)
            if res.status_code == 200:
                data = res.json()
                print(f"✅ SUCCESS! Got {len(data.get('data', []))} tags", file=sys.stderr)
                print(f"Response: {json.dumps(data, indent=2)[:300]}", file=sys.stderr)
            else:
                print(f"❌ FAILED: {res.status_code} - {res.text[:200]}", file=sys.stderr)
    except Exception as e:
        print(f"❌ ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return False
    
    print("\n" + "=" * 60, file=sys.stderr)
    print("Test 2: /api/tags/search?query=te (with query)", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=15.0) as client:
            res = await client.get("/api/tags/search", params={"query": "te", "limit": 3})
            print(f"Status: {res.status_code}", file=sys.stderr)
            if res.status_code == 200:
                data = res.json()
                print(f"✅ SUCCESS! Got {len(data.get('data', []))} tags", file=sys.stderr)
                print(f"Response: {json.dumps(data, indent=2)[:300]}", file=sys.stderr)
            else:
                print(f"❌ FAILED: {res.status_code} - {res.text[:200]}", file=sys.stderr)
    except Exception as e:
        print(f"❌ ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return False
    
    print("\n✅ All tests passed!", file=sys.stderr)
    return True

if __name__ == "__main__":
    success = asyncio.run(test())
    sys.exit(0 if success else 1)

