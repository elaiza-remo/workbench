from django.conf import settings


def site(request):
    match = getattr(request, "resolver_match", None)
    user = getattr(request, "user", None)
    return {
        "SITE_NAME": settings.SITE_NAME,
        "section": (match.app_name if match else "") or "home",
        "is_demo": getattr(user, "username", None) == settings.DEMO_USERNAME,
    }
