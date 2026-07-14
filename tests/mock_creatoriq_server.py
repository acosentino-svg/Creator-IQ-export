"""
Local mock of a CreatorIQ-style paginated publishers endpoint, used only to
exercise creatoriq_export.py end-to-end (pagination, retries, resume, dedup,
CSV flattening) without needing real credentials.

Not part of the shipped export tool -- for development/testing only.
"""
from __future__ import annotations

from flask import Flask, jsonify, request

app = Flask(__name__)

TOTAL_RECORDS = 2500
API_KEY = "test-secret-key"

RECORDS = [
    {
        "id": i,
        "name": f"Creator {i}",
        "email": f"creator{i}@example.com",
        "status": "active",
        "profile": {"followers": 1000 + i, "platform": "instagram"},
        "tags": ["fitness", "lifestyle"] if i % 2 == 0 else ["beauty"],
    }
    for i in range(1, TOTAL_RECORDS + 1)
]

# Simulate transient flakiness: fail every Nth request once with a 429.
_request_count = {"n": 0}
_failed_once: set[int] = set()


@app.route("/publishers")
def publishers():
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {API_KEY}":
        return jsonify({"error": "unauthorized"}), 401

    offset = int(request.args.get("offset", 0))
    limit = int(request.args.get("limit", 500))

    _request_count["n"] += 1
    if _request_count["n"] % 5 == 0 and offset not in _failed_once:
        _failed_once.add(offset)
        resp = jsonify({"error": "rate limited"})
        resp.status_code = 429
        resp.headers["Retry-After"] = "1"
        return resp

    page = RECORDS[offset : offset + limit]
    return jsonify(
        {
            "data": page,
            "meta": {"total": TOTAL_RECORDS, "offset": offset, "limit": limit},
        }
    )


if __name__ == "__main__":
    app.run(port=8765)
