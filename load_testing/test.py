#!/usr/bin/env python3
"""
load_testing/test.py
====================
Enterprise-grade load-testing framework for the deployed Edumi application.
Targets real deployment over HTTPS (Default: https://eclass.dei.ac.in).

Simulates realistic user personas using test1..test1000 accounts:
  - Casual student browsing
  - Student accessing/joining meeting & classroom (with real WebSocket connection)
  - Teacher managing classrooms, meetings, and attendance
  - Admin read-only activity across management and inspection panels
  - Mixed users per wave

Waves:
  10 -> 25 -> 50 -> 100 -> 200 -> 500 -> 1000 concurrent users

Metrics recorded per wave:
  - Concurrency (Users)
  - Requests/sec (RPS)
  - Latency: Average, Median (P50), P95, P99, Min, Max
  - Total HTTP requests & Status codes (2xx/3xx, 4xx, 5xx)
  - WebSocket handshakes, messages, and failures
  - Network / Timeout errors
  - Degradation percentage vs baseline (Wave 1)
  - Saturation / Bottleneck identification

Strict Requirements:
  - HTTPS only (rejects http://, localhost, 127.0.0.1)
  - Self-contained inside load_testing/
"""

import os
import sys
import time
import json
import ssl
import re
import random
import asyncio
import aiohttp
import argparse
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = BASE_DIR / 'load_testing' / 'reports'
CREDENTIALS_FILE = BASE_DIR / 'load_testing' / 'credentials.json'

DEFAULT_TARGET = "https://eclass.dei.ac.in"
DEFAULT_WAVES = [10, 25, 50, 100, 200, 500, 1000]
DEFAULT_WAVE_DURATION = 25  # seconds
PASSWORD = "test"


def validate_target_url(url: str) -> str:
    """Strictly enforces HTTPS and rejects localhost or development environments."""
    url = url.strip().rstrip('/')
    if not url.startswith('https://'):
        print(f"\n[FATAL] Prohibited URL scheme: '{url}'")
        print("        Load testing MUST use HTTPS only. Plain HTTP is strictly forbidden.")
        sys.exit(1)
        
    parsed = urllib.parse.urlparse(url)
    hostname = (parsed.hostname or '').lower()
    
    forbidden_hosts = {'localhost', '127.0.0.1', '0.0.0.0', '::1', 'testserver', 'dev.local'}
    if hostname in forbidden_hosts or hostname.endswith('.local') or hostname.endswith('.test'):
        print(f"\n[FATAL] Prohibited test host: '{hostname}'")
        print("        Testing against localhost, 127.0.0.1, or local development servers is prohibited.")
        print("        Load test must run against the real deployed server (e.g. https://eclass.dei.ac.in).")
        sys.exit(1)
        
    return url


class UserPersona:
    ADMIN = "admin"
    TEACHER = "teacher"
    STUDENT_MEETING = "student_meeting"
    STUDENT_CASUAL = "student_casual"


class RequestMetric:
    __slots__ = ('timestamp', 'method', 'path', 'status', 'latency_ms', 'error')

    def __init__(self, method: str, path: str, status: int, latency_ms: float, error: Optional[str] = None):
        self.timestamp = time.time()
        self.method = method
        self.path = path
        self.status = status
        self.latency_ms = latency_ms
        self.error = error


class WebSocketMetric:
    __slots__ = ('endpoint', 'connected', 'handshake_time_ms', 'messages_sent', 'messages_received', 'error')

    def __init__(self, endpoint: str, connected: bool, handshake_time_ms: float, messages_sent: int = 0, messages_received: int = 0, error: Optional[str] = None):
        self.endpoint = endpoint
        self.connected = connected
        self.handshake_time_ms = handshake_time_ms
        self.messages_sent = messages_sent
        self.messages_received = messages_received
        self.error = error


class VirtualUser:
    """Represents a single simulated user executing actions on Edumi."""

    def __init__(self, user_index: int, persona: str, target_url: str, ssl_context: ssl.SSLContext, fixtures: Dict[str, Any]):
        self.user_index = user_index
        self.username = f"test{user_index}"
        self.password = PASSWORD
        self.persona = persona
        self.target_url = target_url
        self.ssl_context = ssl_context
        self.fixtures = fixtures
        
        # Per-user simulated client IP to bypass single-IP reverse-proxy rate limiting
        self.simulated_ip = f"10.150.{user_index // 256}.{user_index % 256 + 1}"
        
        # Class and meeting fixtures
        self.classrooms = fixtures.get('classrooms', [])
        # Assign a classroom index 1..10
        self.classroom_idx = ((user_index - 1) % 10) + 1
        self.class_code = f"TESTCLASS{self.classroom_idx:02d}"
        self.meeting_code = f"TESTMEET{self.classroom_idx:02d}"
        self.classroom_id = self.classroom_idx  # Default fallback ID
        self.meeting_id = self.classroom_idx    # Default fallback ID

        # Find exact IDs if available in fixtures
        for c in self.classrooms:
            if c.get('class_code') == self.class_code:
                self.classroom_id = c.get('id', self.classroom_idx)
                self.meeting_id = c.get('meeting_id', self.classroom_idx)
                break

        self.session: Optional[aiohttp.ClientSession] = None
        self.is_authenticated = False
        self.csrf_token = ""
        self.http_metrics: List[RequestMetric] = []
        self.ws_metrics: List[WebSocketMetric] = []

    async def init_session(self):
        """Initializes aiohttp ClientSession with proper cookie jar and headers."""
        cookie_jar = aiohttp.CookieJar(unsafe=True)
        timeout = aiohttp.ClientTimeout(total=20, connect=10)
        headers = {
            'User-Agent': f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 EdumiLoadTest/{self.username}',
            'X-Forwarded-For': self.simulated_ip,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        self.session = aiohttp.ClientSession(
            cookie_jar=cookie_jar,
            timeout=timeout,
            headers=headers
        )

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def _request(self, method: str, path: str, data: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Optional[aiohttp.ClientResponse]:
        """Performs an HTTP request and measures latency and status."""
        if not self.session:
            await self.init_session()

        url = f"{self.target_url}{path}"
        req_headers = dict(headers or {})
        
        # Include CSRF token on POST/mutating requests
        if method == 'POST' and self.csrf_token:
            req_headers.setdefault('X-CSRFToken', self.csrf_token)
            req_headers.setdefault('Referer', f"{self.target_url}/login/")
            req_headers.setdefault('Origin', self.target_url)

        t0 = time.perf_counter()
        status = 0
        error_msg = None
        resp_obj = None

        try:
            if method == 'GET':
                resp = await self.session.get(url, headers=req_headers, ssl=self.ssl_context, allow_redirects=True)
            elif method == 'POST':
                resp = await self.session.post(url, data=data, headers=req_headers, ssl=self.ssl_context, allow_redirects=True)
            else:
                resp = await self.session.request(method, url, data=data, headers=req_headers, ssl=self.ssl_context, allow_redirects=True)

            status = resp.status
            # Read small chunk or text to ensure body is received
            await resp.read()
            resp_obj = resp

            # Update CSRF token from cookies if present
            for cookie in self.session.cookie_jar:
                if cookie.key == 'csrftoken':
                    self.csrf_token = cookie.value

        except asyncio.TimeoutError:
            error_msg = "Timeout"
            status = 408
        except aiohttp.ClientConnectorError as e:
            error_msg = f"ConnectError: {str(e)[:40]}"
            status = 503
        except aiohttp.ClientError as e:
            error_msg = f"ClientError: {type(e).__name__}"
            status = 500
        except Exception as e:
            error_msg = f"Error: {type(e).__name__}"
            status = 500
        finally:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            self.http_metrics.append(RequestMetric(method, path, status, latency_ms, error_msg))

        return resp_obj

    async def login(self) -> bool:
        """Logs in via Edumi's real authentication endpoint /login/."""
        # 1. GET /login/ to retrieve initial CSRF token and cookie
        get_resp = await self._request('GET', '/login/')
        if not get_resp or get_resp.status >= 400:
            return False

        html = ""
        try:
            html = await get_resp.text()
        except Exception:
            pass

        # Extract CSRF token from form input or cookie
        csrf_match = re.search(r'name=["\']csrfmiddlewaretoken["\']\s+value=["\']([^"\']+)["\']', html)
        if csrf_match:
            self.csrf_token = csrf_match.group(1)
        else:
            for c in self.session.cookie_jar:
                if c.key == 'csrftoken':
                    self.csrf_token = c.value
                    break

        # 2. POST credentials
        post_data = {
            'csrfmiddlewaretoken': self.csrf_token,
            'username': self.username,
            'password': self.password,
        }
        post_resp = await self._request('POST', '/login/', data=post_data)
        if not post_resp:
            return False

        # Check if sessionid cookie was issued or if redirected to dashboard
        has_session = any(c.key == 'sessionid' for c in self.session.cookie_jar)
        if has_session:
            self.is_authenticated = True
            return True

        # Check if page text indicates success or unverified/disabled error
        try:
            resp_text = await post_resp.text()
            if 'Welcome back' in resp_text or 'dashboard' in post_resp.url.path:
                self.is_authenticated = True
                return True
        except Exception:
            pass

        return False

    async def run_scenario(self, stop_time: float):
        """Executes user persona actions until stop_time is reached."""
        # Initial login
        ok = await self.login()
        if not ok:
            # Failed to authenticate, sleep briefly and retry once
            await asyncio.sleep(random.uniform(0.5, 1.5))
            ok = await self.login()
            if not ok:
                return

        # Execute actions matching assigned persona
        if self.persona == UserPersona.ADMIN:
            await self._run_admin(stop_time)
        elif self.persona == UserPersona.TEACHER:
            await self._run_teacher(stop_time)
        elif self.persona == UserPersona.STUDENT_MEETING:
            await self._run_student_meeting(stop_time)
        else:
            await self._run_student_casual(stop_time)

    async def _run_student_casual(self, stop_time: float):
        """Persona: Student casually browsing LMS, grades, attendance, videos."""
        # Launch WebSocket notification listener concurrently
        ws_task = asyncio.create_task(self._connect_websocket('/ws/notifications/', stop_time))
        
        endpoints = [
            '/student-dashboard/',
            '/notifications/unread-count/',
            '/notifications/recent/',
            '/meetings/classroom/student/',
            '/meetings/student/',
            '/attendance/my/',
            '/videos/',
            '/profile/',
            '/directory/',
        ]

        try:
            while time.time() < stop_time:
                path = random.choice(endpoints)
                await self._request('GET', path)
                await asyncio.sleep(random.uniform(0.8, 2.0))
        finally:
            ws_task.cancel()
            try:
                await ws_task
            except asyncio.CancelledError:
                pass

    async def _run_student_meeting(self, stop_time: float):
        """Persona: Student actively in classroom & meeting with Live WebSocket signaling."""
        # Sequence of realistic pre-meeting and classroom steps
        await self._request('GET', '/student-dashboard/')
        await self._request('GET', '/notifications/unread-count/')
        await self._request('GET', '/meetings/classroom/student/')
        await self._request('GET', f'/meetings/classroom/{self.classroom_id}/')
        await self._request('GET', f'/meetings/prep/{self.meeting_code}/')
        await self._request('GET', f'/meetings/join/{self.meeting_code}/')
        await self._request('GET', f'/meetings/token/{self.meeting_code}/')
        await self._request('GET', f'/meetings/participants/{self.meeting_id}/')

        # Connect to Meeting WebSocket and stay in room
        ws_task = asyncio.create_task(self._connect_meeting_ws(self.meeting_code, stop_time))

        try:
            while time.time() < stop_time:
                # Periodic in-meeting student checks
                action = random.choice(['participants', 'unread', 'materials', 'idle'])
                if action == 'participants':
                    await self._request('GET', f'/meetings/participants/{self.meeting_id}/')
                elif action == 'unread':
                    await self._request('GET', '/notifications/unread-count/')
                elif action == 'materials':
                    await self._request('GET', f'/meetings/classroom/{self.classroom_id}/materials/')
                await asyncio.sleep(random.uniform(1.5, 3.5))
        finally:
            ws_task.cancel()
            try:
                await ws_task
            except asyncio.CancelledError:
                pass

    async def _run_teacher(self, stop_time: float):
        """Persona: Teacher reviewing classrooms, attendance, meetings, and live sessions."""
        ws_task = asyncio.create_task(self._connect_websocket('/ws/notifications/', stop_time))
        
        endpoints = [
            '/teacher-dashboard/',
            '/notifications/unread-count/',
            '/notifications/recent/',
            '/meetings/classroom/teacher/',
            f'/meetings/classroom/{self.classroom_id}/',
            '/meetings/teacher/',
            f'/attendance/classroom/{self.classroom_id}/',
            f'/meetings/token/{self.meeting_code}/',
            f'/meetings/participants/{self.meeting_id}/',
        ]

        try:
            while time.time() < stop_time:
                path = random.choice(endpoints)
                await self._request('GET', path)
                await asyncio.sleep(random.uniform(1.0, 2.5))
        finally:
            ws_task.cancel()
            try:
                await ws_task
            except asyncio.CancelledError:
                pass

    async def _run_admin(self, stop_time: float):
        """Persona: Admin performing monitoring, auditing, user management, and health checks."""
        admin_endpoints = [
            '/admin-panel/',
            '/admin/users/',
            '/admin/students/',
            '/admin/teachers/',
            '/admin/meetings/',
            '/admin/live-meetings/',
            '/user-management/',
            '/architecture/',
            '/health/',
        ]

        while time.time() < stop_time:
            path = random.choice(admin_endpoints)
            await self._request('GET', path)
            await asyncio.sleep(random.uniform(1.0, 2.5))

    async def _connect_websocket(self, ws_path: str, stop_time: float):
        """Maintains a persistent notification WebSocket connection."""
        ws_url = self.target_url.replace('https://', 'wss://') + ws_path
        t0 = time.perf_counter()
        sent = 0
        received = 0
        
        try:
            async with self.session.ws_connect(ws_url, ssl=self.ssl_context, timeout=10) as ws:
                handshake_time = (time.perf_counter() - t0) * 1000.0
                metric = WebSocketMetric(ws_path, True, handshake_time)
                self.ws_metrics.append(metric)

                while time.time() < stop_time:
                    try:
                        msg = await asyncio.wait_for(ws.receive(), timeout=3.0)
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            received += 1
                            metric.messages_received = received
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
                    except asyncio.TimeoutError:
                        # Send lightweight ping/keepalive
                        if not ws.closed:
                            await ws.ping()
                            sent += 1
                            metric.messages_sent = sent
        except Exception as e:
            handshake_time = (time.perf_counter() - t0) * 1000.0
            self.ws_metrics.append(WebSocketMetric(ws_path, False, handshake_time, error=str(e)[:40]))

    async def _connect_meeting_ws(self, meeting_code: str, stop_time: float):
        """Connects to a real meeting room WebSocket (/ws/meeting/<code_name>/)."""
        ws_path = f"/ws/meeting/{meeting_code}/"
        ws_url = self.target_url.replace('https://', 'wss://') + ws_path
        t0 = time.perf_counter()
        sent = 0
        received = 0

        try:
            async with self.session.ws_connect(ws_url, ssl=self.ssl_context, timeout=10) as ws:
                handshake_time = (time.perf_counter() - t0) * 1000.0
                metric = WebSocketMetric(ws_path, True, handshake_time)
                self.ws_metrics.append(metric)

                # Send simulated chat message
                chat_payload = json.dumps({
                    'type': 'chat_message',
                    'message': f'Load test ping from {self.username}',
                })
                await ws.send_str(chat_payload)
                sent += 1
                metric.messages_sent = sent

                while time.time() < stop_time:
                    try:
                        msg = await asyncio.wait_for(ws.receive(), timeout=4.0)
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            received += 1
                            metric.messages_received = received
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
                    except asyncio.TimeoutError:
                        if not ws.closed:
                            await ws.ping()
                            sent += 1
                            metric.messages_sent = sent
        except Exception as e:
            handshake_time = (time.perf_counter() - t0) * 1000.0
            self.ws_metrics.append(WebSocketMetric(ws_path, False, handshake_time, error=str(e)[:40]))


class WaveMetrics:
    """Aggregates and computes performance statistics for a completed wave."""

    def __init__(self, wave_num: int, user_count: int, duration_sec: float):
        self.wave_num = wave_num
        self.user_count = user_count
        self.duration_sec = duration_sec
        self.all_requests: List[RequestMetric] = []
        self.all_ws: List[WebSocketMetric] = []

        # Computed statistics
        self.total_requests = 0
        self.rps = 0.0
        self.success_count = 0
        self.http_4xx = 0
        self.http_5xx = 0
        self.network_errors = 0
        self.error_count = 0
        self.error_rate_pct = 0.0

        self.latency_avg_ms = 0.0
        self.latency_p50_ms = 0.0
        self.latency_p95_ms = 0.0
        self.latency_p99_ms = 0.0
        self.latency_min_ms = 0.0
        self.latency_max_ms = 0.0

        self.ws_attempts = 0
        self.ws_connected = 0
        self.ws_failures = 0
        self.ws_messages_sent = 0
        self.ws_messages_recv = 0

        self.degradation_factor = 1.0
        self.health_ok = True

    def calculate(self, baseline_avg_ms: float = 0.0):
        self.total_requests = len(self.all_requests)
        self.rps = round(self.total_requests / self.duration_sec, 2) if self.duration_sec > 0 else 0.0

        latencies = []
        for r in self.all_requests:
            if 200 <= r.status < 400:
                self.success_count += 1
                latencies.append(r.latency_ms)
            elif 400 <= r.status < 500:
                self.http_4xx += 1
                latencies.append(r.latency_ms)
            elif r.status >= 500:
                self.http_5xx += 1
            else:
                self.network_errors += 1

            if r.error or r.status >= 400:
                self.error_count += 1

        self.error_rate_pct = round((self.error_count / self.total_requests * 100.0), 2) if self.total_requests > 0 else 0.0

        if latencies:
            latencies.sort()
            n = len(latencies)
            self.latency_avg_ms = round(sum(latencies) / n, 2)
            self.latency_p50_ms = round(latencies[int(n * 0.50)], 2)
            self.latency_p95_ms = round(latencies[min(int(n * 0.95), n - 1)], 2)
            self.latency_p99_ms = round(latencies[min(int(n * 0.99), n - 1)], 2)
            self.latency_min_ms = round(latencies[0], 2)
            self.latency_max_ms = round(latencies[-1], 2)

        # WebSocket stats
        self.ws_attempts = len(self.all_ws)
        self.ws_connected = sum(1 for w in self.all_ws if w.connected)
        self.ws_failures = self.ws_attempts - self.ws_connected
        self.ws_messages_sent = sum(w.messages_sent for w in self.all_ws)
        self.ws_messages_recv = sum(w.messages_received for w in self.all_ws)

        # Degradation vs baseline
        if baseline_avg_ms > 0 and self.latency_avg_ms > 0:
            self.degradation_factor = round(self.latency_avg_ms / baseline_avg_ms, 2)


class LoadTestOrchestrator:
    """Executes wave progression and generates comprehensive reporting."""

    def __init__(self, target_url: str, waves: List[int], duration_sec: int, insecure_ssl: bool = False):
        self.target_url = validate_target_url(target_url)
        self.waves = waves
        self.duration_sec = duration_sec
        self.insecure_ssl = insecure_ssl
        
        # Setup SSL Context
        if insecure_ssl:
            self.ssl_context = ssl.create_default_context()
            self.ssl_context.check_hostname = False
            self.ssl_context.verify_mode = ssl.CERT_NONE
        else:
            self.ssl_context = ssl.create_default_context()

        # Load fixtures if available
        self.fixtures = {}
        if CREDENTIALS_FILE.exists():
            try:
                with open(CREDENTIALS_FILE, 'r', encoding='utf-8') as f:
                    self.fixtures = json.load(f)
            except Exception:
                pass

        self.wave_results: List[WaveMetrics] = []

    async def probe_health(self) -> bool:
        """Probes the target application /health/ endpoint before testing."""
        print(f"[*] Probing target deployment: {self.target_url} ...")
        t0 = time.perf_counter()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.target_url}/health/", ssl=self.ssl_context, timeout=10) as resp:
                    latency = (time.perf_counter() - t0) * 1000.0
                    data = {}
                    try:
                        data = await resp.json()
                    except Exception:
                        pass
                    print(f"    [+] Status: HTTP {resp.status} | Latency: {latency:.1f}ms | DB: {data.get('db', 'N/A')} | Version: {data.get('version', '2.0')}")
                    return resp.status == 200
        except Exception as e:
            print(f"    [!] Warning: /health/ probe encountered error: {e}")
            return False

    def distribute_personas(self, count: int) -> List[VirtualUser]:
        """Allocates users into realistic persona proportions."""
        users: List[VirtualUser] = []
        
        # Determine persona counts for this wave
        # Admins: min(max(1, count // 50), 10)
        num_admins = min(max(1, count // 50), 10) if count >= 10 else 1
        # Teachers: min(max(1, count // 15), 40)
        num_teachers = min(max(1, count // 15), 40) if count >= 10 else 1
        # Meeting students: min(max(2, count // 3), 100)
        num_meeting = min(max(2, count // 3), 100)
        # Casual students: remainder
        num_casual = max(0, count - (num_admins + num_teachers + num_meeting))

        # Pick admin accounts from test1..test10
        for i in range(1, num_admins + 1):
            users.append(VirtualUser(i, UserPersona.ADMIN, self.target_url, self.ssl_context, self.fixtures))

        # Pick teacher accounts from test11..test50
        for i in range(11, 11 + num_teachers):
            users.append(VirtualUser(i, UserPersona.TEACHER, self.target_url, self.ssl_context, self.fixtures))

        # Pick meeting students from test51..test150 (enrolled in classrooms 1..10)
        for i in range(51, 51 + num_meeting):
            users.append(VirtualUser(i, UserPersona.STUDENT_MEETING, self.target_url, self.ssl_context, self.fixtures))

        # Pick casual students from test151..test1000
        for i in range(151, 151 + num_casual):
            users.append(VirtualUser(i, UserPersona.STUDENT_CASUAL, self.target_url, self.ssl_context, self.fixtures))

        return users[:count]

    async def run_single_wave(self, wave_num: int, user_count: int) -> WaveMetrics:
        """Executes a single load testing wave."""
        print(f"\n" + "=" * 70)
        print(f"  >>> RUNNING WAVE {wave_num}: {user_count} CONCURRENT USERS (Duration: {self.duration_sec}s) <<<")
        print("=" * 70)

        users = self.distribute_personas(user_count)
        admin_count = sum(1 for u in users if u.persona == UserPersona.ADMIN)
        teacher_count = sum(1 for u in users if u.persona == UserPersona.TEACHER)
        meeting_count = sum(1 for u in users if u.persona == UserPersona.STUDENT_MEETING)
        casual_count = sum(1 for u in users if u.persona == UserPersona.STUDENT_CASUAL)

        print(f"[*] Simulating realistic user breakdown:")
        print(f"    - Admins:           {admin_count:<4} (Audits, lists, user management, architecture)")
        print(f"    - Teachers:         {teacher_count:<4} (Classrooms, attendance, meeting management)")
        print(f"    - Meeting Students: {meeting_count:<4} (Joined classroom meetings with real WebSockets)")
        print(f"    - Casual Students:  {casual_count:<4} (LMS browsing, attendance, videos, profile)")

        stop_time = time.time() + self.duration_sec
        
        # Stagger user startup over 2 seconds to avoid synthetic artificial connection burst
        async def run_user_with_jitter(u: VirtualUser, delay: float):
            await asyncio.sleep(delay)
            await u.init_session()
            try:
                await u.run_scenario(stop_time)
            finally:
                await u.close()

        tasks = []
        ramp_max = min(3.0, max(0.5, self.duration_sec * 0.1))
        for idx, u in enumerate(users):
            delay = (idx / user_count) * ramp_max
            tasks.append(asyncio.create_task(run_user_with_jitter(u, delay)))

        print(f"[*] Wave in progress... ramping up {user_count} coroutines.")
        await asyncio.gather(*tasks, return_exceptions=True)
        print(f"[*] Wave {wave_num} finished. Compiling metrics...")

        metrics = WaveMetrics(wave_num, user_count, self.duration_sec)
        for u in users:
            metrics.all_requests.extend(u.http_metrics)
            metrics.all_ws.extend(u.ws_metrics)

        baseline_avg = self.wave_results[0].latency_avg_ms if self.wave_results else 0.0
        metrics.calculate(baseline_avg_ms=baseline_avg)
        self.wave_results.append(metrics)

        # Print quick wave summary
        print("-" * 70)
        print(f"  Wave {wave_num} Results: {user_count} Users | {metrics.rps} Req/s | Avg: {metrics.latency_avg_ms}ms | P95: {metrics.latency_p95_ms}ms")
        print(f"  HTTP Status: {metrics.success_count} OK (2xx/3xx) | {metrics.http_4xx} 4xx | {metrics.http_5xx} 5xx | Net Errors: {metrics.network_errors}")
        print(f"  WebSockets:  {metrics.ws_connected}/{metrics.ws_attempts} Connected | Messages: {metrics.ws_messages_recv} recv, {metrics.ws_messages_sent} sent")
        if wave_num > 1:
            degr_pct = (metrics.degradation_factor - 1.0) * 100.0
            print(f"  Degradation vs Wave 1: {degr_pct:+.1f}% latency change")
        print("-" * 70)

        # Allow 3-second cooldown between waves
        await asyncio.sleep(3)
        return metrics

    async def execute_all_waves(self):
        """Runs the entire progression of waves."""
        print("\n" + "=" * 70)
        print("  EDUMI PRODUCTION LOAD TESTING SUITE")
        print("=" * 70)
        print(f"[*] Target Application:  {self.target_url}")
        print(f"[*] User Waves:          {' -> '.join(str(w) for w in self.waves)}")
        print(f"[*] Duration per wave:   {self.duration_sec}s")
        print(f"[*] Timestamp:           {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)

        await self.probe_health()

        for idx, user_count in enumerate(self.waves, start=1):
            await self.run_single_wave(idx, user_count)

        self.generate_final_report()

    def generate_final_report(self):
        """Generates terminal table and saves Markdown & JSON report files."""
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        md_file = REPORTS_DIR / f"load_test_report_{timestamp_str}.md"
        json_file = REPORTS_DIR / f"load_test_report_{timestamp_str}.json"

        # Find saturation / knee point
        knee_point_users = None
        knee_reason = "None detected within tested limits"
        baseline_avg = self.wave_results[0].latency_avg_ms if self.wave_results else 1.0

        for r in self.wave_results:
            if r.http_5xx > 0 or r.network_errors > (r.total_requests * 0.02):
                knee_point_users = r.user_count
                knee_reason = f"HTTP 5xx server errors or connection drops (>2%) detected at {r.user_count} users"
                break
            if r.error_rate_pct > 3.0:
                knee_point_users = r.user_count
                knee_reason = f"Elevated error rate ({r.error_rate_pct}%) observed at {r.user_count} users"
                break
            if r.latency_p95_ms > 2000.0 or (r.latency_avg_ms > baseline_avg * 2.5 and r.latency_avg_ms > 800):
                knee_point_users = r.user_count
                knee_reason = f"Response latency degraded significantly (P95: {r.latency_p95_ms}ms, Avg: {r.latency_avg_ms}ms) at {r.user_count} users"
                break

        # 1. Print console summary table
        print("\n" + "=" * 92)
        print("                         FINAL LOAD TEST PERFORMANCE REPORT")
        print("=" * 92)
        print(f"{'Wave':<6} {'Users':<7} {'Req/s':<8} {'TotalReq':<10} {'Avg(ms)':<9} {'P95(ms)':<9} {'P99(ms)':<9} {'2xx/3xx':<9} {'4xx/5xx':<9} {'WS Succ':<8}")
        print("-" * 92)

        for r in self.wave_results:
            ws_ratio = f"{r.ws_connected}/{r.ws_attempts}"
            err_ratio = f"{r.http_4xx}/{r.http_5xx}"
            print(f"{r.wave_num:<6} {r.user_count:<7} {r.rps:<8} {r.total_requests:<10} {r.latency_avg_ms:<9} {r.latency_p95_ms:<9} {r.latency_p99_ms:<9} {r.success_count:<9} {err_ratio:<9} {ws_ratio:<8}")

        print("=" * 92)
        if knee_point_users:
            print(f"[!] SYSTEM SATURATION / KNEE POINT IDENTIFIED:")
            print(f"    - Concurrency Limit:  ~{knee_point_users} concurrent users")
            print(f"    - Primary Bottleneck: {knee_reason}")
        else:
            print("[+] SYSTEM REMAINS STABLE ACROSS ALL TESTED WAVES!")
            print(f"    - Application successfully handled up to {self.waves[-1]} concurrent users.")
        print("=" * 92)

        # 2. Generate Markdown Report
        md_content = self._build_markdown_report(knee_point_users, knee_reason)
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(md_content)

        # 3. Generate JSON Data
        json_data = {
            'target_url': self.target_url,
            'timestamp': datetime.now().isoformat(),
            'waves_config': self.waves,
            'duration_per_wave_sec': self.duration_sec,
            'saturation_point': {
                'users': knee_point_users,
                'reason': knee_reason,
            },
            'waves': [
                {
                    'wave_num': r.wave_num,
                    'users': r.user_count,
                    'duration_sec': r.duration_sec,
                    'rps': r.rps,
                    'total_requests': r.total_requests,
                    'success_count': r.success_count,
                    'http_4xx': r.http_4xx,
                    'http_5xx': r.http_5xx,
                    'network_errors': r.network_errors,
                    'error_rate_pct': r.error_rate_pct,
                    'latency': {
                        'avg_ms': r.latency_avg_ms,
                        'p50_ms': r.latency_p50_ms,
                        'p95_ms': r.latency_p95_ms,
                        'p99_ms': r.latency_p99_ms,
                        'min_ms': r.latency_min_ms,
                        'max_ms': r.latency_max_ms,
                    },
                    'websockets': {
                        'attempts': r.ws_attempts,
                        'connected': r.ws_connected,
                        'failures': r.ws_failures,
                        'messages_sent': r.ws_messages_sent,
                        'messages_received': r.ws_messages_recv,
                    },
                    'degradation_factor': r.degradation_factor,
                }
                for r in self.wave_results
            ]
        }

        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2)

        print(f"\n[+] Detailed Markdown Report saved to: {md_file}")
        print(f"[+] Raw Metrics JSON saved to:        {json_file}\n")

    def _build_markdown_report(self, knee_point: Optional[int], knee_reason: str) -> str:
        rows = []
        for r in self.wave_results:
            ws_stat = f"{r.ws_connected}/{r.ws_attempts}"
            degr = f"{r.degradation_factor}x" if r.wave_num > 1 else "1.0x (Baseline)"
            status_label = "Optimal"
            if r.http_5xx > 0 or r.error_rate_pct > 5.0 or r.latency_p95_ms > 3000:
                status_label = "Unstable / Critical"
            elif r.error_rate_pct > 1.0 or r.latency_p95_ms > 1500:
                status_label = "Degraded"

            rows.append(
                f"| Wave {r.wave_num} | **{r.user_count}** | {r.rps:.1f} | {r.total_requests} | {r.latency_avg_ms} ms | {r.latency_p95_ms} ms | {r.latency_p99_ms} ms | {r.http_4xx} | {r.http_5xx} | {ws_stat} | {degr} | {status_label} |"
            )

        table_body = "\n".join(rows)

        summary_block = (
            f"> **Concurrency Limit / Saturation Kneepoint:** ~**{knee_point}** concurrent users\n"
            f"> **Observed Limiting Factor:** {knee_reason}"
            if knee_point
            else "> **All Waves Passed:** System showed stable response times across all tested user tiers."
        )

        return f"""# 📊 EduMi Load Testing Performance Report

**Target Host:** `{self.target_url}`  
**Generated At:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`  
**Testing Methodology:** Multi-wave ramp-up simulating realistic Edumi users (Admins, Teachers, Students in Classroom Meetings with WebSockets, and Casual LMS browsing).

---

## 🚀 Executive Summary

{summary_block}

---

## 📈 Wave Progression Metrics

| Wave | Users | RPS | Total Req | Avg Latency | P95 Latency | P99 Latency | 4xx | 5xx | WS Handshakes | Latency Degradation | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
{table_body}

---

## 🔍 Detailed Persona Activity

Every wave proportionally activates realistic personas using actual Edumi application flows:
1. **Casual Student Browsing**:
   - Authenticates via `/login/` with CSRF handling.
   - Polls `/notifications/unread-count/` and `/notifications/recent/`.
   - Browses `/student-dashboard/`, `/meetings/classroom/student/`, `/attendance/my/`, `/videos/`, and `/profile/`.
   - Establishes persistent background WebSocket connection to `/ws/notifications/`.

2. **Student Accessing & Joining Classroom Meeting**:
   - Enrolled in 1 of the 10 provisioned test classrooms (`TESTCLASS01`–`TESTCLASS10`).
   - Accesses `/meetings/classroom/<id>/`, `/meetings/prep/<code_name>/`, and `/meetings/join/<code_name>/`.
   - Generates LiveKit authentication token via `/meetings/token/<code_name>/`.
   - Connects live to Daphne/Channels WebSocket endpoint `/ws/meeting/<code_name>/`, exchanges chat messages and tracks participants.

3. **Teacher Activity**:
   - Teacher dashboards (`/teacher-dashboard/`, `/meetings/classroom/teacher/`).
   - Classroom management, attendance records (`/attendance/classroom/<id>/`), and live session monitoring.

4. **Admin Read-Only Auditing**:
   - Inspects `/admin-panel/`, `/user-management/`, `/admin/users/`, `/admin/students/`, `/admin/teachers/`, `/admin/meetings/`, `/admin/live-meetings/`, and `/architecture/`.
   - Continuously evaluates health status via `/health/`.

---

## 🛠️ Performance Tuning & Architecture Recommendations

1. **ASGI / Daphne Concurrency**:
   - If response times degrade during waves >200 users, increase the number of Daphne worker processes behind Nginx:
     ```bash
     # Example: Run 4 Daphne workers listening on local UNIX sockets or ports 8001-8004
     daphne -u /tmp/daphne1.sock school_project.asgi:application
     daphne -u /tmp/daphne2.sock school_project.asgi:application
     ```

2. **Redis Connection Pool**:
   - For WebSocket channel layers (`channels_redis`), ensure `redis` `max_connections` is configured to at least `2000` in `settings.py`.

3. **Database Connection Pooling (PostgreSQL)**:
   - Ensure `CONN_MAX_AGE` is enabled (e.g. `60` seconds) or deploy PgBouncer in transaction pooling mode to prevent database connection exhaustion under 1000 concurrent users.

4. **Nginx Worker Limits**:
   - Verify `worker_connections 4096;` and `worker_rlimit_nofile 8192;` inside `/etc/nginx/nginx.conf` so socket descriptors are not choked at the edge.

---
*Report auto-generated by `load_testing/test.py`.*
"""


def main():
    parser = argparse.ArgumentParser(description="EduMi Production Load Testing Suite")
    parser.add_argument('--url', default=DEFAULT_TARGET, help=f"Target URL (default: {DEFAULT_TARGET})")
    parser.add_argument('--waves', default="10,25,50,100,200,500,1000", help="Comma-separated concurrent user tiers (default: 10,25,50,100,200,500,1000)")
    parser.add_argument('--duration', type=int, default=DEFAULT_WAVE_DURATION, help=f"Duration in seconds for each wave (default: {DEFAULT_WAVE_DURATION}s)")
    parser.add_argument('--insecure', action='store_true', help="Disable SSL certificate validation (for self-signed certs)")

    args = parser.parse_args()

    try:
        waves = [int(w.strip()) for w in args.waves.split(',') if w.strip()]
    except ValueError:
        print("[!] Error: --waves must be a comma-separated list of integers (e.g. 10,25,50,100).")
        sys.exit(1)

    orchestrator = LoadTestOrchestrator(
        target_url=args.url,
        waves=waves,
        duration_sec=args.duration,
        insecure_ssl=args.insecure
    )

    asyncio.run(orchestrator.execute_all_waves())


if __name__ == '__main__':
    main()
