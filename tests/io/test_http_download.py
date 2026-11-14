"""Tests for the shared downloader: atomic writes, size checks, headers. No network: requests.get is faked.

Run: ``pytest tests/io/test_http_download.py``
"""

import pytest
import requests

from leodragkit.io import http_download
from leodragkit.io.http_download import USER_AGENT, download_file


class FakeResponse:
    """Enough of requests.Response for download_file: a status, headers and chunks of bytes."""

    def __init__(self, chunks, status_code=200, content_length="auto"):
        self.chunks, self.status_code = chunks, status_code
        size = sum(len(chunk) for chunk in chunks)
        self.headers = (
            {}
            if content_length is None
            else {"Content-Length": str(size if content_length == "auto" else content_length)}
        )

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

    def iter_content(self, chunk_size):
        yield from self.chunks

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_get(response, calls):
    def get(url, headers, timeout, stream):
        calls.append({"url": url, "headers": headers, "timeout": timeout, "stream": stream})
        return response

    return get


def test_a_download_lands_complete_under_its_name_with_no_part_file_left(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(http_download.requests, "get", fake_get(FakeResponse([b"KPL/", b"LSK\n"]), calls))
    target = tmp_path / "kernels" / "naif0012.tls"
    assert download_file("https://example.org/naif0012.tls", target) == target
    assert target.read_bytes() == b"KPL/LSK\n"
    assert list(target.parent.iterdir()) == [target]
    assert calls[0]["headers"] == {"User-Agent": USER_AGENT} and calls[0]["timeout"] > 0


def test_a_short_download_raises_and_leaves_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        http_download.requests, "get", fake_get(FakeResponse([b"KPL"], content_length=100), [])
    )
    target = tmp_path / "naif0012.tls"
    with pytest.raises(OSError, match="Incomplete download.*3 of 100 bytes"):
        download_file("https://example.org/naif0012.tls", target)
    assert list(tmp_path.iterdir()) == []


def test_an_http_error_raises_and_keeps_an_existing_file(tmp_path, monkeypatch):
    target = tmp_path / "naif0012.tls"
    target.write_bytes(b"old copy")
    monkeypatch.setattr(http_download.requests, "get", fake_get(FakeResponse([b""], status_code=404), []))
    with pytest.raises(requests.HTTPError):
        download_file("https://example.org/naif0012.tls", target)
    assert target.read_bytes() == b"old copy" and list(tmp_path.iterdir()) == [target]


def test_a_download_without_a_size_is_accepted(tmp_path, monkeypatch):
    monkeypatch.setattr(
        http_download.requests, "get", fake_get(FakeResponse([b"abc"], content_length=None), [])
    )
    assert download_file("https://example.org/f", tmp_path / "f").read_bytes() == b"abc"
