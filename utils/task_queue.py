"""
Task queue management using Redis and RQ
Method-based module following coding protocol
"""

import os
from redis import Redis
from rq import Queue
from dotenv import load_dotenv

load_dotenv()

def get_redis_connection():
    """Get Redis connection"""
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    return Redis.from_url(redis_url)

def get_trip_queue():
    """Get trip execution queue"""
    redis_conn = get_redis_connection()
    return Queue('trip_execution', connection=redis_conn)

def enqueue_trip_execution(trip_id):
    """Enqueue trip execution job"""
    queue = get_trip_queue()
    job = queue.enqueue(
        'utils.trip_execution.execute_trip_background_job',
        trip_id,
        job_timeout='30m'  # 30 minute timeout for trip execution
    )
    return job.id

def get_report_queue():
    """Get report generation queue"""
    redis_conn = get_redis_connection()
    return Queue('report_generation', connection=redis_conn)

def enqueue_inventory_report():
    """Enqueue inventory report generation job"""
    import platform
    queue = get_report_queue()
    
    # Disable timeout on Windows to avoid signal issues
    if platform.system() == 'Windows':
        job = queue.enqueue(
            'utils.rpt_generation.generate_inventory_report_simple'
            # No timeout on Windows
        )
    else:
        job = queue.enqueue(
            'utils.rpt_generation.generate_inventory_report_simple',
            job_timeout='10m'  # 10 minute timeout for report generation
        )
    return job.id

def enqueue_finished_goods_report():
    """Enqueue finished goods report generation job"""
    import platform
    queue = get_report_queue()
    
    # Disable timeout on Windows to avoid signal issues
    if platform.system() == 'Windows':
        job = queue.enqueue(
            'utils.rpt_generation.generate_finished_goods_report_simple'
            # No timeout on Windows
        )
    else:
        job = queue.enqueue(
            'utils.rpt_generation.generate_finished_goods_report_simple',
            job_timeout='10m'  # 10 minute timeout for report generation
        )
    return job.id
