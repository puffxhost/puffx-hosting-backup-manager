# 🌤️ Puffx Hosting Backup Manager

**Step-by-step backups for cPanel websites and MySQL databases.** This Python command-line tool copies website folders, exports the database with `mysqldump`, packages both into a compressed archive, verifies it with SHA-256, and applies a retention policy to older local backups. Optional SFTP support can send an off-site copy.

![Animated backup workflow](assets/backup-workflow.gif)

> 🎞️ The animated GIF shows the backup workflow. A scalable vector version is also available at [assets/backup-workflow.svg](assets/backup-workflow.svg); some viewers may display SVG animation as a static image.

## 🧭 What this guide covers

1. Checking cPanel requirements
2. Downloading the project and setting up Python
3. Configuring backup folders, website paths, and database details
4. Protecting the database password
5. Creating and verifying the first backup
6. Scheduling a cPanel Cron Job
7. Restoring website files or a database
8. Setting up optional off-site SFTP copies
9. Troubleshooting common errors

---

## ✅ Before you begin

- cPanel login with **Terminal/SSH** access
- The **Cron Jobs** feature in cPanel
- Python **3.12 or newer**
- The `mysqldump` and `mysql` command-line tools
- Permission to read the website directory
- The exact MySQL database name, username, password, and host
- Enough free space in your home directory for backups

### Step 0: Check requirements in cPanel Terminal

Open cPanel → **Terminal**, then run these commands one at a time:

```sh
python3.12 --version
mysqldump --version
mysql --version
```

**Expected:** Python reports version `3.12` or newer, and the MySQL tools report their versions. If a command returns `command not found`, ask your hosting provider to enable it. Do not try to run this tool with Python 3.11 or older.

### 🔐 Keep backup data outside the public website

`public_html` may be accessible from the web. Backup archives can contain database records, user sessions, and website files. Keep the config, password file, archives, and logs under `/home/CPANEL_USER/`—never inside `public_html`.

---

# 🚀 Setup: follow each step in order

## Step 1 — Find your cPanel username and home path

In Terminal, run:

```sh
whoami
pwd
```

`whoami` prints your username. `pwd` usually prints a path such as `/home/CPANEL_USER`. Replace every `CPANEL_USER` placeholder in this guide with your actual cPanel username. **Do not leave the placeholder unchanged in commands.**

## Step 2 — Download the project to your home directory

In Terminal, run:

```sh
cd ~
git clone https://github.com/puffxhost/puffx-hosting-backup-manager.git backup-manager
cd ~/backup-manager
pwd
ls
```

**Expected:** `pwd` shows `/home/CPANEL_USER/backup-manager`; `ls` shows `backup_manager.py`, `config.example.toml`, and `pyproject.toml`.

### If `git` is not available

1. Open the [GitHub repository](https://github.com/puffxhost/puffx-hosting-backup-manager) in your browser.
2. Choose **Code → Download ZIP**.
3. Use cPanel **File Manager** to upload and extract the ZIP in your home folder. Do not extract it inside `public_html`.
4. In Terminal, change to the extracted project folder. For example, if the folder is named `puffx-hosting-backup-manager`, run:

```sh
cd ~/puffx-hosting-backup-manager
```

The remaining steps use `~/backup-manager`. If you used the ZIP method, replace it with the path to your extracted folder wherever it appears.

## Step 3 — Create a virtual environment

A virtual environment keeps this project's Python packages separate:

```sh
cd ~/backup-manager
python3.12 -m venv .venv
source .venv/bin/activate
python --version
```

**Expected:** `(.venv)` appears at the start of your prompt, and Python reports version `3.12` or newer.

If the `venv` module is missing or you get a permission error, ask your hosting provider to enable Python virtual environments. You should not need system-wide `sudo pip` access.

## Step 4 — Install the tool

With the virtual environment active, run:

```sh
python -m pip install --upgrade pip
python -m pip install .
```

**Expected:** installation completes without errors. The core features have no third-party Python dependencies. If you want optional SFTP support, use this command instead of the normal install command:

```sh
python -m pip install '.[sftp]'
```

> In each new Terminal session, activate the environment again: `cd ~/backup-manager && source .venv/bin/activate`.

## Step 5 — Create the backup directory

Replace the username placeholder with yours:

```sh
mkdir -p /home/CPANEL_USER/backups
chmod 700 /home/CPANEL_USER/backups
```

This directory is outside `public_html` and is accessible only to the account owner.

## Step 6 — Copy the example config

```sh
cd ~/backup-manager
cp config.example.toml config.toml
nano config.toml
```

In `nano`, save with **Ctrl+O**, then **Enter**. Exit with **Ctrl+X**. Do not commit or share this config on GitHub; `.gitignore` already excludes `config.toml`.

## Step 7 — Set the website and backup locations

Update the `[backup]` section in `config.toml` with your paths:

```toml
[backup]
directory = "/home/CPANEL_USER/backups"
retention_count = 14
paths = ["/home/CPANEL_USER/public_html"]
```

- `directory`: the folder you created in Step 5.
- `retention_count`: how many recent **local** archives to keep after a successful backup. It must be at least `1`.
- `paths`: the full paths to one or more existing website directories. For multiple folders, add entries to the TOML list, separated by commas:

```toml
paths = ["/home/CPANEL_USER/public_html", "/home/CPANEL_USER/store"]
```

Every path must already exist and be a directory. The tool stores source folders in the archive as `files/site-1`, `files/site-2`, and so on; it does not preserve their original folder names. Use absolute paths rather than relative paths.

## Step 8 — Set the database details

Open cPanel → **MySQL Databases**. Note the database used by your website and the user assigned to it. Update the `[database]` section:

```toml
[database]
host = "localhost"
port = 3306
name = "CPANEL_USER_database"
user = "CPANEL_USER_dbuser"
password_env = "PUFFX_BACKUP_DB_PASSWORD"
```

- Enter the full database `name` and `user` shown in cPanel—these often include your cPanel username as a prefix.
- Set `host` and `port` according to your hosting provider. `localhost:3306` is only a common example.
- The database user needs the privileges required to dump the database. Restoring also requires write privileges.
- Do **not** put the password in the TOML file. The next step stores it in a private environment file.

## Step 9 — Store the database password in a private environment file

```sh
mkdir -p ~/.config/puffx-backup
chmod 700 ~/.config/puffx-backup
nano ~/.config/puffx-backup/env.sh
```

Add this line to the file and replace the placeholder with your actual database password:

```sh
export PUFFX_BACKUP_DB_PASSWORD='YOUR_DATABASE_PASSWORD'
```

Save and exit (**Ctrl+O**, **Enter**, **Ctrl+X**), then run:

```sh
chmod 600 ~/.config/puffx-backup/env.sh
source ~/.config/puffx-backup/env.sh
```

The `password_env` value in your config and the exported variable name in `env.sh` must match **exactly**. If you changed the name in the TOML file, change it here too. Avoid typing the password as a command-line argument. If your password contains a single quote (`'`), this shell example will not work as written; ask your provider how to set a protected environment variable.

**Check the file permissions:** `cat ~/.config/puffx-backup/env.sh` displays the secret, so do not run it on a shared screen or save its output to a log. Check permissions with `ls -l ~/.config/puffx-backup/env.sh`; the mode should be `-rw-------`.

## Step 10 — Validate the config and folders

```sh
cd ~/backup-manager
source .venv/bin/activate
source ~/.config/puffx-backup/env.sh
ls -ld /home/CPANEL_USER/backups /home/CPANEL_USER/public_html
```

Both paths must exist. Reopen `config.toml` and check the username, folder paths, database name/user, and `password_env`. When loading the config, the tool checks that the website paths exist and that the password environment variable is set.

## Step 11 — Create the first backup manually

Run this manually before scheduling a Cron Job:

```sh
cd ~/backup-manager
source ~/.config/puffx-backup/env.sh
.venv/bin/python backup_manager.py --config config.toml backup
```

**Successful output:**

```text
Created verified backup: /home/CPANEL_USER/backups/backup-YYYYMMDDTHHMMSSZ.tar.gz
```

The actual timestamp will differ. The tool stages the website folders, creates an SQL dump with `mysqldump`, writes a `.tar.gz` archive and a `.json` manifest with the SHA-256 digest, verifies the archive, uploads it over SFTP if enabled, then applies retention to older verified local backups.

If the first run fails, do not create the Cron Job yet. Fix the error first using the **Troubleshooting** section.

## Step 12 — Verify the archive

```sh
cd ~/backup-manager
.venv/bin/python backup_manager.py verify --backup-dir /home/CPANEL_USER/backups
```

**Expected:** each archive is followed by an `OK /home/.../backup-....tar.gz` message. Verification also requires the matching `.tar.gz.json` manifest. It checks the archive name, SHA-256 digest, and inventory of files inside the archive. If no archives are found, the command prints `No backup archives found`.

To verify one archive only:

```sh
.venv/bin/python backup_manager.py verify --archive /home/CPANEL_USER/backups/backup-YYYYMMDDTHHMMSSZ.tar.gz
```

## Step 13 — Schedule a cPanel Cron Job

Cron runs the backup command automatically each day. Do not paste the password directly into the Cron UI; the command loads the protected `env.sh` file.

1. Open cPanel → **Cron Jobs**.
2. Select **Once Per Day** under Common Settings (or choose your preferred schedule).
3. Choose the hour and minute. For example: 02:30.
4. Paste the command below into the command field. Replace `CPANEL_USER` with your username:

```sh
/bin/bash -c 'source /home/CPANEL_USER/.config/puffx-backup/env.sh && cd /home/CPANEL_USER/backup-manager && /home/CPANEL_USER/backup-manager/.venv/bin/python backup_manager.py --config config.toml backup >> /home/CPANEL_USER/backup-manager/backup.log 2>&1'
```

5. Click **Add New Cron Job**.
6. After the next scheduled run, check `~/backup-manager/backup.log`. A successful run prints the archive path; if there is an error, read the end of the log.

🕒 Cron runs in the server's timezone. Confirm the timezone with cPanel or your hosting provider. `backup.log` is in the project folder, which must be outside `public_html`. If Bash is not at `/bin/bash` on your host, ask your provider for its path.

---

# ♻️ Restore guide

> Before restoring, keep the archive **and its matching `.json` manifest** together. Website files are first extracted to a review folder. A database restore replaces data in the configured database, so first make a safety backup of the current database.

## Extract website files to a review folder

1. Find the exact archive name in the backup folder:

```sh
ls -lh /home/CPANEL_USER/backups
```

2. Replace the timestamp in this command with the archive's actual timestamp:

```sh
cd ~/backup-manager
.venv/bin/python backup_manager.py restore-files --archive /home/CPANEL_USER/backups/backup-YYYYMMDDTHHMMSSZ.tar.gz --target /home/CPANEL_USER/restore-review
```

3. The output should say `Files extracted for review to ...`.
4. Extracted files will be in `/home/CPANEL_USER/restore-review/files/site-1/`. Data from a second configured path will be in `site-2/`.
5. Review and test the files, then manually copy them to the correct live hosting folder. The tool does not overwrite live website files automatically.

## Restore the MySQL database

⚠️ **This command overwrites the current data in the configured database.** First create a separate safety backup of the current database through cPanel and confirm the target and archive.

```sh
cd ~/backup-manager
source ~/.config/puffx-backup/env.sh
.venv/bin/python backup_manager.py --config config.toml restore-database --archive /home/CPANEL_USER/backups/backup-YYYYMMDDTHHMMSSZ.tar.gz --database-name CPANEL_USER_database --yes
```

- Replace `--archive` with the exact archive path.
- `--database-name` must **exactly match** the `[database] name` in the config.
- `--yes` is a required confirmation switch. Use it only after making a safety backup and confirming the target database.
- The matching `.tar.gz.json` manifest must be available; the archive is verified before restore.

---

# ☁️ Optional off-site SFTP copy

SFTP sends a second backup copy to another server. Verify the remote account, directory, and host-key fingerprint with your provider first. SFTP stays disabled unless you set `enabled = true` in `[sftp]`.

## Option A — SFTP password

Update the existing `[sftp]` section in `config.toml`:

```toml
[sftp]
enabled = true
host = "backup.example.com"
port = 22
username = "backup-user"
password_env = "PUFFX_BACKUP_SFTP_PASSWORD"
remote_directory = "/backups/CPANEL_USER"
known_hosts = "/home/CPANEL_USER/.ssh/known_hosts"
```

Create the remote directory in advance. The tool does not create remote folders or automatically delete older remote backups.

Add the SFTP password to `env.sh` as well:

```sh
export PUFFX_BACKUP_DB_PASSWORD='YOUR_DATABASE_PASSWORD'
export PUFFX_BACKUP_SFTP_PASSWORD='YOUR_SFTP_PASSWORD'
```

Run `chmod 600 ~/.config/puffx-backup/env.sh` again. The Cron command loads this file, so both variables will be available to scheduled runs.

## Option B — SSH private key

Instead of a password environment variable, set this in the `[sftp]` section:

```toml
key_file = "/home/CPANEL_USER/.ssh/backup_key"
```

Make the private key readable only by the account owner (for example, `chmod 600 ~/.ssh/backup_key`). The matching public key must be authorized on the SFTP server for that user.

## Verify the SSH host key

The tool rejects unknown host keys. The `known_hosts` file must contain the SFTP server's verified host key. Get the fingerprint from your provider through a trusted channel, compare it with the fingerprint they provide, and then add the host key to the file. Do not trust `ssh-keyscan` output without separately verifying the fingerprint. If the host key does not match, confirm it with your provider—do not disable verification.

After setting up SFTP, run a backup manually and confirm that both the archive and its `.json` manifest arrive at the remote location. If the upload fails, the backup command returns an error; check `backup.log` in cPanel.

---

# 🧰 Troubleshooting

| Error / symptom | What to check |
|---|---|
| `python3.12: command not found` | Ask your host to enable Python 3.12; the available version must be 3.12 or newer. |
| `No module named venv` | Ask your provider to enable virtual environment support. |
| `Every configured backup path must exist and be a directory` | Check the spelling and permissions of every absolute path in `[backup] paths`. |
| `Set environment variable ... before running` | Run `source ~/.config/puffx-backup/env.sh`; the TOML `password_env` and exported name must match. Check the env file path in the Cron command. |
| `mysqldump failed` | Check `mysqldump --version`, database host/port/name/user, password, and database user privileges. Confirm the MySQL host with your provider. |
| `mysql restore failed` | Check the restore user's write privileges and database availability. Restore replaces existing data. |
| `No backup archives found` | Match `--backup-dir` to the actual folder set in `[backup] directory`. |
| `Archive checksum or name does not match the manifest` | Check that the archive and `.tar.gz.json` sidecar belong together and were not changed or truncated during transfer. |
| `Archive contents do not match manifest inventory` | The archive and manifest may be mismatched or corrupt; use another verified backup. |
| No archive after a Cron run | Check `backup.log`, absolute paths, `.venv/bin/python`, `/bin/bash`, env file permissions, and the server timezone. First run the same command manually in Terminal. |
| `No such file or directory: known_hosts` / SFTP host-key error | Check the `known_hosts` path/file and verified server host key. Do not accept an unknown host key. |
| SFTP permission or path error | Make sure the remote folder exists, the SFTP account can write to it, and the host/port/username are correct. |

If the issue persists, give your hosting provider the exact error and relevant part of `backup.log`. **Do not share your password, private SSH key, database dump, or archive.**

---

# 📦 What is inside a backup?

Each successful backup creates two files:

- `backup-<UTC timestamp>.tar.gz` — the configured website directories and `database/database.sql`.
- `backup-<UTC timestamp>.tar.gz.json` — the archive name, UTC creation time, SHA-256 checksum, and file inventory.

Timestamps use UTC, for example `backup-20261028T203000Z.tar.gz`. The tool keeps local backups newest-first. With `retention_count = 14`, older **verified local** archives may be removed after a successful backup. Remote SFTP files are never deleted automatically.

## Available commands

Run these from the project directory:

```sh
# Create a backup, verify it, optionally upload over SFTP, and apply local retention
.venv/bin/python backup_manager.py --config config.toml backup

# Verify every archive in a backup directory
.venv/bin/python backup_manager.py verify --backup-dir /home/CPANEL_USER/backups

# Verify one specific archive
.venv/bin/python backup_manager.py verify --archive /home/CPANEL_USER/backups/backup-TIMESTAMP.tar.gz

# Extract verified website files to a review location
.venv/bin/python backup_manager.py restore-files --archive /path/backup-TIMESTAMP.tar.gz --target /path/restore-review

# Restore the configured database (overwrites data; --yes is required)
.venv/bin/python backup_manager.py --config config.toml restore-database --archive /path/backup-TIMESTAMP.tar.gz --database-name DB_NAME --yes
```

Put `--config` before the subcommand. `backup` and `restore-database` require the password environment variable to be loaded. `verify` and `restore-files` do not require a database password.

---

# 🔒 Security and limitations

- Keep `config.toml`, the password environment file, archives, manifests, and logs outside `public_html`.
- Never commit database/SFTP passwords, private keys, or config files to Git or share them.
- Backups may contain sensitive customer data. Check disk quota, retention, and access regularly. Use your hosting provider's encrypted storage option where available.
- The tool sets restrictive file permissions on archives, but you must also secure the backup directory and host account.
- SFTP host-key checking is enabled; unknown hosts are rejected.
- Review files before restoring them; database restore overwrites existing data.
- This version does not include a dashboard, cPanel API integration, VPS agent, built-in encryption, or automated restore drills.
- A successful backup is not the same as a tested restore. For important sites, manually test the restore process in a safe/staging environment.

📘 Additional notes: [SECURITY.md](SECURITY.md) · 🐛 Bug reports: [GitHub Issues](https://github.com/puffxhost/puffx-hosting-backup-manager/issues) · 📄 License: [MIT](LICENSE)

