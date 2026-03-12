from __future__ import annotations

import time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Callable, Iterable, TypeVar


ItemT = TypeVar("ItemT")
ResultT = TypeVar("ResultT")


def run_parallel_with_retries(
    items: Iterable[ItemT],
    worker: Callable[[ItemT], ResultT],
    *,
    max_workers: int,
    max_retries: int,
    should_retry: Callable[[ResultT], bool],
    on_retry: Callable[[ItemT, int], None] | None = None,
    on_result: Callable[[ItemT, ResultT], None] | None = None,
) -> list[ResultT]:
    pending = deque(items)
    results: list[ResultT] = []
    retries: dict[ItemT, int] = {item: 0 for item in pending}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        in_flight: dict = {}
        while pending or in_flight:
            while pending and len(in_flight) < max_workers:
                item = pending.popleft()
                in_flight[executor.submit(worker, item)] = item

            done_futures, _ = wait(in_flight.keys(), return_when=FIRST_COMPLETED)
            for future in done_futures:
                item = in_flight.pop(future)
                result = future.result()
                if should_retry(result) and retries[item] < max_retries:
                    retries[item] += 1
                    if on_retry:
                        on_retry(item, retries[item])
                    time.sleep(min(0.2 * retries[item], 1.0))
                    pending.append(item)
                    continue
                results.append(result)
                if on_result:
                    on_result(item, result)
    return results
