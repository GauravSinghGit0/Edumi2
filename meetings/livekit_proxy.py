"""
WebSocket proxy: browser <-> Django/ngrok <-> LiveKit (localhost:7880)

Browser connects to:  wss://<ngrok>/livekit-proxy/rtc?access_token=...
Proxy forwards to:    ws://localhost:7880/rtc?access_token=...
"""
import asyncio
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
import websockets
from django.conf import settings

logger = logging.getLogger(__name__)

LIVEKIT_INTERNAL = getattr(settings, 'LIVEKIT_INTERNAL_URL', "ws://localhost:7880")


class LiveKitProxyConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        lk_path = self.scope["url_route"]["kwargs"].get("lk_path") or "/rtc"
        qs = self.scope.get("query_string", b"").decode()

        target = f"{LIVEKIT_INTERNAL}{lk_path}"
        if qs:
            target += f"?{qs}"

        logger.info(f"LiveKit proxy -> {target}")

        try:
            self._lk_ws = await asyncio.wait_for(
                websockets.connect(
                    target,
                    ping_interval=20,
                    ping_timeout=20,
                    max_size=10 * 1024 * 1024,
                    close_timeout=5,
                    additional_headers={
                        "X-Forwarded-For": self.scope.get("client", [""])[0] or "",
                    },
                ),
                timeout=8,
            )
        except asyncio.TimeoutError:
            logger.error(f"LiveKit proxy connect TIMEOUT -> {target}. LiveKit server not running on {LIVEKIT_INTERNAL}?")
            await self.close(code=1013)
            return
        except Exception as e:
            logger.error(
                f"LiveKit proxy connect FAILED -> {target}. "
                f"Verify LiveKit server is running at {LIVEKIT_INTERNAL}. "
                f"Error: {e!r}"
            )
            await self.close(code=1013)
            return

        await self.accept(subprotocol=None)
        self._lk_task = asyncio.ensure_future(self._lk_to_browser())

    async def disconnect(self, code):
        if hasattr(self, "_lk_task") and self._lk_task and not self._lk_task.done():
            self._lk_task.cancel()
        if hasattr(self, "_lk_ws"):
            try:
                await asyncio.wait_for(self._lk_ws.close(), timeout=2)
            except Exception:
                pass

    async def receive(self, text_data=None, bytes_data=None):
        """Browser → LiveKit"""
        if not hasattr(self, "_lk_ws"):
            return
        try:
            if bytes_data is not None:
                await self._lk_ws.send(bytes_data)
            elif text_data is not None:
                await self._lk_ws.send(text_data)
        except Exception as e:
            logger.warning(f"Proxy -> LiveKit send error: {e}")
            await self.close()

    async def _lk_to_browser(self):
        """LiveKit → Browser"""
        try:
            async for msg in self._lk_ws:
                if isinstance(msg, bytes):
                    await self.send(bytes_data=msg)
                else:
                    await self.send(text_data=msg)
        except Exception as e:
            logger.debug(f"LiveKit -> proxy stream ended: {e}")
        finally:
            try:
                await self.close()
            except Exception:
                pass
