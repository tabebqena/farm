"""Custom Django shortcuts with meaningful error messages."""
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404
from django.shortcuts import get_object_or_404 as django_get_object_or_404


def get_object_or_404(klass, *args, error_message=None, **kwargs):
	"""
	Wrapper around Django's get_object_or_404 that allows custom error messages.

	Args:
		klass: Model class or queryset
		error_message: Custom error message to display if object not found
		*args, **kwargs: Arguments passed to Django's get_object_or_404

	Usage:
		entity = get_object_or_404(
			Entity,
			pk=entity_id,
			error_message="Entity not found or has been deleted"
		)
	"""
	try:
		return django_get_object_or_404(klass, *args, **kwargs)
	except Http404:
		if error_message:
			raise Http404(error_message)
		raise


def paginate(request, items, per_page=25):
	"""
	Paginate *items* (a queryset or list) using the request's ``page`` param.

	Returns a ``(page_obj, paginator)`` tuple. ``paginator.get_page`` handles
	non-integer and out-of-range page numbers, so callers don't need the
	``PageNotAnInteger``/``EmptyPage`` try/except dance.
	"""
	from django.core.paginator import Paginator

	paginator = Paginator(items, per_page)
	return paginator.get_page(request.GET.get("page")), paginator
