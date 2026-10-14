#!/usr/bin/env python3
"""Compare compressed OCI image sizes for the AI Studio runtime (production vs candidate).

Read-only, anonymous GHCR queries. Prints compressed layer totals (the number that
governs the cold image download) and the delta in bytes/GiB/percent, plus each
layer's compressed size so layer-boundary changes can be checked.

Usage:
    python scripts/compare-image-sizes.py [ref ...]
    # default refs: runtime-20261008  candidate-20261014

Network safety: https only, host allowlist, resolved-IP public-address check,
redirects permitted only to the GHCR blob CDN.
"""
import hashlib
import ipaddress
import json
import socket
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse

REPO = "denborn03-star/ai-studio-runtime"
ALLOWED_HOSTS = {"ghcr.io"}
CDN_HOSTS = {"pkg-containers.githubusercontent.com", "objects.githubusercontent.com"}
INDEX_ACCEPT = ("application/vnd.oci.image.index.v1+json,"
                "application/vnd.docker.distribution.manifest.list.v2+json")
MANIFEST_ACCEPT = ("application/vnd.oci.image.manifest.v1+json,"
                   "application/vnd.docker.distribution.manifest.v2+json")


def _assert_safe(url, hosts=None):
    p = urlparse(url)
    if p.scheme != "https":
        raise SystemExit("BLOCKED: non-https scheme: " + p.scheme)
    if p.hostname not in (hosts or ALLOWED_HOSTS):
        raise SystemExit("BLOCKED: host not allowlisted: " + str(p.hostname))
    for _fam, _t, _p, _c, sa in socket.getaddrinfo(p.hostname, 443, proto=socket.IPPROTO_TCP):
        ip = ipaddress.ip_address(sa[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise SystemExit("BLOCKED: host resolves to non-public address")


class _GuardedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _assert_safe(newurl, CDN_HOSTS)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_GuardedRedirect)


def fetch(url, accept=None, token=None):
    _assert_safe(url)
    req = urllib.request.Request(url)
    if accept:
        req.add_header("Accept", accept)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with _OPENER.open(req, timeout=120) as r:
        return r.read()


def image_report(ref):
    token = json.loads(fetch(f"https://ghcr.io/token?scope=repository:{REPO}:pull"))["token"]
    body = fetch(f"https://ghcr.io/v2/{REPO}/manifests/{ref}", accept=INDEX_ACCEPT, token=token)
    index_digest = "sha256:" + hashlib.sha256(body).hexdigest()
    doc = json.loads(body)
    if "manifests" not in doc:
        return {"ref": ref, "resolved": True, "index_digest": index_digest,
                "manifest_digest": index_digest, "layers": doc.get("layers", []),
                "total": sum(l["size"] for l in doc.get("layers", []))}
    for child in doc["manifests"]:
        plat = child.get("platform", {})
        if plat.get("os") == "linux" and plat.get("architecture") == "amd64":
            man = json.loads(fetch(f"https://ghcr.io/v2/{REPO}/manifests/{child['digest']}",
                                   accept=MANIFEST_ACCEPT, token=token))
            layers = man.get("layers", [])
            return {"ref": ref, "resolved": True, "index_digest": index_digest,
                    "manifest_digest": child["digest"], "layers": layers,
                    "total": sum(l["size"] for l in layers)}
    return {"ref": ref, "resolved": False, "error": "no linux/amd64 manifest"}


def main():
    refs = sys.argv[1:] or ["runtime-20261008", "candidate-20261014"]
    reports = []
    for ref in refs:
        try:
            rep = image_report(ref)
        except urllib.error.HTTPError as e:
            rep = {"ref": ref, "resolved": False, "error": f"HTTP {e.code}"}
        reports.append(rep)
        if rep.get("resolved"):
            print(f"{ref}: index {rep['index_digest']}")
            print(f"{ref}: amd64 manifest {rep['manifest_digest']}")
            print(f"{ref}: layers {len(rep['layers'])}  compressed {rep['total']} B "
                  f"({rep['total']/1024**3:.2f} GiB)")
            for i, l in enumerate(rep["layers"]):
                print(f"    L{i:02d} {l['size']:>13,} B {l['size']/1024**2:>9.1f} MiB")
        else:
            print(f"{ref}: NOT AVAILABLE ({rep.get('error', 'unknown')})")
        print()

    if len(reports) == 2 and all(r.get("resolved") for r in reports):
        base, cand = reports[0], reports[1]
        delta = base["total"] - cand["total"]
        pct = 100.0 * delta / base["total"] if base["total"] else 0.0
        print(f"DELTA compressed: {delta} B ({delta/1024**3:+.2f} GiB) = {pct:+.2f}% "
              f"({'smaller' if delta > 0 else 'not smaller'} candidate)")
        bl, cl = base["layers"], cand["layers"]
        if len(bl) == len(cl) and all(a["size"] == b["size"] for a, b in zip(bl, cl)):
            print("NOTE: layer sizes identical -> compression override did not take effect")
        else:
            print(f"NOTE: layer count {len(bl)} -> {len(cl)} (boundary/compression changed)")


if __name__ == "__main__":
    main()
