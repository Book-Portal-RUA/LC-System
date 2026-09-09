class HtmxMiddleware:
    """Sets request.htmx = True/False based on the HX-Request header sent by htmx.

    Kept as a tiny hand-rolled middleware (instead of the django-htmx package)
    so this project has the smallest possible dependency footprint.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.htmx = request.headers.get('HX-Request') == 'true'
        return self.get_response(request)
