---
name: design-patterns
description: >
    Production-ready guide to software design patterns in Python and FastAPI. Covers creational,
    structural, and behavioral patterns with a pain-first diagnostic decision tree, full
    implementations, and 15 antipatterns to avoid.
applyTo: 'src/**/*.py, **/*.py'
---

# Design Patterns in Python & FastAPI

> "Design patterns rarely fail because they are 'wrong.' They fail because we reach for them at the
> wrong moment, for the wrong reason." — the real failure is pattern-first thinking rather than
> problem-first thinking.

---

## Pain-First Decision Tree

**The single most important rule: diagnose the friction BEFORE picking a pattern.**

Reaching for a pattern without first identifying the pain it relieves leads to over-engineering,
unnecessary indirection, and code that is harder to read than what it replaced. Use this decision
tree as your entry point.

### Step 1: Identify Which Friction You Feel

```
What is actually hurting right now?
│
├─► "This object is complex to create — lots of params,
│    multiple steps, or many implementations to choose from."
│    └─► Friction Type 1: Object Creation → go to Creational Patterns
│
├─► "This code depends on something awkward — a legacy system,
│    a third-party lib with a bad interface, or I need transparent
│    access control / lazy loading around an object."
│    └─► Friction Type 2: Component Boundaries → go to Structural Patterns
│
└─► "This code is getting tangled with conditionals — if-elif
     chains that grow every time behavior changes, or I need to
     decouple event producers from consumers."
     └─► Friction Type 3: Changing Behavior → go to Behavioral Patterns
```

---

### Friction Type 1 — Object Creation Candidates

```
What about object creation is hurting?
│
├─► "I keep constructing this in multiple places and
│    need exactly one shared instance."
│    └─► Singleton
│
├─► "I need one of several concrete types, selected at
│    runtime, and callers shouldn't know which."
│    └─► Factory / Abstract Factory
│
├─► "The object has many optional fields and I'm tired
│    of huge constructors or long keyword-arg lists."
│    └─► Builder
│
└─► "Creating this object is expensive; I need similar
     copies with small variations."
     └─► Prototype
```

**Ask before choosing a Creational pattern:**

- [ ] Is the creation pain actually FROM the caller, or is the class itself too complex?
- [ ] Would a plain `dataclass` or `Pydantic` model solve it without a pattern?
- [ ] For Singleton: can FastAPI's `Depends()` injection serve the same purpose more testably?
- [ ] For Factory: are you sure there are multiple real implementations today (not hypothetical)?

---

### Friction Type 2 — Component Boundary Candidates

```
What about the object boundary is hurting?
│
├─► "I'm working with a legacy system / third-party lib
│    whose interface doesn't match what my code expects."
│    └─► Adapter
│
├─► "I need to add behavior (logging, caching, auth)
│    to objects dynamically without modifying them."
│    └─► Decorator
│
├─► "I have a complex hierarchy — leaves and composites —
│    and I want to treat them all the same way."
│    └─► Composite
│
├─► "My caller has to coordinate 5+ objects to accomplish
│    one task; I want to hide that complexity."
│    └─► Facade
│
└─► "I need to intercept access to an object — for lazy
     loading, access control, or logging."
     └─► Proxy
```

**Ask before choosing a Structural pattern:**

- [ ] Could simpler refactoring (extracting a method or class) remove the pain instead?
- [ ] For Facade: are you hiding complexity or just moving it?
- [ ] For Decorator: is this composable behavior (the pattern fits) or just one extra thing?
- [ ] For Proxy: is the same interface needed, or would a thin wrapper function suffice?

---

### Friction Type 3 — Behavior Change Candidates

```
What about behavior is hurting?
│
├─► "Something needs to react to events in another
│    object without tight coupling."
│    └─► Observer
│
├─► "I have interchangeable algorithms and a big if-elif
│    chain that grows when I add a new one."
│    └─► Strategy
│
├─► "I need to queue, log, or undo operations — requests
│    should be first-class objects."
│    └─► Command
│
└─► "Behavior depends on state and I have a tangled
     mess of if-elifs checking which state I'm in."
     └─► State
```

**Ask before choosing a Behavioral pattern:**

- [ ] Is the real problem too many responsibilities in one class (SRP violation)?
- [ ] For Observer: does simpler function callbacks solve it without the Observer ceremony?
- [ ] For Strategy: is there actually more than one algorithm today, or is this speculative?
- [ ] For State: are there at least 3 states with different rules? Fewer may not justify the
      pattern.
- [ ] For Command: do you need undo, queue, or audit log? Without these, a plain function suffices.

---

## Design Patterns in Production

Design patterns are proven architectural solutions to recurring problems. Understanding **when** and
**how** to apply them is essential for building maintainable, scalable systems. This section covers
creational, structural, and behavioral patterns with production-ready examples for FastAPI and async
services.

---

## Creational Patterns (Object Creation)

**Purpose:** Manage object instantiation flexibly, decoupling creation logic from usage.

### 1. Singleton Pattern

Ensures a class has **only one instance** with global access. Useful for configuration, logging,
database connections, and shared resources.

**When to use:**

- Shared resource managers (database connection pool, logger, config).
- Stateful services that must not be duplicated.
- **Not recommended for:** Stateless services (just use dependency injection instead).

**Implementation via Decorator (Preferred for FastAPI):**

```python
from functools import lru_cache
from typing import TypeVar

T = TypeVar("T")

def singleton(cls: type[T]) -> T:
    """Decorator pattern for lazy Singleton."""
    _instances: dict = {}

    def get_instance(*args, **kwargs) -> T:
        if cls not in _instances:
            _instances[cls] = cls(*args, **kwargs)
        return _instances[cls]

    return get_instance  # type: ignore

@singleton
class DatabaseConfig:
    """Shared database configuration—loaded once."""
    def __init__(self, db_url: str):
        self.db_url = db_url
        logger.info(f"Database config initialized: {db_url}")

# Usage: Always returns the same instance
config1 = DatabaseConfig("postgresql://...")
config2 = DatabaseConfig("postgresql://...")
assert config1 is config2  # True
```

**Using `@lru_cache` for Simple Singletons:**

```python
from functools import lru_cache
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application settings (Singleton via lru_cache)."""
    database_url: str
    redis_url: str
    debug: bool = False

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Dependency: returns singleton settings."""
    return Settings()

# FastAPI dependency injection
@app.get("/health")
async def health(settings: Settings = Depends(get_settings)) -> dict:
    return {"db": settings.database_url, "debug": settings.debug}
```

**Key principle:** For FastAPI, prefer dependency injection over explicit singletons—it's cleaner
and testable.

---

### 2. Factory Pattern

Provides an abstraction for creating objects based on a type or parameter. Decouples creation logic
from usage.

**When to use:**

- Multiple implementations of an interface, selected at runtime.
- Payment processors, storage backends, authentication strategies.
- Plugin systems or adapters.

**Simple Factory (Static Method):**

```python
from abc import ABC, abstractmethod

class PaymentProcessor(ABC):
    """Abstract interface for payment processing."""
    @abstractmethod
    async def process(self, amount: float) -> dict:
        pass

class CreditCardProcessor(PaymentProcessor):
    async def process(self, amount: float) -> dict:
        logger.info(f"Processing credit card: ${amount}")
        return {"status": "success", "amount": amount}

class PayPalProcessor(PaymentProcessor):
    async def process(self, amount: float) -> dict:
        logger.info(f"Processing PayPal: ${amount}")
        return {"status": "success", "amount": amount}

class PaymentProcessorFactory:
    """Factory for creating payment processors."""
    _processors: dict[str, type[PaymentProcessor]] = {
        "credit_card": CreditCardProcessor,
        "paypal": PayPalProcessor,
    }

    @classmethod
    def create(cls, processor_type: str) -> PaymentProcessor:
        """Create processor or raise ValueError."""
        if processor_type not in cls._processors:
            raise ValueError(f"Unknown processor: {processor_type}")
        return cls._processors[processor_type]()

# Usage in FastAPI
@app.post("/pay")
async def pay(payment_method: str, amount: float) -> dict:
    processor = PaymentProcessorFactory.create(payment_method)
    result = await processor.process(amount)
    return result
```

**Abstract Factory (for Related Objects):**

```python
# Use Abstract Factory when creating **families** of related objects
class CacheBackend(ABC):
    @abstractmethod
    async def get(self, key: str) -> str | None:
        pass

class RedisCache(CacheBackend):
    async def get(self, key: str) -> str | None:
        return await redis_client.get(key)

class MemoryCache(CacheBackend):
    def __init__(self):
        self._cache = {}
    async def get(self, key: str) -> str | None:
        return self._cache.get(key)

class CacheFactory:
    """Factory for cache implementations."""
    @staticmethod
    def create(cache_type: str) -> CacheBackend:
        if cache_type == "redis":
            return RedisCache()
        elif cache_type == "memory":
            return MemoryCache()
        raise ValueError(f"Unknown cache: {cache_type}")

# Inject cache backend via dependency
def get_cache_backend() -> CacheBackend:
    return CacheFactory.create(get_settings().cache_backend)

@app.get("/data/{key}")
async def get_data(key: str, cache: CacheBackend = Depends(get_cache_backend)) -> dict:
    value = await cache.get(key)
    return {"key": key, "value": value}
```

**Key principle:** Use factories to hide creation complexity and enable swapping implementations
(testing, deployment-time config).

---

### 3. Builder Pattern

Constructs **complex objects step by step**, separating construction from representation. Reduces
parameter-heavy constructors.

**When to use:**

- Complex objects with many optional parameters.
- Immutable/frozen dataclasses with many fields.
- Fluent configuration APIs.

**Implementation:**

```python
class QueryBuilder:
    """Fluent builder for database queries."""
    def __init__(self):
        self._select = ["*"]
        self._table = None
        self._where_clauses = []
        self._limit_val = None
        self._offset_val = None

    def select(self, *columns: str) -> "QueryBuilder":
        self._select = list(columns)
        return self  # ✓ Return self for chaining

    def from_table(self, table: str) -> "QueryBuilder":
        self._table = table
        return self

    def where(self, condition: str) -> "QueryBuilder":
        self._where_clauses.append(condition)
        return self

    def limit(self, count: int) -> "QueryBuilder":
        self._limit_val = count
        return self

    def offset(self, count: int) -> "QueryBuilder":
        self._offset_val = count
        return self

    def build(self) -> str:
        """Build SQL query from accumulated state."""
        if not self._table:
            raise ValueError("Must specify table via .from_table()")
        query = f"SELECT {', '.join(self._select)} FROM {self._table}"
        if self._where_clauses:
            query += " WHERE " + " AND ".join(self._where_clauses)
        if self._limit_val:
            query += f" LIMIT {self._limit_val}"
        if self._offset_val:
            query += f" OFFSET {self._offset_val}"
        return query

# Fluent usage
query = (QueryBuilder()
    .select("id", "name", "email")
    .from_table("users")
    .where("active = true")
    .where("role != 'guest'")
    .limit(10)
    .offset(0)
    .build())

print(query)
# SELECT id, name, email FROM users WHERE active = true AND role != 'guest' LIMIT 10 OFFSET 0
```

**Using Builder with httpx:**

```python
class RequestBuilder:
    """Builder for HTTP requests (fluent API)."""
    def __init__(self):
        self._method = "GET"
        self._url = None
        self._headers = {}
        self._body = None
        self._timeout = 30

    def post(self) -> "RequestBuilder":
        self._method = "POST"
        return self

    def url(self, url: str) -> "RequestBuilder":
        self._url = url
        return self

    def header(self, key: str, value: str) -> "RequestBuilder":
        self._headers[key] = value
        return self

    def json_body(self, data: dict) -> "RequestBuilder":
        self._body = data
        self._headers["Content-Type"] = "application/json"
        return self

    def timeout(self, seconds: int) -> "RequestBuilder":
        self._timeout = seconds
        return self

    async def send(self) -> dict:
        """Execute HTTP request."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(
                self._method,
                self._url,
                headers=self._headers,
                json=self._body,
            )
            return response.json()

# Usage
result = await (RequestBuilder()
    .post()
    .url("https://api.example.com/events")
    .header("Authorization", "Bearer TOKEN")
    .json_body({"user_id": 123, "event": "login"})
    .timeout(10)
    .send())
```

**Key principle:** Builder is ideal for API design because it's fluent, discoverable, and handles
optional parameters ergonomically.

---

### 4. Prototype Pattern

Creates new objects by **cloning an existing object** (prototype) rather than constructing from
scratch. Useful when copying is cheaper than creating anew.

**When to use:**

- Object creation is expensive (complex initialization, database queries).
- You need similar objects with minor variations.
- Avoiding deep constructor chains.

**Implementation:**

```python
from abc import ABC, abstractmethod
from copy import deepcopy
from datetime import datetime

class Document(ABC):
    """Abstract prototype for documents."""
    @abstractmethod
    def clone(self) -> "Document":
        pass

class Report(Document):
    """Concrete document type that can be cloned."""
    def __init__(self, title: str, content: str, author: str):
        self.title = title
        self.content = content
        self.author = author
        self.created_at = datetime.utcnow()
        self.metadata = {}  # Can hold arbitrary data

    def clone(self) -> "Report":
        """Deep copy this report."""
        return deepcopy(self)

    def __repr__(self):
        return f"Report(title={self.title!r}, author={self.author}, created={self.created_at})"

# Usage
template = Report(
    title="Quarterly Report",
    content="[Template content]",
    author="Finance Team"
)

# Clone and customize
q1_report = template.clone()
q1_report.title = "Q1 2026 Quarterly Report"
q1_report.content = "Q1 results..."

q2_report = template.clone()
q2_report.title = "Q2 2026 Quarterly Report"
q2_report.content = "Q2 results..."

assert q1_report is not template  # ✓ True — different objects
assert q1_report.content != q2_report.content  # ✓ Different content
```

**Key principle:** Use `copy.deepcopy()` for recursive cloning; `copy.copy()` for shallow copies
when safe.

---

## Structural Patterns (Object Composition)

**Purpose:** Compose objects and classes to form larger structures while maintaining flexibility and
loose coupling.

### 1. Adapter Pattern

Wraps an **incompatible interface** to make it work with expected code. Acts as a bridge between two
systems.

**When to use:**

- Integrating legacy systems with new code.
- Third-party libraries with incompatible interfaces.
- Creating unified interfaces from diverse sources.

**Implementation:**

```python
from abc import ABC, abstractmethod

# New (expected) interface
class PaymentGateway(ABC):
    @abstractmethod
    async def charge(self, amount: float, currency: str = "USD") -> dict:
        pass

# Old (incompatible) interface
class LegacyBillingAPI:
    """Legacy system with different interface."""
    def __init__(self, api_key: str):
        self.api_key = api_key

    def bill_customer(self, cents: int) -> bool:
        """Legacy method: expects amount in cents, no currency parameter."""
        logger.info(f"Charging ${cents / 100} via legacy API")
        return True

# Adapter: wraps legacy API in new interface
class LegacyBillingAdapter(PaymentGateway):
    """Adapter converts legacy interface to new gateway interface."""
    def __init__(self, legacy_api: LegacyBillingAPI):
        self.legacy_api = legacy_api

    async def charge(self, amount: float, currency: str = "USD") -> dict:
        """Adapt new interface to legacy method."""
        # Convert dollars to cents
        cents = int(amount * 100)
        success = self.legacy_api.bill_customer(cents)
        return {
            "success": success,
            "amount": amount,
            "currency": currency,
            "method": "legacy_api"
        }

# Usage
legacy_api = LegacyBillingAPI(api_key="secret123")
adapter = LegacyBillingAdapter(legacy_api)  # Wrap it

result = await adapter.charge(49.99, currency="USD")
print(result)  # {'success': True, 'amount': 49.99, ...}
```

**Key principle:** Adapters are **read-only wrappers**—they don't modify the original object, just
change the interface.

---

### 2. Decorator Pattern

**Attaches additional responsibilities to an object dynamically** without modifying its class.
Python decorators (functions) are a special case; this covers object decoration.

**When to use:**

- Adding behavior to objects without subclassing (avoids class explosion).
- Feature flags or optional enhancements (caching, logging, rate limiting).
- Composable middleware / pipelines.

**Implementation (Object Decoration):**

```python
from abc import ABC, abstractmethod

# Component interface
class Coffee(ABC):
    @abstractmethod
    async def get_price(self) -> float:
        pass

    @abstractmethod
    async def get_description(self) -> str:
        pass

# Concrete component
class SimpleCoffee(Coffee):
    async def get_price(self) -> float:
        return 2.00

    async def get_description(self) -> str:
        return "Simple coffee"

# Decorator base class
class CoffeeDecorator(Coffee):
    """Base class for coffee decorators."""
    def __init__(self, coffee: Coffee):
        self.coffee = coffee

# Concrete decorators — composable
class MilkDecorator(CoffeeDecorator):
    async def get_price(self) -> float:
        return await self.coffee.get_price() + 0.50

    async def get_description(self) -> str:
        return f"{await self.coffee.get_description()} + milk"

class WhippedCreamDecorator(CoffeeDecorator):
    async def get_price(self) -> float:
        return await self.coffee.get_price() + 0.75

    async def get_description(self) -> str:
        return f"{await self.coffee.get_description()} + whipped cream"

class CaramelDecorator(CoffeeDecorator):
    async def get_price(self) -> float:
        return await self.coffee.get_price() + 0.60

    async def get_description(self) -> str:
        return f"{await self.coffee.get_description()} + caramel"

# Composable application
basic = SimpleCoffee()
fancy_latte = CaramelDecorator(
    WhippedCreamDecorator(
        MilkDecorator(basic)
    )
)

print(await fancy_latte.get_description())
# Simple coffee + milk + whipped cream + caramel
print(f"${await fancy_latte.get_price():.2f}")  # $3.85
```

**FastAPI Middleware as Decoration:**

```python
from fastapi import FastAPI, Request
from time import time

app = FastAPI()

@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    """Middleware decorator—adds timing to all requests."""
    start_time = time()
    response = await call_next(request)
    process_time = time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    logger.info(f"{request.url.path} took {process_time:.3f}s")
    return response

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Middleware decorator—adds authentication check."""
    token = request.headers.get("Authorization")
    if request.url.path == "/health":  # Skip auth for health check
        return await call_next(request)
    if not verify_token(token):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return await call_next(request)
```

**Key principle:** Decoration is more flexible than inheritance—you can combine decorators
dynamically.

---

### 3. Composite Pattern

Composes objects into **tree structures** to represent part-whole hierarchies, letting clients treat
individual and composite objects uniformly.

**When to use:**

- Hierarchical data structures (file systems, org charts, menu hierarchies).
- Recursively composed operations (e.g., rendering nested UI).

**Implementation:**

```python
from abc import ABC, abstractmethod
from typing import List

class FileSystemNode(ABC):
    """Abstract component for file system tree."""
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def get_size(self) -> int:
        """Get total size in bytes."""
        pass

    @abstractmethod
    def display(self, indent: int = 0):
        """Display tree structure."""
        pass

class File(FileSystemNode):
    """Leaf node: a file."""
    def __init__(self, name: str, size: int):
        super().__init__(name)
        self.size = size

    def get_size(self) -> int:
        return self.size

    def display(self, indent: int = 0):
        print("  " * indent + f"📄 {self.name} ({self.size} bytes)")

class Directory(FileSystemNode):
    """Composite node: a folder containing files/folders."""
    def __init__(self, name: str):
        super().__init__(name)
        self.children: List[FileSystemNode] = []

    def add(self, child: FileSystemNode):
        self.children.append(child)

    def remove(self, child: FileSystemNode):
        self.children.remove(child)

    def get_size(self) -> int:
        """Recursively sum size of all children."""
        return sum(child.get_size() for child in self.children)

    def display(self, indent: int = 0):
        print("  " * indent + f"📁 {self.name}/")
        for child in self.children:
            child.display(indent + 1)

# Usage: build tree
root = Directory("home")
documents = Directory("Documents")
downloads = Directory("Downloads")

documents.add(File("resume.pdf", 512000))
documents.add(File("cover_letter.docx", 256000))
downloads.add(File("image.png", 2048000))

root.add(documents)
root.add(downloads)
root.add(File("readme.txt", 4096))

root.display()
# 📁 home/
#   📁 Documents/
#     📄 resume.pdf (512000 bytes)
#     📄 cover_letter.docx (256000 bytes)
#   📁 Downloads/
#     📄 image.png (2048000 bytes)
#   📄 readme.txt (4096 bytes)

print(f"Total size: {root.get_size()} bytes")  # 2820096
```

**Key principle:** Composite lets you treat leaf and composite objects uniformly—the tree traversal
logic is simple and recursive.

---

### 4. Facade Pattern

Provides a **simplified interface to a complex subsystem**. Hides complexity behind a clean API.

**When to use:**

- Simplifying complex multistep workflows.
- Decoupling clients from internal implementation details.
- Creating intentional boundaries in large systems.

**Implementation:**

```python
# Complex subsystem: multiple interacting components
class PaymentProcessor:
    async def process(self, amount: float) -> dict:
        return {"status": "processed", "amount": amount}

class NotificationService:
    async def send_email(self, email: str, subject: str, body: str):
        logger.info(f"Email to {email}: {subject}")

class AuditService:
    async def log_transaction(self, user_id: int, amount: float):
        logger.info(f"Transaction logged: user={user_id}, amount={amount}")

# Facade: simplifies the workflow
class PaymentFacade:
    """Facade simplifying complex payment workflow."""
    def __init__(
        self,
        processor: PaymentProcessor,
        notifier: NotificationService,
        auditor: AuditService,
    ):
        self.processor = processor
        self.notifier = notifier
        self.auditor = auditor

    async def pay(self, user_id: int, email: str, amount: float) -> dict:
        """Simplified payment API—handles all steps."""
        result = await self.processor.process(amount)
        await self.auditor.log_transaction(user_id, amount)
        await self.notifier.send_email(
            email,
            subject="Payment Received",
            body=f"You were charged ${amount}."
        )
        return result

# Usage: client sees clean API, not complexity
facade = PaymentFacade(
    processor=PaymentProcessor(),
    notifier=NotificationService(),
    auditor=AuditService(),
)

result = await facade.pay(user_id=123, email="user@example.com", amount=49.99)
```

**FastAPI Facade Example:**

```python
@app.post("/checkout")
async def checkout(
    user_id: int,
    email: str,
    amount: float,
    facade: PaymentFacade = Depends(get_payment_facade),
) -> dict:
    """Checkout endpoint—delegates to facade."""
    return await facade.pay(user_id, email, amount)
```

**Key principle:** Facades hide complexity but **don't change behavior**—they're about hiding, not
modifying.

---

### 5. Proxy Pattern

Provides a **placeholder or surrogate** for another object to control access to it. Enables lazy
loading, access control, logging, or caching.

**When to use:**

- Lazy initialization of expensive objects.
- Access control / authorization on sensitive objects.
- Logging/monitoring access to objects.
- Caching of expensive computations.

**Implementation (Virtual Proxy / Lazy Loading):**

```python
from abc import ABC, abstractmethod
import asyncio

class DataSource(ABC):
    @abstractmethod
    async def fetch_data(self) -> dict:
        pass

class RealDataSource(DataSource):
    """Expensive data source (slow to initialize)."""
    def __init__(self, source_url: str):
        self.source_url = source_url
        logger.info(f"RealDataSource created for {source_url} (not connected yet)")

    async def fetch_data(self) -> dict:
        """Simulate slow network call."""
        logger.info(f"Connecting to {self.source_url}...")
        await asyncio.sleep(2)  # Expensive operation
        return {"data": "from remote source", "url": self.source_url}

class DataSourceProxy(DataSource):
    """Proxy—delays creation of RealDataSource until needed."""
    def __init__(self, source_url: str):
        self.source_url = source_url
        self._real_source: RealDataSource | None = None

    async def fetch_data(self) -> dict:
        """Lazy load on first access."""
        if self._real_source is None:
            logger.info("Proxy: Creating real source on first access")
            self._real_source = RealDataSource(self.source_url)
        return await self._real_source.fetch_data()

# Usage
proxy = DataSourceProxy("https://api.example.com/data")
# Here, RealDataSource is NOT created yet
result = await proxy.fetch_data()
# Only here does real source get created (lazy loading)
```

**Proxy with Access Control:**

```python
class ProtectedResource(ABC):
    @abstractmethod
    async def read(self) -> str:
        pass

    @abstractmethod
    async def write(self, data: str):
        pass

class SensitiveData(ProtectedResource):
    def __init__(self, secret: str):
        self.secret = secret

    async def read(self) -> str:
        return self.secret

    async def write(self, data: str):
        self.secret = data

class AccessControlledProxy(ProtectedResource):
    """Proxy—controls access based on user role."""
    def __init__(self, resource: ProtectedResource, user_role: str):
        self.resource = resource
        self.user_role = user_role

    async def read(self) -> str:
        if self.user_role not in ["admin", "reader"]:
            raise PermissionError(f"Role {self.user_role} cannot read")
        return await self.resource.read()

    async def write(self, data: str):
        if self.user_role != "admin":
            raise PermissionError(f"Role {self.user_role} cannot write")
        await self.resource.write(data)

# Admin can read and write
admin_proxy = AccessControlledProxy(resource, user_role="admin")
print(await admin_proxy.read())
await admin_proxy.write("newsecret")

# Reader can only read
reader_proxy = AccessControlledProxy(resource, user_role="reader")
print(await reader_proxy.read())
# await reader_proxy.write("data")  # Raises PermissionError
```

**Key principle:** Proxies are **transparent** to the client—they implement the same interface as
the real object.

---

## Behavioral Patterns (Object Communication)

**Purpose:** Define how objects communicate and distribute responsibility.

### 1. Observer Pattern

Defines a **one-to-many dependency** between objects so that when one changes state, all dependents
are notified automatically.

**When to use:**

- Event systems and pub-sub models.
- Real-time notifications (user updates, status changes).
- Decoupling components that need to react to events.

**Implementation:**

```python
from abc import ABC, abstractmethod
from typing import List

class Observer(ABC):
    """Observer interface."""
    @abstractmethod
    async def update(self, event: dict):
        pass

class EmailNotifier(Observer):
    """Concrete observer: sends email notifications."""
    def __init__(self, email: str):
        self.email = email

    async def update(self, event: dict):
        logger.info(f"📧 Email to {self.email}: {event}")

class SlackNotifier(Observer):
    """Concrete observer: sends Slack messages."""
    def __init__(self, channel: str):
        self.channel = channel

    async def update(self, event: dict):
        logger.info(f"💬 Slack to #{self.channel}: {event}")

class EventEmitter:
    """Subject: manages observers and emits events."""
    def __init__(self):
        self._observers: List[Observer] = []

    def subscribe(self, observer: Observer):
        """Register observer."""
        self._observers.append(observer)
        logger.info(f"Observer subscribed: {observer.__class__.__name__}")

    def unsubscribe(self, observer: Observer):
        """Unregister observer."""
        self._observers.remove(observer)

    async def emit(self, event: dict):
        """Notify all observers of event."""
        logger.info(f"Emitting event: {event}")
        for observer in self._observers:
            await observer.update(event)

# Usage
emitter = EventEmitter()
emitter.subscribe(EmailNotifier("user@example.com"))
emitter.subscribe(SlackNotifier("alerts"))

await emitter.emit({
    "type": "payment",
    "user_id": 123,
    "amount": 49.99,
    "timestamp": "2026-01-15T10:30:00Z"
})
```

**FastAPI Integration:**

```python
# Global event emitter
payment_events = EventEmitter()

@app.on_event("startup")
async def startup_events():
    """Subscribe observers at startup."""
    payment_events.subscribe(EmailNotifier("team@example.com"))
    payment_events.subscribe(SlackNotifier("payments"))

@app.post("/payments")
async def process_payment(payment_data: dict) -> dict:
    """Process payment and emit event."""
    result = {"status": "success", "payment": payment_data}
    await payment_events.emit(result)  # Notify all observers
    return result
```

**Key principle:** Observers decouple event producers from consumers—neither needs to know about the
other.

---

### 2. Strategy Pattern

Defines a **family of interchangeable algorithms** and encapsulates each, allowing the algorithm to
vary independently from clients using it.

**When to use:**

- Multiple sorting/filtering algorithms, selected at runtime.
- Different authentication, payment, or caching strategies.
- Avoiding large `if-elif` chains for behavior selection.

**Implementation:**

```python
from abc import ABC, abstractmethod
from typing import List

class SortingStrategy(ABC):
    """Strategy interface."""
    @abstractmethod
    def sort(self, data: List[int]) -> List[int]:
        pass

class QuickSort(SortingStrategy):
    def sort(self, data: List[int]) -> List[int]:
        if len(data) <= 1:
            return data
        pivot = data[len(data) // 2]
        left = [x for x in data if x < pivot]
        middle = [x for x in data if x == pivot]
        right = [x for x in data if x > pivot]
        return self.sort(left) + middle + self.sort(right)

class MergeSort(SortingStrategy):
    def sort(self, data: List[int]) -> List[int]:
        if len(data) <= 1:
            return data
        mid = len(data) // 2
        left = self.sort(data[:mid])
        right = self.sort(data[mid:])
        return self._merge(left, right)

    def _merge(self, left: List[int], right: List[int]) -> List[int]:
        result = []
        i = j = 0
        while i < len(left) and j < len(right):
            if left[i] <= right[j]:
                result.append(left[i])
                i += 1
            else:
                result.append(right[j])
                j += 1
        result.extend(left[i:])
        result.extend(right[j:])
        return result

class Sorter:
    """Context: uses strategy."""
    def __init__(self, strategy: SortingStrategy):
        self.strategy = strategy

    def sort(self, data: List[int]) -> List[int]:
        return self.strategy.sort(data)

# Usage: choose algorithm at runtime
data = [5, 2, 8, 1, 9]
quick_sorter = Sorter(QuickSort())
print(quick_sorter.sort(data))  # [1, 2, 5, 8, 9]
```

**FastAPI Example (Caching Strategies):**

```python
class CachingStrategy(ABC):
    @abstractmethod
    async def get(self, key: str) -> str | None:
        pass

    @abstractmethod
    async def set(self, key: str, value: str, ttl: int):
        pass

class RedisStrategy(CachingStrategy):
    async def get(self, key: str) -> str | None:
        return await redis_client.get(key)

    async def set(self, key: str, value: str, ttl: int):
        await redis_client.set(key, value, ex=ttl)

class MemoryStrategy(CachingStrategy):
    def __init__(self):
        self._cache = {}

    async def get(self, key: str) -> str | None:
        return self._cache.get(key)

    async def set(self, key: str, value: str, ttl: int):
        self._cache[key] = value

class CacheService:
    def __init__(self, strategy: CachingStrategy):
        self.strategy = strategy

    async def get_cached(self, key: str):
        return await self.strategy.get(key)

    async def cache_result(self, key: str, value: str, ttl: int):
        await self.strategy.set(key, value, ttl)

# Dependency: select strategy based on config
def get_cache_service() -> CacheService:
    strategy = RedisStrategy() if get_settings().use_redis else MemoryStrategy()
    return CacheService(strategy)

@app.get("/data/{key}")
async def get_data(key: str, cache: CacheService = Depends(get_cache_service)):
    cached = await cache.get_cached(key)
    if cached:
        return {"data": cached, "source": "cache"}
    fresh_data = await fetch_data(key)
    await cache.cache_result(key, fresh_data, ttl=3600)
    return {"data": fresh_data, "source": "fresh"}
```

**Key principle:** Strategy allows you to select algorithms at runtime without modifying client
code.

---

### 3. Command Pattern

**Encapsulates a request as an object**, allowing you to parameterize clients with different
requests, queue/log operations, or support undo.

**When to use:**

- Task queues and job scheduling.
- Undo/redo implementations.
- Logging and auditing all operations.
- Decoupling request sender from receiver.

**Implementation (Task Queue with Undo):**

```python
from abc import ABC, abstractmethod
from typing import List

class Command(ABC):
    """Command interface."""
    @abstractmethod
    async def execute(self):
        pass

    @abstractmethod
    async def undo(self):
        pass

class EmailCommand(Command):
    """Concrete command: send email."""
    def __init__(self, email: str, subject: str, body: str):
        self.email = email
        self.subject = subject
        self.body = body
        self.sent = False

    async def execute(self):
        logger.info(f"Sending email to {self.email}: {self.subject}")
        self.sent = True

    async def undo(self):
        if self.sent:
            logger.info(f"Unsending email to {self.email}")
            self.sent = False

class PaymentCommand(Command):
    """Concrete command: process payment."""
    def __init__(self, user_id: int, amount: float):
        self.user_id = user_id
        self.amount = amount
        self.transaction_id: str | None = None

    async def execute(self):
        logger.info(f"Processing payment: user={self.user_id}, amount=${self.amount}")
        self.transaction_id = f"txn_{self.user_id}_{self.amount}"

    async def undo(self):
        if self.transaction_id:
            logger.info(f"Refunding transaction {self.transaction_id}")
            self.transaction_id = None

class CommandQueue:
    """Invoker: manages command execution and history."""
    def __init__(self):
        self.history: List[Command] = []
        self.redo_stack: List[Command] = []

    async def execute(self, command: Command):
        """Execute command and add to history."""
        await command.execute()
        self.history.append(command)
        self.redo_stack.clear()  # Clear redo on new command

    async def undo(self):
        """Undo last command."""
        if self.history:
            command = self.history.pop()
            await command.undo()
            self.redo_stack.append(command)

    async def redo(self):
        """Redo last undone command."""
        if self.redo_stack:
            command = self.redo_stack.pop()
            await command.execute()
            self.history.append(command)

# Usage
queue = CommandQueue()
await queue.execute(EmailCommand("user@example.com", "Confirmation", "Your order is confirmed"))
await queue.execute(PaymentCommand(user_id=123, amount=49.99))

await queue.undo()  # Undo payment
await queue.undo()  # Undo email
await queue.redo()  # Redo email
```

**FastAPI Task Queueing:**

```python
@app.post("/checkout")
async def checkout(order_data: dict, queue: CommandQueue = Depends(get_command_queue)) -> dict:
    """Queue commands for asynchronous processing."""
    charge_cmd = PaymentCommand(user_id=order_data["user_id"], amount=order_data["total"])
    email_cmd = EmailCommand(
        email=order_data["email"],
        subject="Order Confirmation",
        body=f"Total: ${order_data['total']}"
    )
    await queue.execute(charge_cmd)
    await queue.execute(email_cmd)
    return {"status": "queued", "order": order_data}
```

**Key principle:** Commands decouple the request (what to do) from the invoker (when/how to do it).

---

### 4. State Pattern

Allows an object to **alter its behavior when internal state changes**. The object appears to change
class.

**When to use:**

- Objects with multiple states and complex transitions (state machines).
- Workflow engines, order processing, user account statuses.
- Avoiding large `if-elif` chains based on state.

**Implementation:**

```python
from abc import ABC, abstractmethod

class OrderState(ABC):
    """State interface."""
    @abstractmethod
    async def confirm(self, order: "Order"):
        pass

    @abstractmethod
    async def cancel(self, order: "Order"):
        pass

    @abstractmethod
    async def ship(self, order: "Order"):
        pass

    @abstractmethod
    def can_cancel(self) -> bool:
        pass

class PendingState(OrderState):
    """Pending state: awaiting confirmation."""
    async def confirm(self, order: "Order"):
        logger.info("Order confirmed")
        order.state = ConfirmedState()

    async def cancel(self, order: "Order"):
        logger.info("Order cancelled")
        order.state = CancelledState()

    async def ship(self, order: "Order"):
        raise RuntimeError("Cannot ship: order not confirmed")

    def can_cancel(self) -> bool:
        return True

class ConfirmedState(OrderState):
    """Confirmed state: ready to ship."""
    async def confirm(self, order: "Order"):
        raise RuntimeError("Order already confirmed")

    async def cancel(self, order: "Order"):
        raise RuntimeError("Cannot cancel confirmed order")

    async def ship(self, order: "Order"):
        logger.info("Order shipped")
        order.state = ShippedState()

    def can_cancel(self) -> bool:
        return False

class ShippedState(OrderState):
    """Shipped state: final."""
    async def confirm(self, order: "Order"):
        raise RuntimeError("Order already shipped")

    async def cancel(self, order: "Order"):
        raise RuntimeError("Cannot cancel shipped order")

    async def ship(self, order: "Order"):
        raise RuntimeError("Order already shipped")

    def can_cancel(self) -> bool:
        return False

class CancelledState(OrderState):
    """Cancelled state: terminal."""
    async def confirm(self, order: "Order"):
        raise RuntimeError("Order is cancelled")

    async def cancel(self, order: "Order"):
        logger.info("Already cancelled")

    async def ship(self, order: "Order"):
        raise RuntimeError("Cannot ship cancelled order")

    def can_cancel(self) -> bool:
        return False

class Order:
    """Context: uses state."""
    def __init__(self, order_id: int):
        self.order_id = order_id
        self.state: OrderState = PendingState()

    async def confirm(self):
        await self.state.confirm(self)

    async def cancel(self):
        await self.state.cancel(self)

    async def ship(self):
        await self.state.ship(self)

# Usage
order = Order(order_id=123)
await order.confirm()  # PendingState → ConfirmedState
await order.ship()     # ConfirmedState → ShippedState
# await order.cancel()  # Raises RuntimeError: cannot cancel shipped order
```

**FastAPI Example:**

```python
@app.post("/orders/{order_id}/confirm")
async def confirm_order(order_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Transition order to confirmed state."""
    order = await get_order(order_id, db)
    try:
        await order.confirm()
        await db.commit()
        return {"order_id": order_id, "state": order.state.__class__.__name__}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

**Key principle:** State pattern eliminates complex conditional logic by encoding state transitions
as separate classes.

---

## Pattern Selection Guide

| Pattern       | Solves                           | Use When                                               |
| ------------- | -------------------------------- | ------------------------------------------------------ |
| **Singleton** | Single global instance           | Shared resource (config, logger, connection pool)      |
| **Factory**   | Object creation logic            | Multiple implementations, runtime selection            |
| **Builder**   | Complex construction             | Many optional params, fluent API                       |
| **Prototype** | Expensive object cloning         | Deep copying needed, template-based creation           |
| **Adapter**   | Incompatible interfaces          | Legacy system integration, third-party libs            |
| **Decorator** | Dynamic behavior attachment      | Composable features (logging, caching, auth)           |
| **Composite** | Tree structures                  | Hierarchical data (file system, org chart)             |
| **Facade**    | Complex subsystem simplification | Hiding internal complexity                             |
| **Proxy**     | Object access control            | Lazy loading, access control, logging                  |
| **Observer**  | One-to-many event notification   | Event systems, pub-sub, reactive updates               |
| **Strategy**  | Interchangeable algorithms       | Runtime algorithm selection, avoiding `if-elif` chains |
| **Command**   | Request encapsulation            | Task queues, undo/redo, operation logging              |
| **State**     | State-dependent behavior         | State machines, workflow engines, complex transitions  |

---

## Antipatterns to Avoid

### 1. Catching `Exception` (Too Broad)

**Antipattern:**

```python
try:
    do_something()
except Exception:  # ✗ Catches everything—even KeyboardInterrupt parent classes
    pass
```

**Why it hurts:** Swallows unexpected errors silently. Masks bugs during development. Hides
programming mistakes.

**Better:**

```python
try:
    do_something()
except ValueError as exc:  # ✓ Specific exception
    logger.error("Validation failed: %s", exc)
    raise
```

---

### 2. Magic Numbers / Strings

**Antipattern:**

```python
if status == 2:  # ✗ What is 2? Nobody knows without reading the whole file
    return "active"
```

**Why it hurts:** Unreadable. Changing the number means searching for all `2` literals. Breaks
self-documentation.

**Better:**

```python
from enum import IntEnum

class UserStatus(IntEnum):
    INACTIVE = 1
    ACTIVE = 2
    SUSPENDED = 3

if status == UserStatus.ACTIVE:  # ✓ Self-documenting
    return "active"
```

---

### 3. Mutable Default Arguments

**Antipattern:**

```python
def add_tag(tag: str, tags: list = []) -> list:  # ✗ Same list across ALL calls
    tags.append(tag)
    return tags
```

**Why it hurts:** Python evaluates defaults once at function definition. All callers share the same
`tags` list. Extremely subtle and hard to debug.

**Better:**

```python
def add_tag(tag: str, tags: list | None = None) -> list:  # ✓ None sentinel
    if tags is None:
        tags = []  # New list per call
    tags.append(tag)
    return tags
```

---

### 4. Heavy Work in `__init__`

**Antipattern:**

```python
class DatabaseService:
    def __init__(self):
        self.connection = connect_to_db()  # ✗ Network call in constructor
```

**Why it hurts:** Constructors should be fast and not fail. Network calls, file I/O, and heavy
computation in `__init__` delay object creation unpredictably.

**Better:**

```python
class DatabaseService:
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.connection = None  # ✓ Initialized later

    async def start(self):
        """Async startup: connect to DB after construction."""
        self.connection = await connect_to_db(self.db_url)
```

---

### 5. Type-Checking Instead of Duck Typing

**Antipattern:**

```python
if type(x) == list:  # ✗ Rigid type check
    return len(x)
```

**Why it hurts:** Excludes subclasses, tuples, and other sequences. Violates Python's EAFP
principle.

**Better:**

```python
try:
    return len(x)  # ✓ EAFP: works for any sized container
except TypeError:
    return 0
```

---

### 6. `except: pass` — Swallowing Exceptions

**Antipattern:**

```python
try:
    cache.delete(key)
except:  # ✗ Bare except catches EVERYTHING including SystemExit
    pass
```

**Why it hurts:** `except:` without a type catches `SystemExit`, `KeyboardInterrupt`, and
generator-internal exceptions. Even `except Exception: pass` can hide real problems.

**Better:**

```python
try:
    cache.delete(key)
except KeyError:  # ✓ Specific exception
    # Key already gone; safe to ignore.
    pass

# OR log the error
try:
    do_something()
except (ValueError, OSError) as exc:
    logger.warning("Operation failed: %s", exc)
```

---

### 7. Too-Wide `try` Blocks

**Antipattern:**

```python
try:
    user_id = int(raw_user_id)   # Can raise ValueError
    user = repo.get_user(user_id) # Can raise ValueError (elsewhere)
    send_email(user.email)        # Can raise ValueError (elsewhere)
except ValueError:  # ✗ Which line? Which ValueError?
    return
```

**Why it hurts:** `except ValueError` might hide a `ValueError` from a later line. You catch the
wrong error from the wrong place. Hard to debug.

**Better:**

```python
try:
    user_id = int(raw_user_id)  # ✓ Tight scope—only this can raise ValueError
except ValueError:
    logger.warning("Invalid user ID format: %s", raw_user_id)
    return

user = repo.get_user(user_id)
send_email(user.email)
```

---

### 8. Wildcard Imports

**Antipattern:**

```python
from utils import *   # ✗ What names are imported? Nobody knows.
from services import * # ✗ Silently overwrites existing names
```

**Why it hurts:** You don't know what's imported. Static analysis fails. Refactoring breaks
silently. Name collisions are hidden.

**Better:**

```python
from utils import parse_date, normalize_email  # ✓ Explicit
from services import UserService, PaymentService  # ✓ Clear
```

---

### 9. Shadowing Built-in Names

**Antipattern:**

```python
list = [1, 2, 3]         # ✗ Shadows built-in list()
id = "abc"               # ✗ Shadows built-in id()
filter = lambda x: x > 0 # ✗ Shadows built-in filter()
```

**Why it hurts:** Built-in functions no longer work in this scope. Later code using `list(...)` or
`id(...)` throws confusing errors.

**Better:**

```python
items = [1, 2, 3]              # ✓ Descriptive name
user_id = "abc"                # ✓ Clear, doesn't shadow
threshold_filter = lambda x: x > 0  # ✓ Explicit
```

---

### 10. Global Mutable State

**Antipattern:**

```python
CACHE = {}  # ✗ Global mutable state

def get_user(user_id: int) -> User:
    if user_id in CACHE:  # Behavior depends on execution order
        return CACHE[user_id]
    user = load_user(user_id)
    CACHE[user_id] = user  # Shared state, concurrency issues
    return user
```

**Why it hurts:** Behavior depends on execution history. Testing requires state teardown.
Concurrency breaks silently. Debugging is a nightmare.

**Better:**

```python
class UserService:
    """Service with explicit, scoped state."""
    def __init__(self):
        self._cache: dict[int, User] = {}  # ✓ Instance, not global

    async def get_user(self, user_id: int) -> User:
        if user_id in self._cache:
            return self._cache[user_id]
        user = await load_user(user_id)
        self._cache[user_id] = user
        return user
```

---

### 11. Deep Nesting Instead of Guard Clauses

**Antipattern:**

```python
def handle(request):
    if request.user:
        if request.user.is_active:              # ✗ Pyramid of doom
            if request.user.has_permission("edit"):
                return do_edit()
    return "forbidden"
```

**Why it hurts:** Logic buried under indents. Hard to scan. The "happy path" is hidden. Maintenance
becomes tedious.

**Better:**

```python
def handle(request) -> str:
    """Use early returns to keep code flat."""
    if not request.user:
        return "forbidden"  # ✓ Exit early
    if not request.user.is_active:
        return "forbidden"
    if not request.user.has_permission("edit"):
        return "forbidden"
    return do_edit()  # Happy path is clear
```

---

### 12. Comparing to `None` with `==`

**Antipattern:**

```python
if value == None:  # ✗ Wrong identity check
    ...
```

**Why it hurts:** `None` is a singleton; use identity comparison (`is`). Some objects can override
`==` and surprise you with unexpected behavior.

**Better:**

```python
if value is None:      # ✓ Identity check
    ...
if value is not None:  # ✓ Explicit
    ...
```

---

### 13. List Comprehensions for Side Effects

**Antipattern:**

```python
[send_email(u) for u in users]  # ✗ Builds list of None values for side effect
```

**Why it hurts:** List comprehensions are for building lists. Here you're wasting memory on `None`
values just to iterate. Confusing to readers.

**Better:**

```python
for user in users:  # ✓ Clear: iteration, not collection
    await send_email(user)
```

---

### 14. Using `print()` as Logging

**Antipattern:**

```python
print("Something happened", data)    # ✗ Unstructured, hard to filter/route
print(f"Error: {error_message}")      # ✗ Lost in stdout noise
```

**Why it hurts:** In production services, `print()` is unstructured noise. Impossible to filter,
correlate, or route. No timestamps, levels, or context.

**Better:**

```python
import logging

logger = logging.getLogger(__name__)

logger.info("Something happened: %s", data)   # ✓ Structured, filterable
logger.error("Error: %s", error_message)       # ✓ Log levels, integration
```

---

### 15. Not Using Context Managers for Resources

**Antipattern:**

```python
f = open("data.txt")   # ✗ Can leak if exception happens
data = f.read()
f.close()              # If exception above, this never runs
```

**Why it hurts:** If an exception happens between `open()` and `close()`, the file stays open. Same
with locks, connections, network sockets.

**Better:**

```python
with open("data.txt", encoding="utf-8") as f:  # ✓ Always closes, even on exception
    data = f.read()

# For async resources
async with httpx.AsyncClient() as client:  # ✓ Closes connection
    response = await client.get("https://example.com")
```

---

## Design Pattern Application Checklist

### Before Reaching for a Pattern

- [ ] Can you describe the pain in one sentence without naming a pattern?
- [ ] Is the friction coming from object creation, component boundaries, or behavior change?
- [ ] Would a simpler refactoring (extract method/class) remove the pain without a pattern?
- [ ] Does the pattern solve a problem you have TODAY, not a hypothetical future problem?
- [ ] If this is "for flexibility," can you name a concrete scenario where that flexibility is
      needed?

### Pattern-Specific Checks

- [ ] **Singleton**: Is there only ONE shared instance? (config, logger) — prefer `Depends()` in
      FastAPI.
- [ ] **Factory**: Are there multiple REAL implementations already selected at runtime?
- [ ] **Builder**: Does the object have many optional parameters causing caller confusion?
- [ ] **Prototype**: Is copying genuinely cheaper than constructing from scratch?
- [ ] **Adapter**: Are you bridging an incompatible external/legacy interface?
- [ ] **Decorator**: Is this behavior composable — can multiple decorators stack independently?
- [ ] **Decorator NOT overused**: Would straightforward inheritance or a plain function be simpler?
- [ ] **Composite**: Is the hierarchy actually recursive (nodes contain nodes)?
- [ ] **Facade**: Is complexity genuinely hidden, or just moved one level deeper?
- [ ] **Proxy**: Same interface as the real object? If not, consider Adapter instead.
- [ ] **Observer**: Are there truly multiple independent consumers of the same event?
- [ ] **Strategy**: More than one algorithm exists today (not speculative)?
- [ ] **Command**: Undo, audit log, or queue are concrete requirements?
- [ ] **State**: At least three distinct states with different transition rules?
- [ ] **All patterns**: Is the added indirection justified by the complexity being removed?
