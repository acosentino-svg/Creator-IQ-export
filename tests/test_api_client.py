from __future__ import annotations

import responses

from creatoriq_dashboard.api_client import CreatorIQClient, get_path
from creatoriq_dashboard.config import AppConfig, Settings


def make_config(**overrides) -> AppConfig:
    defaults = dict(
        mode="live",
        base_url="https://api.example.test",
        api_key="test-key",
        org_id="org-1",
        db_path="/tmp/does-not-matter.db",
        slack_webhook_url="",
        settings=Settings(raw={}),
        endpoints={
            "pagination": {
                "style": "page",
                "page_param": "page",
                "page_size_param": "page_size",
                "page_size": 2,
                "results_path": "data",
                "has_more_path": "meta.has_more",
            },
            "resources": {
                "widgets": {"path": "/widgets", "method": "GET"},
            },
        },
        field_mappings={},
    )
    defaults.update(overrides)
    return AppConfig(**defaults)


def test_get_path_nested():
    record = {"Publisher": {"Id": 42}}
    assert get_path(record, "Publisher.Id") == 42
    assert get_path(record, "Publisher.Missing", default="x") == "x"


@responses.activate
def test_iter_resource_pages_until_has_more_false():
    config = make_config()
    responses.add(
        responses.GET,
        "https://api.example.test/widgets",
        json={"data": [{"id": 1}, {"id": 2}], "meta": {"has_more": True}},
        status=200,
    )
    responses.add(
        responses.GET,
        "https://api.example.test/widgets",
        json={"data": [{"id": 3}], "meta": {"has_more": False}},
        status=200,
    )

    client = CreatorIQClient(config)
    records = client.fetch_all("widgets")
    assert [r["id"] for r in records] == [1, 2, 3]
    assert len(responses.calls) == 2


@responses.activate
def test_iter_resource_stops_on_empty_page():
    config = make_config()
    responses.add(
        responses.GET,
        "https://api.example.test/widgets",
        json={"data": []},
        status=200,
    )
    client = CreatorIQClient(config)
    records = client.fetch_all("widgets")
    assert records == []
    assert len(responses.calls) == 1


@responses.activate
def test_retries_on_429_then_succeeds():
    config = make_config()
    responses.add(
        responses.GET,
        "https://api.example.test/widgets",
        json={"error": "rate limited"},
        status=429,
        headers={"Retry-After": "0"},
    )
    responses.add(
        responses.GET,
        "https://api.example.test/widgets",
        json={"data": [{"id": 1}], "meta": {"has_more": False}},
        status=200,
    )
    client = CreatorIQClient(config)
    records = client.fetch_all("widgets")
    assert [r["id"] for r in records] == [1]
