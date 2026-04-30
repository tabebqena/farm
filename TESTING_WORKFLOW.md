# 🔄 Testing Workflow Guide

Complete workflow for using the UI testing suite in your development process.

## 📋 Typical Workflow

### During Development

```
1. Make code changes
   └─> Edit your Django templates/CSS/JS

2. Start dev server
   └─> python manage.py runserver

3. Quick visual check (optional)
   └─> Open http://localhost:8000 in browser

4. Run UI tests
   └─> bash run_ui_tests.sh
   
5. Review report
   └─> Open test_screenshots/report.html
   
6. Check for regressions
   └─> Compare new screenshots with previous ones
   
7. Fix any issues
   └─> Go back to step 1
   
8. Commit changes
   └─> git add . && git commit -m "..."
```

## 🔍 What to Look For in Reports

### ✅ All Tests Pass
- Green "✅ PASS" badges on all cards
- All expected elements found
- Screenshots look correct at both viewports
- No blank or broken images

**Action**: Safe to commit! 🎉

### ⚠️ Some Tests Fail
- Orange "⚠️ ISSUES" badges
- Check which page/viewport failed
- Review the screenshot for visual issues
- Check CSS selectors in `test_config.py`

**Action**: Fix the issue and re-run tests

### 🔴 Page Doesn't Load
- Screenshot might be blank
- Check Django console for errors
- Ensure user is logged in
- Verify URL is correct

**Action**: Debug in Django, fix, and re-run

## 🚀 Quick Commands

```bash
# One-line: install + run tests + open report
pip install playwright && playwright install chromium && bash run_ui_tests.sh

# Just run tests (Django server must be running)
python test_views_screenshots.py

# Run tests with browser visible (for debugging)
# Edit test_config.py: HEADLESS = False, then:
python test_views_screenshots.py

# View existing report without running tests
# (just open in browser)
open test_screenshots/report.html
```

## 📊 Using in Different Scenarios

### Scenario 1: Quick Visual Check Before Commit

```bash
# 1. Make changes
# 2. Run tests
bash run_ui_tests.sh

# 3. Review report
open test_screenshots/report.html

# 4. If all green, commit
git add . && git commit -m "Your changes"
```

### Scenario 2: Testing Responsive Design After CSS Changes

```bash
# 1. Edit CSS/styles
# 2. Run tests
bash run_ui_tests.sh

# 3. Look at report
# 4. Check mobile vs desktop side-by-side
# 5. Adjust CSS and re-run
```

### Scenario 3: Debugging a Failing Test

```bash
# 1. Run with visible browser
# Edit test_config.py and set HEADLESS = False

# 2. Run tests
python test_views_screenshots.py

# 3. Watch what happens in the browser
# 4. Check Django console for errors
# 5. Fix the issue
# 6. Re-run tests
```

### Scenario 4: Adding a New Page/Feature

```bash
# 1. Implement new page/feature

# 2. Add to test_config.py:
{
    "name": "My New Feature",
    "url": "/en/my-feature/",
    "checks": ["h1", "button", "form"],
    "needs_auth": True,
}

# 3. Run tests
bash run_ui_tests.sh

# 4. Verify new page appears in report

# 5. Commit both code and config changes
```

## 🔔 Pre-commit Integration

### Option A: Manual Check (Recommended)
Run tests before committing:

```bash
# Before each commit
bash run_ui_tests.sh

# Only commit if all tests pass
git add .
git commit -m "..."
```

### Option B: Automated Git Hook

Create `.git/hooks/pre-commit`:

```bash
#!/bin/bash
# Exit on first error
set -e

# Run UI tests
if ! bash run_ui_tests.sh; then
    echo "❌ UI tests failed. Fix issues and try again."
    exit 1
fi

echo "✅ UI tests passed. Proceeding with commit..."
exit 0
```

Make executable:
```bash
chmod +x .git/hooks/pre-commit
```

### Option C: GitHub Actions (CI/CD)

Add `.github/workflows/ui-tests.yml`:

```yaml
name: UI Tests

on: [push, pull_request]

jobs:
  ui-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install playwright
          playwright install chromium
      
      - name: Run migrations
        run: python manage.py migrate
      
      - name: Run UI tests
        run: bash run_ui_tests.sh
      
      - name: Upload results on failure
        if: failure()
        uses: actions/upload-artifact@v3
        with:
          name: ui-test-results
          path: test_screenshots/
```

## 📈 Comparing Reports Over Time

### Manual Comparison

1. Keep old reports:
   ```bash
   # After each test run
   cp -r test_screenshots test_screenshots_backup_$(date +%Y%m%d_%H%M%S)
   ```

2. Compare screenshots side-by-side:
   ```bash
   # Compare specific screenshots
   open test_screenshots/Entity_List_mobile_*.png
   open test_screenshots_backup/Entity_List_mobile_*.png
   ```

3. Look for visual changes:
   - Layout differences
   - Color changes
   - Missing elements
   - Responsive breakpoints

### Automated Comparison (Advanced)

Script to compare two reports:

```python
# compare_reports.py
import os
from PIL import Image
from pathlib import Path

def compare_screenshots(old_dir, new_dir):
    """Compare two screenshot directories"""
    old_files = set(os.listdir(old_dir))
    new_files = set(os.listdir(new_dir))
    
    added = new_files - old_files
    removed = old_files - new_files
    
    print(f"Added: {added}")
    print(f"Removed: {removed}")
    
    for fname in old_files & new_files:
        if fname.endswith('.png'):
            old_img = Image.open(f"{old_dir}/{fname}")
            new_img = Image.open(f"{new_dir}/{fname}")
            
            if old_img.tobytes() != new_img.tobytes():
                print(f"Changed: {fname}")

compare_screenshots("test_screenshots_old", "test_screenshots")
```

## 🐛 Common Issues and Fixes

### Issue: Screenshot is blank

**Causes:**
- Django server not running
- Wrong URL
- Page requires authentication but login failed
- JavaScript errors

**Fix:**
```bash
# Check server is running
curl http://localhost:8000/en/login/

# Check Django logs for errors
# python manage.py runserver

# Verify test credentials in test_config.py
```

### Issue: "Element not found" errors

**Causes:**
- CSS selector changed
- Page structure changed
- Element isn't rendered yet

**Fix:**
```bash
# Update selectors in test_config.py
# Increase wait time (WAIT_FOR_LOAD)
# Add delay before screenshot (SCREENSHOT_DELAY)
```

### Issue: Tests are slow

**Causes:**
- Slow database queries
- Heavy JavaScript
- Network requests

**Fix:**
- Check Django logs for slow queries
- Optimize database queries
- Run on faster machine
- Increase timeout

### Issue: Some tests pass, some fail inconsistently

**Causes:**
- Race conditions
- JavaScript timing
- Database state

**Fix:**
```bash
# Increase timeout in test_config.py
# TIMEOUT = 45000  # was 30000

# Add delay in test_views_screenshots.py
# await self.page.wait_for_timeout(1000)  # 1 second
```

## 📚 Documentation Links

- [QUICK_START.md](./QUICK_START.md) - Get running in 30 seconds
- [UI_TESTING_GUIDE.md](./UI_TESTING_GUIDE.md) - Detailed reference
- [test_config.py](./test_config.py) - Configuration options
- [TEST_SUITE_SUMMARY.md](./TEST_SUITE_SUMMARY.md) - Complete overview

## ✅ Checklist: Before Major Release

- [ ] All UI tests pass
- [ ] Screenshots reviewed for visual issues
- [ ] Mobile and desktop viewports both render correctly
- [ ] No console errors in browser
- [ ] Forms submit successfully
- [ ] Navigation works on all pages
- [ ] Links point to correct URLs
- [ ] No missing images or assets
- [ ] Text is readable on small screens
- [ ] Buttons are clickable on mobile

## 🚀 Best Practices

1. **Run tests frequently**
   - After any UI changes
   - Before commits
   - Before merges

2. **Keep tests updated**
   - Add new pages as they're created
   - Update selectors if HTML changes
   - Add new viewports if supporting them

3. **Review reports carefully**
   - Don't ignore warnings
   - Compare with previous runs
   - Check both mobile and desktop

4. **Commit thoughtfully**
   - Don't commit broken tests
   - Update test config with code changes
   - Document unusual test behavior

5. **Share results**
   - Show reports in PRs
   - Share failures with team
   - Discuss rendering issues

---

**Happy testing!** 🎉
