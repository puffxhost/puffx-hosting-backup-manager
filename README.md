# Puffx Hosting Backup Manager

A Python CLI for scheduled website and MySQL backups on cPanel hosting. It creates compressed archives, verifies SHA-256 checksums, applies retention, and supports explicit restore. Optional SFTP provides an off-site copy. The first version runs on the cPanel account through Cron Jobs; VPS support is future work.

## Requirements

- Python 3.12+
- `mysqldump` and `mysql` for database backup/restore
- Optional SFTP: `pip install -e '.[sftp]'`

## Quick start

1. Copy `config.example.toml` to `config.toml` and set paths/database details.
2. Set the database password in the environment variable named by `password_env`. Do not put passwords in TOML.
3. Run and verify a backup:

```sh
python3 backup_manager.py --config config.toml backup
python3 backup_manager.py verify --backup-dir ./backups
```

4. Add this under **cPanel → Cron Jobs** for a daily 02:30 run (adjust paths):

```cron
30 2 * * * cd /home/CPANEL_USER/backup-manager && /usr/bin/python3 backup_manager.py --config config.toml backup >> backup.log 2>&1
```

Run it manually as the cPanel account first. Confirm the account can read the website files and access `mysqldump` before scheduling.

## Restore

Restore files to a separate review directory; the tool does not overwrite a live document root automatically:

```sh
python3 backup_manager.py restore-files --archive ./backups/backup-YYYYMMDDTHHMMSSZ.tar.gz --target ./restore-review
```

Database restore replaces data in the configured database and requires an explicit confirmation flag. Make a safety backup and double-check the database name first:

```sh
python3 backup_manager.py --config config.toml restore-database --archive ./backups/backup-YYYYMMDDTHHMMSSZ.tar.gz --database-name CPANEL_USER_database --yes
```

## Features and limits

- Website directories plus a `mysqldump` export in a timestamped `.tar.gz` archive.
- JSON manifest with archive inventory and SHA-256 digest; verification before retention cleanup.
- Optional verified upload to SFTP. Remote backups are never deleted automatically.
- No dashboard, cPanel API integration, VPS agent, encryption, or automated restore drills yet.

Backups contain private website/database data. Keep config, archives and logs outside `public_html`; restrict permissions and use encrypted storage from your provider. See [SECURITY.md](SECURITY.md).

## License

MIT. See [LICENSE](LICENSE).
