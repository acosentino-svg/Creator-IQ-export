from __future__ import annotations

import responses

from creatoriq_dashboard.config import Settings
from creatoriq_dashboard.crm_reports import fetch_crm_report_dataframe
from tests.test_api_client import make_config


@responses.activate
def test_fetch_crm_report_polls_until_done(tmp_path):
    config = make_config(
        crm_base_url="https://crm.example.test/crm/v1",
        settings=Settings(
            raw={
                "live_sync": {
                    "active_members_report": {
                        "view_candidates": ["Reports/ActiveMembers"],
                        "page_size": 2,
                        "max_pages": 1,
                        "poll_interval_seconds": 0,
                        "poll_timeout_seconds": 5,
                    }
                }
            }
        ),
    )
    view = "Reports/ActiveMembers"
    start_url = "https://crm.example.test/crm/v1/api/view"
    responses.add(
        responses.GET,
        start_url,
        json={"TaskId": "task-1", "TaskStatus": "CREATED"},
        match=[
            responses.matchers.query_param_matcher(
                {"view": view, "requestData[take]": "2", "requestData[skip]": "0", "section": "default"}
            )
        ],
    )
    responses.add(
        responses.GET,
        start_url,
        json={
            "TaskId": "task-1",
            "TaskStatus": "DONE",
            "Result": {"Status": 302, "Headers": {"Location": "https://crm.example.test/download.csv"}},
        },
        match=[responses.matchers.query_param_matcher({"view": view, "taskId": "task-1"})],
    )
    responses.add(
        responses.GET,
        "https://crm.example.test/download.csv",
        body="Publisher Id,Last Link Created\n99,2025-01-15\n",
        content_type="text/csv",
    )

    df = fetch_crm_report_dataframe(config, view, page_size=2, max_pages=1, poll_interval=0, poll_timeout=5)
    assert len(df) == 1
    assert df.iloc[0]["Publisher Id"] == 99
