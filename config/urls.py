from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from core import views as core_views

urlpatterns = [
    path("", core_views.home, name="home"),
    path("login/", core_views.login_view, name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("demo/", core_views.demo_login, name="demo_login"),
    path("cron/reset-demo/", core_views.cron_reset_demo, name="cron_reset_demo"),
    path("prep/", include("prep.urls")),
    path("projects/", include("journal.urls")),
    path("admin/", admin.site.urls),
]
