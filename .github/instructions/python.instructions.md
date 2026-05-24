---
name: python-standards
description:
    'Apply to: backend Python code (src/scenario_*/backend/, src/config/). Enforces Python 3.14
    typing, PEP 8, async patterns, Pydantic v2, testing conventions, and error handling for FastAPI
    services.'
applyTo: 'src/**/*.py, **/*.py'
---

# Python Code Standards

## Language & Typing

### Python Version & Type Hints

- **Minimum**: Python 3.14 with modern syntax.
- **Type hints**: Mandatory for all function signatures and complex variables.
- **Modern syntax**: Use PEP 585 (`list[str]`, `dict[str, int]`) and PEP 604 (`str | None`) instead
  of `List`, `Dict`, `Optional`.
- **Return types**: Always annotate return types explicitly.
- **Type checker**: Run `ty check src/` regularly. All code must pass type checking.

### Examples

```python
# ✓ Good
async def get_user(user_id: int, db: AsyncSession) -> User | None:
    """Fetch user by ID. Returns None if not found."""
    query = select(UserModel).where(UserModel.id == user_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()

# ✗ Bad
def get_user(user_id, db):  # Missing types
    query = select(UserModel).where(UserModel.id == user_id)
    return db.execute(query).scalar_one_or_none()
```

---

## Formatting & Linting

### Ruff Configuration

- **Line length**: 119 characters.
- **Quote style**: Double quotes (`"string"`).
- **Import style**: `from x import y` with double quotes.
- **Rules**: E (pycodestyle errors), W (warnings), F (pyflakes), I (isort), B (flake8-bugbear), UP
  (pyupgrade), SIM (simplify).
- **Run before commit**: `ruff check --fix && ruff format src/`.

### Naming Conventions

- **Functions/variables**: `snake_case`.
- **Classes**: `PascalCase`.
- **Constants**: `UPPERCASE_WITH_UNDERSCORES`.
- **Private members**: `_leading_underscore` (convention, not enforced).

### Imports

- Standard library first, then third-party, then local imports.
- Group imports using blank lines.
- For async imports, use `from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine`.

---

## Async/Await & Event Loop

### FastAPI Routes

- **All routes must be `async`**: Never use sync functions in FastAPI handlers.
- **Never block the event loop**: No `time.sleep()`, blocking I/O, or CPU-intensive work directly in
  handlers.
- **Async HTTP**: Use `httpx.AsyncClient` for external API calls.
- **Database queries**: Use `asyncpg` with SQLAlchemy 2.0 async patterns.
- **Offload heavy work**: Use background tasks or task queues for long-running operations.

### Good Pattern

```python
from fastapi import FastAPI
import httpx

app = FastAPI()

@app.get("/users/{user_id}")
async def get_user(user_id: int, db: AsyncSession) -> User:
    """Fetch user with async database query."""
    query = select(UserModel).where(UserModel.id == user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.post("/notify")
async def notify(user_id: int, db: AsyncSession) -> dict:
    """Send async notification without blocking."""
    async with httpx.AsyncClient() as client:
        response = await client.post("https://api.notification.com/send", json={"user_id": user_id})
    return {"status": "sent"}
```

### Bad Pattern

```python
@app.get("/users/{user_id}")
async def get_user(user_id: int):
    time.sleep(1)  # ✗ Blocks event loop
    return db.query(User).filter(User.id == user_id).first()  # ✗ Sync query in async context

@app.post("/notify")
async def notify(user_id: int):
    requests.post("https://...", json={"user_id": user_id})  # ✗ Blocking sync HTTP
```

---

## Python Memory Model & Object System

Understanding Python's memory model is critical for writing efficient, predictable code. Many subtle
bugs and performance issues stem from misunderstanding how Python manages objects, references, and
mutability.

### Fundamental Principle: Everything Is an Object

Python has one fundamental rule: **everything is an object**. When you write:

```python
x = 42
```

You're not creating a variable `x` that contains the integer 42. Instead:

1. Python creates an `int` object with value 42 on the **heap** (not the stack).
2. It creates a **name binding** `x` in the current namespace (local, global, etc.).
3. The name `x` **references** (points to) the object.
4. This is fundamentally different from C/C++, where a variable is a named block of memory holding a
   value.

**Consequence:** Multiple names can reference the same object:

```python
x = 42
y = x  # Both x and y reference the same int object
print(id(x) == id(y))  # True — same object in memory

a = [1, 2, 3]
b = a  # Both a and b reference the same list object
b.append(4)
print(a)  # [1, 2, 3, 4] — mutation via b affects a's view
```

### Object Identity vs Equality

Every Python object has three attributes:

```python
x = 42

# Value: What the object represents
print(x)  # 42

# Type: The object's class
print(type(x))  # <class 'int'>

# Identity: Memory address (CPython implementation detail)
print(id(x))  # Unique memory ID

# Size: Bytes allocated
print(x.__sizeof__())  # 28 bytes (on 64-bit)
```

**Critical distinction: `==` vs `is`**

```python
# == checks VALUE equality
a = [1, 2, 3]
b = [1, 2, 3]
print(a == b)  # True — same values

# is checks IDENTITY (same object)
print(a is b)  # False — different objects
print(id(a) == id(b))  # False

# Small integer caching: Python caches -5 to 256
x = 5
y = 5
print(x is y)  # True — same object (cached)

# But larger integers are not cached
x = 1000
y = 1000
print(x is y)  # False — different objects
```

**Rule: Use `==` for value comparison, `is` for identity checks (especially with `None`)**

```python
# ✓ Good
if value is None:
    pass

# ✗ Bad (can fail with custom __eq__ implementations)
if value == None:
    pass
```

### Python Memory Architecture: Three Layers

Python manages memory using a multi-layered system:

**Layer 1: System Memory (`malloc`/`free`)**

The operating system allocates and deallocates memory blocks. Direct use is inefficient for
thousands of small objects.

**Layer 2: PyMalloc (Python Memory Manager)**

PyMalloc is customized for objects up to 512 bytes:

- Allocates memory in bulk from the system.
- Divides into smaller chunks for fast object creation/destruction.
- Reduces overhead of system `malloc`/`free`.

**Layer 3: Object-Specific Allocators**

Each object type may use optimizations:

```python
# Small integers cached: -5 to 256 (pre-created at Python startup)
a = 100
b = 100
print(a is b)  # True

# String interning: identifiers and short strings are cached
s1 = "hello"
s2 = "hello"
print(s1 is s2)  # True

# Force interning with sys.intern()
s3 = sys.intern("hello world")
s4 = sys.intern("hello world")
print(s3 is s4)  # True

# List pre-allocation: lists over-allocate for faster append()
lst = []  # Allocates space for ~4 items
for i in range(100):  # Only reallocates ~10 times, not 100
    lst.append(i)
```

**Memory profiling:**

```python
import sys
import gc
from collections import defaultdict

def memory_snapshot():
    """Count objects by type."""
    counts = defaultdict(int)
    for obj in gc.get_objects():
        counts[type(obj).__name__] += 1
    return dict(counts)

initial = memory_snapshot()
data = [{"id": i, "value": i**2} for i in range(10_000)]
final = memory_snapshot()

# Show what changed
for obj_type in sorted(set(initial) | set(final)):
    initial_count = initial.get(obj_type, 0)
    final_count = final.get(obj_type, 0)
    if final_count > initial_count:
        print(f"{obj_type}: +{final_count - initial_count}")
```

### Mutable vs Immutable: The Critical Difference

**Immutable objects** (int, float, str, tuple, frozenset, bytes):

- Cannot be modified after creation.
- Operations create new objects.
- Safe to cache/share by identity.

```python
# Immutable: operations create new objects
s = "hello"
before_id = id(s)
s = s + " world"  # New string created
after_id = id(s)
print(before_id == after_id)  # False

number = 42
before_id = id(number)
number += 1  # New int object created
after_id = id(number)
print(before_id == after_id)  # False
```

**Mutable objects** (list, dict, set, custom classes):

- Can be modified after creation.
- In-place modifications keep the same object identity.
- Aliasing can cause unexpected changes.

```python
# Mutable: modifications keep same object
lst = [1, 2, 3]
before_id = id(lst)
lst.append(4)  # Modify in place
after_id = id(lst)
print(before_id == after_id)  # True — same list object

d = {"a": 1}
before_id = id(d)
d["b"] = 2  # Modify in place
after_id = id(d)
print(before_id == after_id)  # True — same dict object
```

### Argument Passing: By Object Reference

**Everything in Python is passed by object reference.** The implications depend on mutability.

**Passing immutable objects:**

```python
def increment_number(n: int) -> int:
    """Immutable: changes don't affect original."""
    print(f"Received ID: {id(n)}")
    n = n + 1  # Creates new int object
    print(f"After modification ID: {id(n)}")
    return n

original = 42
result = increment_number(original)
print(f"Original: {original}")  # 42 — unchanged
print(f"Result: {result}")      # 43 — new object
```

**Passing mutable objects:**

```python
def add_item(items: list[int]):
    """Mutable: in-place modifications affect original."""
    print(f"Received list ID: {id(items)}")
    items.append(999)  # Modifies the list in place
    print(f"After append ID: {id(items)}")
    items = [100, 200]  # Reassignment creates new reference
    print(f"After reassignment ID: {id(items)}")

original_list = [1, 2, 3]
add_item(original_list)
print(f"Original: {original_list}")  # [1, 2, 3, 999] — MODIFIED
```

**Key insight:** You can modify mutable objects through a function, but reassigning the parameter
only affects the local variable.

### Common Memory Pitfalls

#### 1. Mutable Default Arguments

**Antipattern:**

```python
def append_to(item: int, container: list[int] = []):  # ✗ Shared, mutable default
    container.append(item)
    return container

result1 = append_to(1)  # [1]
result2 = append_to(2)  # [1, 2] — DEFAULT LIST IS SHARED!
print(result1 is result2)  # True — same object
```

**Why it hurts:** The default list is created **once** at function definition time, not per call.
All calls share it.

**Better:**

```python
def append_to(item: int, container: list[int] | None = None) -> list[int]:
    if container is None:
        container = []  # ✓ Fresh list per call
    container.append(item)
    return container
```

#### 2. Multiple Assignment with Mutable Objects

**Antipattern:**

```python
# All refer to the SAME list
a = b = c = [1, 2, 3]
a.append(4)
print(b)  # [1, 2, 3, 4] — all affected
print(c)  # [1, 2, 3, 4] — all affected
```

**Better:**

```python
# Create independent lists
a = [1, 2, 3]
b = a.copy()  # ✓ Shallow copy for simple lists
c = list(a)   # ✓ Alternative shallow copy
# For nested lists, use copy.deepcopy()
```

#### 3. Shallow vs Deep Copy

**Antipattern (shallow copy):**

```python
import copy

original = [[1, 2], [3, 4]]
shallow = original.copy()  # Only copies outer list

shallow[0].append(999)  # Modifies nested list
print(original)  # [[1, 2, 999], [3, 4]] — ✗ Original affected!
```

**Better (deep copy when needed):**

```python
import copy

original = [[1, 2], [3, 4]]
deep = copy.deepcopy(original)  # ✓ Recursively copies all levels

deep[0].append(999)
print(original)  # [[1, 2], [3, 4]] — ✓ Original unchanged
```

#### 4. Mutation During Iteration

**Antipattern:**

```python
items = [1, 2, 3, 4, 5]
for item in items:
    if item % 2 == 0:
        items.remove(item)  # ✗ Modifying list while iterating
print(items)  # [1, 3, 5] — but skipped items due to iterator confusion
```

**Better:**

```python
# Option 1: List comprehension (preferred)
items = [1, 2, 3, 4, 5]
items = [item for item in items if item % 2 != 0]  # ✓ Clean
print(items)  # [1, 3, 5]

# Option 2: Iterate over copy
items = [1, 2, 3, 4, 5]
for item in items[:]:  # ✓ Iterate over shallow copy
    if item % 2 == 0:
        items.remove(item)
print(items)  # [1, 3, 5]

# Option 3: Filter before iteration
items = [1, 2, 3, 4, 5]
even_items = [item for item in items if item % 2 == 0]
for item in even_items:
    items.remove(item)  # ✓ Remove only what we found
print(items)  # [1, 3, 5]
```

### Memory Optimization Techniques

#### 1. Using `__slots__` for Memory Efficiency

Regular classes store an instance dictionary (`__dict__`), which is overhead:

```python
# Regular class: includes __dict__ overhead
class RegularPerson:
    def __init__(self, name: str, age: int):
        self.name = name
        self.age = age

# Slotted class: no __dict__, fixed attributes only
class SlottedPerson:
    __slots__ = ['name', 'age']

    def __init__(self, name: str, age: int):
        self.name = name
        self.age = age

# Memory comparison
import sys

regular = RegularPerson("Alice", 30)
slotted = SlottedPerson("Alice", 30)

regular_size = sys.getsizeof(regular) + sys.getsizeof(regular.__dict__)
slotted_size = sys.getsizeof(slotted)

print(f"Regular: {regular_size} bytes")  # ~296 bytes
print(f"Slotted: {slotted_size} bytes")  # ~56 bytes

# Trade-off: slotted classes can't add new attributes
try:
    regular.email = "alice@example.com"  # ✓ Works
    slotted.email = "alice@example.com"  # ✗ AttributeError
except AttributeError:
    pass
```

**Use `__slots__`** when:

- You create many instances of a class (memory matters).
- Attributes are fixed (never added dynamically).
- You're in performance-critical code.

**Don't use `__slots__`** when:

- You need dynamic attribute assignment.
- The class is rarely instantiated (overhead doesn't matter).
- You need to inherit from multiple classes (incompatible).

#### 2. Using `array` and `bytes` for Numeric Data

For dense numeric data, specialized types are more efficient:

```python
import sys
import array

# Regular list: each integer is an 8-byte pointer + object overhead
regular_list = [1, 2, 3, 4, 5] * 1000
print(f"List size: {sys.getsizeof(regular_list)} bytes")  # ~40,000+ bytes

# array: stores compact integers (8 bytes per int)
int_array = array.array('i', [1, 2, 3, 4, 5] * 1000)
print(f"Array size: {sys.getsizeof(int_array)} bytes")  # ~4,000 bytes

# bytes: compact, immutable bytes
byte_data = bytes([1, 2, 3, 4, 5] * 1000)
print(f"Bytes size: {sys.getsizeof(byte_data)} bytes")  # ~5,000 bytes

# Performance trade-off: array/bytes are faster for iteration and smaller memory
```

#### 3. Generators for Memory Efficiency

Use generators instead of lists for large datasets:

```python
import sys

# List approach: loads all 1M items into memory
def list_squares(n: int) -> list[int]:
    return [x**2 for x in range(n)]

# Generator approach: yields items one-by-one
def generator_squares(n: int) -> int:
    for x in range(n):
        yield x**2

# Memory comparison
n = 1_000_000
list_result = list_squares(n)
print(f"List: {sys.getsizeof(list_result) / 1024:.1f} KB")  # ~8,000 KB

gen_result = generator_squares(n)
print(f"Generator: {sys.getsizeof(gen_result)} bytes")  # ~128 bytes
```

### Memory Debugging & Profiling

**Using the `gc` module:**

```python
import gc

# Get memory stats
stats = gc.get_stats()
print(f"Garbage collector stats: {stats}")

# Force garbage collection (rarely needed in production)
gc.collect()

# Check for garbage (uncollectable cycles)
gc.set_debug(gc.DEBUG_SAVEALL)
gc.collect()
garbage = gc.garbage
print(f"Uncollectable objects: {len(garbage)}")
gc.set_debug(0)
```

**Using `psutil` for process memory:**

```python
# pip install psutil
import psutil
import os

process = psutil.Process(os.getpid())

# Memory before
print(f"Memory at start: {process.memory_info().rss / 1024 / 1024:.2f} MB")

# Create data
data = [{"id": i, "value": i**2} for i in range(100_000)]
print(f"After allocation: {process.memory_info().rss / 1024 / 1024:.2f} MB")

# Cleanup
del data
print(f"After deletion: {process.memory_info().rss / 1024 / 1024:.2f} MB")
```

---

## Pydantic v2 Validation

### Schemas & Models

- Use `BaseModel` for request/response schemas.
- Use `BaseSettings` (from `pydantic-settings`) for configuration.
- All schemas must have type hints and field descriptions where relevant.
- Use `Field()` for additional validation, examples, or descriptions (useful for OpenAPI docs).

### Example

```python
from pydantic import BaseModel, Field

class UserCreate(BaseModel):
    """Request schema for creating a user."""
    name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., pattern=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    age: int = Field(None, ge=0, le=150)

class UserResponse(BaseModel):
    """Response schema for user data."""
    id: int
    name: str
    email: str
    created_at: datetime

    class Config:
        from_attributes = True  # For SQLAlchemy ORM models
```

### Configuration

```python
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    """Application configuration from environment variables."""
    database_url: str
    redis_url: str
    api_key: str
    debug: bool = False

    class Config:
        env_file = ".env"

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

---

## Database & ORM (SQLAlchemy 2.0 + asyncpg)

### Async Session Management

- Always use `AsyncSession` context managers for clean connection handling.
- Use dependency injection in FastAPI to pass sessions.

### Example

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

DATABASE_URL = "postgresql+asyncpg://user:password@localhost/dbname"

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency: get database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# Usage in routes
@app.get("/users")
async def list_users(db: AsyncSession = Depends(get_db)) -> list[UserResponse]:
    """Fetch all users."""
    query = select(UserModel).order_by(UserModel.created_at.desc())
    result = await db.execute(query)
    users = result.scalars().all()
    return [UserResponse.model_validate(u) for u in users]
```

### ORM Models

- Define models in `models.py` using `declarative_base()`.
- Use `__tablename__` explicitly.
- Always provide meaningful column names and types.
- Add foreign keys, indexes, and constraints as needed.

```python
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime, timezone

Base = declarative_base()

class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    posts = relationship("PostModel", back_populates="author")
```

---

## Error Handling & Logging

### HTTP Exceptions

- Use `HTTPException` from FastAPI for client errors (4xx).
- Always provide meaningful `status_code` and `detail` messages.
- Log errors with structured JSON logging.

### Example

```python
from fastapi import HTTPException
from python_json_logger import jsonlogger
import logging

# Setup structured logging
logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter()
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

@app.get("/users/{user_id}")
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)) -> UserResponse:
    """Fetch user or raise 404."""
    try:
        query = select(UserModel).where(UserModel.id == user_id)
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        if not user:
            logger.warning(f"User not found", extra={"user_id": user_id, "action": "get_user"})
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")
        return UserResponse.model_validate(user)
    except SQLAlchemyError as e:
        logger.error(f"Database error", extra={"error": str(e), "user_id": user_id})
        raise HTTPException(status_code=500, detail="Internal server error")
```

### Structured Logging

- Always log in JSON format (via `python-json-logger`).
- Include request IDs for tracing across services.
- Log at appropriate levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.
- Include relevant context (e.g., user_id, request_path, elapsed_time).

---

## Lambda & Functional Programming

### Lambda Functions: Uses and Limits

**What is a lambda?** An anonymous function with a single expression (no `return`, no statements).

```python
# Lambda syntax
add = lambda x, y: x + y
print(add(3, 5))  # 8

# Equivalent to
def add(x, y):
    return x + y
```

**Key limitation:** Lambda can only contain a single **expression**, never statements (`for`,
`while`, `try/except`, multi-line `if/elif/else`):

```python
# ✗ Syntax error: statements not allowed
bad = lambda x: (
    for i in range(x):  # ← SyntaxError: can't use statements
        print(i)
)

# ✓ Ternary expressions work (they're expressions, not statements)
risk_label = lambda score: "high" if score >= 80 else ("medium" if score >= 50 else "low")
```

### Lambda Best Practices

**1. Use lambda with `sorted()`, `min()`, `max()`** (their natural habitat):

```python
# ✓ Good: lambda for key functions
people = [
    {"name": "Alice", "age": 30},
    {"name": "Bob", "age": 25},
]
sorted_people = sorted(people, key=lambda p: p["age"])

# Better: use operator.itemgetter (faster + clearer)
from operator import itemgetter
sorted_people = sorted(people, key=itemgetter("age"))
```

**2. Prefer list comprehensions over `map()`/`filter()` with lambdas:**

```python
# ✗ Less readable
prices = [19.99, 5.50, 3.25]
with_tax = list(map(lambda p: round(p * 1.2, 2), prices))

# ✓ More readable
with_tax = [round(p * 1.2, 2) for p in prices]

# ✗ Less readable
positives = list(filter(lambda x: x > 0, [-2, 0, 7, 10]))

# ✓ More readable
positives = [x for x in [-2, 0, 7, 10] if x > 0]
```

**3. Avoid reusing the same lambda** (a sign it should be a named function):

```python
# ✗ Bad: duplicated lambda across codebase
users = [u for u in all_users if (lambda x: x.age >= 18)(u)]
admins = [u for u in users if (lambda x: x.role == "admin")(u)]

# ✓ Good: named functions are reusable
def is_adult(user):
    return user.age >= 18

def is_admin(user):
    return user.role == "admin"

users = [u for u in all_users if is_adult(u)]
admins = [u for u in users if is_admin(u)]
```

**4. Watch for the "late binding" trap in loops:**

```python
# ✗ Gotcha: all lambdas capture the same variable
multipliers = []
for factor in [2, 3, 4]:
    multipliers.append(lambda x: x * factor)

print([m(10) for m in multipliers])  # [40, 40, 40] ← All use final factor=4!

# ✓ Fix 1: freeze with default argument
multipliers = [lambda x, f=factor: x * f for factor in [2, 3, 4]]
print([m(10) for m in multipliers])  # [20, 30, 40]

# ✓ Fix 2: use functools.partial (clearer)
from functools import partial
from operator import mul
multipliers = [partial(mul, factor) for factor in [2, 3, 4]]
print([m(10) for m in multipliers])  # [20, 30, 40]
```

### When to Use Lambda

| Scenario                                    | Use Lambda? | Example                                 |
| ------------------------------------------- | ----------- | --------------------------------------- |
| **Sorting/min/max with custom key**         | ✓ Yes       | `sorted(items, key=lambda x: x["age"])` |
| **Quick callback in higher-order function** | ✓ Yes       | `filter(lambda x: x > 0, numbers)`      |
| **Duplicated logic (reused twice+)**        | ✗ No        | Extract to named function               |
| **Complex expression needing parentheses**  | ✗ No        | Needs more than one line?Use `def`      |
| **Code that needs debugging/docstring**     | ✗ No        | Lambdas can't have breakpoints          |

**Golden rule:** If lambda doesn't fit comfortably on one line, or if you'd want to debug it, use
`def`.

### Closures and Function Factories

Lambda can capture variables from outer scope:

```python
def make_multiplier(n):
    """Return a function that multiplies by n."""
    return lambda x: x * n

double = make_multiplier(2)
triple = make_multiplier(3)

print(double(5))  # 10
print(triple(5))  # 15
```

**Use case in FastAPI:** Creating reusable middleware or dependencies:

```python
def create_rate_limiter(max_calls: int):
    """Return a rate limiter function."""
    call_count = 0

    def is_allowed():
        nonlocal call_count
        call_count += 1
        return call_count <= max_calls

    return is_allowed  # Returns a closure

# Instead of lambda, use def for complexity
```

### Built-in Functional Tools

**`map()`**: Transform items lazily.

```python
# Good: already using a named function
lines = ["  hello  ", "  world  "]
stripped = map(str.strip, lines)  # Lazy evaluation

# With lambda is verbose; comprehension is clearer
stripped = [line.strip() for line in lines]
```

**`filter()`**: Keep matching items.

```python
# Comprehension often clearer than filter + lambda
values = [1, 2, 3, 4, 5]

# ✗ filter with lambda
evens = list(filter(lambda x: x % 2 == 0, values))

# ✓ comprehension
evens = [x for x in values if x % 2 == 0]
```

**`functools.reduce()`**: Accumulate/fold values.

```python
from functools import reduce
from operator import add

numbers = [1, 2, 3, 4, 5]

# ✗ reduce + lambda is dense
total = reduce(lambda acc, x: acc + x, numbers)

# ✓ sum() is clearer for this case
total = sum(numbers)

# ✓ Use reduce only when no built-in applies
product = reduce(lambda acc, x: acc * x, numbers)  # no built-in product
```

### Functional Patterns in FastAPI

**Composing middleware via lambdas:**

```python
# Instead of lambdas, use explicit middleware classes
# But for simple transformations, lambdas can be useful

# ✓ Good: sorting/filtering in route handlers
@app.get("/orders")
async def list_orders(
    sort_by: str = "created_at",
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
) -> list[OrderResponse]:
    """List orders sorted by requested key."""
    query = select(OrderModel)

    # Use sort key to select ordering
    sort_keys = {
        "created_at": OrderModel.created_at,
        "amount": OrderModel.amount,
    }
    sort_column = sort_keys.get(sort_by, OrderModel.created_at)

    query = query.order_by(sort_column).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()
```

**Avoid lambdas in complex business logic:**

```python
# ✗ Bad: lambda in complex calculation
def calculate_discount(order):
    discount_fn = lambda amount: amount * 0.1 if amount > 100 else 0
    return discount_fn(order["total"])

# ✓ Good: explicit function
def calculate_discount(order: dict) -> float:
    """Calculate 10% discount for orders over $100."""
    if order["total"] > 100:
        return order["total"] * 0.1
    return 0
```

### Lambda Code of Conduct

1. **One-screen rule**: Fits on one line? Use lambda. Needs wrapping? Use `def`.
2. **Reader-first rule**: If someone has to decode it, you lost. Use `def`.
3. **Comprehension-first rule**: Before using `map`/`filter` with lambda, ask: would a comprehension
   be clearer? (Usually yes.)
4. **Where lambdas shine**: `key=` functions in `sorted`/`min`/`max`, short callbacks in UI code,
   function factories.
5. **Debugging rule**: Lambdas can't have docstrings or breakpoints. If you'd debug it, name it.

---

## Testing (pytest + pytest-asyncio)

### Test Structure

- Place tests in `tests/` directory alongside `app/`.
- Use `conftest.py` for shared fixtures (database, mock services, etc.).
- Name test functions/files with `test_` prefix.
- Organize tests: unit tests, integration tests, end-to-end tests.

### Async Tests

- Decorate with `@pytest.mark.asyncio`.
- Use async fixtures with `@pytest_asyncio.fixture`.

### Example

```python
import pytest
from pytest_asyncio import fixture
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models import Base, UserModel
from app.api import app

@fixture
async def db_session():
    """Fixture: in-memory test database."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with AsyncSessionLocal() as session:
        yield session

@pytest.mark.asyncio
async def test_get_user_not_found(db_session: AsyncSession):
    """Test: fetching non-existent user returns 404."""
    client = TestClient(app)
    response = client.get("/users/999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

@pytest.mark.asyncio
async def test_create_user(db_session: AsyncSession):
    """Test: creating a user stores data correctly."""
    client = TestClient(app)
    payload = {"name": "Alice", "email": "alice@example.com"}
    response = client.post("/users", json=payload)
    assert response.status_code == 201
    assert response.json()["name"] == "Alice"

    # Verify in database
    query = select(UserModel).where(UserModel.email == "alice@example.com")
    result = await db_session.execute(query)
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.name == "Alice"
```

### Coverage

- Aim for >80% coverage on critical paths (services, API handlers).
- Test error cases, edge cases, and failure scenarios.
- Use `pytest --cov=src` to measure coverage.

---

## Resilience Patterns

### Retry Logic with Backoff

When calling external services, always implement retry logic with exponential backoff:

```python
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def call_external_api(user_id: int) -> dict:
    """Call external API with retry logic."""
    async with httpx.AsyncClient() as client:
        response = await client.post("https://api.example.com/process", json={"user_id": user_id})
        response.raise_for_status()
        return response.json()
```

### Circuit Breaker Pattern

For services prone to cascading failures, use a circuit breaker:

```python
from pybreaker import CircuitBreaker

breaker = CircuitBreaker(fail_max=5, reset_timeout=60)

async def get_from_cache(key: str) -> str | None:
    """Get from cache with circuit breaker protection."""
    try:
        result = await breaker.call(redis_client.get, key)
        return result
    except Exception as e:
        logger.error(f"Circuit breaker open or cache error: {e}")
        return None
```

---

## Design Patterns

> See [design-patterns.instructions.md](design-patterns.instructions.md) for the full guide:
> pain-first decision tree, 13 patterns (creational, structural, behavioral), pattern selection
> guide, and 15 antipatterns to avoid.

---

## Docstrings & Comments

### Google-Style Docstrings

- Use for all functions and classes, especially complex ones.
- Include: Args, Returns, Raises, Examples.

### Example

```python
async def process_payment(user_id: int, amount: float, db: AsyncSession) -> Transaction:
    """Process a payment transaction for a user.

    This function creates a new transaction record, deducts from the user's balance,
    and notifies the payment service. It uses retry logic to handle transient failures.

    Args:
        user_id: The ID of the user making the payment.
        amount: The payment amount in cents.
        db: Database session for ORM queries.

    Returns:
        Transaction: The created transaction record with status and timestamp.

    Raises:
        HTTPException: If user not found (404) or insufficient balance (400).
        PaymentServiceError: If the payment service is unreachable after retries.

    Example:
        >>> transaction = await process_payment(user_id=123, amount=5000, db=session)
        >>> print(transaction.id)
        456
    """
    # Fetch user and validate balance
    user = await get_user(user_id, db)
    if user.balance < amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    # Create transaction (eventually consistent with payment service)
    transaction = TransactionModel(user_id=user_id, amount=amount, status="pending")
    db.add(transaction)
    await db.commit()

    # Notify payment service (with retry)
    await call_payment_service(transaction.id, amount)
    return transaction
```

### Inline Comments

- Explain the "why," not the "what" (code should be self-documenting).
- Use for non-obvious logic or trade-off justifications.

```python
# Good comment: explains why
# We retry with exponential backoff because the payment service may be temporarily overloaded
# during peak hours. A linear backoff would waste resources; exponential gives the service time to recover.
await call_with_backoff(payment_service_url, transaction_data)

# Bad comment: just describes the code
# Loop through users and send email
for user in users:
    send_email(user.email)
```

---

## Code Organization

### File Structure

```
backend/app/
  ├── main.py              # FastAPI initialization, app setup, middleware
  ├── config.py            # Settings (Pydantic BaseSettings)
  ├── api.py               # Route handlers (v1 of API endpoints)
  ├── models.py            # SQLAlchemy ORM models
  ├── schemas.py           # Pydantic request/response models
  ├── database.py          # Session management, connection pooling
  ├── middleware.py        # Logging, error handling, CORS setup
  ├── services/            # Business logic (decoupled from routes)
  │   ├── user_service.py  # User-related operations
  │   └── payment_service.py
  ├── utils/               # Utilities (helpers, constants)
  │   ├── logger.py        # Logging setup
  │   ├── decorators.py    # Custom decorators (e.g., @require_auth)
  │   └── constants.py
  └── exceptions.py        # Custom exception classes

tests/
  ├── conftest.py          # Pytest fixtures
  ├── unit/
  │   ├── test_services.py
  │   └── test_utils.py
  ├── integration/
  │   ├── test_api_users.py
  │   └── test_api_payments.py
  └── fixtures/
      └── sample_data.py   # Test data fixtures
```

### Single Responsibility

- Each module should have a clear, single purpose.
- Move business logic to `services/` instead of leaking into routes.
- Keep models, schemas, and database concerns separate.

---

## Data Structures & Performance

Understanding Python's built-in data structures and their performance characteristics is critical
for writing efficient code, especially in high-load systems.

### Lists: Dynamic Arrays (Not Linked Lists)

**What lists actually are:**

- Contiguous memory block storing pointers to objects (not the objects themselves).
- Each pointer is 8 bytes on 64-bit builds.
- Random access via index is **O(1)** constant time (`base_address + i * pointer_size`).

**Performance characteristics:**

| Operation                      | Complexity         | Notes                                                               |
| ------------------------------ | ------------------ | ------------------------------------------------------------------- |
| `list[i]` (access by index)    | O(1)               | Constant time, very fast                                            |
| `list.append(x)`               | **Amortized O(1)** | CPython over-allocates; most appends are free; reallocation is rare |
| `list.pop()` (from end)        | O(1)               | Fast, no shifting needed                                            |
| `list.insert(0, x)`            | O(n)               | All pointers shift; expensive for large lists                       |
| `list.pop(0)` or `del list[0]` | O(n)               | All pointers shift left                                             |
| `list[a:b]` (slicing)          | O(k)               | k = slice length; creates new list with copied pointers             |
| `x in list` (linear search)    | O(n)               | Must check each element                                             |

**Key insight: `.append()` amortization**

CPython allocates extra capacity when growing. Growth factor is roughly 1.125× (varies by
implementation):

```python
# Under the hood (simplified):
# Append 1: allocate ~1 slot
# Append 2-5: reuse pre-allocated slots (free)
# Append 6: capacity exceeded, allocate ~9 slots
# Append 7-13: reuse pre-allocated slots (free)
# ... pattern continues

# Real CPython output:
# [init] items=0, bytes=56
# [grow] items=1, bytes=88, x1.57
# [grow] items=5, bytes=120, x1.36
# [grow] items=9, bytes=184, x1.53
```

**When lists are inefficient:**

- Heavy churn at the front (`insert(0, x)`, `pop(0)`) — use `collections.deque` instead.
- Frequent search (`x in list`) on large lists — use `set` for O(1) lookup.
- Frequent mutations in the middle — consider `deque` or custom data structures.

**Practical tips:**

```python
# ✓ Good: Use list comprehension (allows CPython to pre-size)
items = [process(x) for x in data]

# ✗ Bad: Repeated append in loop (forces multiple reallocations)
items = []
for x in data:
    items.append(process(x))

# ✓ Good: Frequent add/remove at both ends → use deque
from collections import deque
queue = deque([1, 2, 3])
queue.appendleft(0)  # O(1)
queue.popleft()      # O(1)

# ✗ Bad: Using list for frequent front operations
my_list = [1, 2, 3]
my_list.insert(0, 0)  # O(n) — all pointers shift
my_list.pop(0)        # O(n) — all pointers shift
```

### Dicts: Hash Tables with Open Addressing

**What dicts actually are:**

- Hash table with slots/buckets in a contiguous array (size is always a power of 2).
- Uses open addressing (not linked lists) for collision handling.
- Insertion order guaranteed as of Python 3.7+ (CPython 3.6+ already had it).

**Performance characteristics:**

| Operation                    | Complexity       | Notes                                                 |
| ---------------------------- | ---------------- | ----------------------------------------------------- |
| `dict[key]` (lookup)         | **Average O(1)** | Hash + index arithmetic + probe steps                 |
| `dict[key] = value` (insert) | **Average O(1)** | Same as lookup; rare reallocation                     |
| `del dict[key]` (delete)     | **Average O(1)** | Mark slot as deleted; no reallocation                 |
| `key in dict` (membership)   | **Average O(1)** | Hash lookup, not linear search                        |
| Resizes around 2/3 full      | —                | Rebuilds table with larger array to reduce collisions |

**Why O(1):**

1. Compute `hash(key)` — constant time.
2. Map to array index via masking (fast bitwise op).
3. Jump to slot and verify key.
4. Typical collision resolution takes only a few probes (load factor keeps it low).

**Why keys must be immutable (hashable):**

```python
# ✗ Bad: Mutable key changes hash, breaks table
try:
    d = {[1, 2]: "value"}  # TypeError: unhashable type: 'list'
except TypeError:
    pass

# ✗ Even tuples with mutable items are unhashable
try:
    d = {(1, [2]): "value"}  # TypeError: unhashable type: 'list'
except TypeError:
    pass

# ✓ Good: Immutable keys only
d = {(1, 2): "tuple key"}  # tuple is hashable
d = {frozenset([1, 2]): "frozenset key"}  # frozenset is hashable
d = {"name": "value"}  # strings are hashable
d = {42: "int key"}  # ints are hashable
```

If a key were mutable and you modified it after insertion, its hash would change, and the table
lookup would fail (or find the wrong slot).

**Internal structure (simplified):**

```python
# CPython's dict internals (conceptual):
# 1. Hash each key: hash('name') → 12345
# 2. Compute index: index = 12345 & (size - 1)  # size is power of 2
# 3. Store triple at slot: (hash, key, value)
# 4. On collision: probe for next open slot
# 5. On lookup: recompute hash, jump to index, probe if needed, verify hash+key

# Memory footprint grows as:
# [init] items=0, bytes=64
# [grow] items=6, bytes=240
# [grow] items=11, bytes=368
# [grow] items=22, bytes=640
```

**Insertion order preservation (Python 3.7+):**

```python
d = {}
d['z'] = 1
d['a'] = 2
d['m'] = 3

# Before 3.7: iteration order was arbitrary (hash order)
# Python 3.7+: guaranteed insertion order
for key in d:
    print(key)  # z, a, m (in insertion order)
```

**When dicts are efficient:**

- Fast lookups on large datasets (O(1) vs O(n) for linear search).
- Dynamic key-value associations where insertion order matters.
- Deduplication of items (convert list to dict keys, then back).

**Common performance pitfalls:**

```python
# ✗ Bad: Using list for frequent lookups
config_list = [("key1", "value1"), ("key2", "value2")]
if ("key1", "value1") in config_list:  # O(n) search
    ...

# ✓ Good: Use dict for fast lookups
config_dict = {"key1": "value1", "key2": "value2"}
if "key1" in config_dict:  # O(1) lookup
    ...

# ✗ Bad: Iterating over dict and looking up in list repeatedly
user_ids = [1, 2, 3, 4, 5]
for user_key in large_dict:
    if user_key in user_ids:  # O(n) for each key
        process(user_key)

# ✓ Good: Convert to set for repeated membership checks
user_ids_set = set([1, 2, 3, 4, 5])  # O(1) conversion
for user_key in large_dict:
    if user_key in user_ids_set:  # O(1) lookup
        process(user_key)
```

### Sets: Hash-Based Collections

**What sets are:**

- Hash table (like dict) storing only keys, no values.
- Unordered, unique elements.
- Immutable elements only (same hashability rules as dict keys).

**Performance:**

| Operation                    | Complexity                   |
| ---------------------------- | ---------------------------- |
| `x in set`                   | O(1) average                 |
| `set.add(x)`                 | O(1) average                 |
| `set.remove(x)`              | O(1) average                 |
| `set1 & set2` (intersection) | O(min(len(set1), len(set2))) |
| `set1 \| set2` (union)       | O(len(set1) + len(set2))     |

**When to use sets:**

```python
# ✓ Good: Deduplication
tags = ["python", "async", "python", "fastapi", "async"]
unique_tags = set(tags)  # O(n) insertion → O(1) average per item

# ✓ Good: Membership testing (faster than 'x in list' for large collections)
allowed = {"admin", "moderator", "user"}
if role in allowed:  # O(1) not O(n)
    grant_access()

# ✓ Good: Set operations (intersection, union, difference)
admins = {"alice", "bob"}
moderators = {"bob", "charlie"}
super_users = admins | moderators  # union: O(n)
overlap = admins & moderators      # intersection: O(n)
admin_only = admins - moderators   # difference: O(n)
```

### Guidance: Choose the Right Structure

**Use `list` when:**

- You need ordered data with fast index access.
- You iterate sequentially (not searching).
- You rarely insert/delete from the front or middle.

**Use `dict` when:**

- You need O(1) key-value lookups.
- You need associative mapping (key → value).
- Insertion order matters (Python 3.7+).

**Use `set` when:**

- You need O(1) membership testing.
- You need to deduplicate items.
- You perform set operations (union, intersection, difference).

**Use `deque` when:**

- You frequently add/remove from both ends.
- You need O(1) appendleft/popleft.
- Standard list operations at front would be O(n).

**Use `tuple` when:**

- You need immutable sequences (dict keys, set members).
- You want a lightweight, memory-efficient container.
- You're unpacking: `x, y, z = my_tuple`.

---

## Generators & Iterators

Generators are a powerful Python feature for creating memory-efficient iterators. They use the
`yield` keyword to pause and resume execution, maintaining state between iterations. This makes them
ideal for processing large datasets, infinite sequences, and building coroutines.

### Generator Basics: `yield` and Function-Based Generators

**What makes a generator:**

- A function containing the `yield` keyword becomes a generator function.
- Calling it returns a generator object (an iterator), not executing the function body.
- `yield` pauses the function, saves local state, and resumes at that point on the next iteration.

```python
def simple_generator() -> None:
    """A simple generator that yields values."""
    print("START")  # Doesn't execute until iteration begins
    yield 1
    print("MIDDLE")  # Executes after first next()
    yield 2
    print("END")  # Executes after second next()
    yield 3

gen = simple_generator()  # ✓ Function NOT called yet
print(type(gen))  # <class 'generator'>

# Execution starts here:
print(next(gen))  # START\n1
print(next(gen))  # MIDDLE\n2
print(next(gen))  # END\n3
print(next(gen))  # Raises StopIteration
```

**Key behavior:**

- Generators are iterators: they work with `iter()`, `next()`, `for` loops, list comprehensions,
  etc.
- `iter(generator) is generator` — generators are their own iterators.
- State is preserved between calls: local variables, execution position, everything.
- When the generator finishes (reaches the end), `StopIteration` is raised.

### Generator Expressions

Generators can also be created using concise generator expressions (like list comprehensions, but
lazy):

```python
# Generator expression (parentheses instead of brackets)
gen = (x ** 2 for x in range(10))  # Not executed yet
print(type(gen))  # <class 'generator'>

# These are equivalent:
# 1. Generator expression (lazy, memory-efficient)
squares_gen = (x ** 2 for x in range(1_000_000))

# 2. List comprehension (eager, loads all into memory)
squares_list = [x ** 2 for x in range(1_000_000)]  # Memory hog

# Use generator expressions for large datasets
for square in squares_gen:  # Only computes what's needed
    if square > 1_000_000:
        break
```

### Common Use Cases

**Processing large files:**

```python
async def read_large_file(file_path: str, chunk_size: int = 1024) -> None:
    """Generator for reading large files in chunks."""
    async with aiofiles.open(file_path, "r") as f:
        while True:
            chunk = await f.read(chunk_size)
            if not chunk:
                break
            yield chunk

# Usage: memory-efficient, never loads entire file
async for chunk in read_large_file("huge_dataset.txt"):
    process_chunk(chunk)  # Work on one chunk at a time
```

**Infinite sequences:**

```python
def count_from(n: int = 0) -> int:
    """Generate infinite sequence starting from n."""
    while True:
        yield n
        n += 1

# Take first 5: 0, 1, 2, 3, 4
first_five = [x for x, _ in zip(count_from(), range(5))]
```

**Processing pipelines:**

```python
def read_data(filepath: str) -> str:
    """Read data lines."""
    with open(filepath) as f:
        for line in f:
            yield line.strip()

def filter_data(lines: list[str], prefix: str) -> str:
    """Filter lines by prefix."""
    for line in lines:
        if line.startswith(prefix):
            yield line

def transform_data(lines: list[str]) -> dict:
    """Parse lines into dicts."""
    for line in lines:
        parts = line.split(",")
        yield {"name": parts[0], "value": int(parts[1])}

# Lazy pipeline: each stage processes only what's needed
pipeline = transform_data(filter_data(read_data("data.csv"), "USER"))
for record in pipeline:
    print(record)  # Lazy! No intermediate lists
```

### `return` Inside a Generator

`return` in a generator completes iteration and attaches a value to the `StopIteration` exception:

```python
def gen_with_return(limit: int) -> int:
    """Generator that yields up to limit, then returns a final message."""
    for i in range(limit):
        yield i
    return "DONE"  # Attached to StopIteration.value

gen = gen_with_return(3)
try:
    while True:
        print(next(gen))
except StopIteration as e:
    print(f"Final value: {e.value}")

# Output:
# 0
# 1
# 2
# Final value: DONE
```

### Advanced: Bidirectional Communication with `send()`

`yield` is not just a statement—it's also an **expression** that can receive values back from the
caller via `send()`.

**Basic concept:**

```python
def receiver() -> None:
    """Generator that receives values via send()."""
    x = yield  # Pause, wait for value from send()
    print(f"Received: {x}")
    y = yield  # Pause again
    print(f"Received: {y}")

gen = receiver()
next(gen)  # Prime: advance to first yield
gen.send("hello")  # Resume, inject "hello" into yield
gen.send("world")  # Resume, inject "world" into yield
# Output: Received: hello\nReceived: world
```

**Practical example: squarer coroutine**

```python
def squarer() -> int:
    """A coroutine that squares numbers sent to it."""
    number = yield  # Pause, ready for first value
    while number is not None:
        print(f"Squaring {number}")
        number = yield number ** 2  # Yield result, wait for next

gen = squarer()
next(gen)  # Prime the generator
print("5² =", gen.send(5))  # Send 5, gets 25
print("7² =", gen.send(7))  # Send 7, gets 49

# Output:
# Squaring 5
# 5² = 25
# Squaring 7
# 7² = 49
```

**Key rules for `send()`:**

- You cannot `send(non_None)` to a just-started generator—it hasn't reached `yield` yet. Use
  `next(gen)` or `send(None)` to prime it first.
- `send(None)` is equivalent to `next(gen)`.

### Exception Handling: `throw()`

Inject exceptions into a generator using `throw()`. If caught, the generator can continue yielding.

```python
def gen_with_exception_handling() -> int:
    """Generator that handles exceptions."""
    for i in range(5):
        try:
            yield i
        except ValueError as e:
            print(f"Caught exception: {e}")
            yield -1  # Yield a placeholder value

gen = gen_with_exception_handling()
print(next(gen))  # 0
print(next(gen))  # 1
print(gen.throw(ValueError("oops")))  # Caught exception: oops\n-1
print(next(gen))  # 2
```

**Advanced: buffer and flush pattern**

```python
class BufferAndFlush:
    """Exception-driven buffer flushing."""
    pass

def buffering_generator() -> list:
    """Buffer strings, flush on special exception."""
    buffer = []
    try:
        while True:
            s = yield
            if isinstance(s, str):
                buffer.append(s)
    except BufferAndFlush:
        return buffer  # Return all buffered items

gen = buffering_generator()
next(gen)  # Prime
gen.send("hello")
gen.send("world")
try:
    gen.throw(BufferAndFlush)
except StopIteration as e:
    print(f"Buffered: {e.value}")  # Buffered: ['hello', 'world']
```

### Cleanup: `close()`

Call `close()` to terminate a generator gracefully. It raises `GeneratorExit` inside the generator,
allowing cleanup:

```python
def generator_with_cleanup() -> int:
    """Generator that performs cleanup on close()."""
    try:
        for i in range(10):
            yield i
    except GeneratorExit:
        print("Cleaning up resources...")
        # Close files, connections, etc.
        raise  # Must re-raise GeneratorExit

gen = generator_with_cleanup()
print(next(gen))  # 0
print(next(gen))  # 1
gen.close()  # Triggers cleanup
# Output: Cleaning up resources...
```

**Python 3.13+: `close()` can return a value**

Starting with Python 3.13, `close()` can return the final value from `return`:

```python
def summarizer() -> str:
    """Summarize received strings."""
    items = []
    try:
        while True:
            s = yield
            if isinstance(s, str):
                items.append(s)
    except GeneratorExit:
        return ",".join(items)  # Python 3.13+ returns from close()

gen = summarizer()
next(gen)
gen.send("cat")
gen.send("dog")
result = gen.close()  # Python 3.13: returns "cat,dog"
print(result)  # cat,dog (or None in Python 3.12)
```

### Generators vs. Lists: When to Use Each

| Factor          | Generators                                     | Lists                               |
| --------------- | ---------------------------------------------- | ----------------------------------- |
| **Memory**      | O(1) — only current item in memory             | O(n) — all items in memory          |
| **Speed**       | Lazy evaluation — start immediately            | Eager — delayed until iteration     |
| **Reusability** | Can't iterate twice (exhausted after one pass) | Can iterate multiple times          |
| **Size**        | Good for infinite/large sequences              | Good for small, finite datasets     |
| **Use case**    | Streaming, pipelines, large files              | Small datasets, multiple iterations |

**Choose generators when:**

- Processing large files or streams.
- Building transformation pipelines.
- Generating infinite or expensive sequences.
- You iterate only once.

**Choose lists when:**

- Dataset is small.
- You need to iterate multiple times.
- You need random access (`mylist[i]`).

### Practical Guidelines for Production Code

**Memory-efficient file processing:**

```python
# ✓ Good: Generator preserves memory
async def process_events(log_file: str) -> dict:
    """Stream events from log file (memory-efficient)."""
    async with aiofiles.open(log_file) as f:
        async for line in f:
            parsed = json.loads(line)
            yield parsed  # Never load entire file

async for event in process_events("events.jsonl"):
    await handle_event(event)

# ✗ Bad: Loads entire file into memory
with open("events.jsonl") as f:
    events = [json.loads(line) for line in f]  # OOM with huge files
for event in events:
    await handle_event(event)
```

**Database query pagination:**

```python
async def paginated_query(db: AsyncSession, batch_size: int = 100) -> User:
    """Fetch users in batches (memory-efficient)."""
    offset = 0
    while True:
        query = select(UserModel).offset(offset).limit(batch_size)
        results = await db.execute(query)
        users = results.scalars().all()
        if not users:
            break
        for user in users:
            yield user  # Yield one at a time
        offset += batch_size

# Usage: processes one batch at a time, never loads all users
async for user in paginated_query(db):
    await process_user(user)
```

**Decorator pattern with generators:**

```python
def timer_decorator(gen_func):
    """Decorator that times generator execution."""
    def wrapper(*args, **kwargs):
        gen = gen_func(*args, **kwargs)
        start = time.time()
        for item in gen:
            yield item
        elapsed = time.time() - start
        logger.info(f"Generator took {elapsed:.2f}s")
    return wrapper

@timer_decorator
async def fetch_all_users(db: AsyncSession) -> User:
    """Fetch and yield all users (with timing)."""
    query = select(UserModel)
    result = await db.execute(query)
    for user in result.scalars():
        yield user
```

---

## Performance & Observability

### Metrics & Health Checks

- Expose Prometheus metrics on `/metrics`.
- Implement `/health` endpoint for liveness/readiness checks.
- Track key metrics: request latency, error rates, queue depth, database connection pool.

### Example

```python
from prometheus_client import Counter, Histogram, Gauge
from fastapi import FastAPI
from prometheus_client import generate_latest, CollectorRegistry, REGISTRY

REGISTRY = CollectorRegistry()
request_duration = Histogram("request_duration_seconds", "Request latency", registry=REGISTRY)
request_count = Counter("requests_total", "Total requests", ["method", "endpoint", "status"], registry=REGISTRY)
db_connection_pool = Gauge("db_connection_pool_current", "Current DB connections", registry=REGISTRY)

@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy"}

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return generate_latest(REGISTRY)
```

---

## Quick Checklist

Before committing Python code:

- [ ] Type hints on all function signatures
- [ ] `ty check src/` passes without errors
- [ ] `ruff check --fix && ruff format` applied
- [ ] All routes are `async`
- [ ] Database queries use `AsyncSession`
- [ ] Errors are logged with structured JSON
- [ ] Tests exist for critical paths (>80% coverage)
- [ ] Docstrings on complex functions/classes
- [ ] No sync I/O (no `time.sleep()`, `requests.get()`, etc.)
- [ ] Pydantic v2 schemas for request/response validation

### Antipattern Checks

- [ ] No `except Exception:` or bare `except:` — use specific exceptions
- [ ] No magic numbers/strings — use `Enum` or named constants
- [ ] No mutable default arguments (e.g., `items=[]`)
- [ ] No heavy work in `__init__` — defer to explicit `start()`, `connect()` methods
- [ ] No wildcard imports (`from x import *`)
- [ ] No shadowing of built-ins (`list`, `id`, `filter`, etc.)
- [ ] No global mutable state — inject dependencies or wrap in classes
- [ ] Exception handlers are tight (not too many lines in `try` block)
- [ ] Comparisons to `None` use `is` / `is not` , not `==` / `!=`
- [ ] No list comprehensions for side effects — use explicit `for` loops
- [ ] Using `logger` (not `print()`) for all logging
- [ ] Resources use context managers (`with` / `async with`)

### Lambda & Functional Programming Checks

- [ ] Lambda used only for simple, single-line expressions
- [ ] Lambda fits comfortably on one line (no wrapping)
- [ ] No duplicated lambdas — extract to named function if used 2+ times
- [ ] Lambda used appropriately: `sorted(key=lambda ...)`, not `map(lambda ...)` when list
      comprehension is clearer
- [ ] Late binding in loops captured explicitly (default args: `lambda x, f=factor:` or
      `functools.partial`)
- [ ] No complex logic in lambda — if it needs parentheses to parse visually, use `def`
- [ ] Prefer `list`/`dict`/`set` comprehensions over `map()`/`filter()` with lambdas
- [ ] No lambda in business logic — if debugging is needed, use named function
- [ ] Short callbacks (UI, event handlers) are reasonable uses of lambda
- [ ] `operator.itemgetter()` or `operator.attrgetter()` preferred over `lambda` for simple key
      extraction
- [ ] No docstrings expected in lambda — if you'd need to explain it with docs, use `def`
- [ ] No breakpoints expected in lambda — if it needs debugging, use `def`

### Memory Model & Object System Checks

- [ ] No mutable default arguments (e.g., `func(items: list = [])`)
- [ ] Mutable kwargs defaults checked for shared state issues
- [ ] Multiple assignment with mutable objects avoided unless intentional
- [ ] Deep copy used where needed (not just shallow copy)
- [ ] No mutation during iteration (use list comprehension or iterate over copy)
- [ ] `is` used for identity checks (`None`, singletons), `==` for value comparison
- [ ] `__slots__` considered for memory-heavy classes with fixed attributes
- [ ] Generators used for large datasets (not loading all into memory)
- [ ] `array` or `bytes` considered for dense numeric data
- [ ] Closure variables captured correctly (default args for lambdas to capture by value)

### Object Reference & Passing Checks

- [ ] Immutable arguments assumed safe from external changes
- [ ] Mutable arguments understood to be passed by reference
- [ ] Function return values clarified if returning same object or new
- [ ] Call sites checked for unintended aliasing with mutable objects
- [ ] Shallow copy implications understood for nested structures

### Data Structure Performance Checks

- [ ] Not using `list` for frequent front/middle inserts/deletes — use `deque` instead
- [ ] Not using `list` for frequent membership tests on large collections — consider `set`
- [ ] Not using repeated linear search (`x in list`) — use `dict` or `set` for O(1) lookup
- [ ] Using `dict` keys instead of list for deduplication where applicable
- [ ] Not mutating dict keys after insertion (keys are immutable/hashable)
- [ ] Efficient data structure choice for the access pattern (index, lookup, uniqueness)

### Generator & Iterator Checks

- [ ] Large file processing uses generators (not loading entire file into memory)
- [ ] Infinite sequences or pipelines use generators for lazy evaluation
- [ ] Generator expressions preferred over list comprehensions for one-time iteration
- [ ] Generator functions primer called before send() (use `next(gen)` to prime)
- [ ] No reusing exhausted generators without reinitializing
- [ ] Cleanup logic in generators wrapped in try/except for GeneratorExit
- [ ] Bidirectional communication (send/throw) only used in advanced coroutines
- [ ] Database queries paginated with generators to avoid OOM on large result sets

### Design Pattern Application Checks

> See the full checklist in [design-patterns.instructions.md](design-patterns.instructions.md).

- [ ] Pain diagnosed before pattern chosen: friction identified (creation / boundary / behavior)?
- [ ] Pattern solves a real TODAY problem, not a hypothetical future one?
- [ ] Patterns used judiciously: not over-engineering simple features
