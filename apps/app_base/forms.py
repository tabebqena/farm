"""Forms for the base app.

:class:`UserProfileForm` edits a Django user's first name, last name and email,
styling the fields with the project's ``form-control`` CSS class.
"""

from django import forms
from django.contrib.auth.models import User


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
