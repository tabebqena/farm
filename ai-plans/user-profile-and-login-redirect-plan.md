# User Profile & Login Redirect Plan

## Goal
1. Add a link to the user's profile (detail) page in the username dropdown menu.
2. Add a link from the profile detail page to the profile edit page.
3. On login, redirect to home (`/`) or the `next` parameter when provided.

## Changes

### 1. Username dropdown menu
- [`templates/base.html`](../templates/base.html): Added a **Profile** link in the user dropdown menu (before the Sign Out button) that goes to `{% url 'profile' %}`.

### 2. Profile detail page (read-only)
- [`apps/app_base/views.py`](../apps/app_base/views.py): `profile` is now a read-only detail view (GET only) rendering the profile details.
- [`apps/app_base/templates/registration/profile.html`](../apps/app_base/templates/registration/profile.html): Rewritten as a read-only detail page showing username, first/last name, email, and member-since date. Includes an **Edit Profile** button linking to `{% url 'profile_edit' %}` and the Sign Out action.

### 3. Profile edit page
- [`apps/app_base/views.py`](../apps/app_base/views.py): Added `profile_edit` view (GET/POST) that saves via `UserProfileForm` and redirects back to `profile` on success.
- [`apps/app_base/urls.py`](../apps/app_base/urls.py): Added URL pattern `profile/edit/` named `profile_edit`.
- [`apps/app_base/templates/registration/profile_edit.html`](../apps/app_base/templates/registration/profile_edit.html): New edit page with the editable first name / last name / email form plus a **Back to Profile** link.

### 4. Login redirect
- [`farm/settings.py`](../farm/settings.py): `LOGIN_REDIRECT_URL` changed from `profile` to `/` (home). Users are sent home after login unless a `next` parameter is present.
- [`apps/app_base/templates/registration/login.html`](../apps/app_base/templates/registration/login.html): Form action simplified to `{% url 'login' %}`; the hidden `next` field (from context) preserves the original requested URL so redirect-to-next works.

## Verification
- `python manage.py check` — no issues.
- `python manage.py test apps.app_base.tests --parallel=8` — 26 tests OK.
- Manual shell checks confirmed:
  - Login without `next` redirects to `/`.
  - Login with `next` (GET or POST) redirects to the requested page.
  - Profile detail page shows user info and the Edit link.
  - Profile edit page renders the form and redirects to profile on save.
  - Anonymous users are redirected to login on the edit page.
  - Dropdown renders both Profile and Sign Out links.

## Implemented
- Completed per plan; all changes verified.
