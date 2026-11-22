"""
attendance/face_metrics.py
Metrics for Face Tracking Performance & Queue Monitoring.
"""
from prometheus_client import Histogram, Counter, Gauge

face_processing_latency = Histogram(
    'edumi_face_processing_latency_seconds',
    'Face frame processing latency',
    buckets=[0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0, 2.0]
)

face_frames_processed = Counter(
    'edumi_face_frames_processed_total',
    'Total frames processed',
    ['meeting_code', 'status']
)

face_queue_depth = Gauge(
    'edumi_face_queue_depth',
    'Number of frames in processing queue'
)

active_face_workers = Gauge(
    'edumi_face_workers_active',
    'Number of active face tracking workers'
)
