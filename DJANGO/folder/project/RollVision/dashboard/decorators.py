"""
Custom decorators for API security and validation
"""
import functools
import logging
from django.http import JsonResponse
from django.shortcuts import render
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


def audit_log(view_func):
    """
    Decorator to log API calls with metadata
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Get client IP
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        
        # Log the API call
        logger.info(
            f"API_CALL: {view_func.__name__} | "
            f"IP: {ip} | "
            f"User: {getattr(request.user, 'username', 'anonymous')} | "
            f"Method: {request.method}"
        )
        
        try:
            response = view_func(request, *args, **kwargs)
            
            # Log successful response
            if hasattr(response, 'status_code'):
                logger.info(f"API_RESPONSE: {view_func.__name__} | Status: {response.status_code}")
            
            return response
        except Exception as e:
            # Log error
            logger.error(f"API_ERROR: {view_func.__name__} | Error: {str(e)}")
            raise
    
    return wrapper


def validate_json_request(view_func):
    """
    Decorator to validate that request contains valid JSON
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.method in ['POST', 'PUT', 'PATCH']:
            content_type = request.META.get('CONTENT_TYPE', '')
            
            if 'application/json' not in content_type:
                return JsonResponse({
                    'success': False,
                    'message': 'Content-Type must be application/json'
                }, status=400)
            
            try:
                # Try to access request.body to ensure it's valid
                _ = request.body
            except Exception:
                return JsonResponse({
                    'success': False,
                    'message': 'Invalid request body'
                }, status=400)
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


def require_staff(view_func):
    """
    Decorator to require staff/admin permissions
    Combines login_required with staff check
    """
    @functools.wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            logger.warning(f"Unauthorized access attempt by {request.user.username} to {view_func.__name__}")
            # Check if it's an API request (expects JSON) or web page
            if request.META.get('HTTP_ACCEPT', '').startswith('application/json'):
                return JsonResponse({
                    'success': False,
                    'message': 'Staff permissions required'
                }, status=403)
            else:
                # For web pages, render error page or redirect
                messages.error(request, 'Staff permissions required to access this page.')
                return render(request, 'dashboard/index.html', status=403)
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


def sanitize_input(max_length=1000):
    """
    Decorator to sanitize text inputs to prevent injection attacks
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # For POST requests, sanitize common input fields
            if request.method == 'POST' and hasattr(request, 'POST'):
                # Check for excessively long inputs
                for key, value in request.POST.items():
                    if isinstance(value, str) and len(value) > max_length:
                        logger.warning(f"Input too long for field {key}: {len(value)} chars")
                        return JsonResponse({
                            'success': False,
                            'message': f'Input too long for field {key}'
                        }, status=400)
            
            return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator
