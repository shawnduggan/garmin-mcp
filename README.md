# garmin-mcp

A Model Context Protocol (MCP) server that provides AI assistants like Claude with access to your Garmin Connect health and fitness data.

## Overview

This MCP server enables Claude Desktop (and other MCP-compatible clients) to query your Garmin data on demand, including:

- **Daily Health Metrics**: Sleep Score, Training Readiness, Body Battery, HRV, Resting Heart Rate, Stress
- **Activity Data**: Workouts, runs, walks, cycling sessions with duration, distance, heart rate, and calories
- **Sleep Analysis**: Detailed sleep stages, timing, and score breakdowns
- **Trend Analysis**: Query metrics across date ranges for pattern recognition

No scheduled jobs, no CSV files, no stale data. Just live access to your Garmin Connect data when you need it.

## Features

- **On-Demand Data Access**: Query your Garmin data in real-time during conversations
- **Date Range Queries**: Retrieve metrics across multiple days for trend analysis (up to 30 days)
- **Secure Authentication**: Uses Garmin's OAuth flow with persistent token storage
- **Comprehensive Metrics**: Access the same data you see in Garmin Connect
- **Zero Maintenance**: Tokens persist for ~1 year; no cron jobs or scheduled tasks

## Prerequisites

- **Python 3.10 - 3.13** (3.14 is not yet supported by dependencies)
- **A Garmin Connect account** with a compatible Garmin device syncing data
- **Claude Desktop** (or another MCP-compatible client)

## Installation

### 1. Clone the Repository

```bash
cd ~/Dev
git clone https://github.com/shawnduggan/garmin-mcp.git
cd garmin-mcp
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

## Configuration

There are two ways to provide your Garmin credentials: environment file (recommended for initial setup) or Claude Desktop config (recommended for ongoing use).

### Option A: Environment File (Recommended for Setup)

1. Create your environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your Garmin Connect credentials:
   ```bash
   # Garmin Connect Credentials
   GARMIN_EMAIL=your_garmin_email@example.com
   GARMIN_PASSWORD=your_garmin_password
   ```

3. Run initial authentication:
   ```bash
   python -m garmin_mcp.auth
   ```

   If successful, you'll see:
   ```
   Authenticating as your_email@example.com...
   ✓ Authentication successful!
   ✓ Session saved to /Users/shawn/Dev/garmin-mcp/.garth
   ✓ Tokens are valid for approximately one year.
   ✓ Verification: Today's step count = 4521
   ```

4. **Security Note**: After successful authentication, you can delete the `.env` file. The session tokens in `.garth/` are sufficient for ongoing use.

### Option B: Claude Desktop Config with Credentials

If you prefer to keep credentials in the Claude Desktop config (they're passed as environment variables to the MCP server):

```json
{
  "mcpServers": {
    "garmin": {
      "command": "/Users/shawn/Dev/garmin-mcp/venv/bin/python",
      "args": ["-m", "garmin_mcp.server"],
      "cwd": "/Users/shawn/Dev/garmin-mcp",
      "env": {
        "GARMIN_EMAIL": "your_garmin_email@example.com",
        "GARMIN_PASSWORD": "your_garmin_password"
      }
    }
  }
}
```

### Claude Desktop Setup

Add the garmin-mcp server to your Claude Desktop configuration:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`  
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

#### Minimal Configuration (After Token Auth)

If you've already authenticated and have tokens saved in `.garth/`:

```json
{
  "mcpServers": {
    "garmin": {
      "command": "/Users/shawn/Dev/garmin-mcp/venv/bin/python",
      "args": ["-m", "garmin_mcp.server"],
      "cwd": "/Users/shawn/Dev/garmin-mcp"
    }
  }
}
```

#### Full Configuration (With Credentials)

If you want credentials available for re-authentication:

```json
{
  "mcpServers": {
    "garmin": {
      "command": "/Users/shawn/Dev/garmin-mcp/venv/bin/python",
      "args": ["-m", "garmin_mcp.server"],
      "cwd": "/Users/shawn/Dev/garmin-mcp",
      "env": {
        "GARMIN_EMAIL": "your_garmin_email@example.com",
        "GARMIN_PASSWORD": "your_garmin_password"
      }
    }
  }
}
```

#### Adding to Existing Configuration

If you already have other MCP servers configured, add garmin to your existing `mcpServers` object:

```json
{
  "mcpServers": {
    "some-other-server": {
      "...": "..."
    },
    "garmin": {
      "command": "/Users/shawn/Dev/garmin-mcp/venv/bin/python",
      "args": ["-m", "garmin_mcp.server"],
      "cwd": "/Users/shawn/Dev/garmin-mcp"
    }
  }
}
```

### Restart Claude Desktop

After saving your configuration, fully quit and restart Claude Desktop for the MCP server to become available.

## Available Tools

### `get_daily_summary`

Retrieve comprehensive health metrics for a specific date.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `date` | string | No | Date in YYYY-MM-DD format. Defaults to today. |

**Returns:**
```json
{
  "date": "2026-01-03",
  "sleep_score": 73,
  "training_readiness": 58,
  "body_battery_high": 85,
  "body_battery_low": 23,
  "hrv_status": "BALANCED",
  "hrv_value": 24,
  "resting_heart_rate": 52,
  "avg_stress": 28,
  "steps": 8432
}
```

### `get_summary_range`

Retrieve health metrics for a date range, useful for trend analysis.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | string | Yes | Start date in YYYY-MM-DD format |
| `end_date` | string | Yes | End date in YYYY-MM-DD format |

**Limits:** Maximum 30-day range per request.

**Returns:**
```json
{
  "start_date": "2025-12-28",
  "end_date": "2026-01-03",
  "days": 7,
  "summaries": [
    {"date": "2025-12-28", "sleep_score": 80, "...": "..."},
    {"date": "2025-12-29", "sleep_score": 64, "...": "..."}
  ]
}
```

### `get_activities`

Retrieve fitness activities (runs, walks, cycling, strength training, etc.) for a specific date.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `date` | string | No | Date in YYYY-MM-DD format. Defaults to today. |

**Returns:**
```json
{
  "date": "2026-01-02",
  "count": 1,
  "activities": [
    {
      "name": "Indoor Walking",
      "type": "walking",
      "start_time": "2026-01-02T11:30:00",
      "duration_minutes": 32.5,
      "distance_km": 2.8,
      "calories": 185,
      "avg_hr": 118,
      "max_hr": 135,
      "training_effect_aerobic": 2.3,
      "training_effect_anaerobic": 0.1
    }
  ]
}
```

### `get_sleep_details`

Retrieve detailed sleep data including stages, timing, and score breakdown.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `date` | string | No | Date in YYYY-MM-DD format. Returns sleep for the night ending on this date. |

**Returns:**
```json
{
  "date": "2026-01-03",
  "sleep_start": "23:15",
  "sleep_end": "06:42",
  "total_sleep_minutes": 387,
  "deep_sleep_minutes": 62,
  "light_sleep_minutes": 198,
  "rem_sleep_minutes": 89,
  "awake_minutes": 38,
  "sleep_scores": {
    "overall": {"value": 73},
    "quality": {"value": 68},
    "recovery": {"value": 71},
    "duration": {"value": 82}
  }
}
```

## Usage Examples

Once configured, you can ask Claude things like:

**Daily Check-ins:**
- "What were my Garmin stats yesterday?"
- "How did I sleep last night?"
- "What's my Training Readiness today?"

**Trend Analysis:**
- "Show me my sleep and HRV trends for the past week"
- "Compare my recovery metrics from last week to this week"
- "What's my average resting heart rate been this month?"

**Activity Review:**
- "What activities did I log on Tuesday?"
- "Pull my workout data for the past 7 days"
- "How many steps have I averaged this week?"

**Health Correlations:**
- "On days when my sleep score was below 60, what was my stress level?"
- "Show me my Body Battery patterns for December"

## Troubleshooting

### Authentication Errors

If you see authentication failures:

1. **Delete existing tokens:**
   ```bash
   rm -rf /Users/shawn/Dev/garmin-mcp/.garth
   ```

2. **Wait 15 minutes** (Garmin rate limits failed attempts)

3. **Verify credentials** by logging into [connect.garmin.com](https://connect.garmin.com) in a browser

4. **Re-authenticate:**
   ```bash
   cd /Users/shawn/Dev/garmin-mcp
   source venv/bin/activate
   python -m garmin_mcp.auth
   ```

### Two-Factor Authentication (2FA)

If you have 2FA enabled on your Garmin account:
- You may need to create an app-specific password
- Or temporarily disable 2FA during initial authentication
- Once tokens are saved, 2FA won't affect subsequent use

### Token Expiration

Tokens are valid for approximately one year. If requests start failing after extended use:

1. Delete the `.garth` directory
2. Re-run authentication
3. Restart Claude Desktop

### Rate Limiting

Garmin may temporarily block requests if you query too frequently. The server includes automatic retry logic, but if you encounter persistent failures:

- Wait 15-30 minutes before trying again
- Avoid making many rapid requests in succession

### MCP Server Not Appearing in Claude

1. Verify your `claude_desktop_config.json` syntax is valid JSON
2. Check the path to your Python virtual environment is correct
3. Ensure you've fully quit and restarted Claude Desktop
4. Check Claude Desktop's logs for MCP connection errors

### "No data available" Responses

- Ensure your Garmin device has synced recently
- Some metrics (like Training Readiness) require specific Garmin devices
- Check that data exists for the requested date in the Garmin Connect app

## Project Structure

```
garmin-mcp/
├── README.md
├── LICENSE
├── pyproject.toml
├── requirements.txt
├── .env.example
├── .gitignore
└── src/
    └── garmin_mcp/
        ├── __init__.py
        ├── server.py      # MCP server implementation
        └── auth.py        # Authentication module
```

## How It Works

1. **Authentication**: On first run, the server authenticates with Garmin Connect using your credentials and stores OAuth tokens in the `.garth` directory.

2. **Token Persistence**: Subsequent requests use the stored tokens, so your credentials aren't needed after initial setup.

3. **MCP Protocol**: Claude Desktop launches the server as a subprocess and communicates via the Model Context Protocol over stdin/stdout.

4. **On-Demand Queries**: When you ask Claude about your Garmin data, it calls the appropriate tool, which fetches live data from the Garmin Connect API.

## Acknowledgments

This project was inspired by [AI_Fitness](https://github.com/johnson4601/AI_Fitness) by johnson4601, which demonstrated the approach for extracting Garmin data using the garminconnect library.

The Garmin Connect API access is powered by the [garminconnect](https://github.com/cyberjunky/python-garminconnect) Python library and [garth](https://github.com/matin/garth) for OAuth token management.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please:

1. Open an issue to discuss proposed changes before submitting a PR
2. Follow existing code style
3. Add tests for new functionality
4. Update documentation as needed

## Disclaimer

This project is not affiliated with or endorsed by Garmin. It accesses the unofficial Garmin Connect API, which may change without notice. Use responsibly and in accordance with Garmin's terms of service.

## Support

If you encounter issues:

1. Check the [Troubleshooting](#troubleshooting) section
2. Search existing [GitHub Issues](https://github.com/shawnduggan/garmin-mcp/issues)
3. Open a new issue with:
   - Your Python version
   - Your operating system
   - The full error message
   - Steps to reproduce
