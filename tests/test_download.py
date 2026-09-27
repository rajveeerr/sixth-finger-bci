import hashlib
import zipfile

import pytest

from sixthfinger.data import download as dl

PAYLOAD = bytes(range(256)) * 400  # 102 400 bytes
MD5 = hashlib.md5(PAYLOAD).hexdigest()


@pytest.fixture(autouse=True)
def plenty_of_disk(monkeypatch):
    # The downloader keeps a 2 GB margin; these tests write 100 kB and must not
    # depend on how full the test machine's disk is. test_not_enough_space overrides it.
    monkeypatch.setattr(dl, "free_bytes", lambda _p: 10**12)


class FakeResponse:
    def __init__(self, body: bytes, status: int, headers: dict | None = None):
        self.body = body
        self.status_code = status
        self.headers = headers or {"Content-Length": str(len(body))}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size):
        for i in range(0, len(self.body), 4096):
            yield self.body[i : i + 4096]


class FakeSession:
    """Serves PAYLOAD, honouring Range unless told not to."""

    def __init__(self, honour_range: bool = True, body: bytes = PAYLOAD):
        self.honour_range = honour_range
        self.body = body
        self.requests: list[dict] = []

    def get(self, url, stream=True, headers=None, timeout=None, allow_redirects=True):
        headers = headers or {}
        self.requests.append(headers)
        rng = headers.get("Range")
        if rng and self.honour_range:
            start = int(rng.split("=")[1].rstrip("-"))
            if start >= len(self.body):
                return FakeResponse(b"", 416)
            return FakeResponse(self.body[start:], 206)
        return FakeResponse(self.body, 200)


def test_fresh_download(tmp_path):
    dest = tmp_path / "a.zip"
    dl.download_file(
        "u",
        dest,
        expected_size=len(PAYLOAD),
        expected_md5=MD5,
        session=FakeSession(),
        progress=False,
    )
    assert dest.read_bytes() == PAYLOAD
    assert not dest.with_name("a.zip.part").exists()


def test_resume_uses_range(tmp_path):
    dest = tmp_path / "a.zip"
    dest.with_name("a.zip.part").write_bytes(PAYLOAD[:30000])
    sess = FakeSession()
    dl.download_file(
        "u", dest, expected_size=len(PAYLOAD), expected_md5=MD5, session=sess, progress=False
    )
    assert sess.requests[0] == {"Range": "bytes=30000-"}
    assert dest.read_bytes() == PAYLOAD


def test_server_ignoring_range_restarts(tmp_path):
    dest = tmp_path / "a.zip"
    dest.with_name("a.zip.part").write_bytes(PAYLOAD[:30000])
    dl.download_file(
        "u",
        dest,
        expected_size=len(PAYLOAD),
        expected_md5=MD5,
        session=FakeSession(honour_range=False),
        progress=False,
    )
    assert dest.read_bytes() == PAYLOAD


def test_complete_part_file_is_accepted(tmp_path):
    dest = tmp_path / "a.zip"
    dest.with_name("a.zip.part").write_bytes(PAYLOAD)
    dl.download_file(
        "u",
        dest,
        expected_size=len(PAYLOAD),
        expected_md5=MD5,
        session=FakeSession(),
        progress=False,
    )
    assert dest.read_bytes() == PAYLOAD


def test_md5_mismatch_deletes_part(tmp_path):
    dest = tmp_path / "a.zip"
    bad = PAYLOAD[:-1] + b"\x00"
    with pytest.raises(dl.DownloadError, match="md5"):
        dl.download_file(
            "u",
            dest,
            expected_size=len(bad),
            expected_md5=MD5,
            session=FakeSession(body=bad),
            progress=False,
        )
    assert not dest.exists()
    assert not dest.with_name("a.zip.part").exists()


def test_short_download_keeps_part_for_resume(tmp_path):
    dest = tmp_path / "a.zip"
    with pytest.raises(dl.DownloadError, match="resume"):
        dl.download_file(
            "u",
            dest,
            expected_size=len(PAYLOAD) + 10,
            expected_md5=MD5,
            session=FakeSession(),
            progress=False,
        )
    assert dest.with_name("a.zip.part").stat().st_size == len(PAYLOAD)


def test_existing_verified_file_is_not_downloaded_again(tmp_path):
    dest = tmp_path / "a.zip"
    dest.write_bytes(PAYLOAD)
    sess = FakeSession()
    dl.download_file("u", dest, expected_md5=MD5, session=sess, progress=False)
    assert sess.requests == []


def test_not_enough_space(tmp_path, monkeypatch):
    monkeypatch.setattr(dl, "free_bytes", lambda _p: 1000)
    with pytest.raises(dl.DownloadError, match="disk space"):
        dl.download_file(
            "u", tmp_path / "a.zip", expected_size=10**9, session=FakeSession(), progress=False
        )


def _make_zip(path, members):
    with zipfile.ZipFile(path, "w") as zf:
        for name, body in members.items():
            zf.writestr(name, body)


def test_unzip_verified_and_listing(tmp_path):
    zp = tmp_path / "d.zip"
    _make_zip(zp, {"sub-01/pre/a_eeg.mat": b"x" * 10, "sub-01/pre/b_eeg.mat": b"y" * 20})
    listing = tmp_path / "audit" / "listing.tsv"
    n = dl.unzip_verified(zp, tmp_path / "out", expected_files=2, listing_path=listing)
    assert n == 2
    assert (tmp_path / "out/sub-01/pre/b_eeg.mat").stat().st_size == 20
    assert dl.verify_extracted(tmp_path / "out", listing) == []
    (tmp_path / "out/sub-01/pre/a_eeg.mat").unlink()
    assert dl.verify_extracted(tmp_path / "out", listing) == ["missing: sub-01/pre/a_eeg.mat"]


def test_unzip_wrong_count(tmp_path):
    zp = tmp_path / "d.zip"
    _make_zip(zp, {"a_eeg.mat": b"x"})
    with pytest.raises(dl.DownloadError, match="expected 268"):
        dl.unzip_verified(zp, tmp_path / "out", expected_files=268)


def test_unzip_refuses_path_traversal(tmp_path):
    zp = tmp_path / "d.zip"
    _make_zip(zp, {"../evil_eeg.mat": b"x"})
    with pytest.raises(dl.DownloadError, match="outside"):
        dl.unzip_verified(zp, tmp_path / "out")
