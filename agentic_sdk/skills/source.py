"""Where a skill package comes from: a directory, an archive, or a repository.

A source is one string. It is either a path on this machine or an address with
the version written into it — ``https://host/org/name.git@v1.2.0``. Whatever the
source, resolving it ends at a directory, which is the only thing the package
format itself reads. See ADR-0007.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path, PurePosixPath


MAX_PACKAGE_BYTES = 5 * 1024 * 1024
"""How large a package may be once unpacked.

A package is text, so a real one is far smaller. The ceiling is what says an
archive or a repository is carrying something other than a package.
"""

_FETCHABLE_SCHEMES = ("https", "file")
"""A public address, or a repository on this machine. Never a plaintext address.

``file`` is here because a repository on this machine is a path, not a network
address. The Playground narrows this to ``https`` before it calls, because its
addresses are typed into a browser by someone it does not know.
"""

_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/+-]*")
_CACHE_ENVIRONMENT_KEY = "AGENTIC_SDK_SKILL_PACKAGES"


class SkillSourceRefused(ValueError):
    """A source that cannot be turned into a package, and the one rule that says why.

    A package refusal names a rule and a file; this names a rule and the source
    it was asked to read, so the two are told apart by what they point at.
    """

    def __init__(self, *, rule: str, source: str, detail: str = "") -> None:
        self.rule = rule
        self.source = source
        self.detail = detail
        super().__init__(f"skill package source {source!r} refused ({rule}): {detail}" if detail else f"skill package source {source!r} refused ({rule})")


def cache_root() -> Path:
    """Where fetched and unpacked packages are kept between runs."""
    configured = os.environ.get(_CACHE_ENVIRONMENT_KEY)
    if configured:
        return Path(configured)
    return Path.home() / ".cache" / "agentic-sdk" / "skill-packages"


def address_of(source: str | Path) -> tuple[str, str] | None:
    """The repository and version a source names, or ``None`` when it is a path.

    Raises :class:`SkillSourceRefused` for an address this cannot be asked to
    fetch: a scheme that is not public, a login written into the address, a
    missing version, or a version that is not a name.
    """
    if isinstance(source, Path):
        return None
    text = str(source).strip()
    if not text:
        raise SkillSourceRefused(rule="missing_source", source=str(source), detail="a source is a path or an address")
    scheme, separator, _ = text.partition("://")
    if not separator:
        return None
    if scheme not in _FETCHABLE_SCHEMES:
        raise SkillSourceRefused(rule="unsupported_url", source=text, detail=f"only {' and '.join(_FETCHABLE_SCHEMES)} addresses are read")
    rest = text[len(scheme) + len("://") :]
    netloc, _, path = rest.partition("/")
    if "@" in netloc:
        # The address is kept with the agent and shown to everyone who opens it,
        # so a login written into it would be handed out with the agent.
        raise SkillSourceRefused(rule="unsupported_url", source=text, detail="the address carries a login; only public repositories are read")
    if "@" not in path:
        # A package that follows its author's latest commit changes an agent's
        # behaviour without anyone mounting anything.
        raise SkillSourceRefused(rule="missing_version", source=text, detail="write the version into the address, as url@tag")
    path, _, version = path.rpartition("@")
    if not _VERSION.fullmatch(version) or ".." in version:
        raise SkillSourceRefused(rule="unsupported_version", source=text, detail="a version is the name of a tag, a branch or a commit")
    return f"{scheme}://{netloc}/{path}", version


def resolve_package(source: str | Path) -> Path:
    """The directory a source names, fetching or unpacking it once if it has to.

    A directory is used where it is. An archive or a repository is put under the
    cache, keyed by what it came from, so the same source resolves to the same
    directory and is read from the network only the first time.
    """
    address = address_of(source)
    if address is not None:
        return _fetched(*address)
    path = Path(source)
    if path.is_file() and path.suffix == ".zip":
        return _unpacked(path)
    # A directory, or a path that is not there at all: the package format says
    # what is wrong with it, naming the file it could not find.
    return path


def fetch_git_package(url: str, version: str, target: Path) -> Path:
    """Check out one tag, branch or commit of a repository into ``target``.

    Credential prompts are switched off, so a repository that needs a login
    fails at once instead of waiting on a terminal nobody is watching, and the
    machine's own git configuration is left out, so a login stored for another
    purpose is never offered to the repository either. The history is how the
    files arrived, not part of the package, so it is dropped.
    """
    target.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
    commands = (
        ["git", "init", "--quiet"],
        ["git", "remote", "add", "origin", url],
        ["git", "-c", "credential.helper=", "fetch", "--depth", "1", "--quiet", "origin", version],
        ["git", "checkout", "--quiet", "FETCH_HEAD"],
    )
    for command in commands:
        try:
            completed = subprocess.run(command, cwd=target, env=environment, capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SkillSourceRefused(rule="fetch_failed", source=url, detail=str(exc)) from exc
        if completed.returncode != 0:
            raise SkillSourceRefused(rule="fetch_failed", source=url, detail=(completed.stderr or completed.stdout).strip()[-500:])
    shutil.rmtree(target / ".git", ignore_errors=True)
    _within_the_ceiling(_size_of(target), url)
    return target


def unpack_archive(data: bytes, target: Path) -> Path:
    """Unpack a zip archive into ``target`` and return the package directory inside it.

    An archive that holds one folder is that package; an archive of loose files
    is the package itself, and takes the name it is given.
    """
    _within_the_ceiling(len(data), target.name)
    target.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            budget = MAX_PACKAGE_BYTES
            for member in archive.infolist():
                if member.is_dir():
                    continue
                relative = PurePosixPath(member.filename)
                if relative.is_absolute() or ".." in relative.parts:
                    raise SkillSourceRefused(rule="unreadable_archive", source=member.filename, detail="the archive holds a path that leaves it")
                written = target / Path(*relative.parts)
                written.parent.mkdir(parents=True, exist_ok=True)
                # Counted as it is written: the sizes an archive declares are
                # the archive's own claim, and a small upload can unpack to gigabytes.
                with archive.open(member) as source, written.open("wb") as destination:
                    budget -= _copy_within(source, destination, budget, member.filename)
    except zipfile.BadZipFile as exc:
        raise SkillSourceRefused(rule="unreadable_archive", source=target.name, detail=str(exc)) from exc
    return _single_directory_in(target) or target


def _fetched(url: str, version: str) -> Path:
    package = cache_root() / _key(f"{url}@{version}") / repository_name(url)
    if package.is_dir():
        return package
    if package.exists():
        package.unlink()
    try:
        fetch_git_package(url, version, package)
    except SkillSourceRefused:
        shutil.rmtree(package, ignore_errors=True)
        raise
    return package


def _unpacked(archive: Path) -> Path:
    data = archive.read_bytes()
    unpacked = cache_root() / _key(hashlib.sha256(data).hexdigest())
    if unpacked.is_dir():
        return _single_directory_in(unpacked) or unpacked
    try:
        return unpack_archive(data, unpacked / (archive.stem or "package"))
    except SkillSourceRefused:
        shutil.rmtree(unpacked, ignore_errors=True)
        raise


def _key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def repository_name(url: str) -> str:
    """The package name a repository address gives: its last segment, without .git."""
    name = url.rstrip("/").rsplit("/", 1)[-1]
    name = name[: -len(".git")] if name.endswith(".git") else name
    return "".join(character for character in name if character.isalnum() or character in "-_.") or "package"


def _single_directory_in(root: Path) -> Path | None:
    children = [child for child in root.iterdir() if not child.name.startswith("__MACOSX")]
    return children[0] if len(children) == 1 and children[0].is_dir() else None


def _size_of(root: Path) -> int:
    return sum(file.stat().st_size for file in root.rglob("*") if file.is_file() and not file.is_symlink())


def _within_the_ceiling(size: int, source: str) -> None:
    if size > MAX_PACKAGE_BYTES:
        raise SkillSourceRefused(rule="package_too_large", source=source, detail=f"{size} bytes; the limit is {MAX_PACKAGE_BYTES}")


def _copy_within(source, destination, budget: int, name: str) -> int:
    written = 0
    while chunk := source.read(64 * 1024):
        written += len(chunk)
        if written > budget:
            raise SkillSourceRefused(rule="package_too_large", source=name, detail=f"the archive unpacks to more than {MAX_PACKAGE_BYTES} bytes")
        destination.write(chunk)
    return written
