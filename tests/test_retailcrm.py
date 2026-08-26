import pytest

from fakes import FakeHttp
from retailcrm_mg.errors import ApiError, TokenNotIssuedError
from retailcrm_mg.retailcrm import (
    RetailCrmClient,
    extract_mg_endpoint,
    extract_token,
    find_token_candidates,
)

TOKEN = "example-mgbot-token-000000"


def make_client(http: FakeHttp) -> RetailCrmClient:
    return RetailCrmClient("https://crm.example.com", "api-key", http=http)


def test_ping_rejects_unsuccessful_body():
    http = FakeHttp({"/api/v5/reference/sites": {"success": False, "errorMsg": "нет прав"}})
    with pytest.raises(ApiError):
        make_client(http).ping()


def test_bootstrap_sends_refresh_token_flag_and_extracts_token():
    http = FakeHttp(
        {
            "/api/v5/integration-modules/mg_connector_test": {"success": False},
            "/api/v5/integration-modules/mg_connector_test/edit": {
                "success": True,
                "info": {"mgBot": {"token": TOKEN}},
            },
        }
    )
    result = make_client(http).bootstrap_mg_bot(
        code="mg_connector_test", name="Connector", client_id="client-1"
    )

    assert result.token == TOKEN
    assert result.created is True
    form = http.calls[-1][2]
    assert form["integrationModule[integrations][mgBot][refreshToken]"] is True
    assert form["integrationModule[code]"] == "mg_connector_test"


def test_bootstrap_marks_existing_module_as_not_created():
    http = FakeHttp(
        {
            "/api/v5/integration-modules/mg_connector_test": {
                "success": True,
                "integrationModule": {"code": "mg_connector_test"},
            },
            "/api/v5/integration-modules/mg_connector_test/edit": {
                "success": True,
                "integrationModule": {"integrations": {"mgBot": {"token": TOKEN}}},
            },
        }
    )
    result = make_client(http).bootstrap_mg_bot(
        code="mg_connector_test", name="Connector", client_id="client-1"
    )
    assert result.created is False


def test_bootstrap_raises_when_token_is_absent():
    http = FakeHttp(
        {
            "/api/v5/integration-modules/mg_connector_test": {"success": False},
            "/api/v5/integration-modules/mg_connector_test/edit": {"success": True, "info": {}},
        }
    )
    with pytest.raises(TokenNotIssuedError):
        make_client(http).bootstrap_mg_bot(
            code="mg_connector_test", name="Connector", client_id="client-1"
        )


def test_extract_token_falls_back_to_tree_walk():
    body = {"success": True, "result": {"deep": {"botToken": TOKEN}}}
    assert extract_token(body) == TOKEN


def test_extract_token_ignores_short_values():
    assert extract_token({"info": {"mgBot": {"token": "short"}}}) is None


def test_find_token_candidates_reports_paths():
    body = {"a": {"token": TOKEN}, "b": [{"accessToken": TOKEN}]}
    paths = {path for path, _ in find_token_candidates(body)}
    assert paths == {"a.token", "b[0].accessToken"}


def test_list_modules_walks_all_pages():
    pages = {
        "1": {
            "success": True,
            "integrationModules": [{"code": "one"}],
            "pagination": {"totalPageCount": 2},
        },
        "2": {
            "success": True,
            "integrationModules": [{"code": "two"}],
            "pagination": {"totalPageCount": 2},
        },
    }
    http = FakeHttp({"/api/v5/integration-modules": lambda q, f: pages[q["page"]]})
    codes = [module["code"] for module in make_client(http).list_modules()]
    assert codes == ["one", "two"]


def test_extract_mg_endpoint_reads_known_path():
    body = {"success": True, "info": {"mgBot": {"endpointUrl": "https://mg.example.com"}}}
    assert extract_mg_endpoint(body) == "https://mg.example.com"


def test_extract_mg_endpoint_falls_back_to_mg_shaped_keys():
    body = {"info": {"mgTransport": {"url": "https://mg.example.com/api/transport/v1"}}}
    assert extract_mg_endpoint(body) == "https://mg.example.com/api/transport/v1"


def test_extract_mg_endpoint_ignores_unrelated_urls():
    body = {"info": {"shop": {"siteUrl": "https://shop.example.com"}}}
    assert extract_mg_endpoint(body) is None


def test_bootstrap_result_carries_discovered_endpoint():
    http = FakeHttp(
        {
            "/api/v5/integration-modules/mg_connector_test": {"success": False},
            "/api/v5/integration-modules/mg_connector_test/edit": {
                "success": True,
                "info": {"mgBot": {"token": TOKEN, "endpointUrl": "https://mg.example.com"}},
            },
        }
    )
    result = make_client(http).bootstrap_mg_bot(
        code="mg_connector_test", name="Connector", client_id="client-1"
    )
    assert result.mg_api_base == "https://mg.example.com"
