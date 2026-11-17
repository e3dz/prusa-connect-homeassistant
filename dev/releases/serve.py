"""A stand-in for the GitHub releases of Prusa Connect, for the embedded server in development.

It publishes the server binary of the demo image under every version listed in
``/data/versions`` (one per line; `make publish VERSION=…` adds one), each with
``SHA256SUMS`` and ``SHA256SUMS.sig`` signed by a development key. The key is
made at the first start in ``/data/signing-key.pem``, never committed, and its
public half written to ``/data/public.key``: `make up` puts that into the
configuration.yaml of its Home Assistant, and no other Home Assistant trusts it.

Each version's binary gets its version appended as trailing bytes, so the
versions differ the way two builds do and an update really replaces the file.

usage: python3 serve.py <port> <binary>
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import platform
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
)

HERE = Path(__file__).parent
DATA = Path("/data")
ARCHES = {"x86_64": "amd64", "aarch64": "aarch64", "arm64": "aarch64", "armv7l": "armv7"}
ASSET = "prusa_connect_" + ARCHES[platform.machine()]
KEY = DATA / "signing-key.pem"
PUBLIC = DATA / "public.key"


def make_key() -> None:
    """A development key of this environment's own, made once."""
    if KEY.exists():
        return
    key = Ed25519PrivateKey.generate()
    KEY.write_bytes(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
    KEY.chmod(0o600)
    raw = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    PUBLIC.write_text(base64.b64encode(raw).decode() + "\n")


def sign(sums: bytes) -> bytes:
    """The detached signature Prusa Connect releases carry: Ed25519 over SHA256SUMS, as JSON."""
    key = load_pem_private_key(KEY.read_bytes(), None)
    raw = key.sign(sums)  # type: ignore[call-arg, union-attr]
    public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return json.dumps(
        {
            "algorithm": "ed25519",
            "key_id": hashlib.sha256(public).hexdigest()[:32],
            "signature": base64.b64encode(raw).decode(),
        }
    ).encode()


def versions() -> list[str]:
    path = DATA / "versions"
    if not path.exists():
        path.write_text("0.0.1-alpha.1\n")
    return [v.strip() for v in path.read_text().splitlines() if v.strip()]


def build(version: str, binary: Path) -> Path:
    folder = DATA / version
    if not (folder / "SHA256SUMS.sig").exists():
        folder.mkdir(parents=True, exist_ok=True)
        data = binary.read_bytes() + f"\n{version}\n".encode()
        (folder / ASSET).write_bytes(data)
        sums = f"{hashlib.sha256(data).hexdigest()}  {ASSET}\n".encode()
        (folder / "SHA256SUMS").write_bytes(sums)
        (folder / "SHA256SUMS.sig").write_bytes(sign(sums))
    return folder


class Handler(http.server.BaseHTTPRequestHandler):
    binary: Path
    port: int

    def _send(self, status: int, body: bytes, kind: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        base = f"http://localhost:{self.port}"
        if self.path.split("?")[0] == "/repos/prusa3d/prusa-connect/releases":
            releases = []
            for version in reversed(versions()):
                folder = build(version, self.binary)
                releases.append(
                    {
                        "tag_name": f"v{version}",
                        "name": f"Prusa Connect {version} (development)",
                        "draft": False,
                        "prerelease": "-" in version,
                        "html_url": f"{base}/release/{version}",
                        "body": f"A development release of the demo binary, version {version}.",
                        "assets": [
                            {"name": f.name, "browser_download_url": f"{base}/download/{version}/{f.name}"}
                            for f in sorted(folder.iterdir())
                        ],
                    }
                )
            self._send(200, json.dumps(releases).encode())
            return
        parts = self.path.strip("/").split("/")
        if len(parts) == 3 and parts[0] == "download" and parts[1] in versions():
            file = build(parts[1], self.binary) / parts[2]
            if file.is_file():
                self._send(200, file.read_bytes(), "application/octet-stream")
                return
        self._send(404, b'{"message": "Not Found"}')


def main() -> None:
    Handler.port = int(sys.argv[1])
    Handler.binary = Path(sys.argv[2])
    make_key()
    versions()
    print(f"releases of {ASSET} on port {Handler.port}: {', '.join(versions())}", flush=True)
    http.server.ThreadingHTTPServer(("0.0.0.0", Handler.port), Handler).serve_forever()  # noqa: S104


if __name__ == "__main__":
    main()
