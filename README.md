# PocketServer

PocketServer turns a low-powered Android phone or computer into a small local
media and download server. The dashboard works in modern phone, tablet, TV,
and desktop browsers.

The Python application is intentionally small. It uses the standard library
for the web server and delegates HTTP, magnet, and BitTorrent downloads to
`aria2c`, which is substantially more efficient than implementing a torrent
client inside the Python process.

## Features

- Responsive browser dashboard
- Media library with direct playback and HTTP byte-range seeking
- Normal URL, magnet-link, and `.torrent` downloads
- Pause, resume, and remove download controls
- Optional overnight download window
- Live storage, memory, uptime, and download-speed status
- Separate media client and password-protected administration dashboard
- No Python package dependencies

PocketServer does not transcode video. The viewing device decodes the original
file, which keeps memory and CPU usage low on old phones.

## Android / Termux setup

Install a current Termux release from F-Droid or the official Termux GitHub
releases. Android 7 or newer is officially supported. Then copy or clone this
project into Termux and run:

```sh
cd pocketserver
bash scripts/setup-termux.sh
bash scripts/start-termux.sh
```

Accept Android's storage permission prompt. Open the address printed in the
terminal from the phone itself or another device on the same Wi-Fi network.
Android may stop background processes unless battery optimization is disabled
for Termux. The launcher requests a Termux wake lock while the server runs.

Use the two browser interfaces:

- `http://PHONE-IP:8080/` — media client for watching videos
- `http://PHONE-IP:8080/admin` — server administration

The initial administrator username and password are both `admin`. Change the
password immediately from **System → Change password**. Passwords are stored as
salted PBKDF2 hashes, never as plaintext. The media client remains accessible
without a login on the trusted local network in this release.

By default, mobile media and downloads are saved under the phone's shared
`PocketServer` folder. Override the location with `POCKETSERVER_HOME`:

```sh
POCKETSERVER_HOME=/storage/emulated/0/PocketServer python -m pocketserver
```

## Other platforms

Install Python 3.10+ and aria2, then run:

```sh
python -m pocketserver
```

Useful options:

```sh
python -m pocketserver --host 0.0.0.0 --port 8080
python -m pocketserver --no-open
python -m pocketserver --help
```

## Configuration

The first run creates `config.json` inside the PocketServer data directory.
Important settings include:

- `download_window.enabled`: enable automatic overnight pausing/resuming
- `download_window.start`: start time in 24-hour `HH:MM` format
- `download_window.end`: end time in 24-hour `HH:MM` format
- `aria2.seed_time_minutes`: how long completed torrents seed (`0` disables)
- `minimum_free_mb`: refuse new downloads when storage is below this value

The web server is designed for a trusted home network. Do not expose it
directly to the public internet. Administration requires authentication, but
media playback is intentionally available to other devices on the same LAN.

Only download or share content when you have permission to do so.

## Scheduling downloads

Open **Downloads**, enable **Download schedule**, select a start and stop time,
and press **Save schedule**. Times use the server device's local clock. Windows
such as `00:00` to `06:00` and overnight windows such as `23:00` to `05:00`
are supported. All queued downloads are paused outside the selected window.
