from fastapi import HTTPException
from collections import defaultdict
import time

user_requests = defaultdict(list)

def apply_rate_limit(user_id: str):
    current_time = time.time()
    rate_limit = 5
    time_window = 30

    user_requests[user_id] = [
        t for t in user_requests[user_id] if t > current_time - time_window
    ]

    if len(user_requests[user_id]) >= rate_limit:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again later."
        )

    user_requests[user_id].append(current_time)
    return True