from django.shortcuts import render
from django.http import HttpResponseForbidden


def role_required(required_roles):
    def decorator(view_func):
        def _wrapped_view(request, *args, **kwargs):
            if request.user.is_authenticated and request.user.role in required_roles:
                return view_func(request, *args, **kwargs)
            return render(request, 'users/403_forbidden.html', status=403)
        return _wrapped_view
    return decorator
