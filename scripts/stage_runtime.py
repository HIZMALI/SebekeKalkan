"""Construct the original V4.1 runtime layout under the isolated release directory."""
from pathlib import Path
from shutil import copy2
import sys

REPO=Path(__file__).resolve().parents[1]


def copy_tree(source, target):
    for file in sorted(source.rglob("*")):
        if file.is_file() and not file.is_symlink() and "__pycache__" not in file.parts:
            path=target/file.relative_to(source)
            path.parent.mkdir(parents=True,exist_ok=True)
            copy2(file,path)


def stage(target):
    app=target/"01_GELISTIRME_KAYNAK"
    for name in ("backend","data/metadata","data/networks","experiments/configs","frontend/dist"):
        copy_tree(REPO/name,app/name)
    for name in ("sprint02.py","sprint02_sources.py","verify_startup_v2.py"):
        (app/"scripts").mkdir(parents=True,exist_ok=True)
        copy2(REPO/"scripts"/name,app/"scripts"/name)
    copy_tree(REPO/"data/reference",target)
    copy_tree(REPO/"docs",app/"showcase")
    return app


if __name__=="__main__":
    destination=Path(sys.argv[1]).resolve() if len(sys.argv)==2 else REPO/".calisma/runtime"
    print(stage(destination))
