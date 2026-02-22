# stace

[![made-with-python](https://img.shields.io/badge/Made%20with-Python-1f425f.svg)](https://www.python.org/)

stace automates the Steam account creation flow, including email verification handling.

Name
- `stace` is a short, memorable name derived from the phrase "Steam Account Creator" - letters were chosen to form a concise project name.

Features
- Automates Steam account creation flow
- Waits for and extracts the verification link from an IMAP inbox
- Simple username/password generation using wordlists

Requirements
- Python 3.8+
- See `requirements.txt` for dependencies

Environment
Set environment variables (recommended via a `.env` file):

- `EMAIL_HOST` (IMAP host, default: `localhost`)
- `EMAIL_USER` (IMAP username)
- `EMAIL_PASSWORD` (IMAP password)
- `ALIAS_FORMAT=test+[PLACEHOLDER]@example.com` (Alias format, "[PLACEHOLDER]" will be replaced with a random string.)
- `PASSWORD_LENGTH` (Optional password lenght)

Quick start

1. Create and activate a virtualenv:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Add a `.env` file with your IMAP credentials:

```text
EMAIL_HOST=imap.example.com
EMAIL_USER=you@example.com
EMAIL_PASSWORD=supersecret
```

3. Run the script (CLI)

```bash
python main.py --help
python main.py --chrome-path /usr/bin/chromium --driver-path /tmp/chromedriver --password-length 16
```

Behavior notes
- The CLI will retry the full flow a small number of times if the browser session unexpectedly closes (errors like "invalid session id" or "session deleted").
- You can set `PASSWORD_LENGTH` or pass `--password-length` to control generated password length.

Notes & safety
- The script uses `undetected-chromedriver` to reduce automation detection; this may not always work and could violate site terms.
- Use responsibly and only against accounts/resources you own or have permission to test.

Troubleshooting
- If you see the error "TypeError: Binary Location Must be a String" this is a known issue reported against `undetected-chromedriver`: https://github.com/ultrafunkamsterdam/undetected-chromedriver/issues/1544

	Workarounds:
	- Ensure the Chrome/Chromium binary path you pass to the driver is a valid string (e.g. `/usr/bin/chromium`).
	- If you set env vars like `CHROME_PATH` or `CHROMEDRIVER_PATH`, confirm they're non-empty strings.
	- Upgrade `undetected-chromedriver` to the latest version where the bug may be fixed.
	- As a temporary workaround, try using the system Chrome/Chromium binary explicitly and ensure your `create_driver()` call receives the correct string paths.

	See the upstream issue for discussion and additional context: https://github.com/ultrafunkamsterdam/undetected-chromedriver/issues/1544

Contributing
- Bug reports and small improvements welcome. Keep changes focused and add tests where appropriate.

License
- MIT License