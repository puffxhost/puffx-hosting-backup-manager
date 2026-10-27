# Security notes

- Keep `config.toml`, backup archives and logs outside `public_html`.
- Database and SFTP passwords are read from environment variables. Never commit secrets or private keys.
- Use a dedicated SFTP account and SSH host-key verification. The client rejects unknown host keys.
- Backups may contain customer records, sessions and tokens. Restrict access and retention; use encrypted storage from your provider.
- Restore files into a separate review directory. Database restore replaces the configured database and requires `--yes`.
- Run under the least-privileged cPanel account that can read the configured site and database.
