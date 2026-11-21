"""Stage GitHub Pages output and optionally create a single-file offline copy."""
import argparse
from pathlib import Path
import re
from shutil import copy2

ROOT = Path(__file__).resolve().parents[1]


def package(offline):
    source = ROOT / ".calisma/web-build"
    html = (source / "index.html").read_text(encoding="utf-8")
    assets = {
        name: source / "assets" / name
        for name in re.findall(r'(?:src|href)="\./assets/([A-Za-z0-9_.-]+)"', html)
    }
    assert len(assets) == 2 and {path.suffix for path in assets.values()} == {".js", ".css"}
    docs = ROOT / "docs"
    (docs / "demo").mkdir(parents=True, exist_ok=True)
    (docs / "assets").mkdir(parents=True, exist_ok=True)
    for old in (docs / "assets").glob("index-*"):
        if old.is_file() and old.name not in assets and old.suffix in {".css", ".js"}:
            old.unlink()
    for name, asset in assets.items():
        copy2(asset, docs / "assets" / name)
    (docs / ".nojekyll").touch()
    (docs / "index.html").write_text(html, encoding="utf-8")
    (docs / "demo/index.html").write_text(html.replace('"./assets/', '"../assets/'), encoding="utf-8")
    if offline:
        js = next(p for p in assets.values() if p.suffix == ".js").read_text(encoding="utf-8")
        css = next(p for p in assets.values() if p.suffix == ".css").read_text(encoding="utf-8")
        inline = re.sub(r"<script[^>]*></script>", lambda _: f'<script type="module">{js}</script>', html, count=1)
        inline = re.sub(r"<link rel=\"stylesheet\"[^>]*>", lambda _: f"<style>{css}</style>", inline, count=1)
        offline.parent.mkdir(parents=True, exist_ok=True)
        offline.write_text(inline, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", type=Path)
    package(parser.parse_args().offline)
