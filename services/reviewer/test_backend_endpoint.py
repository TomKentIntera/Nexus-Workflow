#!/usr/bin/env python3
"""Test the backend endpoint directly."""
import asyncio
import httpx
import sys
import json

async def test():
    base_url = "http://localhost:7860"
    
    print("=" * 60, file=sys.stderr)
    print("Test 1: Backend endpoint - no query (should use /api/tags/related)", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=15.0) as client:
            res = await client.get("/api/rule34/tags/search", params={"type": "general", "limit": 3})
            print(f"Status: {res.status_code}", file=sys.stderr)
            if res.status_code == 200:
                data = res.json()
                print(f"✅ SUCCESS! Got {len(data.get('data', []))} tags", file=sys.stderr)
                print(f"Response: {json.dumps(data, indent=2)[:500]}", file=sys.stderr)
            else:
                print(f"❌ FAILED: {res.status_code}", file=sys.stderr)
                print(f"Response: {res.text[:500]}", file=sys.stderr)
    except Exception as e:
        print(f"❌ ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return False
    
    print("\n" + "=" * 60, file=sys.stderr)
    print("Test 2: Backend endpoint - with query (should use /api/tags/search)", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=15.0) as client:
            res = await client.get("/api/rule34/tags/search", params={"query": "te", "type": "general", "limit": 3})
            print(f"Status: {res.status_code}", file=sys.stderr)
            if res.status_code == 200:
                data = res.json()
                print(f"✅ SUCCESS! Got {len(data.get('data', []))} tags", file=sys.stderr)
                print(f"Response: {json.dumps(data, indent=2)[:500]}", file=sys.stderr)
            else:
                print(f"❌ FAILED: {res.status_code}", file=sys.stderr)
                print(f"Response: {res.text[:500]}", file=sys.stderr)
    except Exception as e:
        print(f"❌ ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return False
    
    print("\n✅ All backend endpoint tests passed!", file=sys.stderr)
    return True

if __name__ == "__main__":
    success = asyncio.run(test())
    sys.exit(0 if success else 1)



