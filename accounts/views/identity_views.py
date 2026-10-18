"""
accounts/views/identity_views.py
REST API endpoints for the Centralized Identification System (SSOT).
Enforces authentication and classroom boundary checks on all endpoints.
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
            'identity': None,
            'error': 'Authentication required.'
        }, status=401)

    identity = getattr(request, 'identity', None) or IdentityService.get_identity(request.user)
    return JsonResponse({
        'success': True,
        'authenticated': True,
        'identity': identity
    })


@login_required
@require_http_methods(["GET"])
def identity_user_view(request, user_id):
    """
    Returns the canonical identity dictionary for any user by user_id.
    Guarded by authentication and classroom/role boundary validation.
    """
    try:
        target_uid = int(user_id)
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Invalid user ID'}, status=400)

    # Check existence
    if not User.objects.filter(id=target_uid).exists():
        return JsonResponse({'success': False, 'error': 'User identity not found'}, status=404)

    # Enforce institutional classroom boundary & authorization
    if not IdentityService.is_identity_visible(request.user, target_uid):
        return JsonResponse({
            'success': False,
            'error': 'Forbidden: You do not have permission to view this identity.'
        }, status=403)

    identity = IdentityService.get_identity_by_id(target_uid)
    return JsonResponse({
        'success': True,
        'identity': identity
    })


@login_required
@require_http_methods(["POST"])
def identity_batch_view(request):
    """
    Batch resolves up to 100 user IDs into identity dictionaries.
    Only returns identities that the requesting user is authorized to view.
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

    # Filter to authorized IDs based on classroom boundaries
    clean_ids = [int(uid) for uid in user_ids if str(uid).isdigit()][:100]
    authorized_ids = [uid for uid in clean_ids if IdentityService.is_identity_visible(request.user, uid)]

    identities = IdentityService.get_identities_batch(authorized_ids)
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
    if target_user_id and (request.user.is_superuser or (hasattr(request.user, 'userprofile') and request.user.userprofile.user_type == 'admin')):
        try:
            target_user = User.objects.get(id=int(target_user_id))
        except User.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Target user not found'}, status=404)
    else:
        target_user = request.user

    try:
        data = dict(request.POST.items())
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
    except ValueError as ve:
        return JsonResponse({'success': False, 'error': str(ve)}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
