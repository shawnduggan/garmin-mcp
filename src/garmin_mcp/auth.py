"""
Garmin Authentication Module

Run this script to perform initial authentication and save session tokens.
Tokens are stored in the .garth directory and are valid for approximately one year.

Usage:
    python -m garmin_mcp.auth
"""

import os
import sys
from pathlib import Path

import garth
from dotenv import load_dotenv


def authenticate():
    """Perform Garmin authentication and save session."""
    # Load environment variables from .env file
    env_path = Path(__file__).parent.parent.parent / ".env"
    load_dotenv(env_path)
    
    garth_dir = Path(__file__).parent.parent.parent / ".garth"
    
    # Try to resume existing session first
    try:
        garth.resume(str(garth_dir))
        profile = garth.client.profile
        display_name = profile.get("displayName", profile.get("userName", "Unknown"))
        print(f"✓ Existing session valid")
        print(f"✓ Connected as {display_name}")
        print(f"✓ Tokens stored in {garth_dir}")
        return
    except Exception:
        print("No valid existing session, performing fresh login...")
    
    # Need fresh login
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    
    if not email or not password:
        print("Error: GARMIN_EMAIL and GARMIN_PASSWORD must be set.")
        print("Create a .env file with your credentials or set environment variables.")
        sys.exit(1)
    
    print(f"Authenticating as {email}...")
    
    try:
        # Use garth directly for initial SSO login
        garth.login(email, password)
        garth.save(str(garth_dir))
        
        print(f"✓ Authentication successful!")
        print(f"✓ Session saved to {garth_dir}")
        print(f"✓ Tokens are valid for approximately one year.")
        
        # Verify tokens work by fetching profile
        profile = garth.client.profile
        display_name = profile.get("displayName", profile.get("userName", "Unknown"))
        print(f"✓ Verified: Connected as {display_name}")
        
    except Exception as e:
        print(f"✗ Authentication failed: {e}")
        print("\nTroubleshooting:")
        print("  1. Verify your email and password are correct")
        print("  2. Check if you have 2FA enabled (may require app-specific password)")
        print("  3. Wait 15 minutes if you've been rate-limited")
        print("  4. Try logging into Garmin Connect web to verify account status")
        sys.exit(1)


if __name__ == "__main__":
    authenticate()
