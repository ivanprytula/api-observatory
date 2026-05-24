---
name: async-patterns
description:
    'Production-grade async/await patterns and anti-patterns for Python. Covers concurrency models,
    coroutines, event loops, Task vs Future, backpressure, cancellation semantics, timeouts, and
    choosing between async, threads, and processes for FastAPI services.'
applyTo: 'src/**/*.py, **/*.py'
---

# Async/Await Patterns: Production-Grade Concurrency

## Core Mental Model

### The Central Idea

Async is **not** a performance spell. It is a **concurrency model** for managing I/O-bound workloads
efficiently.

**Key insight:** I/O is slow. When your service makes an HTTP request, waits on a database, reads
from a socket, or talks to Redis, the CPU is usually waiting, not computing. Async allows other work
to proceed during that wait instead of blocking the entire execution context.

```text
Blocking I/O:  [Wait for data] → (thread stuck, nothing else happens)
Async I/O:     [Wait for data] → (other tasks run) → (resume on completion)
```

---

## Fundamentals: Blocking vs Non-Blocking I/O

### Blocking I/O

A thread enters a system call and stays there until the operation completes.

```python
# ✗ Blocks the thread
import socket
sock = socket.socket()
data = sock.recv(1024)  # Thread waits here; nothing else runs
```

**Examples:** `read()`, `recv()`, `accept()`, synchronous database calls.

### Non-Blocking I/O

The call returns immediately:

- If the resource is ready, the operation succeeds.
- If not, the call returns without blocking.

The runtime polls the OS asking "which resources became ready?"

```python
# ✓ Returns immediately, doesn't block
import select
select.epoll()  # Ask OS which sockets are ready
asyncio.wait()  # High-level wrapper around select/poll/epoll/kqueue
```

**Mechanisms:** `select`, `poll`, `epoll` (Linux), `kqueue` (macOS), IOCP (Windows).

**The asyncio event loop** sits on top of these mechanisms, making non-blocking I/O accessible.

---

## Async vs Threads vs Processes: Different Tools

### Concurrency Models

| Model         | Scheduling         | GIL Impact       | Use Case                           |
| ------------- | ------------------ | ---------------- | ---------------------------------- |
| **Threads**   | OS (preemptive)    | Contends; blocks | Blocking I/O, sync SDK integration |
| **Async**     | User (cooperative) | Doesn't help     | I/O-bound, many concurrent waits   |
| **Processes** | OS independent     | Bypassed         | CPU-bound, pure Python compute     |

### The Global Interpreter Lock (GIL)

**Important truth:** Only one thread can execute Python bytecode at a time in CPython.

**Consequence 1:** Threads are still useful for I/O-bound work because blocking I/O often releases
the GIL, allowing another thread to run.

**Consequence 2:** Threads don't provide real speedup for CPU-bound pure Python code (both threads
contend for the GIL).

**Consequence 3:** Async does NOT bypass the GIL. It solves a different problem entirely.

```python
# Async is for I/O-bound concurrency, not parallelism
# Using async does not make CPU-heavy code parallel
async def heavy_compute():
    result = 0
    for i in range(10_000_000):  # ✗ This cannot be speeded up by async
        result += i ** 2
    return result
```

**Strong mental model:**

> Async is a lower-overhead way to manage many mostly-waiting operations when they can yield control
> cooperatively. It does not bypass the GIL and does not provide CPU parallelism.

---

## Coroutines: What They Actually Are

### Coroutines are Stateful Execution Objects

When you call an `async def`, Python doesn't immediately run the function. It creates a coroutine
object:

```python
async def foo():
    return 1

coro = foo()  # Not executed; creates a suspended computation
print(coro)   # <coroutine object foo at 0x...>
print(type(coro))  # <class 'coroutine'>

result = await coro  # Now it executes and returns 1
```

**Conceptually, a coroutine is a state machine:**

- Where execution currently is
- What it's waiting for
- What value should eventually be returned
- What exception should be propagated
- How to resume from the last suspension point

### Coroutines vs Generators

**Generator lineage matters.** Async didn't appear from nothing.

```python
# Generator: yield pauses and hands value outward
def gen():
    yield 1
    yield 2

# Generator-based coroutine: yield from delegates control
def coro_old():
    yield from gen()

# Modern async: await pauses until awaitable produces result
async def coro_new():
    result = await something()
    return result
```

**Mental model:**

```
yield    → pause and hand value outward
yield from → delegate control to another generator
await    → pause until awaitable produces result
```

All three are about pause-and-resume. `await` is the specialized version for async I/O.

---

## Awaitables: The Protocol

### What Can Be Awaited?

The weak answer: "a coroutine."

**The correct answer:** Anything implementing the `__await__` protocol.

```python
# Awaitable types
class MyAwaitable:
    def __await__(self):
        yield
        return 42

async def main():
    result = await MyAwaitable()  # Works!
    print(result)  # 42
```

**In practice, you await:**

- **Coroutine objects** (from `async def`)
- **Task** (wraps a coroutine, driven by event loop)
- **Future** (placeholder for eventual result)
- **Custom awaitables** (rarely needed in application code)

---

## The Event Loop: The Beating Heart

### What Does It Do?

```python
while not stopped:
    process_ready_callbacks()
    process_timers()
    poll_io_events()  # Ask OS: which I/O operations are ready
    wake_tasks_waiting_for_events()
```

**The event loop is:**

- The scheduler that decides what gets to run next
- The orchestrator coordinating waiting, timers, I/O events, and task resumption
- Usually a single-threaded loop (though uvloop and other implementations exist)

### What `await asyncio.sleep(1)` Actually Does

**Misconception:** The thread sleeps for one second.

**Reality:**

```python
await asyncio.sleep(1)
# 1. Creates an awaitable tied to a timer
# 2. Suspends current task
# 3. Event loop registers: "resume this task in 1 second"
# 4. Loop runs OTHER ready tasks
# 5. When timer expires, task resumes
```

**The crucial distinction:**

> `asyncio.sleep()` is not blocking sleep. It's a cooperative handoff to the event loop until a
> timer says the task may continue.

---

## Task vs Future: Shape and Role

### Future: A Placeholder

A `Future` is a low-level object representing a result that will exist later:

```python
future = asyncio.Future()
# Holds a value, exception, or cancellation
# Does not actively run anything
```

### Task: A Future That Runs Your Code

A `Task` wraps a coroutine and actively drives its execution in the event loop:

```python
async def worker():
    await asyncio.sleep(1)
    return "done"

task = asyncio.create_task(worker())
# Task is now scheduled and running
```

**Practical distinction:**

```text
Future → container for a result (lazy, doesn't execute)
Task   → schedulable executor of a coroutine (active, drives execution)
```

---

## Cooperative Multitasking: One Bad Function Ruins Everyone's Day

Async relies on **cooperative multitasking**. Tasks must yield voluntarily at `await` points.

If they don't, the event loop can't help:

```python
# ✗ Disastrous: no yield points
async def bad_cpu_work():
    while True:
        do_cpu_work()  # Event loop starved; nothing else runs

# ✗ Disastrous: blocks entire thread
async def bad_blocking():
    time.sleep(5)  # Not asyncio.sleep; blocks the thread

# ✓ Good: yields at appropriate points
async def good():
    await asyncio.sleep(1)
    result = await some_io()
    return result
```

**The most important truth:**

> Async code is only as non-blocking as the code you put inside it. If you put blocking I/O or
> CPU-heavy logic into the event loop, the service becomes unresponsive.

---

## Structured Concurrency: TaskGroup

### The Problem: Scattered `create_task()` Calls

```python
# ✗ Easy to lose track of tasks
task1 = asyncio.create_task(a())
task2 = asyncio.create_task(b())
res1 = await task1
res2 = await task2
# What if task2 fails while we're awaiting task1?
# What cleans up if we exit early?
```

### The Solution: TaskGroup

```python
# ✓ Structured concurrency: clear lifetime
async with asyncio.TaskGroup() as tg:
    tg.create_task(a())
    tg.create_task(b())
    # If one fails, group handles it coherently
    # When scope exits, all tasks accounted for
```

**Benefits:**

- Clear scope owns child tasks
- Coherent failure handling
- Proper cancellation semantics
- No dangling background work
- Predictable cleanup

---

## Cancellation: The Neglected Essential

### How Cancellation Works

When a task is cancelled, a `CancelledError` is injected and the coroutine must unwind correctly:

```python
async def worker():
    try:
        await asyncio.sleep(10)
    finally:
        await cleanup()  # Always runs, even on cancel

task = asyncio.create_task(worker())
await asyncio.sleep(0.1)
task.cancel()  # Injects CancelledError
```

### Why It Matters

Cancellation is not a side issue. It's part of control flow for:

- Graceful shutdown
- Request timeouts
- Cleanup of resources (connections, locks, semaphores)
- Message acknowledgment/rejection
- Health check failures

### Antipattern: Swallowing Cancellation

```python
# ✗ Hides cancellation
async def bad():
    try:
        await some_operation()
    except Exception:
        pass  # Oops, also suppresses CancelledError!

# ✓ Preserve cancellation semantics
async def good():
    try:
        await some_operation()
    except SomeSpecificError:
        handle_it()
    # CancelledError propagates up
```

---

## Timeouts: A Design Policy

Timeouts are not optional. They're a budget:

```python
# ✓ This operation gets 2 seconds max
async with asyncio.timeout(2):
    await call_downstream()

# ✓ If it takes longer, CancelledError is raised
try:
    async with asyncio.timeout(2):
        await slow_operation()
except asyncio.TimeoutError:
    handle_timeout()
```

**Why it matters in production:**

- Hanging requests cause stuck tasks
- Resource pressure in connection pools
- Higher tail latency
- Request pileups
- Cascading failures

**Without timeouts, you get:**

```
downstream stalls → no timeout → tasks accumulate → pool exhaustion → system underresponsive
```

---

## Backpressure & Bounded Concurrency

### The Problem: Unlimited Fan-Out

```python
# ✗ Dangerous: can create thousands of tasks
tasks = [asyncio.create_task(process(item)) for item in huge_list]
await asyncio.gather(*tasks)

# Results:
# - Memory spike (thousands of task objects)
# - Connection pool exhaustion
# - Scheduler overhead
# - Downstream overload
```

### The Solution: Bounded Concurrency

```python
# ✓ Only 100 operations at a time
sem = asyncio.Semaphore(100)

async def bounded_process(item):
    async with sem:
        return await process(item)

tasks = [asyncio.create_task(bounded_process(item)) for item in huge_list]
await asyncio.gather(*tasks)
```

### Better Pattern: Queue + Workers

```python
async def worker(queue: asyncio.Queue):
    while True:
        item = await queue.get()
        try:
            await process(item)
        finally:
            queue.task_done()

async def main(items):
    queue = asyncio.Queue(maxsize=1000)  # Backpressure built-in

    # Start 100 workers
    workers = [asyncio.create_task(worker(queue)) for _ in range(100)]

    # Add work
    for item in items:
        await queue.put(item)  # Blocks if queue full (backpressure)

    await queue.join()  # Wait for all processed

    # Cleanup
    for w in workers:
        w.cancel()
```

**Key benefit:** Natural backpressure = flow control without explicit logic.

---

## Completion Models: gather() vs wait() vs as_completed()

### `asyncio.gather()`

Wait for results and collect them together:

```python
results = await asyncio.gather(a(), b(), c())
# By default, one failure fails everything
# Set return_exceptions=True to collect failures
results = await asyncio.gather(a(), b(), c(), return_exceptions=True)
```

### `asyncio.wait()`

Lower-level control over completion modes:

```python
# Wait for first completion
done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

# Wait for all
done, pending = await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED)

# Wait for first exception
done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
```

### `asyncio.as_completed()`

Process results as soon as ready (streaming behavior):

```python
# Useful for variable-latency tasks
for coro in asyncio.as_completed(coroutines):
    result = await coro  # Process as soon as ready
```

**Choice guide:**

- `gather()`: collect all results together
- `wait()`: fine-grained control over completion modes
- `as_completed()`: streaming results as ready

---

## Async Context Managers & Iteration

### Async Context Managers (`async with`)

Needed when entering/exiting context requires awaiting:

```python
# ✓ Opens/closes connection asynchronously
async with aiohttp.ClientSession() as session:
    response = await session.get(url)

# ✓ Acquiring/releasing async lock
async with async_lock:
    # Protected section
    pass

# ✓ Starting/stopping subscription
async with websocket:
    async for message in websocket:
        handle(message)
```

### Async Iterators (`async for`)

Needed when producer is asynchronous:

```python
# ✓ Streaming socket data
async for chunk in async_reader:
    process(chunk)

# ✓ Queue consumer
async for item in queue:
    handle(item)

# ✓ Paginated database results
async for record in db.stream_results():
    handle(record)
```

---

## Race Conditions & Deadlocks Haven't Disappeared

Async changes concurrency shape, not concurrency problems.

### Still Possible: Shared Mutable State Bugs

```python
# ✗ Race condition
counter = 0

async def increment():
    global counter
    temp = counter
    await asyncio.sleep(0.01)  # Yield here!
    counter = temp + 1

tasks = [asyncio.create_task(increment()) for _ in range(10)]
await asyncio.gather(*tasks)
print(counter)  # Not 10! Race condition!

# ✓ Fix: use Lock
lock = asyncio.Lock()

async def increment():
    global counter
    async with lock:
        temp = counter
        counter = temp + 1
```

### Classic Dangerous Pattern: Lock Across Await

```python
# ✗ Holding lock across I/O
async with lock:
    await external_api_call()  # Lock held while waiting!

# Problems:
# - Increased contention
# - Harder cancellation
# - Often serializes more than intended

# ✓ Better: minimize critical section
await external_api_call()
async with lock:
    update_local_state()
```

---

## Choosing the Right Tool

### When to Use Async

✓ Your workload is **I/O-bound** with **many concurrent operations:**

- HTTP requests
- Database queries
- Redis/cache operations
- Message queues
- Socket reading/writing

```python
@app.get("/orders/{user_id}")
async def get_orders(user_id: int, db: AsyncSession) -> list:
    # Multiple awaits, other requests can run meanwhile
    orders = await db.execute(select(Order).where(Order.user_id == user_id))
    return orders.scalars().all()
```

### When to Use Threads

✓ Your work is **blocking but synchronous:**

- Old SDK that doesn't support async
- Small blocking operations you want to offload
- I/O to synchronous libraries

```python
# Offload blocking call to thread pool
result = await asyncio.to_thread(blocking_sdk_call, arg1, arg2)
```

### When to Use Processes

✓ Your workload is **CPU-bound:**

- Pure Python computation
- Image processing
- Data analysis
- ETL pipelines

```python
from multiprocessing import Pool

with Pool(processes=4) as pool:
    results = pool.map(cpu_intensive_task, items)
```

---

## When Async is NOT the Answer

### Anti-pattern: Async Facade Over Blocking Code

```python
# ✗ Still blocks! async doesn't help
async def fake_async():
    requests.get(url)  # Blocks the thread!
    time.sleep(1)      # Blocks the thread!

# ✓ Use proper async HTTP
async def real_async():
    async with aiohttp.ClientSession() as session:
        await session.get(url)
```

### Anti-pattern: CPU-Heavy Work in Event Loop

```python
# ✗ Freezes the loop
async def serialize_massive_json():
    json.dumps([huge_data_structure] * 10000)  # CPU-heavy, no await

# ✓ Offload to thread
async def serialize_massive_json():
    result = await asyncio.to_thread(
        json.dumps,
        [huge_data_structure] * 10000
    )
```

---

## Practical Production Patterns

### FastAPI Endpoint with Backpressure

```python
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

app = FastAPI()

# Semaphore for bounded concurrency
db_semaphore = asyncio.Semaphore(50)

@app.post("/process")
async def process_item(item_data: ItemCreate, db: AsyncSession) -> dict:
    # Bounded concurrency to prevent DB pool exhaustion
    async with db_semaphore:
        async with asyncio.timeout(5):  # Timeout budget
            item = await db.execute(
                insert(Item).values(**item_data.dict()).returning(Item)
            )
            await db.commit()
            return {"id": item.scalar_one().id, "status": "created"}
```

### Queue-Based Worker Pattern

```python
async def worker(queue: asyncio.Queue, worker_id: int):
    while True:
        try:
            task = await queue.get()
            async with asyncio.timeout(30):
                result = await process_task(task)
                logger.info(f"Worker {worker_id}: {result}")
        except asyncio.TimeoutError:
            logger.error(f"Worker {worker_id}: timeout")
        except Exception as e:
            logger.error(f"Worker {worker_id}: error {e}")
        finally:
            queue.task_done()

async def main():
    queue = asyncio.Queue(maxsize=100)

    # Start workers
    workers = [
        asyncio.create_task(worker(queue, i))
        for i in range(10)
    ]

    # Emit tasks
    for item in work_items:
        await queue.put(item)

    # Wait for completion
    await queue.join()

    # Cleanup
    for w in workers:
        w.cancel()
```

### Graceful Shutdown with Cancellation

```python
async def run_server():
    app = FastAPI()
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=8000))

    try:
        await server.serve()
    except asyncio.CancelledError:
        logger.info("Shutdown initiated")
        await server.shutdown()

async def main():
    server_task = asyncio.create_task(run_server())

    try:
        await server_task
    except KeyboardInterrupt:
        logger.info("Cancelling server")
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
```

---

## Common Misconceptions

### "Async makes everything faster"

**False.** Async doesn't speed up single operations. It improves utilization when there are many
operations that spend time waiting.

```python
# Single query: async might be slower (overhead)
# Many simultaneous queries: async much better
```

### "I should use async everywhere"

**False.** Threads and processes exist for good reasons:

- Blocking libraries don't become async because you `await` them
- Some work is inherently threaded (blocking I/O to sync SDK)
- CPU work belongs in processes or threads

### "The event loop is magic"

**False.** It's a loop doing specific, mechanical work:

```
while not stopped:
    run callbacks ready to go
    process timers
    poll OS: which I/O events ready?
    wake tasks waiting on those events
    repeat
```

### "Async bypasses the GIL"

**False.** Async doesn't help with CPU-bound work. The GIL still prevents parallel bytecode
execution in threads. Use processes for CPU parallelism.

---

## Code Review Checklist: Async Patterns

- [ ] All I/O operations use `async`/`await` (no sync calls in async code)
- [ ] No `time.sleep()` in async code — use `await asyncio.sleep()`
- [ ] No blocking SDK calls — use `asyncio.to_thread()` or find async alternative
- [ ] Timeouts set on all external I/O operations
- [ ] TaskGroup used instead of scattered `create_task()` calls
- [ ] Cancellation semantics preserved (no bare `except Exception`)
- [ ] Semaphores/queues used for bounded concurrency
- [ ] Backpressure considered (queue `maxsize` set appropriately)
- [ ] Connection pools sized appropriately for expected concurrency
- [ ] Lock critical sections minimized (don't hold locks across I/O)
- [ ] No CPU-heavy work in event loop (offload to thread if needed)
- [ ] FastAPI routes all `async` (never sync handlers)
- [ ] Error handling doesn't suppress `CancelledError`
- [ ] No task fan-out without bounds (semaphore or queue limit)
- [ ] Race conditions considered (shared mutable state protected)
- [ ] Deadlock patterns avoided (lock ordering, no nested locks)

---

## Interview-Style Mental Models

### "What is async in Python?"

> In Python, async is a model of cooperative multitasking where many mostly I/O-bound operations
> share a single execution thread through an event loop. Coroutines explicitly yield control at
> `await` points, and the loop uses that time to advance other ready tasks or resume those waiting
> on I/O readiness or timers. It is not CPU parallelism and does not bypass the GIL; it's a way to
> manage large amounts of waiting work efficiently.

### "When would you choose async, threads, or processes?"

> I choose `asyncio` when the workload is I/O-bound with many concurrent waits: HTTP, databases,
> queues, sockets. I use threads when work is blocking but synchronous, or to offload small blocking
> sections without freezing the loop. I use processes when the workload is CPU-bound and I need real
> parallelism. The choice follows the workload shape: waiting, blocking, or compute.

### "Why doesn't async make code parallel?"

> Because `await` only yields control cooperatively. It allows interleaving within a single thread,
> not parallel execution of Python bytecode. Only processes can bypass the GIL for true parallelism.

---

## See Also

- [Lambda & Functional Programming](lambda): Anonymous functions and functional tools
- [Error Handling & Logging](python.instructions.md#error-handling--logging): Structured logging in
  async code
- [Testing (pytest + pytest-asyncio)](python.instructions.md#testing-pytest--pytest-asyncio):
  Testing async code
