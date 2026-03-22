# Version-Pinned NLP Store Downloads

## Problem

`prove advanced setup` and the auto-download in `nlp_store.py` always fetch stores from `/releases/latest`. This means a user running prove v1.1.0 could get stores trained against a v1.3.0 corpus if that's the latest release — potentially introducing mismatched completions or missing new stdlib coverage.

## Proposed Change

`download_stores()` should fetch stores matching the running compiler version:

1. Read the current version from `prove.__version__` (or `importlib.metadata`)
2. Try `/releases/tags/v{version}` first
3. Fall back to `/releases/latest` if the versioned release has no `lsp-ml-stores.tar.gz` (e.g. patch releases that didn't retrain)

```python
# nlp_store.py — sketch
from importlib.metadata import version as pkg_version

def _stores_api_url() -> str:
    ver = pkg_version("prove")
    return f"https://code.botwork.se/api/v1/repos/Botwork/prove/releases/tags/v{ver}"
```

## Considerations

- Patch releases (v1.1.1) may not retrain stores — need graceful fallback to the nearest minor release or latest.
- `workflow_dispatch` manual builds won't have a matching version tag — keep `/releases/latest` as a fallback.
- Offline/air-gapped installs already copy stores manually; this doesn't affect them.
