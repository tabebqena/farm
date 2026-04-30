"""
Configuration file for UI tests
Edit this file to customize test behavior
"""

# ============================================================================
# Server Configuration
# ============================================================================
BASE_URL = "http://localhost:8000"
TIMEOUT = 30000  # milliseconds (30 seconds)

# ============================================================================
# Authentication
# ============================================================================
TEST_USERNAME = "admin"
TEST_PASSWORD = "admin"

# Available users in database:
# - admin (superuser)
# - officer (staff)

# ============================================================================
# Viewport Sizes
# ============================================================================
# These define the screen sizes to test (width × height in pixels)
VIEWPORTS = {
    "mobile": {
        "width": 375,
        "height": 667,
        "description": "iPhone SE / Small Mobile"
    },
    "tablet": {
        "width": 768,
        "height": 1024,
        "description": "iPad / Tablet"
    },
    "desktop": {
        "width": 1920,
        "height": 1080,
        "description": "Desktop / Large Screen"
    },
}

# To test only specific viewports, modify like this:
# VIEWPORTS = {
#     "mobile": {"width": 375, "height": 667},
#     "desktop": {"width": 1920, "height": 1080},
# }

# ============================================================================
# Pages to Test
# ============================================================================
# Each page config should have:
# - name: Display name for the page
# - url: URL path (without domain)
# - checks: CSS selectors that must exist on the page
# - needs_auth: Whether user must be logged in

PAGES_TO_TEST = [
    {
        "name": "Login Page",
        "url": "/en/login/",
        "checks": ["input#id_username", "input#id_password", "button[type='submit']"],
        "needs_auth": False,
    },
    {
        "name": "Entity List",
        "url": "/en/entities/",
        "checks": ["h1", "table", "a[href*='create']"],
        "needs_auth": True,
    },
    {
        "name": "Operations List",
        "url": "/en/entities/operations/",
        "checks": ["h1", "table", "a[href*='create']"],
        "needs_auth": True,
    },
    {
        "name": "Inventory",
        "url": "/en/inventory/",
        "checks": ["h1", "table"],
        "needs_auth": True,
    },
    # Add more pages here
    # {
    #     "name": "Create Entity",
    #     "url": "/en/entities/create/",
    #     "checks": ["form", "input[name='name']", "button[type='submit']"],
    #     "needs_auth": True,
    # },
]

# ============================================================================
# Browser Configuration
# ============================================================================
HEADLESS = True  # Set to False to see browser while testing
SHOW_BROWSER_CONSOLE = True  # Log browser console messages

# ============================================================================
# Output Configuration
# ============================================================================
OUTPUT_DIR = "test_screenshots"
FULL_PAGE_SCREENSHOTS = True  # True = full page, False = viewport only

# ============================================================================
# Test Behavior
# ============================================================================
WAIT_FOR_LOAD = "networkidle"  # networkidle, load, or domcontentloaded
SCREENSHOT_DELAY = 500  # milliseconds - wait before taking screenshot
RETRY_FAILED_TESTS = False  # Retry failed tests automatically
RETRY_COUNT = 1  # How many times to retry

# ============================================================================
# Logging
# ============================================================================
VERBOSE = True  # Show detailed output
DEBUG = False  # Show debug information
LOG_FILE = "test_output.log"  # Where to save test logs
