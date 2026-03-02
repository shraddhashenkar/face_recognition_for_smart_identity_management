"""
Custom middleware for RollVision security and monitoring
"""
import time
import logging
from django.core.cache import cache
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


class RateLimitMiddleware(MiddlewareMixin):
    """
    Rate limiting middleware to prevent API abuse
    Implements sliding window rate limiting using Django cache
    """
    
    # Rate limit configurations for different endpoints
    RATE_LIMITS = {
        '/api/save-face/': {'calls': 5, 'period': 60},  # 5 calls per minute
        '/api/process-attendance/': {'calls': 3, 'period': 60},  # 3 calls per minute
        'default': {'calls': 100, 'period': 60}  # 100 calls per minute for other endpoints
    }
    
    def process_request(self, request):
        """Check rate limit before processing request"""
        # Skip rate limiting for static files and admin
        if request.path.startswith('/static/') or request.path.startswith('/media/') or request.path.startswith('/admin/'):
            return None
        
        # Get client IP address
        ip_address = self.get_client_ip(request)
        
        # Determine rate limit for this endpoint
        rate_limit = self.get_rate_limit(request.path)
        
        # Create cache key
        cache_key = f"rate_limit:{ip_address}:{request.path}"
        
        # Get current request count
        request_count = cache.get(cache_key, 0)
        
        if request_count >= rate_limit['calls']:
            logger.warning(f"Rate limit exceeded for IP {ip_address} on {request.path}")
            return JsonResponse({
                'error': 'Rate limit exceeded. Please try again later.',
                'retry_after': rate_limit['period']
            }, status=429)
        
        # Increment request count
        cache.set(cache_key, request_count + 1, rate_limit['period'])
        
        return None
    
    def get_client_ip(self, request):
        """Extract client IP address from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def get_rate_limit(self, path):
        """Get rate limit configuration for given path"""
        for endpoint, limit in self.RATE_LIMITS.items():
            if endpoint != 'default' and path.startswith(endpoint):
                return limit
        return self.RATE_LIMITS['default']


class AuditLogMiddleware(MiddlewareMixin):
    """
    Middleware to log all sensitive operations for security auditing
    """
    
    # Paths that should be audited
    AUDIT_PATHS = [
        '/api/save-face/',
        '/api/process-attendance/',
        '/faculty/delete/',
        '/settings/',
    ]
    
    def process_request(self, request):
        """Log request start time"""
        request._audit_start_time = time.time()
        return None
    
    def process_response(self, request, response):
        """Log completed requests for audited endpoints"""
        # Check if this path should be audited
        should_audit = any(request.path.startswith(path) for path in self.AUDIT_PATHS)
        
        if should_audit:
            duration = time.time() - getattr(request, '_audit_start_time', time.time())
            
            # Get client IP
            ip_address = self.get_client_ip(request)
            
            # Log the audit trail
            logger.info(
                f"AUDIT: {request.method} {request.path} | "
                f"IP: {ip_address} | "
                f"User: {getattr(request.user, 'username', 'anonymous')} | "
                f"Status: {response.status_code} | "
                f"Duration: {duration:.2f}s"
            )
        
        return response
    
    def get_client_ip(self, request):
        """Extract client IP address from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class SecurityHeadersMiddleware(MiddlewareMixin):
    """
    Add security headers to all responses
    """
    
    def process_response(self, request, response):
        """Add security headers"""
        from django.conf import settings
        
        # Prevent clickjacking
        response['X-Frame-Options'] = 'DENY'
        
        # Prevent MIME type sniffing
        response['X-Content-Type-Options'] = 'nosniff'
        
        # Enable XSS protection
        response['X-XSS-Protection'] = '1; mode=block'
        
       # Referrer policy
        response['Referrer-Policy'] = 'same-origin'
        
        # Content Security Policy - build from settings
        csp_parts = []
        
        if hasattr(settings, 'CSP_DEFAULT_SRC'):
            csp_parts.append(f"default-src {' '.join(settings.CSP_DEFAULT_SRC)}")
        
        if hasattr(settings, 'CSP_SCRIPT_SRC'):
            csp_parts.append(f"script-src {' '.join(settings.CSP_SCRIPT_SRC)}")
        
        if hasattr(settings, 'CSP_STYLE_SRC'):
            csp_parts.append(f"style-src {' '.join(settings.CSP_STYLE_SRC)}")
        
        if hasattr(settings, 'CSP_FONT_SRC'):
            csp_parts.append(f"font-src {' '.join(settings.CSP_FONT_SRC)}")
        
        if hasattr(settings, 'CSP_IMG_SRC'):
            csp_parts.append(f"img-src {' '.join(settings.CSP_IMG_SRC)}")
        
        if hasattr(settings, 'CSP_MEDIA_SRC'):
            csp_parts.append(f"media-src {' '.join(settings.CSP_MEDIA_SRC)}")
        
        if hasattr(settings, 'CSP_CONNECT_SRC'):
            csp_parts.append(f"connect-src {' '.join(settings.CSP_CONNECT_SRC)}")
        
        response['Content-Security-Policy'] = '; '.join(csp_parts)
        
        return response
