from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import responses

from creatoriq_dashboard.api_client import CreatorIQClient, coerce_to_record_list, get_path
from creatoriq_dashboard.config import AppConfig, Settings


def make_config(**overrides) -> AppConfig:
    defaults = dict(
        mode="live",
        base_url="https://api.example.test",
        crm_base_url="https://crm.example.test/crm/v1",
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
                "campaign_activity": {
                    "path": "/campaign/{campaign_id}/activity",
                    "method": "GET",
                    "wrapper_key": "CampaignActivity",
                    "items_key": "items",
                    "pagination_key": "pagination",
                    "page_param": "page",
                },
                "campaign_publishers": {
                    "path": "/campaign/{campaign_id}/publishers",
                    "method": "GET",
                    "results_path": "CampaignPublisher",
                },
                "publisher_summary": {
                    "path": "/publisher/{network_publisher_id}/summary",
                    "method": "GET",
                    "result_key": "Summary",
                },
                "publishers": {
                    "path": "/publishers",
                    "method": "GET",
                    "results_path": "PublisherCollection",
                    "item_unwrap_key": "Publisher",
                },
            },
        },
        field_mappings={},
    )
    defaults.update(overrides)
    return AppConfig(**defaults)


def test_coerce_to_record_list_handles_array_and_indexed_dict():
    assert coerce_to_record_list([{"a": 1}, {"a": 2}]) == [{"a": 1}, {"a": 2}]
    assert coerce_to_record_list({"0": {"a": 1}, "1": {"a": 2}}) == [{"a": 1}, {"a": 2}]
    assert coerce_to_record_list(None) == []


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


@responses.activate
def test_iter_nested_resource_paginates_via_nested_metadata():
    config = make_config()
    responses.add(
        responses.GET,
        "https://api.example.test/campaign/123/activity",
        json={"CampaignActivity": {"items": [{"Id": 1}, {"Id": 2}], "pagination": {"total_pages": 2}}},
        status=200,
    )
    responses.add(
        responses.GET,
        "https://api.example.test/campaign/123/activity",
        json={"CampaignActivity": {"items": [{"Id": 3}], "pagination": {"total_pages": 2}}},
        status=200,
    )
    client = CreatorIQClient(config)
    items = client.fetch_nested_all("campaign_activity", path_params={"campaign_id": 123})
    assert [i["Id"] for i in items] == [1, 2, 3]
    assert len(responses.calls) == 2


@responses.activate
def test_fetch_unpaginated_list_ignores_extra_pages():
    config = make_config()
    responses.add(
        responses.GET,
        "https://api.example.test/campaign/123/publishers",
        json={"CampaignPublisher": {"0": {"PublisherId": 1}, "1": {"PublisherId": 2}}},
        status=200,
    )
    client = CreatorIQClient(config)
    records = client.fetch_unpaginated_list("campaign_publishers", path_params={"campaign_id": 123})
    assert [r["PublisherId"] for r in records] == [1, 2]
    assert len(responses.calls) == 1


@responses.activate
def test_fetch_object_unwraps_result_key():
    config = make_config()
    responses.add(
        responses.GET,
        "https://api.example.test/publisher/net-1/summary",
        json={"Summary": {"Email": "a@example.com", "PublisherId": 1}},
        status=200,
    )
    client = CreatorIQClient(config)
    summary = client.fetch_object("publisher_summary", path_params={"network_publisher_id": "net-1"})
    assert summary["Email"] == "a@example.com"


@responses.activate
def test_resolve_network_publisher_id_uses_filter_query():
    config = make_config()
    responses.add(
        responses.GET,
        "https://api.example.test/publishers",
        json={"PublisherCollection": [{"Publisher": {"Id": 42, "NetworkPublisherId": "net-42"}}]},
        status=200,
    )
    client = CreatorIQClient(config)
    result = client.resolve_network_publisher_id(42)
    assert result == "net-42"
    query = parse_qs(urlparse(responses.calls[0].request.url).query)
    assert query["filter"] == ["Id=42"]


@responses.activate
def test_resolve_network_publisher_id_returns_none_when_not_found():
    config = make_config()
    responses.add(
        responses.GET,
        "https://api.example.test/publishers",
        json={"PublisherCollection": []},
        status=200,
    )
    client = CreatorIQClient(config)
    assert client.resolve_network_publisher_id(999) is None
