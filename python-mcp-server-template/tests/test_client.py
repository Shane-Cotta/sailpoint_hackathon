"""Proxy pass-through: the SDK ignores HTTPS_PROXY, so the client must forward it."""

import pytest

from sailpoint_mcp.client import proxy_for

TENANT = "https://acme.api.identitynow.com"


@pytest.fixture(autouse=True)
def clean_proxy_env(monkeypatch):
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy",
                 "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)


def test_no_proxy_configured():
    assert proxy_for(TENANT) is None


def test_https_proxy_is_used(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.corp:3128")
    assert proxy_for(TENANT) == "http://proxy.corp:3128"


def test_no_proxy_bypasses(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.corp:3128")
    monkeypatch.setenv("NO_PROXY", "localhost,.identitynow.com")
    assert proxy_for(TENANT) is None
