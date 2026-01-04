"""
Garmin MCP Server

A Model Context Protocol server that provides access to Garmin Connect
health and fitness data.
"""

import os
import json
import logging
from datetime import datetime, date, timedelta
from typing import Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from garminconnect import Garmin
import garth

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("garmin-mcp")

# Initialize MCP server
server = Server("garmin-mcp")

# Garmin client singleton
_garmin_client: Optional[Garmin] = None


def get_garmin_client() -> Garmin:
    """Get or create authenticated Garmin client."""
    global _garmin_client
    
    if _garmin_client is not None:
        return _garmin_client
    
    # Check for existing auth tokens
    garth_dir = os.path.join(os.path.dirname(__file__), "..", "..", ".garth")
    
    try:
        # Try to load existing session with garth
        garth.resume(garth_dir)
        
        # Create Garmin client and attach garth session
        client = Garmin()
        client.garth = garth.client
        
        # Get display name to verify connection works
        display_name = client.garth.profile.get("displayName")
        logger.info(f"Authenticated as {display_name}")
        
        _garmin_client = client
        return client
        
    except Exception as e:
        logger.warning(f"Could not resume session: {e}")
    
    # Fall back to credential login if tokens don't exist
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    
    if not email or not password:
        raise ValueError(
            "No saved session found. Run 'python -m garmin_mcp.auth' first, "
            "or provide GARMIN_EMAIL and GARMIN_PASSWORD environment variables."
        )
    
    # Login with garth
    garth.login(email, password)
    garth.save(garth_dir)
    
    # Create client with session
    client = Garmin()
    client.garth = garth.client
    
    _garmin_client = client
    logger.info("Authenticated with Garmin credentials")
    return client


def parse_date(date_str: Optional[str]) -> date:
    """Parse date string or return today."""
    if not date_str:
        return date.today()
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def format_date(d: date) -> str:
    """Format date for Garmin API."""
    return d.strftime("%Y-%m-%d")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available Garmin tools."""
    return [
        Tool(
            name="get_daily_summary",
            description="Get health metrics for a specific date including Sleep Score, Training Readiness, Body Battery, HRV, Resting Heart Rate, and Stress level.",
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format. Defaults to today if not provided.",
                    }
                },
            },
        ),
        Tool(
            name="get_summary_range",
            description="Get health metrics for a date range. Useful for trend analysis over multiple days.",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "Start date in YYYY-MM-DD format.",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date in YYYY-MM-DD format.",
                    },
                },
                "required": ["start_date", "end_date"],
            },
        ),
        Tool(
            name="get_activities",
            description="Get fitness activities (runs, walks, cycling, strength training, etc.) for a specific date.",
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format. Defaults to today if not provided.",
                    }
                },
            },
        ),
        Tool(
            name="get_sleep_details",
            description="Get detailed sleep data including sleep stages, timing, and score breakdown.",
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format. Returns sleep data for the night ending on this date.",
                    }
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    try:
        client = get_garmin_client()
        
        if name == "get_daily_summary":
            result = await get_daily_summary(client, arguments.get("date"))
        elif name == "get_summary_range":
            result = await get_summary_range(
                client, 
                arguments["start_date"], 
                arguments["end_date"]
            )
        elif name == "get_activities":
            result = await get_activities(client, arguments.get("date"))
        elif name == "get_sleep_details":
            result = await get_sleep_details(client, arguments.get("date"))
        else:
            result = {"error": f"Unknown tool: {name}"}
        
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    
    except Exception as e:
        logger.error(f"Error calling tool {name}: {e}")
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def get_daily_summary(client: Garmin, date_str: Optional[str]) -> dict:
    """Get comprehensive daily health summary."""
    target_date = parse_date(date_str)
    date_formatted = format_date(target_date)
    
    # Get display name for API calls
    display_name = client.garth.profile.get("displayName")
    
    summary = {
        "date": date_formatted,
        "sleep_score": None,
        "training_readiness": None,
        "body_battery_high": None,
        "body_battery_low": None,
        "hrv_status": None,
        "hrv_value": None,
        "resting_heart_rate": None,
        "avg_stress": None,
        "steps": None,
    }
    
    # Get user summary (includes steps, stress, etc.)
    try:
        user_summary = client.get_user_summary(date_formatted)
        summary["steps"] = user_summary.get("totalSteps")
        summary["avg_stress"] = user_summary.get("averageStressLevel")
    except Exception as e:
        logger.warning(f"Could not get user summary: {e}")
    
    # Get sleep score
    try:
        sleep_data = client.get_sleep_data(date_formatted)
        if sleep_data and "dailySleepDTO" in sleep_data:
            sleep_dto = sleep_data["dailySleepDTO"]
            summary["sleep_score"] = sleep_dto.get("sleepScores", {}).get("overall", {}).get("value")
    except Exception as e:
        logger.warning(f"Could not get sleep data: {e}")
    
    # Get HRV data
    try:
        hrv_data = client.get_hrv_data(date_formatted)
        if hrv_data and "hrvSummary" in hrv_data:
            hrv_summary = hrv_data["hrvSummary"]
            summary["hrv_value"] = hrv_summary.get("lastNightAvg")
            summary["hrv_status"] = hrv_summary.get("status")
    except Exception as e:
        logger.warning(f"Could not get HRV data: {e}")
    
    # Get body battery
    try:
        bb_data = client.get_body_battery(date_formatted)
        if bb_data and len(bb_data) > 0:
            # Body battery returns array of readings
            values = [r.get("bodyBatteryLevel") for r in bb_data if r.get("bodyBatteryLevel")]
            if values:
                summary["body_battery_high"] = max(values)
                summary["body_battery_low"] = min(values)
    except Exception as e:
        logger.warning(f"Could not get body battery: {e}")
    
    # Get training readiness
    try:
        readiness = client.get_training_readiness(date_formatted)
        if readiness and "score" in readiness:
            summary["training_readiness"] = readiness["score"]
    except Exception as e:
        logger.warning(f"Could not get training readiness: {e}")
    
    # Get resting heart rate
    try:
        rhr_data = client.get_rhr_day(date_formatted)
        if rhr_data and "allMetrics" in rhr_data:
            for metric in rhr_data["allMetrics"]:
                if metric.get("metricsMap", {}).get("WELLNESS_RESTING_HEART_RATE"):
                    summary["resting_heart_rate"] = metric["metricsMap"]["WELLNESS_RESTING_HEART_RATE"]
                    break
    except Exception as e:
        logger.warning(f"Could not get RHR: {e}")
    
    return summary


async def get_summary_range(client: Garmin, start_str: str, end_str: str) -> dict:
    """Get daily summaries for a date range."""
    start_date = parse_date(start_str)
    end_date = parse_date(end_str)
    
    # Limit range to prevent excessive API calls
    max_days = 30
    if (end_date - start_date).days > max_days:
        return {"error": f"Date range cannot exceed {max_days} days"}
    
    summaries = []
    current = start_date
    
    while current <= end_date:
        summary = await get_daily_summary(client, format_date(current))
        summaries.append(summary)
        current += timedelta(days=1)
    
    return {
        "start_date": start_str,
        "end_date": end_str,
        "days": len(summaries),
        "summaries": summaries,
    }


async def get_activities(client: Garmin, date_str: Optional[str]) -> dict:
    """Get activities for a specific date."""
    target_date = parse_date(date_str)
    date_formatted = format_date(target_date)
    
    try:
        # Get activities for the date
        activities = client.get_activities_by_date(
            date_formatted, 
            date_formatted
        )
        
        if not activities:
            return {
                "date": date_formatted,
                "activities": [],
                "count": 0,
            }
        
        formatted_activities = []
        for activity in activities:
            formatted = {
                "name": activity.get("activityName"),
                "type": activity.get("activityType", {}).get("typeKey"),
                "start_time": activity.get("startTimeLocal"),
                "duration_minutes": round(activity.get("duration", 0) / 60, 1),
                "distance_km": round(activity.get("distance", 0) / 1000, 2) if activity.get("distance") else None,
                "calories": activity.get("calories"),
                "avg_hr": activity.get("averageHR"),
                "max_hr": activity.get("maxHR"),
                "training_effect_aerobic": activity.get("aerobicTrainingEffect"),
                "training_effect_anaerobic": activity.get("anaerobicTrainingEffect"),
            }
            formatted_activities.append(formatted)
        
        return {
            "date": date_formatted,
            "activities": formatted_activities,
            "count": len(formatted_activities),
        }
    
    except Exception as e:
        logger.error(f"Error getting activities: {e}")
        return {"error": str(e)}


async def get_sleep_details(client: Garmin, date_str: Optional[str]) -> dict:
    """Get detailed sleep data."""
    target_date = parse_date(date_str)
    date_formatted = format_date(target_date)
    
    try:
        sleep_data = client.get_sleep_data(date_formatted)
        
        if not sleep_data or "dailySleepDTO" not in sleep_data:
            return {
                "date": date_formatted,
                "error": "No sleep data available",
            }
        
        sleep_dto = sleep_data["dailySleepDTO"]
        
        # Convert timestamps to readable times
        def format_time(ts):
            if ts:
                return datetime.fromtimestamp(ts / 1000).strftime("%H:%M")
            return None
        
        result = {
            "date": date_formatted,
            "sleep_start": format_time(sleep_dto.get("sleepStartTimestampLocal")),
            "sleep_end": format_time(sleep_dto.get("sleepEndTimestampLocal")),
            "total_sleep_minutes": round(sleep_dto.get("sleepTimeSeconds", 0) / 60),
            "deep_sleep_minutes": round(sleep_dto.get("deepSleepSeconds", 0) / 60),
            "light_sleep_minutes": round(sleep_dto.get("lightSleepSeconds", 0) / 60),
            "rem_sleep_minutes": round(sleep_dto.get("remSleepSeconds", 0) / 60),
            "awake_minutes": round(sleep_dto.get("awakeSleepSeconds", 0) / 60),
            "sleep_scores": sleep_dto.get("sleepScores", {}),
        }
        
        return result
    
    except Exception as e:
        logger.error(f"Error getting sleep details: {e}")
        return {"error": str(e)}


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
