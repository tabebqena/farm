# 🧪 Farm App - Testing Suite Index

**Complete UI testing suite with automated screenshots for mobile & desktop.**

---

## 🚀 Get Started Now (3 Steps)

```bash
# Step 1: Install dependencies
pip install playwright && playwright install chromium

# Step 2: Run tests
bash run_ui_tests.sh

# Step 3: Open report
# (Browser will open automatically)
```

That's it! The script creates:
- 📸 8 screenshots (4 pages × 2 viewports)
- 📊 Beautiful HTML report
- ✅ Pass/fail validation

---

## 📚 Documentation Map

### 🏃 Just Want to Run Tests?
→ **[QUICK_START.md](./QUICK_START.md)** - 30-second guide

### 🎓 Want Full Details?
→ **[README_TESTING.md](./README_TESTING.md)** - Complete overview with examples

### 📖 Need Reference?
→ **[UI_TESTING_GUIDE.md](./UI_TESTING_GUIDE.md)** - Detailed configuration reference

### 🔄 Want to Integrate into Workflow?
→ **[TESTING_WORKFLOW.md](./TESTING_WORKFLOW.md)** - Development integration guide

### 📋 Want Full Summary?
→ **[TEST_SUITE_SUMMARY.md](./TEST_SUITE_SUMMARY.md)** - Complete feature breakdown

---

## 📁 Files Created

### 🔧 Core Files (What You Run)

```
farm/
├── run_ui_tests.sh ........................ One-command test runner ⭐
│   └─ Does: starts server, runs tests, opens report
│   └─ Run: bash run_ui_tests.sh
│
└── test_views_screenshots.py ............. Main test engine
    └─ Does: browser automation, screenshot, validation
    └─ Run: python test_views_screenshots.py
```

### ⚙️ Configuration

```
├── test_config.py ......................... Test configuration
    └─ Edit this to: add pages, change viewports, etc.
```

### 📚 Documentation (Read These)

```
├── QUICK_START.md ......................... ⭐ START HERE
│   └─ 30-second setup
│
├── README_TESTING.md ...................... Complete overview
│   └─ Features, commands, troubleshooting
│
├── UI_TESTING_GUIDE.md ................... Detailed reference
│   └─ Configuration options, advanced usage
│
├── TESTING_WORKFLOW.md ................... Integration guide
│   └─ How to use in development workflow
│
├── TEST_SUITE_SUMMARY.md ................. Feature breakdown
│   └─ What gets tested, why, how
│
└── TESTING_INDEX.md ...................... This file
    └─ Navigation and overview
```

### 📊 Generated After Running

```
test_screenshots/
├── Login_Page_mobile_*.png .............. Screenshot
├── Login_Page_desktop_*.png ............ Screenshot
├── Entity_List_mobile_*.png ............ Screenshot
├── Entity_List_desktop_*.png .......... Screenshot
├── Operations_List_mobile_*.png ....... Screenshot
├── Operations_List_desktop_*.png ..... Screenshot
├── Inventory_mobile_*.png .............. Screenshot
├── Inventory_desktop_*.png ............ Screenshot
└── report.html .......................... 🎯 Open this in browser!
```

---

## 🎯 What Gets Tested

| Page | Mobile | Desktop | Logic Check |
|------|--------|---------|-------------|
| Login | ✅ | ✅ | Form elements |
| Entity List | ✅ | ✅ | Table, buttons |
| Operations | ✅ | ✅ | Table, links |
| Inventory | ✅ | ✅ | Table |

**Total: 8 automated tests**

---

## 💻 Common Commands

```bash
# Run complete test suite (recommended)
bash run_ui_tests.sh

# Just run Python tests (server must be running)
python test_views_screenshots.py

# View existing report without running tests
open test_screenshots/report.html

# See browser while testing (for debugging)
# Edit test_config.py: HEADLESS = False
python test_views_screenshots.py

# Run only on mobile viewports (advanced)
# Edit test_config.py: VIEWPORTS = {"mobile": {...}}
python test_views_screenshots.py
```

---

## 🔧 Quick Configuration

Edit `test_config.py` to:

### ✅ Add a New Page

```python
PAGES_TO_TEST.append({
    "name": "Dashboard",
    "url": "/en/dashboard/",
    "checks": ["h1", "canvas"],
    "needs_auth": True,
})
```

### ✅ Add Another Viewport

```python
VIEWPORTS["tablet"] = {"width": 768, "height": 1024}
```

### ✅ Change Test User

```python
TEST_USERNAME = "officer"  # or "admin"
```

### ✅ See Browser While Testing

```python
HEADLESS = False
```

---

## 🐛 Quick Troubleshooting

| Problem | Solution |
|---------|----------|
| **"Port 8000 in use"** | `lsof -i :8000` → `kill -9 <PID>` |
| **"Playwright not found"** | `pip install playwright && playwright install chromium` |
| **"Login failed"** | Check TEST_USERNAME in test_config.py |
| **"Blank screenshots"** | Check Django is running: `curl http://localhost:8000` |

→ See [README_TESTING.md](./README_TESTING.md#troubleshooting) for more help

---

## 📊 Sample Output

```
✅ Passed: 8
❌ Failed: 0
📸 Screenshots saved to: test_screenshots
📊 Report: test_screenshots/report.html
```

The HTML report shows:
- Dashboard with pass/fail counts
- Screenshot grid with viewport badges
- Individual test results
- Beautiful, responsive design

---

## ⏱️ Performance

- **Full suite**: 60-90 seconds
- **Single test**: 2-3 seconds
- **Screenshot**: 500ms each

---

## 🔄 Use Cases

### Before Commit
```bash
bash run_ui_tests.sh
# Review report
git commit -m "..."
```

### After CSS Changes
```bash
bash run_ui_tests.sh
# Compare mobile vs desktop
```

### Adding New Feature
```bash
# 1. Implement feature
# 2. Add to test_config.py
# 3. bash run_ui_tests.sh
```

### CI/CD Integration
```yaml
- name: Run UI Tests
  run: bash run_ui_tests.sh
```

---

## 📞 Where to Find Help

| Need | Find In |
|------|----------|
| **Quick start** | [QUICK_START.md](./QUICK_START.md) |
| **How to customize** | [test_config.py](./test_config.py) comments |
| **Detailed guide** | [UI_TESTING_GUIDE.md](./UI_TESTING_GUIDE.md) |
| **How to integrate** | [TESTING_WORKFLOW.md](./TESTING_WORKFLOW.md) |
| **Full overview** | [README_TESTING.md](./README_TESTING.md) |
| **Feature summary** | [TEST_SUITE_SUMMARY.md](./TEST_SUITE_SUMMARY.md) |

---

## 🎓 For Different Roles

### 👨‍💻 Developer
→ [QUICK_START.md](./QUICK_START.md) - How to run tests

### 🏗️ Tech Lead
→ [TESTING_WORKFLOW.md](./TESTING_WORKFLOW.md) - Integration options

### 🔧 DevOps/CI-CD
→ [TEST_SUITE_SUMMARY.md](./TEST_SUITE_SUMMARY.md) - Automation setup

### 📚 QA/Tester
→ [UI_TESTING_GUIDE.md](./UI_TESTING_GUIDE.md) - Complete reference

### 🎯 Product Manager
→ [README_TESTING.md](./README_TESTING.md) - Overview & results

---

## ✅ Status: Ready to Use

All files are in place and ready to go! No additional setup needed beyond Playwright.

```bash
# Install (one-time)
pip install playwright && playwright install chromium

# Run (anytime)
bash run_ui_tests.sh

# That's it! 🎉
```

---

## 🚀 Next Steps

1. ✅ Run: `bash run_ui_tests.sh`
2. ✅ Review: Open `test_screenshots/report.html`
3. ✅ Customize: Edit `test_config.py` to add more pages
4. ✅ Integrate: Add to your workflow/CI-CD

---

**Questions?** Check the appropriate documentation file above.

**Ready to test?** Run:

```bash
bash run_ui_tests.sh
```
