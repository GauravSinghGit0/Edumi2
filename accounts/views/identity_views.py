"""
accounts/views/identity_views.py
REST API endpoints for the Centralized Identification System (SSOT).
"""

import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from accounts.identity import IdentityService
from accounts.services import update_user_identity
from django.contrib.auth import get_user_model

User = get_user_model()


@require_http_methods(["GET"])
def identity_me_view(request):
    """
    Returns the canonical identity dictionary for the current logged-in user.
    """
    if not request.user.is_authenticated:
        return JsonResponse({
            'success': False,
            'authenticated': False,
            'identity': None
        }, status=200)

    identity = getattr(request, 'identity', None) or IdentityService.get_identity(request.user)
    return JsonResponse({
        'success': True,
        'authenticated': True,
        'identity': identity
    })


@require_http_methods(["GET"])
def identity_user_view(request, user_id):
    """
    Returns the canonical identity dictionary for any user by user_id.
    """
    identity = IdentityService.get_identity_by_id(user_id)
    if not identity or not identity.get('user_id'):
        return JsonResponse({
            'success': False,
            'error': 'User identity not found'
        }, status=404)

    return JsonResponse({
        'success': True,
        'identity': identity
    })


@require_http_methods(["POST"])
def identity_batch_view(request):
    """
    Batch resolves up to 100 user IDs into identity dictionaries.
    Ideal for roster rendering (meetings, classrooms, admin lists).
    Payload JSON: { "user_ids": [1, 2, 3] }
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        data = request.POST

    user_ids = data.get('user_ids', [])
    if not isinstance(user_ids, list):
        return JsonResponse({
            'success': False,
            'error': 'user_ids must be a list'
        }, status=400)

    identities = IdentityService.get_identities_batch(user_ids)
    return JsonResponse({
        'success': True,
        'count': len(identities),
        'identities': identities
    })


@login_required
@require_http_methods(["POST"])
def identity_update_view(request):
    """
    API endpoint to update user identity. Saves models and triggers real-time WebSocket sync.
    """
    target_user_id = request.POST.get('user_id') or request.POST.get('target_user_id')
    if target_user_id and request.user.is_superuser:
        try:
            target_user = User.objects.get(id=int(target_user_id))
        except User.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Target user not found'}, status=404)
    else:
        target_user = request.user

    try:
        data = dict(request.POST.items())
        # Handle JSON body if submitted as JSON
        if request.content_type == 'application/json':
            try:
                data.update(json.loads(request.body.decode('utf-8')))
            except Exception:
                pass

        updated_identity = update_user_identity(
            target_user=target_user,
            actor=request.user,
            data=data,
            files=request.FILES
        )

        return JsonResponse({
            'success': True,
            'message': 'Identity updated successfully',
            'identity': updated_identity
        })
    except PermissionError as pe:
        return JsonResponse({'success': False, 'error': str(pe)}, status=403)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
