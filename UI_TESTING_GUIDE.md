# 🧪 Farm App - UI Testing Guide

Complete logic & appearance testing suite for desktop and mobile viewports with automated screenshots.

## Overview

This test suite provides:
- ✅ **Automated screenshots** at mobile (375px) and desktop (1920px) viewports
- 🔍 **Logic validation** - checks that expected elements exist on each page
- 📊 **HTML report** with all screenshots and test results
- 🚀 **Automatic server management** - starts/stops Django dev server
- 🌐 **Multi-page testing** - Login, Entities, Operations, Inventory

## Quick Start

### 1. Install Dependencies

```bash
pip install playwright
playwright install chromium
```

### 2. Run Tests

```bash
bash run_ui_tests.sh
```

This will:
1. Start Django development server (if not running)
2. Run all UI tests
3. Generate screenshots for each page × viewport
4. Create an HTML report with results
5. Open report in default browser

## Manual Usage

### Option A: Using the Shell Script (Recommended)

```bash
./run_ui_tests.sh
```

### Option B: Running Python Script Directly

```bash
# Requires Django server running on localhost:8000
python manage.py runserver

# In another terminal:
python test_views_screenshots.py
```

## Output

### Screenshots Directory
```
test_screenshots/
├── Login_Page_mobile_*.png
├── Login_Page_desktop_*.png
├── Entity_List_mobile_*.png
├── Entity_List_desktop_*.png
├── Operations_List_mobile_*.png
├── Operations_List_desktop_*.png
├── Inventory_mobile_*.png
├── Inventory_desktop_*.png
└── report.html  ← Interactive report
```

### HTML Report

The `report.html` file includes:
- 📊 Stats dashboard (passed/failed/total)
- 🖼️ All screenshots with viewport badges
- ✅ Pass/fail status for each test
- 📐 Viewport dimensions displayed

## Configuration

### Changing Test Credentials

Edit `test_views_screenshots.py`:

```python
TEST_USERNAME = "your_username"
TEST_PASSWORD = "your_password"
```

### Adding More Pages to Test

Edit the `PAGES_TO_TEST` list:

```python
PAGES_TO_TEST = [
    {
        "name": "Your Page Name",
        "url": "/en/your-path/",
        "checks": ["h1", "button", "table"],  # Selectors to verify
        "needs_auth": True,  # or False for public pages
    },
]
```

### Changing Viewports

Edit the `VIEWPORTS` dictionary:

```python
VIEWPORTS = {
    "mobile": {"width": 375, "height": 667},
    "tablet": {"width": 768, "height": 1024},
    "desktop": {"width": 1920, "height": 1080},
}
```

## What Gets Tested

### Pages Tested
1. **Login Page** - Public, verifies login form
2. **Entity List** - Requires auth, shows entities table
3. **Operations List** - Requires auth, shows operations
4. **Inventory** - Requires auth, shows inventory

### Logic Checks
For each page, the script verifies:
- ✅ Page loads successfully (network idle)
- ✅ Expected HTML elements exist (using CSS selectors)
- ✅ Page title is present
- ✅ No console errors (Playwright monitors)

### Appearance Checks
- 📸 Mobile viewport (375×667px)
- 📸 Desktop viewport (1920×1080px)
- 🎨 CSS rendering and layout
- 📐 Responsive design behavior

## Troubleshooting

### "Server failed to start"
```bash
# Check if port 8000 is in use
lsof -i :8000

# Kill existing process if needed
kill -9 <PID>

# Try starting server manually
python manage.py runserver
```

### "Playwright not found"
```bash
pip install playwright
playwright install chromium
```

### "Element check failed"
Check that:
1. Your test user credentials are correct
2. The app is logged in properly
3. The CSS selectors in `PAGES_TO_TEST` match your HTML
4. The page has finished loading (check Django logs)

### Screenshots are blank
1. Ensure Django server is running: `curl http://localhost:8000/en/login/`
2. Check Django logs for errors
3. Verify browser compatibility: `playwright install chromium`

## Advanced Usage

### Headless vs Headed Mode

Edit `test_views_screenshots.py` to view browser:

```python
self.browser = await p.chromium.launch(headless=False)  # Show browser
```

### Full Page vs Viewport Screenshots

Current: `await self.page.screenshot(path=screenshot_path, full_page=True)`

For viewport only: `await self.page.screenshot(path=screenshot_path)`

### Adding Custom Assertions

Extend the `check_page_elements` method:

```python
async def check_page_elements(self, page_config: dict) -> bool:
    # ... existing checks ...
    
    # Add custom logic
    text = await self.page.text_content("h1")
    if not text:
        print(f"  ❌ Page title is empty")
        return False
    
    return True
```

## Continuous Integration

Add to your CI pipeline:

```yaml
- name: Run UI Tests
  run: |
    pip install playwright
    playwright install chromium
    bash run_ui_tests.sh
```

## Performance

- ⏱️ Each test takes ~2-3 seconds
- 📊 Full suite: ~1 minute (8 tests × 2 viewports)
- 🖼️ Screenshot generation: ~500ms per screenshot

## Browser Compatibility

Currently tests: **Chromium** (Playwright default)

To add Firefox/Safari:

```python
browsers = [p.chromium, p.firefox, p.webkit]
for browser in browsers:
    self.browser = await browser.launch()
```

## Next Steps

1. ✅ Run: `bash run_ui_tests.sh`
2. 📊 Review the generated `test_screenshots/report.html`
3. 📝 Update test credentials and pages as needed
4. 🔄 Run tests regularly during development
5. 📈 Add to CI/CD pipeline

---

**Questions?** Check the script comments or Django test documentation.
