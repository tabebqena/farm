# 🚀 Quick Start - UI Testing

## 30-Second Setup

```bash
# Step 1: Install Playwright (one-time)
pip install playwright && playwright install chromium

# Step 2: Run tests (generates screenshots + HTML report)
bash run_ui_tests.sh
```

That's it! The script will:
1. ✅ Start Django dev server
2. 📸 Take screenshots on mobile & desktop
3. 📊 Generate interactive HTML report
4. 🌐 Open it in your browser

## What You'll Get

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
└── report.html  ← Open this to see results
```

## Example Output

The HTML report shows:

```
┌─────────────────────────────────────────┐
│ 🧪 Farm App - UI Test Report            │
├─────────────────────────────────────────┤
│ ✅ Passed: 16                            │
│ ❌ Failed: 0                             │
│ 📸 Total: 16                             │
├─────────────────────────────────────────┤
│                                         │
│ [Screenshot Grid]                       │
│ - Login Page (Mobile) ✅                 │
│ - Login Page (Desktop) ✅                │
│ - Entity List (Mobile) ✅                │
│ - Entity List (Desktop) ✅               │
│ ... and more                            │
└─────────────────────────────────────────┘
```

## Troubleshooting

### Port 8000 already in use?
```bash
# Find and kill existing process
lsof -i :8000
kill -9 <PID>
```

### Test users available:
- **admin** (superuser)
- **officer** (staff)

Change TEST_USERNAME/TEST_PASSWORD in `test_views_screenshots.py` if needed.

### Want to see the browser while testing?
Edit `test_views_screenshots.py` line ~200:
```python
self.browser = await p.chromium.launch(headless=False)  # Show browser
```

## Next Steps

See [UI_TESTING_GUIDE.md](./UI_TESTING_GUIDE.md) for:
- Adding more pages
- Custom assertions
- CI/CD integration
- Advanced configuration

---

**Ready?** Run: `bash run_ui_tests.sh`
