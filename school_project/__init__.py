import sys
import asyncio

# CRITICAL: Set the event loop policy for Windows to support subprocesses in asyncio
# This must be done at the earliest possible moment for Daphne/Channels
if sys.platform == 'win32':
    try:
        if hasattr(asyncio, 'WindowsProactorEventLoopPolicy'):
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

# This will make sure the app is always imported when
# Django starts so that shared_task will use this app.
from .celery import app as celery_app
import django.template.context
import copy

# Monkey-patch Django's Context.__copy__ for Python 3.13+ compatibility
# The original implementation uses duplicate = copy(super()) which fails in 3.13+
# because super() objects are immutable and don't allow setting attributes like .dicts
def patch_context_copy():
    from django.template.context import BaseContext
    
    def __copy__(self):
        # Create a new instance of the same class without calling __init__
        duplicate = self.__class__.__new__(self.__class__)
        # Copy all attributes from the current instance
        duplicate.__dict__.update(self.__dict__)
        # Deep copy the dicts list (as in the original implementation)
        duplicate.dicts = self.dicts[:]
        return duplicate
    
    BaseContext.__copy__ = __copy__

patch_context_copy()

__all__ = ('celery_app',)
