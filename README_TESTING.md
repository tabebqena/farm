# 🧪 Farm App - UI & Logic Testing Suite

**Complete automated testing suite for ensuring all views work correctly on mobile and desktop devices.**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Django 4.2+](https://img.shields.io/badge/Django-4.2+-green.svg)](https://www.djangoproject.com/)
[![Playwright](https://img.shields.io/badge/Playwright-Automated-orange.svg)](https://playwright.dev/)

## 📸 What It Does

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  Your Django App                                        │
│  ├─ Views                                               │
│  ├─ Templates                                           │
│  └─ Styles                                              │
│                                                         │
└───────────────────┬─────────────────────────────────────┘
                    │
          ┌─────────▼─────────┐
          │  Testing Suite    │
          │  (This project)   │
          └─────────┬─────────┘
                    │
     ┌──────────────┼──────────────┐
     │              │              │
┌────▼────┐  ┌─────▼─────┐  ┌─────▼─────┐
│ Mobile  │  │  Desktop  │  │  Validate │
│ Views   │  │   Views   │  │  Logic    │
└────┬────┘  └─────┬─────┘  └─────┬─────┘
     │             │              │
     └─────────────┼──────────────┘
                   │
          ┌────────▼────────┐
          │  Screenshots    │
          │  HTML Report    │
          │  Results        │
          └─────────────────┘
```

## 🚀 Quick Start

### 1️⃣ Install

```bash
pip install playwright
playwright install chromium
```

### 2️⃣ Run

```bash
bash run_ui_tests.sh
```

### 3️⃣ View Results

Open `test_screenshots/report.html` in your browser.

That's it! 🎉

## 📁 Files in This Suite

| File | Purpose |
|------|---------|
| **test_views_screenshots.py** | Core testing engine - takes screenshots, validates logic |
| **run_ui_tests.sh** | Wrapper script - manages server, runs tests, opens report |
| **test_config.py** | Configuration - customize pages, viewports, credentials |
| **QUICK_START.md** | 30-second setup guide |
| **UI_TESTING_GUIDE.md** | Detailed reference documentation |
| **TESTING_WORKFLOW.md** | Integration into your development workflow |
| **TEST_SUITE_SUMMARY.md** | Complete feature overview |
| **README_TESTING.md** | This file |

## 🎯 Features

### ✨ What Gets Tested

- ✅ **4 Key Pages**: Login, Entities, Operations, Inventory
- ✅ **2 Viewports**: Mobile (375px) & Desktop (1920px)
- ✅ **8 Total Combinations**: Each page × each viewport
- ✅ **Logic Validation**: Checks expected elements exist
- ✅ **Appearance Verification**: Full page screenshots
- ✅ **Responsive Design**: Tests layout on different screen sizes

### 📊 Output

- 📸 8 high-quality PNG screenshots
- 📈 Interactive HTML report with dashboard
- ✅ Pass/fail status for each test
- 📐 Viewport dimensions displayed
- 🎨 Beautiful, responsive report design

## 🔧 Configuration

### Easy Customization (Edit test_config.py)

```python
# Add a new page
PAGES_TO_TEST.append({
    "name": "Dashboard",
    "url": "/en/dashboard/",
    "checks": ["h1", "canvas", "button.export"],
    "needs_auth": True,
})

# Add a tablet viewport
VIEWPORTS["tablet"] = {"width": 768, "height": 1024}

# Change test user
TEST_USERNAME = "officer"
```

## 📊 Sample Report

The generated HTML report looks like this:

```
╔════════════════════════════════════════════════╗
║  🧪 Farm App - UI Test Report                 ║
║  Generated: 2024-04-28 10:30:45                ║
╠════════════════════════════════════════════════╣
║                                               ║
║  ✅ Passed: 8    ❌ Failed: 0    📊 Total: 8  ║
║                                               ║
╠════════════════════════════════════════════════╣
║                                               ║
║  Login Page                                    ║
║  ├─ Mobile (375×667) ✅ [Screenshot]          ║
║  └─ Desktop (1920×1080) ✅ [Screenshot]       ║
║                                               ║
║  Entity List                                   ║
║  ├─ Mobile (375×667) ✅ [Screenshot]          ║
║  └─ Desktop (1920×1080) ✅ [Screenshot]       ║
║                                               ║
║  Operations List                               ║
║  ├─ Mobile (375×667) ✅ [Screenshot]          ║
║  └─ Desktop (1920×1080) ✅ [Screenshot]       ║
║                                               ║
║  Inventory                                     ║
║  ├─ Mobile (375×667) ✅ [Screenshot]          ║
║  └─ Desktop (1920×1080) ✅ [Screenshot]       ║
║                                               ║
╚════════════════════════════════════════════════╝
```

## 📚 Documentation

| Document | For |
|----------|-----|
| [QUICK_START.md](./QUICK_START.md) | Getting started in 30 seconds |
| [UI_TESTING_GUIDE.md](./UI_TESTING_GUIDE.md) | Complete reference guide |
| [TESTING_WORKFLOW.md](./TESTING_WORKFLOW.md) | Using in your workflow |
| [TEST_SUITE_SUMMARY.md](./TEST_SUITE_SUMMARY.md) | Feature overview |

## 💻 Commands

### Basic Usage

```bash
# Run complete test suite
bash run_ui_tests.sh

# Run tests only (server must be running)
python test_views_screenshots.py

# Just open existing report
open test_screenshots/report.html
```

### With Custom Configuration

```bash
# See current browser (for debugging)
# Edit test_config.py: HEADLESS = False
python test_views_screenshots.py

# Run on different port
# Edit test_config.py: BASE_URL = "http://localhost:9000"
bash run_ui_tests.sh
```

## 🔄 Integration Examples

### GitHub Actions

```yaml
- name: Run UI Tests
  run: bash run_ui_tests.sh
```

### Pre-commit Hook

```bash
chmod +x .git/hooks/pre-commit
echo 'bash run_ui_tests.sh' > .git/hooks/pre-commit
```

### Before Deployment

```bash
bash run_ui_tests.sh || exit 1  # Fail if tests fail
git push
```

## 🐛 Troubleshooting

| Issue | Fix |
|-------|-----|
| "Port 8000 in use" | `lsof -i :8000` → `kill -9 <PID>` |
| "Playwright not found" | `pip install playwright && playwright install chromium` |
| "Login failed" | Check TEST_USERNAME/PASSWORD in test_config.py |
| "Blank screenshots" | Ensure Django server is running: `curl http://localhost:8000` |
| "Element not found" | Update CSS selectors in test_config.py |

See [TESTING_WORKFLOW.md](./TESTING_WORKFLOW.md) for more troubleshooting.

## ⏱️ Performance

| Operation | Time |
|-----------|------|
| Full test suite (8 tests) | 60-90 seconds |
| Single test | 2-3 seconds |
| Browser startup | 3-5 seconds |
| Screenshot per page | 500ms |

## 🌍 Browser Support

Currently tests: **Chromium**

To add Firefox/Safari, see [UI_TESTING_GUIDE.md](./UI_TESTING_GUIDE.md#browser-compatibility).

## 📋 Test Checklist

Before committing, verify:

- [ ] All tests pass (green checkmarks)
- [ ] Mobile views look correct
- [ ] Desktop views look correct
- [ ] Forms are usable on mobile
- [ ] Navigation works on mobile
- [ ] Images/assets load properly
- [ ] No console errors
- [ ] Text is readable

## 🎓 How It Works

1. **Start Django Server** - Automatically starts on localhost:8000
2. **Launch Browser** - Playwright opens Chromium (headless)
3. **Login** - Uses test credentials to authenticate
4. **Test Each Page** - At each viewport size:
   - Navigate to URL
   - Wait for page to fully load
   - Verify expected elements exist
   - Take full-page screenshot
   - Record results
5. **Generate Report** - Create beautiful HTML report
6. **Open Report** - Display in default browser

## 💡 Tips & Tricks

### See Browser While Testing

Edit `test_config.py`:
```python
HEADLESS = False
```

### Test Specific Page Only

Edit `test_config.py`:
```python
PAGES_TO_TEST = [
    # ... comment out pages you don't want
]
```

### Skip Certain Viewports

Edit `test_config.py`:
```python
VIEWPORTS = {
    # "mobile": {...},  # Skip mobile
    "desktop": {"width": 1920, "height": 1080},
}
```

### Slower Internet?

Edit `test_config.py`:
```python
TIMEOUT = 45000  # was 30000 (milliseconds)
```

## 📞 Support

1. **Quick answers**: Check [QUICK_START.md](./QUICK_START.md)
2. **Detailed help**: See [UI_TESTING_GUIDE.md](./UI_TESTING_GUIDE.md)
3. **Configuration**: Review [test_config.py](./test_config.py) comments
4. **Workflow help**: Read [TESTING_WORKFLOW.md](./TESTING_WORKFLOW.md)

## 📈 Next Steps

1. ✅ Install Playwright: `pip install playwright && playwright install chromium`
2. ✅ Run tests: `bash run_ui_tests.sh`
3. ✅ Review report: Open `test_screenshots/report.html`
4. ✅ Customize: Edit `test_config.py` to add pages
5. ✅ Integrate: Add to CI/CD pipeline

## 📝 License

Part of the Farm Django Application

## 🙋 Questions?

Check the [TESTING_WORKFLOW.md](./TESTING_WORKFLOW.md) for common scenarios and solutions.

---

**Ready to test?** Run:

```bash
bash run_ui_tests.sh
```

The script will handle everything! 🚀
