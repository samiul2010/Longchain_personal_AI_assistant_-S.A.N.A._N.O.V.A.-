"""Optional Hugging Face Dataset persistence for Agent PC.

Required environment variables in the HF Space:
  HF_TOKEN=write-enabled token
  HF_DATASET_REPO_ID=username/agent_pc

The app remains usable locally when these variables or huggingface_hub are
missing; in that case local disk persistence is still used.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

try:
    from huggingface_hub import HfApi, snapshot_download
except Exception:  # optional dependency for local development
    HfApi = None
    snapshot_download = None


class HFDatasetPersistence:
    def __init__(self, local_root: str | Path):
        self.local_root = Path(local_root)
        self.repo_id = os.getenv("HF_DATASET_REPO_ID", "").strip()
        self.token = os.getenv("HF_TOKEN", "").strip()
        self.enabled = bool(self.repo_id and self.token and HfApi and snapshot_download)
        self.last_error: str | None = None
        self.last_sync: str | None = None

    def _api(self):
        if not self.enabled:
            raise RuntimeError("HF Dataset persistence is not configured")
        return HfApi(token=self.token)

    def ensure_dataset(self) -> None:
        self._api().create_repo(repo_id=self.repo_id, repo_type="dataset", private=True, exist_ok=True)

    def restore(self) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "enabled": False, "message": "Set HF_TOKEN and HF_DATASET_REPO_ID to enable Dataset restore"}
        temp = Path(tempfile.mkdtemp(prefix="agent_pc_restore_"))
        try:
            self.ensure_dataset()
            snapshot = Path(snapshot_download(repo_id=self.repo_id, repo_type="dataset", token=self.token, local_dir=str(temp), local_dir_use_symlinks=False))
            restored = 0
            for source in snapshot.rglob("*"):
                if not source.is_file() or ".cache" in source.parts:
                    continue
                relative = source.relative_to(snapshot)
                destination = self.local_root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                restored += 1
            self.last_error = None
            return {"ok": True, "enabled": True, "files": restored, "repo_id": self.repo_id}
        except Exception as exc:  # do not prevent the Space from booting
            self.last_error = str(exc)
            return {"ok": False, "enabled": True, "error": str(exc), "repo_id": self.repo_id}
        finally:
            shutil.rmtree(temp, ignore_errors=True)

    def sync(self) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "enabled": False, "message": "Set HF_TOKEN and HF_DATASET_REPO_ID to enable Dataset sync"}
        try:
            self.ensure_dataset()
            result = self._api().upload_folder(
                repo_id=self.repo_id,
                repo_type="dataset",
                folder_path=str(self.local_root),
                commit_message="Agent PC automatic state sync",
                ignore_patterns=["*.tmp", ".cache/*", "__pycache__/*"],
            )
            self.last_error = None
            self.last_sync = str(result)
            return {"ok": True, "enabled": True, "repo_id": self.repo_id, "commit": str(result)}
        except Exception as exc:
            self.last_error = str(exc)
            return {"ok": False, "enabled": True, "error": str(exc), "repo_id": self.repo_id}
