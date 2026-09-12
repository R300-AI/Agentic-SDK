"""Where the Playground keeps skill packages, and how one gets from an upload to an agent.

A package passes through two places. It is first *staged*: unpacked where it can
be checked and shown to the person, with nothing on the agent changed. Once the
person confirms, it is *committed*: copied into the store under its content
digest, so the same package mounted on several agents is kept once, and the agent
spec records only its name, source and version.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from agentic_sdk.skills import SkillPackage, SkillPackageRefused, mount_packages


_STAGED_META = "staged.json"

MAX_PACKAGE_BYTES = 5 * 1024 * 1024
"""How large a package may be once unpacked.

A package is text, so a real one is far smaller; the limit keeps an upload or a
repository from filling the disk before the package checks ever run.
"""

_DIGEST = re.compile(r"[0-9a-f]{64}")
_PACKAGE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/+-]*")

REFUSAL_MESSAGES = {
    "not_text": "技能包只收文字檔，這個檔案不是文字。",
    "missing_file": "找不到這個檔案：對應檔或技能用到了它，但技能包裡沒有。",
    "outside_package": "對應檔指到技能包資料夾以外的位置。技能只能引用自己技能包裡的檔案。",
    "linked_file": "技能包不收符號連結，請放入檔案本身。",
    "name_mismatch": "技能名稱不一致：目錄名、SKILL.md 裡的名稱與對應檔條目必須相同。",
    "name_taken": "這個 agent 已經掛了同名的技能。",
    "description_too_long": "技能說明超過 1,024 字元。",
    "too_large": "這個技能加進對話的內容超過上限。",
    "missing_frontmatter": "SKILL.md 的開頭要寫出技能名稱與說明。",
    "invalid_mapping": "對應檔的內容不對：請確認它是合法的 YAML，且每個技能各自一個條目。",
    "invalid_declaration": "disable-model-invocation 只能寫 true 或 false。",
    "package_too_large": "技能包超過 5 MB。技能包只放文字，請確認沒有夾帶其他內容。",
    "unreadable_archive": "無法讀取這個壓縮檔。",
    "missing_source": "請上傳技能包壓縮檔，或填寫 git repo 網址與版本。",
    "missing_version": "請填寫要鎖定的版本標籤或 commit。",
    "unsupported_version": "版本只能是標籤、分支或 commit 的名稱，不能以 - 開頭，也不能含空白。",
    "unsupported_url": "只接受 https 開頭、不含帳號密碼的公開 git repo 網址。",
    "fetch_failed": "無法取回這個 git repo。它可能不存在、版本不對，或需要帳密（目前只支援公開 repo）。",
}


class SkillSourceError(ValueError):
    """A package that never became something to check: no source, or one that could not be read."""

    def __init__(self, rule: str, detail: str = "") -> None:
        self.rule = rule
        self.detail = detail
        super().__init__(f"{rule}: {detail}")

    def payload(self) -> dict[str, str]:
        return {"rule": self.rule, "path": "", "detail": self.detail, "message": REFUSAL_MESSAGES.get(self.rule, self.detail)}


class StagingNotFound(LookupError):
    """A confirmation for a package that was never inspected, or already committed."""


def store_root() -> Path:
    configured = os.environ.get("PLAYGROUND_SKILL_STORE_ROOT", "").strip()
    return Path(configured) if configured else Path(tempfile.gettempdir()) / "agentic-sdk-playground" / "skill-packages"


def refusal_payload(refusal: SkillPackageRefused) -> dict[str, str]:
    return {
        "rule": refusal.rule,
        "path": refusal.path,
        "package": refusal.package,
        "detail": refusal.detail,
        "message": REFUSAL_MESSAGES.get(refusal.rule, refusal.detail),
    }


def stage_upload(data: bytes, filename: str) -> str:
    """Unpack an uploaded archive into a fresh staging area and return its id."""
    if len(data) > MAX_PACKAGE_BYTES:
        raise SkillSourceError("package_too_large", f"the archive is {len(data)} bytes; the limit is {MAX_PACKAGE_BYTES}")
    staging_id = uuid.uuid4().hex
    unpacked = _staging_dir(staging_id) / "unpacked"
    unpacked.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            budget = MAX_PACKAGE_BYTES
            for member in members:
                relative = PurePosixPath(member.filename)
                if relative.is_absolute() or ".." in relative.parts:
                    raise SkillSourceError("unreadable_archive", f"unsafe path in archive: {member.filename}")
                target = unpacked / Path(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                # Counted as it is written: the sizes an archive declares are
                # the archive's own claim, and a small upload can unpack to gigabytes.
                with archive.open(member) as source, target.open("wb") as destination:
                    budget -= _copy_within(source, destination, budget)
    except zipfile.BadZipFile as exc:
        shutil.rmtree(_staging_dir(staging_id), ignore_errors=True)
        raise SkillSourceError("unreadable_archive", str(exc)) from exc
    except SkillSourceError:
        shutil.rmtree(_staging_dir(staging_id), ignore_errors=True)
        raise
    package_dir = _single_top_directory(unpacked) or _rename_to(unpacked, Path(filename).stem or "package")
    _write_meta(staging_id, {"source": "upload", "url": None, "version": None, "package_dir": str(package_dir)})
    return staging_id


def stage_git(url: str, version: str) -> str:
    """Fetch a public repository at a fixed version into a fresh staging area and return its id.

    A version is required: a package that follows its author's latest commit
    changes an agent's behaviour without anyone mounting anything.
    """
    url = url.strip()
    version = version.strip()
    if not url:
        raise SkillSourceError("missing_source")
    address = urlsplit(url)
    if address.scheme != "https" or not address.hostname:
        raise SkillSourceError("unsupported_url", url)
    if "@" in address.netloc:
        # The address is kept on the agent and shown to everyone who opens it,
        # so a login written into it would be handed out with the agent.
        raise SkillSourceError("unsupported_url", "the address carries a login; only public repositories are supported")
    if not version:
        raise SkillSourceError("missing_version")
    if not _VERSION.fullmatch(version) or ".." in version:
        raise SkillSourceError("unsupported_version", version)
    staging_id = uuid.uuid4().hex
    repository = _staging_dir(staging_id) / "repository" / _repository_name(url)
    repository.parent.mkdir(parents=True, exist_ok=True)
    try:
        fetch_git_repository(url, version, repository)
        # The history is how the files arrived, not part of the package.
        shutil.rmtree(repository / ".git", ignore_errors=True)
        size = sum(file.stat().st_size for file in repository.rglob("*") if file.is_file() and not file.is_symlink())
        if size > MAX_PACKAGE_BYTES:
            raise SkillSourceError("package_too_large", f"the repository holds {size} bytes; the limit is {MAX_PACKAGE_BYTES}")
    except SkillSourceError:
        shutil.rmtree(_staging_dir(staging_id), ignore_errors=True)
        raise
    _write_meta(staging_id, {"source": "git", "url": url, "version": version, "package_dir": str(repository)})
    return staging_id


def fetch_git_repository(url: str, version: str, target: Path) -> None:
    """Check out one tag, branch or commit of a public repository into ``target``.

    Credential prompts are switched off, so a repository that needs a login fails
    at once instead of waiting on a terminal nobody is watching, and the server's
    own git configuration is left out, so a login stored for another purpose is
    never offered to the repository either.
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
            raise SkillSourceError("fetch_failed", str(exc)) from exc
        if completed.returncode != 0:
            raise SkillSourceError("fetch_failed", (completed.stderr or completed.stdout).strip()[-500:])


def inspect(staging_id: str, mounted: list[dict[str, Any]]) -> dict[str, Any]:
    """Check a staged package against the agent it would join, and describe it.

    Raises :class:`SkillPackageRefused` naming the first rule it breaks. A package
    with the same name as one already mounted is an upgrade, not a clash.
    """
    meta = _read_meta(staging_id)
    package = SkillPackage.load(Path(meta["package_dir"]))
    others = [path_for(entry) for entry in mounted if entry.get("name") != package.name and is_stored(entry)]
    # The mounting function reads packages from disk, so the staged one goes
    # in by path like the rest.
    mount_packages([*others, package.path])
    version = meta.get("version") or _digest(package.path)[:12]
    replaces = package.name if any(entry.get("name") == package.name for entry in mounted) else None
    return {
        "staging_id": staging_id,
        "package": _describe(package, source=meta["source"], url=meta.get("url"), version=version),
        "replaces": replaces,
    }


def commit(staging_id: str, mounted: list[dict[str, Any]]) -> dict[str, Any]:
    """Copy a staged package into the store, checking it again, and return its spec entry."""
    preview = inspect(staging_id, mounted)
    meta = _read_meta(staging_id)
    package_dir = Path(meta["package_dir"])
    name = preview["package"]["name"]
    digest = _digest(package_dir)
    target = store_root() / "packages" / digest / name
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(package_dir, target)
    shutil.rmtree(_staging_dir(staging_id), ignore_errors=True)
    return {
        "name": name,
        "source": preview["package"]["source"],
        "url": preview["package"]["url"],
        "version": preview["package"]["version"],
        "digest": digest,
    }


def names_a_stored_package(entry: dict[str, Any]) -> bool:
    """Whether an entry's digest and name can only point inside the store.

    A spec arrives from AI Hub as well as from this server, so its entries are
    read as data, not as paths to trust.
    """
    return bool(_DIGEST.fullmatch(str(entry.get("digest") or "")) and _PACKAGE_NAME.fullmatch(str(entry.get("name") or "")))


def path_for(entry: dict[str, Any]) -> Path:
    return store_root() / "packages" / str(entry.get("digest") or "") / str(entry.get("name") or "")


def is_stored(entry: dict[str, Any]) -> bool:
    return names_a_stored_package(entry) and path_for(entry).is_dir()


def describe(entry: dict[str, Any]) -> dict[str, Any]:
    """A mounted package as the Builder shows it, including one whose files this server lacks."""
    source = str(entry.get("source") or "upload")
    version = str(entry.get("version") or "")
    if not is_stored(entry):
        return {"name": entry.get("name"), "source": source, "url": entry.get("url"), "version": version, "maintainer": {}, "skills": [], "missing": True}
    package = SkillPackage.load(path_for(entry))
    return {**_describe(package, source=source, url=entry.get("url"), version=version), "missing": False}


def mounted_entries(spec: dict[str, Any]) -> list[dict[str, Any]]:
    skills = spec.get("skills") if isinstance(spec.get("skills"), dict) else {}
    return [entry for entry in skills.get("packages") or [] if isinstance(entry, dict) and names_a_stored_package(entry)]


def missing_packages(spec: dict[str, Any]) -> list[str]:
    """Names of packages the agent mounts whose files are not on this server."""
    return [str(entry["name"]) for entry in mounted_entries(spec) if not is_stored(entry)]


def package_paths(spec: dict[str, Any]) -> list[Path]:
    return [path_for(entry) for entry in mounted_entries(spec)]


def with_entry(spec: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    """The spec with this package mounted, replacing one of the same name in place."""
    entries: list[dict[str, Any]] = []
    replaced = False
    for existing in mounted_entries(spec):
        if existing.get("name") == entry["name"]:
            entries.append(entry)
            replaced = True
        else:
            entries.append(existing)
    if not replaced:
        entries.append(entry)
    return {**spec, "skills": {"packages": entries}}


def without_package(spec: dict[str, Any], name: str) -> dict[str, Any]:
    return {**spec, "skills": {"packages": [entry for entry in mounted_entries(spec) if entry.get("name") != name]}}


def _describe(package: SkillPackage, *, source: str, url: Any, version: str) -> dict[str, Any]:
    return {
        "name": package.name,
        "source": source,
        "url": url,
        "version": version,
        "maintainer": dict(package.maintainer),
        "skills": [{"name": skill.name, "description": skill.description} for skill in package.skills],
    }


def _repository_name(url: str) -> str:
    name = url.rstrip("/").rsplit("/", 1)[-1]
    name = name[: -len(".git")] if name.endswith(".git") else name
    return "".join(character for character in name if character.isalnum() or character in "-_.") or "package"


def _staging_dir(staging_id: str) -> Path:
    return store_root() / "staging" / staging_id


def _write_meta(staging_id: str, meta: dict[str, Any]) -> None:
    (_staging_dir(staging_id) / _STAGED_META).write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


def _read_meta(staging_id: str) -> dict[str, Any]:
    if not staging_id or "/" in staging_id or "\\" in staging_id or ".." in staging_id:
        raise StagingNotFound(staging_id)
    meta_path = _staging_dir(staging_id) / _STAGED_META
    if not meta_path.is_file():
        raise StagingNotFound(staging_id)
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _single_top_directory(unpacked: Path) -> Path | None:
    children = [child for child in unpacked.iterdir() if not child.name.startswith("__MACOSX")]
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return None


def _rename_to(unpacked: Path, name: str) -> Path:
    target = unpacked.parent / "package" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    unpacked.rename(target)
    return target


def _copy_within(source, destination, budget: int) -> int:
    written = 0
    while chunk := source.read(64 * 1024):
        written += len(chunk)
        if written > budget:
            raise SkillSourceError("package_too_large", f"the archive unpacks to more than {MAX_PACKAGE_BYTES} bytes")
        destination.write(chunk)
    return written


def _digest(root: Path) -> str:
    hasher = hashlib.sha256()
    for file in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        hasher.update(file.relative_to(root).as_posix().encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(file.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()
