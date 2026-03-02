from .models import SystemSettings

def theme_context(request):
    settings_obj = SystemSettings.objects.first()
    return {
        "theme": settings_obj.theme if settings_obj else "light"
    }
