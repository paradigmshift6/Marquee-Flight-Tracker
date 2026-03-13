# Marquee Board

A smart adaptive LED matrix display that shows nearby flights, weather, and upcoming calendar events. Designed for a 64x64 HUB75 RGB LED panel driven by a Raspberry Pi.

![Display Modes](https://img.shields.io/badge/modes-flight%20%7C%20weather%20%7C%20calendar%20%7C%20split-blue)
![Python](https://img.shields.io/badge/python-3.9%2B-green)

## What It Does

Marquee Board automatically picks the best layout based on what's happening:

- **Flight overhead** — shows flight number, route, altitude, aircraft type, and distance
- **Upcoming meeting** — shows event name, start time, and countdown
- **Weather** — temperature, conditions, wind, and forecast
- **Split view** — flight + urgent calendar event simultaneously
- **Idle** — clock and date when nothing is active

The display adapts in real time. An approaching aircraft takes priority. An upcoming meeting in the next 30 minutes gets promoted to urgent. Weather fills the gaps.

## Hardware

- **Raspberry Pi** (3B+, 4, or 5)
- **64x64 HUB75 RGB LED Matrix** (P3 or P4 pitch recommended)
- **Adafruit RGB Matrix Bonnet** or **HAT** (recommended for clean wiring)
- **5V power supply** (at least 4A for a single 64x64 panel)

> Any HUB75 panel size works (64x32, 128x64, etc.) — set `renderer.width` and `renderer.height` in your config.

## Raspberry Pi Setup

### 1. System Dependencies

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv git
```

### 2. RGB Matrix Driver

Install the [hzeller/rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix) library:

```bash
# Clone and build the RGB matrix driver
cd ~
git clone https://github.com/hzeller/rpi-rgb-led-matrix.git
cd rpi-rgb-led-matrix
make build-python PYTHON=$(which python3)
sudo make install-python PYTHON=$(which python3)
```

> **Important:** Disable the Raspberry Pi's onboard sound to avoid GPIO conflicts:
> ```bash
> sudo nano /boot/config.txt
> # Comment out: dtparam=audio=on
> # Add: dtparam=audio=off
> sudo reboot
> ```

### 3. Install Marquee Board

```bash
cd ~
git clone https://github.com/paradigmshift6/Marquee-board.git marquee-board
cd marquee-board

python3 -m venv .venv
source .venv/bin/activate

# Install with LED matrix and all optional provider support
pip install -e ".[led,web,calendar]"
```

### 4. Configure

**Option A — Web Settings UI (recommended for first-time setup):**

Just start the server. If no `config.yaml` exists, one is created automatically and the web settings page opens:

```bash
source .venv/bin/activate
PORT=5050 python -m marquee_board --display web
```

Then open `http://<your-pi-ip>:5050/settings` in a browser and fill in your location, API keys, and preferences. Click **Save & Restart** when done.

**Option B — Edit config file directly:**

```bash
cp config.example.yaml config.yaml
nano config.yaml
```

Edit these sections:

```yaml
# Your location (get coordinates from Google Maps)
location:
  latitude: 40.7128
  longitude: -74.0060
  radius_miles: 3
  local_airport: KJFK   # Nearest ICAO airport code (optional)

# Display — use "led" for the physical matrix
display:
  backend: led

# LED matrix settings
renderer:
  width: 64
  height: 64
  brightness: 80         # 0-100
  gpio_slowdown: 4       # Increase to 5 if you see flickering
```

### 5. Run

```bash
# Must run as root for GPIO access
sudo .venv/bin/python -m marquee_board -c config.yaml --display led
```

Use `-v` for verbose/debug logging:

```bash
sudo .venv/bin/python -m marquee_board -c config.yaml --display led -v
```

## Data Providers

### Flights (OpenSky Network)

Tracks aircraft near your location using the [OpenSky Network](https://opensky-network.org) API.

**Setup:**
1. Create a free account at [opensky-network.org](https://opensky-network.org)
2. Go to Account > API Clients and create a new client
3. Add credentials to `config.yaml`:

```yaml
opensky:
  client_id: "your_client_id"
  client_secret: "your_client_secret"

flights:
  enabled: true
```

> Works without credentials (anonymous), but authenticated requests get better rate limits and route data.

### Weather (OpenWeatherMap)

Shows current conditions and 24-hour forecast.

**Setup:**
1. Create a free account at [openweathermap.org](https://openweathermap.org)
2. Go to API Keys and copy your key
3. Add to `config.yaml`:

```yaml
weather:
  enabled: true
  api_key: "your_api_key"
  units: imperial          # or "metric"
  poll_interval: 300       # seconds (5 min default)
```

### Calendar (Google Calendar)

Displays upcoming events with countdowns.

**Setup:**
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project (or select existing)
3. Enable the **Google Calendar API**
4. Go to Credentials > Create Credentials > OAuth 2.0 Client ID
5. Choose "Desktop app" as application type
6. Download the JSON file and save as `credentials.json` in the project root
7. Add to `config.yaml`:

```yaml
calendar:
  enabled: true
  credentials_file: credentials.json
  token_file: data/calendar_token.json
  calendar_id: primary
  lookahead_hours: 24
```

**First run:** You'll be prompted to authorize in a browser. On a headless Pi, run once from a machine with a browser first, then copy the generated `data/calendar_token.json` to your Pi.

## Run on Boot (systemd)

Create a service file:

```bash
sudo nano /etc/systemd/system/marquee-board.service
```

```ini
[Unit]
Description=Marquee Board LED Display
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/pi/marquee-board
ExecStart=/home/pi/marquee-board/.venv/bin/python -m marquee_board -c config.yaml --display led
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable marquee-board
sudo systemctl start marquee-board

# Check status
sudo systemctl status marquee-board

# View logs
sudo journalctl -u marquee-board -f
```

## Web Settings UI

Configure everything through a browser — no need to edit YAML files.

```bash
source .venv/bin/activate
PORT=5050 python -m marquee_board -c config.yaml --display web
```

Open `http://<your-pi-ip>:5050/settings` to manage:

- **Location** — latitude, longitude, radius, local airport
- **Schedule** — active hours (auto-sleep at night)
- **Flights** — enable/disable, OpenSky API credentials
- **Weather** — enable/disable, API key, units, poll interval
- **Calendar** — enable/disable, credentials file, calendar ID
- **Display** — idle message, LED brightness

API keys and secrets are masked in the UI and preserved when saving unchanged. Click **Save** to write config, or **Save & Restart** to apply changes immediately (works with systemd auto-restart on Pi).

## Web Simulator

Preview the display in a browser without any LED hardware:

```bash
source .venv/bin/activate
PORT=5050 python -m marquee_board -c config.yaml --display web
```

Then open `http://<your-pi-ip>:5050/simulator` in a browser.

> **Note:** On macOS, port 5000 is used by AirPlay Receiver. Use `PORT=5050` or any other open port.

## Display Backends

| Backend    | Use Case                            | Requirement          |
|------------|-------------------------------------|----------------------|
| `led`      | Physical HUB75 RGB LED matrix       | Raspberry Pi + panel |
| `web`      | Browser preview / remote monitoring | Flask (`pip install .[web]`) |
| `terminal` | Quick text-based testing            | None (default)       |

## Configuration Reference

| Section | Key | Default | Description |
|---------|-----|---------|-------------|
| `location.latitude` | | *required* | Your latitude |
| `location.longitude` | | *required* | Your longitude |
| `location.radius_miles` | | `5.0` | Flight search radius |
| `location.local_airport` | | `null` | ICAO code for arrival/departure detection |
| `polling.interval_seconds` | | `12` | Flight poll interval (min 10s) |
| `display.backend` | | `terminal` | `terminal`, `web`, or `led` |
| `renderer.width` | | `64` | Matrix width in pixels |
| `renderer.height` | | `64` | Matrix height in pixels |
| `renderer.brightness` | | `80` | LED brightness (0-100) |
| `renderer.gpio_slowdown` | | `4` | GPIO timing (increase if flickering) |
| `schedule.enabled` | | `false` | Enable active hours schedule |
| `schedule.active_start` | | `06:30` | Time to turn on (HH:MM, 24h) |
| `schedule.active_end` | | `18:00` | Time to turn off (HH:MM, 24h) |
| `web.port` | | `5000` | Web server port |
| `weather.enabled` | | `false` | Enable weather provider |
| `weather.api_key` | | | OpenWeatherMap API key |
| `calendar.enabled` | | `false` | Enable Google Calendar |
| `flights.enabled` | | `true` | Enable flight tracking |

## Troubleshooting

**Display is flickering or has artifacts**
- Increase `renderer.gpio_slowdown` from 4 to 5
- Make sure onboard audio is disabled in `/boot/config.txt`
- Use a sufficient power supply (4A+ for 64x64)

**No flights showing**
- Verify your lat/lon coordinates are correct
- Try increasing `radius_miles`
- Check that you're in an area with air traffic
- OpenSky anonymous API has a 10-second rate limit

**Calendar auth fails on headless Pi**
- Run once on a desktop machine with a browser
- Copy `data/calendar_token.json` to your Pi
- The token refreshes automatically after initial auth

**Port 5000 already in use (macOS)**
- Set `PORT=5050` environment variable or change `web.port` in config

**"Permission denied" when running LED display**
- The LED driver requires root access for GPIO: use `sudo`
