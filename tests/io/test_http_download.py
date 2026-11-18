"""Tests for the shared downloader: atomic writes, size checks, headers, an optional session. No network.

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


class FakeSession:
    """Enough of requests.Session for download_file: a get that records its calls."""

    def __init__(self, response, calls):
        self.get = fake_get(response, calls)


def test_with_a_session_the_file_comes_through_it(tmp_path, monkeypatch):
    def no_plain_request(*arguments, **options):
        pytest.fail("requests.get was called although a session was given")

    monkeypatch.setattr(http_download.requests, "get", no_plain_request)
    calls = []
    session = FakeSession(FakeResponse([b"KPL/", b"LSK\n"]), calls)
    target = tmp_path / "naif0012.tls"
    assert download_file("https://example.org/naif0012.tls", target, session=session) == target
    assert target.read_bytes() == b"KPL/LSK\n" and list(tmp_path.iterdir()) == [target]
    (call,) = calls
    assert call["headers"] == {"User-Agent": USER_AGENT} and call["timeout"] > 0 and call["stream"] is True


def test_requests_drops_a_sessions_authorisation_when_a_redirect_leaves_the_host():
    # download_file's docstring relies on this: a token sent to CSDA is not passed on to the storage host its
    # files redirect to. Pinned here, so a change in requests would show.
    session = requests.Session()
    assert session.should_strip_auth(
        "https://csdap.earthdata.nasa.gov/a", "https://bucket.s3.amazonaws.com/b"
    )
    assert not session.should_strip_auth(
        "https://csdap.earthdata.nasa.gov/a", "https://csdap.earthdata.nasa.gov/c"
    )
