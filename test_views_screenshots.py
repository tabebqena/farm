#!/usr/bin/env python
"""
Complete Logic & Appearance Test Script
Tests all views at mobile (375px) and desktop (1920px) viewports
Generates screenshots and validates page logic
"""

import asyncio
import os
import sys
import time
import requests
from datetime import datetime
from pathlib import Path

try:
    from playwright.async_api import async_playwright, Browser, Page
except ImportError:
    print("❌ Playwright not installed. Installing...")
    os.system("pip install playwright")
    os.system("playwright install chromium")
    from playwright.async_api import async_playwright, Browser, Page

# Configuration
BASE_URL = "http://localhost:8000"
OUTPUT_DIR = Path(__file__).parent / "test_screenshots"
TIMEOUT = 30000  # 30 seconds
VIEWPORTS = {
    "mobile": {"width": 375, "height": 667},
    "desktop": {"width": 1920, "height": 1080},
}

# Pages to test
PAGES_TO_TEST = [
    {
        "name": "Login Page",
        "url": "/en/login/",
        "checks": ["input[name='username']", "input[name='password']", "button[type='submit']"],
        "needs_auth": False,
    },
    {
        "name": "Entity List",
        "url": "/en/entities/",
        "checks": ["h2", "table", "a"],
        "needs_auth": True,
    },
    {
        "name": "Inventory",
        "url": "/en/inventory/",
        "checks": ["h1", "table"],
        "needs_auth": True,
    },
]

# Test credentials
# Available users: admin (superuser), officer (staff)
TEST_USERNAME = "admin"
TEST_PASSWORD = "admin"


class ViewTester:
    def __init__(self):
        self.browser = None
        self.page = None
        self.results = []
        self.passed = 0
        self.failed = 0
        self.session_cookies = None
        OUTPUT_DIR.mkdir(exist_ok=True)

    def login_via_http(self):
        """Authenticate using HTTP requests to get valid session cookies"""
        print("🔐 Logging in via HTTP...")
        try:
            session = requests.Session()

            # Get login page to extract CSRF token
            login_page = session.get(f"{BASE_URL}/en/login/")
            if login_page.status_code != 200:
                print(f"❌ Failed to access login page: {login_page.status_code}")
                return False

            # Extract CSRF token from page content
            import re
            csrf_match = re.search(r'csrfmiddlewaretoken["\']?\s*value="([^"]+)"', login_page.text)
            if not csrf_match:
                print("❌ CSRF token not found in login page")
                return False

            csrf_token = csrf_match.group(1)

            # Submit login form
            login_data = {
                'username': TEST_USERNAME,
                'password': TEST_PASSWORD,
                'csrfmiddlewaretoken': csrf_token,
            }

            response = session.post(
                f"{BASE_URL}/en/login/",
                data=login_data,
                allow_redirects=True,
                headers={'Referer': f"{BASE_URL}/en/login/"}
            )

            # Check if login was successful by looking for authenticated content
            if TEST_USERNAME.lower() in response.text.lower() or '/login' not in response.url:
                print("✅ Login successful")
                # Store cookies for later use in Playwright
                self.session_cookies = [
                    {
                        'name': name,
                        'value': value,
                        'domain': 'localhost',
                        'path': '/',
                    }
                    for name, value in session.cookies.items()
                ]
                return True
            else:
                print(f"❌ Login failed: Response doesn't indicate authenticated user")
                return False

        except Exception as e:
            print(f"❌ Login via HTTP failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def login(self):
        """Login and establish session in Playwright"""
        # First, login via HTTP to get valid session cookies
        if not self.login_via_http():
            return False

        # Add the session cookies to Playwright context
        if self.session_cookies:
            await self.page.context.add_cookies(self.session_cookies)

        print("✅ Session cookies added to browser")
        return True

    async def check_page_elements(self, page_config: dict) -> bool:
        """Verify that expected elements exist on the page"""
        try:
            for selector in page_config["checks"]:
                elements = await self.page.query_selector_all(selector)
                if not elements:
                    print(f"  ⚠️  Missing: {selector}")
                    return False
            return True
        except Exception as e:
            print(f"  ❌ Element check failed: {e}")
            return False

    async def test_page(self, page_config: dict, viewport_name: str, viewport_size: dict):
        """Test a single page at a specific viewport"""
        try:
            # Navigate to page
            url = f"{BASE_URL}{page_config['url']}"
            await self.page.goto(url, wait_until="networkidle", timeout=TIMEOUT)

            # Small delay to ensure rendering
            await self.page.wait_for_timeout(500)

            # Check elements exist
            elements_valid = await self.check_page_elements(page_config)

            # Get page title and dimensions
            title = await self.page.title()
            viewport = viewport_size

            # Take screenshot
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_name = (
                f"{page_config['name'].replace(' ', '_')}"
                f"_{viewport_name}_{timestamp}.png"
            )
            screenshot_path = OUTPUT_DIR / screenshot_name

            await self.page.screenshot(path=screenshot_path, full_page=True)

            status = "✅" if elements_valid else "⚠️"
            print(
                f"  {status} {page_config['name']} ({viewport_name}): "
                f"{screenshot_path.name}"
            )

            # Record result
            result = {
                "page": page_config["name"],
                "viewport": viewport_name,
                "url": url,
                "title": title,
                "screenshot": screenshot_path.name,
                "elements_valid": elements_valid,
                "viewport_size": viewport,
            }
            self.results.append(result)

            if elements_valid:
                self.passed += 1
            else:
                self.failed += 1

            return elements_valid

        except Exception as e:
            print(f"  ❌ Error testing {page_config['name']}: {e}")
            self.failed += 1
            return False

    async def run_tests(self):
        """Run complete test suite"""
        async with async_playwright() as p:
            print("🚀 Starting browser...")
            self.browser = await p.chromium.launch(headless=True)

            # Test authenticated pages
            if any(page["needs_auth"] for page in PAGES_TO_TEST):
                context = await self.browser.new_context()
                self.page = await context.new_page()

                if not await self.login():
                    print("❌ Cannot proceed without login")
                    await context.close()
                    await self.browser.close()
                    return

                for page_config in PAGES_TO_TEST:
                    if not page_config["needs_auth"]:
                        continue

                    print(f"\n📄 Testing: {page_config['name']}")
                    for viewport_name, viewport_size in VIEWPORTS.items():
                        await self.page.set_viewport_size(viewport_size)
                        await self.test_page(page_config, viewport_name, viewport_size)

                await context.close()

            # Test public pages (login)
            context = await self.browser.new_context()
            self.page = await context.new_page()

            for page_config in PAGES_TO_TEST:
                if page_config["needs_auth"]:
                    continue

                print(f"\n📄 Testing: {page_config['name']}")
                for viewport_name, viewport_size in VIEWPORTS.items():
                    await self.page.set_viewport_size(viewport_size)
                    await self.test_page(page_config, viewport_name, viewport_size)

            await context.close()
            await self.browser.close()

    def generate_report(self):
        """Generate HTML report with screenshots"""
        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Farm App - UI Test Report</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        .header {{
            background: white;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }}
        .header h1 {{
            color: #333;
            margin-bottom: 10px;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }}
        .stat-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
        }}
        .stat-card .number {{
            font-size: 2.5em;
            font-weight: bold;
        }}
        .stat-card .label {{
            font-size: 0.9em;
            opacity: 0.9;
        }}
        .results {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(450px, 1fr));
            gap: 30px;
        }}
        .result-card {{
            background: white;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }}
        .result-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 8px 12px rgba(0,0,0,0.15);
        }}
        .result-header {{
            padding: 20px;
            background: #f8f9fa;
            border-bottom: 2px solid #e9ecef;
        }}
        .result-header h3 {{
            color: #333;
            margin-bottom: 5px;
        }}
        .result-meta {{
            font-size: 0.85em;
            color: #666;
            display: flex;
            justify-content: space-between;
        }}
        .result-image {{
            position: relative;
            background: #f0f0f0;
            overflow: hidden;
        }}
        .result-image img {{
            width: 100%;
            height: auto;
            display: block;
        }}
        .viewport-badge {{
            position: absolute;
            top: 10px;
            right: 10px;
            background: rgba(0,0,0,0.7);
            color: white;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.75em;
            font-weight: bold;
        }}
        .status-badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: bold;
        }}
        .status-badge.pass {{
            background: #d4edda;
            color: #155724;
        }}
        .status-badge.fail {{
            background: #f8d7da;
            color: #721c24;
        }}
        .timestamp {{
            color: #999;
            font-size: 0.85em;
        }}
        @media (max-width: 768px) {{
            .results {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🧪 Farm App - UI Test Report</h1>
            <p class="timestamp">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <div class="stats">
                <div class="stat-card">
                    <div class="number">{self.passed}</div>
                    <div class="label">Passed</div>
                </div>
                <div class="stat-card" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
                    <div class="number">{self.failed}</div>
                    <div class="label">Failed</div>
                </div>
                <div class="stat-card" style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);">
                    <div class="number">{len(self.results)}</div>
                    <div class="label">Total Tests</div>
                </div>
            </div>
        </div>

        <div class="results">
"""

        for result in self.results:
            status = "pass" if result["elements_valid"] else "fail"
            status_text = "✅ PASS" if result["elements_valid"] else "⚠️ ISSUES"

            html_content += f"""
            <div class="result-card">
                <div class="result-header">
                    <h3>{result['page']}</h3>
                    <div class="result-meta">
                        <span>{result['viewport'].upper()}</span>
                        <span class="status-badge {status}">{status_text}</span>
                    </div>
                    <div style="margin-top: 8px; font-size: 0.8em; color: #666;">
                        {result['viewport_size']['width']}x{result['viewport_size']['height']}px
                    </div>
                </div>
                <div class="result-image">
                    <img src="{result['screenshot']}" alt="{result['page']} - {result['viewport']}">
                    <div class="viewport-badge">{result['viewport']}</div>
                </div>
            </div>
"""

        html_content += """
        </div>
    </div>
</body>
</html>
"""

        report_path = OUTPUT_DIR / "report.html"
        with open(report_path, "w") as f:
            f.write(html_content)

        print(f"\n📊 Report generated: {report_path}")
        return report_path

    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        print(f"✅ Passed: {self.passed}")
        print(f"❌ Failed: {self.failed}")
        print(f"📸 Screenshots saved to: {OUTPUT_DIR}")
        print("=" * 60)


async def main():
    """Main entry point"""
    print("🏗️  Farm App - Complete UI Test Suite")
    print(f"📍 Testing against: {BASE_URL}")
    print(f"📁 Output directory: {OUTPUT_DIR}\n")

    tester = ViewTester()

    try:
        await tester.run_tests()
        tester.generate_report()
        tester.print_summary()
    except KeyboardInterrupt:
        print("\n⚠️  Tests interrupted by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        return 1

    return 0 if tester.failed == 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
