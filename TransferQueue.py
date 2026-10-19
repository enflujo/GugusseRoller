"""Persistent, destination-specific capture spool shared by both exporters."""
import fcntl
import hashlib
import json
import os
import shutil
from pathlib import Path


SPOOL_ROOT = Path(__file__).resolve().parent / "capture-spool"
LEGACY_QUEUE = Path("/dev/shm/complete")


def unassigned_files():
    if not LEGACY_QUEUE.exists():
        return []
    return sorted(p.name for p in LEGACY_QUEUE.iterdir())


def frame_index(filename):
    stem = Path(filename).name.split(".")[0].split("_")[0]
    return int(stem) if stem.isdigit() else -1


def sync_directory(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class TransferQueue:
    def __init__(self, destination):
        encoded = json.dumps(destination, sort_keys=True).encode()
        self.root = SPOOL_ROOT / hashlib.sha256(encoded).hexdigest()[:24]
        self.directory = self.root / "ready"
        self.staging = self.root / "staging"
        self.destination = destination
        self.lock = None

    def acquire(self, allow_legacy=False):
        # Old RAM files have no project/destination metadata. Never guess their
        # owner and silently upload them into whichever project is selected.
        if not allow_legacy and unassigned_files():
            raise RuntimeError(
                "Unassigned images: usa «Asignar pendientes» en la interfaz "
                "para seleccionar su proyecto. No reinicies el equipo antes de guardarlas."
            )
        self.directory.mkdir(parents=True, exist_ok=True)
        self.staging.mkdir(exist_ok=True)
        sync_directory(self.root)
        sync_directory(self.root.parent)
        sync_directory(self.root.parent.parent)
        lock = open(self.root / "lock", "a")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            lock.close()
            raise RuntimeError("Another exporter is using this capture destination")
        self.lock = lock
        try:
            metadata = self.root / "destination.json"
            if not metadata.exists():
                with open(metadata, "x") as h:
                    json.dump(self.destination, h, indent=2)
                    h.flush()
                    os.fsync(h.fileno())
                sync_directory(self.root)
            # A crash during camera saving can leave an incomplete image. Do
            # not send it or reuse its number without an operator reviewing it.
            if any(self.staging.iterdir()):
                raise RuntimeError(
                    f"Unfinished capture files in {self.staging}; review them "
                    "before resuming the film. Ready images are preserved."
                )
        except Exception:
            self.release()
            raise

    def release(self):
        if self.lock is not None:
            self.lock.close()
            self.lock = None

    def files(self):
        return sorted(p.name for p in self.directory.iterdir() if p.is_file())

    def next_index(self):
        return max((frame_index(name) for name in self.files()), default=-1) + 1

    def publish(self, source):
        source = Path(source)
        # Save must be durable before the film advances. link() publishes the
        # completed image atomically and refuses to overwrite an existing name.
        with open(source, "rb") as h:
            os.fsync(h.fileno())
        os.link(source, self.directory / source.name)
        sync_directory(self.directory)
        source.unlink()
        sync_directory(self.staging)

    def begin_frame(self, index):
        if shutil.disk_usage(self.root).free < 256 * 1024 * 1024:
            raise OSError("Less than 256 MiB free for capture; film will not advance")
        marker = self.staging / "frame-in-progress"
        with open(marker, "x") as h:
            h.write(str(index))
            h.flush()
            os.fsync(h.fileno())
        sync_directory(self.staging)

    def finish_frame(self):
        (self.staging / "frame-in-progress").unlink()
        sync_directory(self.staging)

    def remove(self, name):
        (self.directory / name).unlink()
        sync_directory(self.directory)
