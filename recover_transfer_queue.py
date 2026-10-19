"""Explicitly assign old RAM images to a project; never performs network IO."""
import argparse
import filecmp
import shutil
from pathlib import Path
from ConfigFiles import ConfigFiles
from TransferQueue import LEGACY_QUEUE, TransferQueue, frame_index


def recover(queue, filenames=None):
    # GUI callers can assign a subset when RAM contains more than one project.
    names = sorted(p.name for p in LEGACY_QUEUE.iterdir()) if filenames is None else sorted(set(filenames))
    sources = []
    for name in names:
        if not name or name != Path(name).name:
            raise ValueError(f"Invalid legacy filename: {name}")
        source = LEGACY_QUEUE / name
        if not source.is_file() or source.suffix.lower() not in (".jpg", ".dng"):
            raise ValueError(f"Unrecognized legacy file: {source}; preserve for review")
        if frame_index(source.name) < 0:
            raise ValueError(f"Unrecognized frame number: {source}")
        sources.append(source)
    queue.acquire(allow_legacy=True)
    count = 0
    try:
        for source in sources:
            destination = queue.directory / source.name
            if destination.exists():
                if not filecmp.cmp(source, destination, shallow=False):
                    raise FileExistsError(f"Different pending image already exists: {destination}")
            else:
                staged = queue.staging / source.name
                with open(source, "rb") as original, open(staged, "xb") as target:
                    shutil.copyfileobj(original, target)
                queue.publish(staged)
            # Only remove the RAM copy after the disk copy is durable.
            source.unlink()
            count += 1
    finally:
        queue.release()
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True,
                        help="Original project owning ALL images in /dev/shm/complete")
    args = parser.parse_args()
    cfg = ConfigFiles("ftp.json")
    queue = TransferQueue({"mode": "ftp", "server": cfg["server"],
                           "user": cfg["user"], "path": cfg["path"],
                           "project": args.project})
    count = recover(queue)
    print(f"Preserved {count} images in {queue.directory}. No images sent to FTP.")
    print("Select the same project and FTP configuration in the app to resume.")


if __name__ == "__main__":
    main()
