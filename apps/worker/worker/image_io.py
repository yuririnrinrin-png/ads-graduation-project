"""Safe image read/write for Windows (locked files, in-place overwrite)."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from PIL import Image

logger = logging.getLogger("tiamo.worker")


def open_image(path: Path, mode: str) -> Image.Image:
    """Load the whole file and close the handle (Windows cannot overwrite an open JPEG)."""
    with Image.open(path) as im:
        converted = im.convert(mode)
        converted.load()
        return converted.copy()


def save_image(img: Image.Image, path: Path, fmt: str, **kwargs) -> None:
    """Write via a temp file, then replace. Retry if the destination is locked."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fmt_u = fmt.upper()
    if fmt_u in ("JPEG", "JPG"):
        working = img.convert("RGB")
    else:
        working = img.copy()
    working.load()
    detached = working.copy()
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    last: OSError | None = None
    for attempt in range(10):
        try:
            detached.save(tmp, fmt, **kwargs)
            try:
                os.replace(tmp, path)
            except OSError:
                path.unlink(missing_ok=True)
                os.replace(tmp, path)
            return
        except OSError as exc:
            last = exc
            logger.warning("save retry %s/%s %s: %s", attempt + 1, 10, path.name, exc)
            time.sleep(0.2 * (attempt + 1))
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
    raise last if last else OSError(f"could not save {path}")
