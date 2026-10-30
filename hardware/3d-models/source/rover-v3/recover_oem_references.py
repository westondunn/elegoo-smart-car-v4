#!/usr/bin/env python3
"""Download original ELEGOO electrical references without running their code."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent / "electrical_reference"
REPOSITORIES = ("ELEGOO-Smart-Robot-Car-Kit-V4.0", "ELEGOO-Smart-Robot-Car-Kit-V4.0-New")


def read_url(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Rover-Project-Reference"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read()


def fetch(repo):
    tree_url = f"https://api.github.com/repos/elegooofficial/{repo}/git/trees/main?recursive=1"
    tree = json.loads(read_url(tree_url))
    target = ROOT / repo
    target.mkdir(parents=True, exist_ok=True)
    (target / "repository_tree.json").write_text(json.dumps(tree, indent=2) + "\n")
    references = []
    for item in tree.get("tree", []):
        path = item["path"]
        lower = path.lower()
        is_diagram = (any(word in lower for word in ("schematic", "diagram", "circuit"))
                      and lower.endswith((".zip", ".pdf")))
        is_revision_readme = path == "README.md"
        if item.get("type") != "blob" or not (is_diagram or is_revision_readme):
            continue
        url = f"https://raw.githubusercontent.com/elegooofficial/{repo}/main/" + urllib.parse.quote(path)
        raw = read_url(url)
        output = target / Path(path).name.replace(" ", "_")
        output.write_bytes(raw)
        record = {"repository": repo, "path": path, "source_url": url,
                  "git_blob_sha": item.get("sha"), "sha256": hashlib.sha256(raw).hexdigest(),
                  "bytes": len(raw), "local_path": str(output.relative_to(ROOT))}
        if output.suffix.lower() == ".zip":
            with zipfile.ZipFile(output) as archive:
                if sum(member.file_size for member in archive.infolist()) > 50_000_000:
                    raise ValueError("Reference archive exceeds extraction size limit")
                record["archive_members"] = archive.namelist()
                extracted = target / "extracted"
                extracted.mkdir(exist_ok=True)
                for member in archive.infolist():
                    if member.is_dir():
                        continue
                    mp = Path(member.filename)
                    if mp.is_absolute() or ".." in mp.parts or "\\" in member.filename:
                        raise ValueError("Unsafe ZIP member path")
                    actual = extracted.joinpath(*[part.replace(" ", "_") for part in mp.parts])
                    actual.parent.mkdir(parents=True, exist_ok=True)
                    actual.write_bytes(archive.read(member))
        references.append(record)
    return {"repository": repo, "tree_sha": tree.get("sha"), "references": references}


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(fetch, REPOSITORIES))
    provenance = {"retrieved_utc": datetime.now(timezone.utc).isoformat(), "repositories": results}
    (ROOT / "download_provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    main()
