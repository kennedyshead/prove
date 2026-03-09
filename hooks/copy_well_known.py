import shutil
from pathlib import Path


def on_post_build(config, builder=None):
    """Copy .well-known folder to site directory after build."""
    docs_dir = Path(config.config_file_path).parent / "docs"
    src = docs_dir / ".well-known"
    dst = Path(config.site_dir) / ".well-known"

    if src.exists():
        dst.mkdir(parents=True, exist_ok=True)
        for f in src.rglob("*"):
            if f.is_file():
                rel = f.relative_to(src)
                target = dst / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, target)
