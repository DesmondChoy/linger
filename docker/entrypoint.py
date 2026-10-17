"""Hand an existing Railway state volume to the unprivileged application user."""

import os
import stat
import sys

APP_UID = 10001
APP_GID = 10001
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def open_state_directory(path: str) -> int:
    """Open the state directory without traversing a symlink in its path."""
    components = path.split("/")
    if not path.startswith("/") or ".." in components or not any(components):
        raise ValueError("LINGER_STATE_DIR must be an absolute directory below /")
    components = [component for component in components if component and component != "."]
    if not components:
        raise ValueError("LINGER_STATE_DIR must be an absolute directory below /")

    directory = os.open("/", DIRECTORY_FLAGS)
    try:
        for index, component in enumerate(components):
            if index == len(components) - 1:
                try:
                    os.mkdir(component, mode=0o700, dir_fd=directory)
                except FileExistsError:
                    pass
            child = os.open(component, DIRECTORY_FLAGS, dir_fd=directory)
            os.close(directory)
            directory = child
        return directory
    except BaseException:
        os.close(directory)
        raise


def migrate_ownership(directory: int) -> None:
    """Change ownership through directory descriptors; reject links and devices."""
    with os.scandir(directory) as entries:
        for entry in entries:
            mode = entry.stat(follow_symlinks=False).st_mode
            if stat.S_ISDIR(mode):
                child = os.open(entry.name, DIRECTORY_FLAGS, dir_fd=directory)
                try:
                    migrate_ownership(child)
                finally:
                    os.close(child)
            elif stat.S_ISREG(mode):
                child = os.open(
                    entry.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=directory,
                )
                try:
                    metadata = os.fstat(child)
                    if not stat.S_ISREG(metadata.st_mode):
                        raise ValueError("State entries must be regular files or directories")
                    if metadata.st_nlink != 1:
                        raise ValueError("Hard links in state are refused")
                    os.fchown(child, APP_UID, APP_GID)
                finally:
                    os.close(child)
            else:
                raise ValueError("State entries must be regular files or directories; links are refused")
    os.fchown(directory, APP_UID, APP_GID)


def main(arguments: list[str] | None = None) -> None:
    arguments = sys.argv[1:] if arguments is None else arguments
    if not arguments:
        raise ValueError("An application command is required")
    if os.geteuid() == 0:
        directory = open_state_directory(os.environ.get("LINGER_STATE_DIR", "/var/lib/linger"))
        try:
            migrate_ownership(directory)
        finally:
            os.close(directory)
        os.setgroups([])
        os.setgid(APP_GID)
        os.setuid(APP_UID)
        os.environ["HOME"] = "/home/linger"
    os.execvp(arguments[0], arguments)


if __name__ == "__main__":
    main()
