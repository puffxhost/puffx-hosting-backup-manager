#!/usr/bin/env python3
"""Create, verify, retain, and restore cPanel account backups."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


def load_config(path: Path) -> dict:
    with path.open("rb") as stream:
        config = tomllib.load(stream)
    backup, database = config.get("backup", {}), config.get("database", {})
    if not backup.get("directory") or not backup.get("paths"):
        raise ValueError("Config needs backup.directory and at least one backup.paths entry")
    if not isinstance(backup["paths"], list) or not all(Path(item).is_dir() for item in backup["paths"]):
        raise ValueError("Every configured backup path must exist and be a directory")
    if not database.get("name") or not database.get("user") or not database.get("password_env"):
        raise ValueError("Config needs database name, user, and password_env")
    if not os.environ.get(database["password_env"]):
        raise ValueError(f"Set environment variable {database['password_env']} before running")
    if int(backup.get("retention_count", 14)) < 1:
        raise ValueError("retention_count must be at least 1")
    return config


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_database_dump(config: dict, target: Path) -> None:
    db = config["database"]
    env = os.environ.copy()
    env["MYSQL_PWD"] = os.environ[db["password_env"]]
    command = ["mysqldump", "--single-transaction", "--quick", "--skip-lock-tables",
               "--host", str(db.get("host", "localhost")), "--port", str(db.get("port", 3306)),
               "--user", db["user"], db["name"]]
    with target.open("wb") as output:
        result = subprocess.run(command, stdout=output, stderr=subprocess.PIPE, env=env, check=False)
    if result.returncode:
        target.unlink(missing_ok=True)
        raise RuntimeError("mysqldump failed: " + result.stderr.decode(errors="replace")[-1000:])


def inventory(archive: Path) -> list[dict]:
    with tarfile.open(archive, "r:gz") as bundle:
        return [{"path": item.name, "size": item.size} for item in bundle.getmembers() if item.isfile()]


def verify_backup(archive: Path) -> dict:
    archive = archive.expanduser().resolve()
    manifest_path = archive.with_suffix(archive.suffix + ".json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("archive") != archive.name or manifest.get("sha256") != sha256_file(archive):
        raise ValueError("Archive checksum or name does not match the manifest")
    if inventory(archive) != manifest.get("files"):
        raise ValueError("Archive contents do not match manifest inventory")
    return manifest


def upload_sftp(config: dict, archive: Path, manifest: Path) -> None:
    options = config.get("sftp", {})
    if not options.get("enabled", False):
        return
    try:
        import paramiko
    except ImportError as exc:
        raise RuntimeError("Install SFTP support with: pip install -e '.[sftp]'") from exc
    password_env = options.get("password_env")
    password = os.environ.get(password_env) if password_env else None
    key_path = Path(options["key_file"]).expanduser() if options.get("key_file") else None
    if not password and not key_path:
        raise ValueError("SFTP needs password_env or key_file")
    known_hosts = Path(options.get("known_hosts", "~/.ssh/known_hosts")).expanduser()
    client = paramiko.SSHClient()
    client.load_host_keys(str(known_hosts))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(options["host"], port=int(options.get("port", 22)), username=options["username"],
                   password=password, key_filename=str(key_path) if key_path else None,
                   timeout=15, allow_agent=False, look_for_keys=False)
    try:
        with client.open_sftp() as sftp:
            remote = options["remote_directory"].rstrip("/")
            sftp.put(str(archive), f"{remote}/{archive.name}")
            sftp.put(str(manifest), f"{remote}/{manifest.name}")
    finally:
        client.close()


def prune_backups(directory: Path, keep: int) -> None:
    archives = sorted(directory.glob("backup-*.tar.gz"), key=lambda path: path.name, reverse=True)
    for archive in archives[keep:]:
        verify_backup(archive)
        archive.unlink()
        archive.with_suffix(archive.suffix + ".json").unlink(missing_ok=True)


def create_backup(config: dict) -> Path:
    settings = config["backup"]
    destination = Path(settings["directory"]).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = destination / f"backup-{stamp}.tar.gz"
    with tempfile.TemporaryDirectory(prefix="puffx-backup-") as temporary:
        stage = Path(temporary)
        for index, source in enumerate(settings["paths"], start=1):
            shutil.copytree(Path(source).resolve(), stage / "files" / f"site-{index}", symlinks=False)
        dump = stage / "database" / "database.sql"
        dump.parent.mkdir(parents=True)
        run_database_dump(config, dump)
        with tarfile.open(archive, "w:gz") as bundle:
            bundle.add(stage / "files", arcname="files")
            bundle.add(stage / "database", arcname="database")
    archive.chmod(0o600)
    manifest_path = archive.with_suffix(archive.suffix + ".json")
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "archive": archive.name,
                "sha256": sha256_file(archive), "files": inventory(archive)}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    manifest_path.chmod(0o600)
    verify_backup(archive)
    upload_sftp(config, archive, manifest_path)
    prune_backups(destination, int(settings.get("retention_count", 14)))
    return archive


def safe_extract(archive: Path, target: Path) -> None:
    target = target.expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as bundle:
        for item in bundle.getmembers():
            name = PurePosixPath(item.name)
            if name.is_absolute() or ".." in name.parts or not (item.isfile() or item.isdir()):
                raise ValueError(f"Unsafe archive entry: {item.name}")
            resolved = (target / Path(*name.parts)).resolve()
            if resolved != target and target not in resolved.parents:
                raise ValueError(f"Archive entry escapes target: {item.name}")
        bundle.extractall(target, filter="data")


def restore_database(config: dict, archive: Path, confirmed: bool) -> None:
    if not confirmed:
        raise ValueError("Database restore overwrites data; review the archive and pass --yes to confirm")
    verify_backup(archive)
    db = config["database"]
    env = os.environ.copy()
    env["MYSQL_PWD"] = os.environ[db["password_env"]]
    with tarfile.open(archive, "r:gz") as bundle:
        dump = bundle.extractfile("database/database.sql")
        if dump is None:
            raise ValueError("Database dump is missing")
        command = ["mysql", "--host", str(db.get("host", "localhost")), "--port", str(db.get("port", 3306)),
                   "--user", db["user"], db["name"]]
        result = subprocess.run(command, stdin=dump, stderr=subprocess.PIPE, env=env, check=False)
    if result.returncode:
        raise RuntimeError("mysql restore failed: " + result.stderr.decode(errors="replace")[-1000:])
    print(f"Restored database {db['name']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("backup", help="Create, verify, upload, and retain a backup")
    verify_cmd = commands.add_parser("verify", help="Verify archives against their manifests")
    verify_cmd.add_argument("--archive", type=Path)
    verify_cmd.add_argument("--backup-dir", type=Path, default=Path("./backups"))
    files = commands.add_parser("restore-files", help="Extract verified files into a review directory")
    files.add_argument("--archive", type=Path, required=True)
    files.add_argument("--target", type=Path, required=True)
    database = commands.add_parser("restore-database", help="Restore the configured database")
    database.add_argument("--archive", type=Path, required=True)
    database.add_argument("--database-name", required=True)
    database.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            archives = [args.archive] if args.archive else sorted(args.backup_dir.glob("backup-*.tar.gz"))
            if not archives:
                raise ValueError("No backup archives found")
            for archive in archives:
                verify_backup(archive)
                print(f"OK {archive}")
            return 0
        config = load_config(args.config)
        if args.command == "backup":
            print(f"Created verified backup: {create_backup(config)}")
        elif args.command == "restore-files":
            verify_backup(args.archive)
            safe_extract(args.archive, args.target)
            print(f"Files extracted for review to {args.target.expanduser().resolve()}")
        elif args.command == "restore-database":
            if args.database_name != config["database"]["name"]:
                raise ValueError("--database-name must exactly match config.toml")
            restore_database(config, args.archive, args.yes)
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, tarfile.TarError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
