from django.views.generic import TemplateView
from django.contrib import messages

class HomeView(TemplateView):
    template_name = 'core/home.html'

    def get(self, request, *args, **kwargs):
        messages.success(request, 'This is a test message to verify Bootstrap alert styling.')
        return super().get(request, *args, **kwargs)
