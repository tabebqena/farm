# Authentication System Documentation

## Overview

Your Django project has a complete authentication system that requires users to log in before accessing any protected resources.

## How It Works

### 1. **Middleware Protection** (`farm/middlewares.py`)
- `LoginRequiredMiddleware` automatically redirects unauthenticated users to the login page
- All URLs are protected except for:
  - `/login/` - Login page (in all languages: `/en/login/`, `/ar/login/`)
  - `/auth/register/` - User registration page
  - `/admin/` - Admin interface
  - `/i18n/` - Language switching endpoint

### 2. **Login View** (`farm/urls.py`)
- Provided by Django's built-in `auth_views.LoginView`
- URL: `login` (accessible as `/en/login/` or `/ar/login/`)
- Template: `apps/app_base/templates/registration/login.html`
- Includes link to registration page for new users

### 3. **Registration View** (`apps/app_base/views.py`)
- Custom registration form with validation
- URL: `/auth/register/` (accessible as `/en/auth/register/` or `/ar/auth/register/`)
- Requires: username, email, password confirmation
- Optional: first name, last name
- Features:
  - Email uniqueness validation
  - Username uniqueness validation
  - Password strength validation
  - Bootstrap-styled form
- Template: `apps/app_base/templates/registration/register.html`

### 4. **Logout View** (`farm/urls.py`)
- Provided by Django's built-in `auth_views.LogoutView`
- URL: `logout`
- Redirects to `LOGOUT_REDIRECT_URL` (configured as `login`)

### 5. **Settings Configuration** (`farm/settings.py`)
```python
LOGIN_URL = "login"  # Redirect unauthenticated users here
LOGIN_REDIRECT_URL = "entity_list"  # Redirect after successful login
LOGOUT_REDIRECT_URL = "login"  # Redirect after logout
```

## Features

✅ **Automatic Login Requirement** - All pages require authentication by default
✅ **User Registration** - New users can self-register with email validation
✅ **User Session Management** - Built on Django's session framework
✅ **Logout Functionality** - User dropdown with sign-out button in navbar
✅ **Redirect After Login** - Users are redirected to their requested page or home
✅ **Multi-language Support** - Login and registration pages work in English and Arabic
✅ **Admin Login** - Admin panel accessible with same credentials
✅ **Email & Username Validation** - Prevents duplicate accounts

## Using Authentication in Views

### Option 1: Automatic (Recommended)
All views are automatically protected by the middleware. No additional code needed.

### Option 2: Explicit Protection (Function-Based Views)
```python
from farm.auth_utils import require_login

@require_login
def my_view(request):
    user = request.user  # Current authenticated user
    return render(request, 'template.html', {'user': user})
```

### Option 3: Explicit Protection (Class-Based Views)
```python
from farm.auth_utils import AuthRequiredMixin
from django.views.generic import ListView

class MyListView(AuthRequiredMixin, ListView):
    model = MyModel
    template_name = 'my_list.html'
```

## User Access in Templates

Check if user is authenticated:
```html
{% if user.is_authenticated %}
  <p>Welcome, {{ user.username }}!</p>
  <a href="{% url 'logout' %}">Logout</a>
{% else %}
  <a href="{% url 'login' %}">Login</a>
{% endif %}
```

## User Registration

### Self-Registration (For End Users)
1. Visit `/register/` (or `/en/register/` / `/ar/register/`)
2. Fill in the registration form:
   - **Username** - Required, unique identifier
   - **Email** - Required, must be unique
   - **Password** - Required, must meet security requirements
   - **Confirm Password** - Required, must match password
   - **First Name** - Optional
   - **Last Name** - Optional
3. Submit the form
4. Account is created immediately and user can log in

### Form Validation
The registration form validates:
- ✅ Username is unique
- ✅ Email is unique and valid format
- ✅ Password is strong (8+ characters, not purely numeric)
- ✅ Passwords match
- ✅ Username doesn't resemble password

## Database User Management

### Create a Superuser
```bash
python manage.py createsuperuser
```

### Create Regular Users
Via Django admin, registration page, or programmatically:
```python
from django.contrib.auth.models import User

User.objects.create_user(
    username='john',
    password='securepassword123',
    email='john@example.com'
)
```

## User Object in Views

Access the current user in any view:
```python
def my_view(request):
    user = request.user
    
    # Check authentication
    if user.is_authenticated:
        username = user.username
        email = user.email
        # ... use user data
    else:
        # Middleware redirects before reaching here
        pass
    
    return render(request, 'template.html', {'user': user})
```

## Security Notes

⚠️ **In Production:**
1. Change `SECRET_KEY` in settings
2. Set `DEBUG = False`
3. Set `ALLOWED_HOSTS` appropriately
4. Use strong password validators
5. Enable HTTPS (set `SECURE_SSL_REDIRECT = True`)
6. Configure `CSRF_TRUSTED_ORIGINS`

## Troubleshooting

### Users Keep Getting Logged Out
- Check session settings in `settings.py`
- Ensure cookies are enabled in browser
- Check `SESSION_COOKIE_AGE` setting (default: 2 weeks)

### Forgot Password
Currently, the basic Django auth system is in place. To add password reset:
1. Add password reset views from `django.contrib.auth.views`
2. Create password reset email templates
3. Configure email backend in settings

### Custom User Model
If you need additional user fields (phone, department, etc.), create a custom user model extending `AbstractUser` in your app before running migrations.

## Related Files

- Middleware: `farm/middlewares.py`
- Auth utilities: `farm/auth_utils.py`
- Registration form: `apps/app_base/forms.py`
- Registration view: `apps/app_base/views.py`
- App URLs: `apps/app_base/urls.py`
- Login template: `apps/app_base/templates/registration/login.html`
- Registration template: `apps/app_base/templates/registration/register.html`
- Base template: `templates/base.html`
- Main URL configuration: `farm/urls.py`
- Settings: `farm/settings.py`
