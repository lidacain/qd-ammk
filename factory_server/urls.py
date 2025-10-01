from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from django.conf.urls.static import static
from django.conf import settings
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from users.views import login_view
from django.conf.urls import handler403
from django.shortcuts import render


def custom_permission_denied_view(request, exception=None):
    return render(request, "errors/403.html", status=403)


handler403 = custom_permission_denied_view


# Функция для автоматического редиректа на страницу логина
def redirect_to_login(request):
    return redirect("login")


urlpatterns = [
    path('secure-admin-lidacain/', admin.site.urls),
    path('', redirect_to_login),  # Автоматически перенаправляем на логин
    path('users/', include('users.urls')),
    path("supplies/", include("supplies.urls")),
    path("assembly/", include("assembly.urls")),
    path("vehicle_history/", include("vehicle_history.urls", namespace="vehicle_history")),
    path('login/', login_view, name='login'),
    path('qrr/', include('qrr.urls')),
    path("directory/", include("public_directory.urls")),
    path("administrators/", include("administrators.urls")),
    path("line-stats/", include("line_stats.urls", namespace="line_stats")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
