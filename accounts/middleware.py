class TenantMiddleware:
    """Attach the authenticated user's school to each request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.school = None
        user = request.user
        if user.is_authenticated and hasattr(user, 'school_id'):
            request.school = user.school
        return self.get_response(request)
