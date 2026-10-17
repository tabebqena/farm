"""Custom error views for the farm project."""
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.translation import get_language


def healthz(request):
    """Liveness probe used by load balancers and container orchestrators."""
    return HttpResponse("ok", content_type="text/plain")


def handler404(request, exception=None):
	"""Handle 404 errors with custom error messages."""
	error_message = None

	# Extract error message from the exception if available
	if exception and str(exception):
		error_message = str(exception)

	context = {
		'error_message': error_message,
		'request': request,
	}
	return render(request, '404.html', context, status=404)


def handler500(request):
	"""Handle 500 errors."""
	return render(request, '500.html', status=500)


def handler403(request, exception=None):
	"""Handle 403 errors."""
	error_message = None
	if exception and str(exception):
		error_message = str(exception)

	context = {
		'error_message': error_message,
		'request': request,
	}
	return render(request, '403.html', context, status=403)


def handler400(request, exception=None):
	"""Handle 400 errors."""
	error_message = None
	if exception and str(exception):
		error_message = str(exception)

	context = {
		'error_message': error_message,
		'request': request,
	}
	return render(request, '400.html', context, status=400)
