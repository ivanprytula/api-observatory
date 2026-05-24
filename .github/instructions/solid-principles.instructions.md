---
name: solid-principles
description:
    'SOLID principles for maintainable, flexible, and testable code. Covers Single Responsibility,
    Open-Closed, Liskov Substitution, Interface Segregation, and Dependency Inversion with Python
    examples for FastAPI services and distributed systems.'
applyTo: 'src/**/*.py, **/*.py'
---

# SOLID Principles for Clean, Maintainable Code

## Overview

SOLID is an acronym for **five design principles** that help make code more maintainable, flexible,
testable, and understandable. These principles are not Python-specific—they apply to all
object-oriented languages—but are especially powerful when applied consistently in distributed
systems and microservices.

| Principle                 | Purpose                                              | Symbol |
| ------------------------- | ---------------------------------------------------- | ------ |
| **S**ingle Responsibility | One reason to change per class                       | 🎯     |
| **O**pen-Closed           | Open for extension, closed for modification          | 🔒     |
| **L**iskov Substitution   | Subtypes substitutable without breaking behavior     | 🔄     |
| **I**nterface Segregation | Clients depend only on methods they use              | ✂️     |
| **D**ependency Inversion  | Depend on abstractions, not concrete implementations | 🔗     |

---

## 1. Single Responsibility Principle (SRP)

**Definition:** Every class, function, or module should have one and only one reason to change. It
should do one thing, and do it well.

### The Problem: Multiple Responsibilities

When a class violates SRP, it becomes a "god class"—a monolithic object trying to handle everything.

**Antipattern:**

```python
# ✗ Bad: UserOrderService does too much
class UserOrderService:
    """Violates SRP: mixes user and order logic."""

    def create_user(self, name: str, email: str) -> User:
        """Create user and persist."""
        # User creation logic
        pass

    def get_user(self, user_id: int) -> User:
        """Fetch user from database."""
        pass

    def create_order(self, user_id: int, items: list) -> Order:
        """Create order for user."""
        # Order creation logic
        pass

    def apply_discount(self, order_id: int, discount: float) -> None:
        """Apply discount to order."""
        pass

    def send_notification(self, user_id: int, message: str) -> None:
        """Send email notification."""
        pass

    def generate_report(self) -> str:
        """Generate daily sales report."""
        pass

# Problems:
# - Testing is hard: must mock user + order + email + reporting
# - Changes to order logic affect user functionality
# - Reusing user logic requires pulling in order logic
# - At 500+ lines, it becomes unmaintainable
```

### The Solution: Separate Concerns

Each class should have a single, well-defined responsibility:

```python
# ✓ Good: Separated responsibilities
from abc import ABC, abstractmethod

class UserService:
    """Handles user creation, retrieval, and updates only."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_user(self, name: str, email: str) -> User:
        user = UserModel(name=name, email=email)
        self.db.add(user)
        await self.db.commit()
        return user

    async def get_user(self, user_id: int) -> User | None:
        query = select(UserModel).where(UserModel.id == user_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

class OrderService:
    """Handles order creation and management only."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_order(self, user_id: int, items: list) -> Order:
        order = OrderModel(user_id=user_id, items=items)
        self.db.add(order)
        await self.db.commit()
        return order

    async def apply_discount(self, order_id: int, discount: float) -> None:
        order = await self.get_order(order_id)
        order.discount = discount
        await self.db.commit()

class NotificationService:
    """Handles all notification logic (email, SMS, etc.)."""

    async def send_email(self, email: str, subject: str, body: str) -> dict:
        # Email sending logic
        logger.info(f"Email sent to {email}")
        return {"status": "sent"}

    async def send_sms(self, phone: str, message: str) -> dict:
        # SMS sending logic
        logger.info(f"SMS sent to {phone}")
        return {"status": "sent"}

class ReportingService:
    """Handles report generation only."""

    async def generate_daily_report(self, db: AsyncSession) -> dict:
        # Report generation logic
        pass

# Benefits:
# - Easy to test: mock only the service you're testing
# - Independent changes: order logic changes don't affect user logic
# - Reusable: UserService can be used anywhere
# - Maintainable: each class is ~50-100 lines
```

### FastAPI Routes with SRP

```python
from fastapi import FastAPI, Depends

app = FastAPI()

# ✓ Routes delegate to services (single responsibility per route)
@app.post("/users", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    service: UserService = Depends(get_user_service),
) -> UserResponse:
    """Route: accepts input, calls service, returns output."""
    user = await service.create_user(user_data.name, user_data.email)
    return UserResponse.model_validate(user)

@app.post("/orders", response_model=OrderResponse)
async def create_order(
    order_data: OrderCreate,
    service: OrderService = Depends(get_order_service),
) -> OrderResponse:
    """Route: accepts input, calls service, returns output."""
    order = await service.create_order(order_data.user_id, order_data.items)
    return OrderResponse.model_validate(order)

# ✓ Route handles HTTP concerns only; service handles business logic
# ✓ Services are testable without FastAPI
```

### SRP Checklist

- [ ] Each class has a singular, clear purpose (easily describable in one sentence)
- [ ] Class is unlikely to change for multiple reasons
- [ ] Responsibilities aren't leaking into other classes
- [ ] Services are independent and reusable
- [ ] Tests don't need to mock multiple unrelated services

---

## 2. Open-Closed Principle (OCP)

**Definition:** Software entities (classes, modules, functions) should be **open for extension** but
**closed for modification**. Add new functionality via extension, not by modifying existing code.

### The Problem: Continuous Modification

Generic code with giant if-else chains breaks OCP:

```python
# ✗ Bad: Must modify when adding new payment processors
class PaymentService:
    """Violates OCP: must modify for each new payment method."""

    async def process_payment(self, method: str, amount: float) -> dict:
        if method == "credit_card":
            # Credit card logic
            logger.info(f"Charging credit card: ${amount}")
            return {"status": "success", "method": "credit_card"}

        elif method == "paypal":
            # PayPal logic
            logger.info(f"Charging PayPal: ${amount}")
            return {"status": "success", "method": "paypal"}

        elif method == "crypto":
            # Crypto logic
            logger.info(f"Charging crypto: ${amount}")
            return {"status": "success", "method": "crypto"}

        # Add new payment method? Must modify this class!
        else:
            raise ValueError(f"Unknown payment method: {method}")

# Problems:
# - Every new payment method requires modifying this class
# - Risk of breaking existing methods when adding new ones
# - Hard to test: all branches tested together
# - Violates "closed for modification"
```

### The Solution: Polymorphism via Abstraction

Define an abstract interface and extend via concrete implementations:

```python
from abc import ABC, abstractmethod

# Abstract interface (extension point)
class PaymentProcessor(ABC):
    """Define payment processing contract."""

    @abstractmethod
    async def process(self, amount: float) -> dict:
        """Process payment. Returns result dict."""
        pass

    @abstractmethod
    def supports_refund(self) -> bool:
        """Whether this processor supports refunds."""
        pass

# Concrete implementations (extensions)
class CreditCardProcessor(PaymentProcessor):
    """Credit card payment processor."""

    async def process(self, amount: float) -> dict:
        logger.info(f"Processing credit card: ${amount}")
        # Actual credit card processing
        return {"status": "success", "method": "credit_card", "amount": amount}

    def supports_refund(self) -> bool:
        return True

class PayPalProcessor(PaymentProcessor):
    """PayPal payment processor."""

    async def process(self, amount: float) -> dict:
        logger.info(f"Processing PayPal: ${amount}")
        # Actual PayPal processing
        return {"status": "success", "method": "paypal", "amount": amount}

    def supports_refund(self) -> bool:
        return True

class CryptoProcessor(PaymentProcessor):
    """Cryptocurrency payment processor."""

    async def process(self, amount: float) -> dict:
        logger.info(f"Processing crypto: ${amount}")
        # Actual crypto processing
        return {"status": "success", "method": "crypto", "amount": amount}

    def supports_refund(self) -> bool:
        return False  # Crypto doesn't support refunds

# Factory for creating processors (closed for modification)
class PaymentProcessorFactory:
    """Factory encapsulates processor creation."""

    _processors: dict[str, type[PaymentProcessor]] = {
        "credit_card": CreditCardProcessor,
        "paypal": PayPalProcessor,
        "crypto": CryptoProcessor,
    }

    @classmethod
    def create(cls, method: str) -> PaymentProcessor:
        """Get processor or raise error."""
        if method not in cls._processors:
            raise ValueError(f"Unknown payment method: {method}")
        return cls._processors[method]()

# Service: closed for modification, open for extension
class PaymentService:
    """Closed for modification, open for extension."""

    async def process_payment(self, method: str, amount: float) -> dict:
        # ✓ Get processor via factory (abstraction)
        processor = PaymentProcessorFactory.create(method)
        # ✓ Call via abstract interface (polymorphism)
        return await processor.process(amount)

# Adding a new payment method (e.g., Apple Pay)?
# ✓ Create new class: ApplePayProcessor(PaymentProcessor)
# ✓ Register in factory: _processors["apple_pay"] = ApplePayProcessor
# ✓ No modification to PaymentService
# ✓ Extend, not modify!

class ApplePayProcessor(PaymentProcessor):
    """New payment processor (extension, not modification)."""

    async def process(self, amount: float) -> dict:
        logger.info(f"Processing Apple Pay: ${amount}")
        return {"status": "success", "method": "apple_pay", "amount": amount}

    def supports_refund(self) -> bool:
        return True

# Register the new processor (one-liner)
PaymentProcessorFactory._processors["apple_pay"] = ApplePayProcessor
```

### FastAPI: Open for Extension

```python
# ✓ Routes are open for extension through specification
@app.post("/pay")
async def pay(
    payment_request: PaymentRequest,
    service: PaymentService = Depends(get_payment_service),
) -> dict:
    """Route is generic; service handles any processor."""
    return await service.process_payment(
        payment_request.method,
        payment_request.amount
    )

# Adding a new endpoint? No modification to existing code:
@app.post("/pay/instant")  # New endpoint
async def pay_instant(
    payment_data: InstantPaymentRequest,
    service: PaymentService = Depends(get_payment_service),
) -> dict:
    """New endpoint via extension."""
    # Can reuse same service
    return await service.process_payment(payment_data.method, payment_data.amount)
```

### OCP Checklist

- [ ] New functionality added via extension (new classes/modules), not modification
- [ ] Abstract contracts defined for varying behavior (interfaces, base classes)
- [ ] Concrete implementations plugged into abstractions
- [ ] Factory or dependency injection used to select implementations
- [ ] Existing classes rarely (never?) modified when requirements change
- [ ] No giant if-elif chains; use polymorphism instead

---

## 3. Liskov Substitution Principle (LSP)

**Definition:** Subtypes must be substitutable for their base types without breaking the program's
behavior. If S is a subtype of T, then objects of type S may be substituted for objects of type T
without altering correctness.

### The Problem: Unexpected Behavior in Subtypes

When a subclass violates the contract of its parent, substitution breaks:

```python
# ✗ Bad: OnlineOrderService violates the contract
class OrderProcessor(ABC):
    """Contract: process an order and print receipt."""

    @abstractmethod
    async def process(self) -> dict:
        pass

    @abstractmethod
    def print_receipt(self) -> str:
        """Print receipt—required for all subtypes."""
        pass

class OfflineOrderProcessor(OrderProcessor):
    """Offline orders: process and print receipt."""

    async def process(self) -> dict:
        return {"status": "processed", "type": "offline"}

    def print_receipt(self) -> str:
        return "--- RECEIPT (OFFLINE) ---\nOrder processed...\n---"

class OnlineOrderProcessor(OrderProcessor):
    """Online orders: violate LSP!"""

    async def process(self) -> dict:
        return {"status": "processed", "type": "online"}

    def print_receipt(self) -> str:
        # ✗ Violates contract: throws exception instead of printing
        raise NotImplementedError("Online orders can't print receipts")

# Client code assumes contract
async def handle_order(processor: OrderProcessor) -> None:
    """Assumes all processors have print_receipt."""
    await processor.process()
    print(processor.print_receipt())  # ✗ Crashes if OnlineOrderProcessor!

# This breaks; client expects substitution to work:
offline_proc = OfflineOrderProcessor()
online_proc = OnlineOrderProcessor()
await handle_order(offline_proc)  # ✓ Works
await handle_order(online_proc)   # ✗ NotImplementedError!
```

### The Solution: Correct Class Hierarchy

Respect the contract; use composition or separate hierarchies:

```python
# Fix 1: Separate concerns via different abstractions
class OrderProcessor(ABC):
    """Handles order processing—required for all."""

    @abstractmethod
    async def process(self) -> dict:
        pass

class ReceiptPrinter(ABC):
    """Handles receipt printing—optional."""

    @abstractmethod
    def print_receipt(self) -> str:
        pass

# Offline: process + print
class OfflineOrderProcessor(OrderProcessor, ReceiptPrinter):
    """Offline orders: full functionality."""

    async def process(self) -> dict:
        return {"status": "processed", "type": "offline"}

    def print_receipt(self) -> str:
        return "--- RECEIPT (OFFLINE) ---\n..."

# Online: process only (no printing)
class OnlineOrderProcessor(OrderProcessor):
    """Online orders: process only, no printing."""

    async def process(self) -> dict:
        return {"status": "processed", "type": "online"}

# Client code: safe substitution
async def handle_order(processor: OrderProcessor) -> None:
    """All processors can do this."""
    await processor.process()
    # ✓ Check if printer capability exists before using
    if isinstance(processor, ReceiptPrinter):
        print(processor.print_receipt())

# Both work safely:
offline_proc = OfflineOrderProcessor()
online_proc = OnlineOrderProcessor()
await handle_order(offline_proc)  # ✓ Prints receipt
await handle_order(online_proc)   # ✓ Skips printing (no error)
```

**Fix 2: Composition (Preferred)**

```python
# Inject receipt printing as optional dependency
class OrderService:
    """Service that processes orders."""

    def __init__(
        self,
        processor: OrderProcessor,
        receipt_printer: ReceiptPrinter | None = None,
    ):
        self.processor = processor
        self.receipt_printer = receipt_printer

    async def handle_order(self) -> dict:
        result = await self.processor.process()

        # Conditionally print (respects contract)
        if self.receipt_printer:
            print(self.receipt_printer.print_receipt())

        return result

# Usage
offline_service = OrderService(
    processor=OfflineOrderProcessor(),
    receipt_printer=OfflineReceiptPrinter(),  # Optional
)

online_service = OrderService(
    processor=OnlineOrderProcessor(),
    receipt_printer=None,  # No printer for online
)

# Both work correctly; no violations
await offline_service.handle_order()
await online_service.handle_order()
```

### LSP with FastAPI

```python
# ✓ Define a PaymentMethod contract
class PaymentMethod(ABC):
    @abstractmethod
    async def charge(self, amount: float) -> dict:
        pass

# All concrete implementations honor the contract
class CreditCardMethod(PaymentMethod):
    async def charge(self, amount: float) -> dict:
        return {"status": "charged", "amount": amount}

# Client code: safe substitution
@app.post("/checkout")
async def checkout(
    payment_data: PaymentRequest,
    method: PaymentMethod = Depends(get_payment_method),
) -> dict:
    """Works with any PaymentMethod subtype."""
    return await method.charge(payment_data.amount)
```

### LSP Checklist

- [ ] All subtypes honor parent class contracts
- [ ] Subclass doesn't throw unexpected exceptions
- [ ] Subclass doesn't remove or restrict parent functionality
- [ ] Substitution doesn't break client code behavior
- [ ] Use composition (optional dependencies) instead of forced inheritance
- [ ] Test substitution: `isinstance(subtype, parent_type)` implementations work uniformly

---

## 4. Interface Segregation Principle (ISP)

**Definition:** Clients should not depend on interfaces they don't use. Don't force clients to
implement methods they don't need.

### The Problem: Fat Interfaces

Fat, all-in-one interfaces force unnecessary implementations:

```python
# ✗ Bad: Fat interface; not all orders need all methods
class OrderService(ABC):
    """One bloated interface."""

    @abstractmethod
    def create_order(self) -> dict:
        pass

    @abstractmethod
    def apply_discount(self) -> dict:
        pass

    @abstractmethod
    def print_receipt(self) -> str:
        pass

    @abstractmethod
    def schedule_delivery(self, date: str) -> dict:
        pass

# Offline orders: forced to implement methods they don't use
class OfflineOrderService(OrderService):
    def create_order(self) -> dict:
        return {"status": "created"}

    def apply_discount(self) -> dict:
        raise NotImplementedError("Offline orders don't support discounts")

    def print_receipt(self) -> str:
        raise NotImplementedError("Offline has no receipts")

    def schedule_delivery(self, date: str) -> dict:
        raise NotImplementedError("Offline doesn't schedule delivery")

# Online orders: forced to implement methods they don't use
class OnlineOrderService(OrderService):
    def create_order(self) -> dict:
        return {"status": "created"}

    def apply_discount(self) -> dict:
        return {"discount": 0.10}  # Online supports discounts

    def print_receipt(self) -> str:
        return "Digital receipt..."  # Online can email receipts

    def schedule_delivery(self, date: str) -> dict:
        return {"scheduled": date}  # Online needs shipping

# Problems:
# - Both classes forced to implement unwanted methods
# - Raises NotImplementedError (violated LSP!)
# - Violates both ISP and LSP
```

### The Solution: Segregate Interfaces

Split large interfaces into smaller, focused contracts:

```python
# ✓ Good: Segregated interfaces, each focused
class OrderCreator(ABC):
    """Create orders—required for all order types."""

    @abstractmethod
    async def create_order(self, data: dict) -> dict:
        pass

class DiscountApplier(ABC):
    """Apply discounts—only for applicable orders."""

    @abstractmethod
    async def apply_discount(self, discount_code: str) -> float:
        pass

class ReceiptGenerator(ABC):
    """Generate receipts—only for applicable orders."""

    @abstractmethod
    def generate_receipt(self) -> str:
        pass

class DeliveryScheduler(ABC):
    """Schedule delivery—only for applicable orders."""

    @abstractmethod
    async def schedule_delivery(self, date: str) -> dict:
        pass

# Offline: only implements what it needs
class OfflineOrderService(OrderCreator, ReceiptGenerator):
    """Offline orders: create + print receipt."""

    async def create_order(self, data: dict) -> dict:
        return {"status": "created", "type": "offline"}

    def generate_receipt(self) -> str:
        return "Physical receipt..."

# Online: implements its capabilities
class OnlineOrderService(
    OrderCreator,
    DiscountApplier,
    ReceiptGenerator,
    DeliveryScheduler,
):
    """Online orders: full capabilities."""

    async def create_order(self, data: dict) -> dict:
        return {"status": "created", "type": "online"}

    async def apply_discount(self, discount_code: str) -> float:
        # Lookup discount for code
        return 0.15

    def generate_receipt(self) -> str:
        return "Digital receipt (email)..."

    async def schedule_delivery(self, date: str) -> dict:
        # Schedule with logistics
        return {"scheduled": date}

# Client: only depends on what it uses
async def create_and_discount(
    service: OrderCreator,
    discount_applicator: DiscountApplier | None = None,
) -> dict:
    order = await service.create_order({"items": [...]})

    if discount_applicator:
        discount = await discount_applicator.apply_discount("SAVE10")
        order["discount"] = discount

    return order

# Both services work correctly:
await create_and_discount(OfflineOrderService())  # No discount capability
await create_and_discount(OnlineOrderService())   # Uses discount
```

### FastAPI: Segregated Endpoints

```python
# ✓ Each endpoint depends only on capabilities it uses
@app.post("/orders/offline", response_model=OrderResponse)
async def create_offline_order(
    data: OfflineOrderData,
    creator: OrderCreator = Depends(get_offline_service),
) -> OrderResponse:
    """Offline endpoint—doesn't expect discount support."""
    return await creator.create_order(data)

@app.post("/orders/online", response_model=OrderResponse)
async def create_online_order(
    data: OnlineOrderData,
    creator: OrderCreator = Depends(get_online_service),
    discounter: DiscountApplier = Depends(get_online_service),
) -> OrderResponse:
    """Online endpoint—uses discount capability."""
    order = await creator.create_order(data)
    if data.discount_code:
        discount = await discounter.apply_discount(data.discount_code)
        order["discount"] = discount
    return order
```

### ISP Checklist

- [ ] Interfaces focused on a single capability
- [ ] No methods raise `NotImplementedError`
- [ ] Classes implement only interfaces they genuinely use
- [ ] Clients depend on minimal interface contracts
- [ ] Easy to add new capabilities without modifying existing contracts
- [ ] No "fat" interfaces with dozens of methods

---

## 5. Dependency Inversion Principle (DIP)

**Definition:** High-level modules should not depend on low-level modules. Both should depend on
abstractions. Abstractions should not depend on details; details should depend on abstractions.

### The Problem: Hard Coupling to Low-Level Details

Services tightly coupled to concrete implementations:

```python
# ✗ Bad: High-level depends on low-level concrete details
class EmailService:
    """Low-level: concrete email implementation."""

    async def send(self, email: str, message: str) -> dict:
        logger.info(f"Email to {email}: {message}")
        return {"status": "sent"}

class OrderService:
    """High-level: depends on concrete EmailService."""

    def __init__(self):
        # ✗ Tightly coupled to concrete EmailService
        self.notification_service = EmailService()

    async def place_order(self, order_data: dict) -> dict:
        order = await self._create_order(order_data)
        # ✗ Calls concrete service
        await self.notification_service.send(
            order_data["email"],
            f"Order {order['id']} confirmed"
        )
        return order

# Problems:
# - OrderService changes if email changes (tight coupling)
# - Can't test OrderService without sending real emails
# - Can't swap email for SMS or Slack
# - Violates DIP: high-level depends on low-level
```

### The Solution: Depend on Abstractions

Invert dependency direction via interfaces:

```python
from abc import ABC, abstractmethod

# Abstraction: high-level and low-level both depend on this
class NotificationsService(ABC):
    """Abstract notification contract."""

    @abstractmethod
    async def send(self, recipient: str, message: str) -> dict:
        pass

# Low-level: concrete implementations depend on abstraction
class EmailNotifier(NotificationsService):
    """Concrete: email notifications."""

    async def send(self, recipient: str, message: str) -> dict:
        logger.info(f"Sending email to {recipient}: {message}")
        # Actual email sending
        return {"status": "sent", "channel": "email"}

class SmsNotifier(NotificationsService):
    """Concrete: SMS notifications."""

    async def send(self, recipient: str, message: str) -> dict:
        logger.info(f"Sending SMS to {recipient}: {message}")
        # Actual SMS sending
        return {"status": "sent", "channel": "sms"}

class SlackNotifier(NotificationsService):
    """Concrete: Slack notifications."""

    async def send(self, recipient: str, message: str) -> dict:
        logger.info(f"Posting to Slack {recipient}: {message}")
        # Actual Slack posting
        return {"status": "sent", "channel": "slack"}

# High-level: depends on abstraction, not concrete details
class OrderService:
    """High-level: depends on NotificationsService abstraction."""

    def __init__(self, notifier: NotificationsService):
        # ✓ Injected abstraction (DIP)
        self.notifier = notifier

    async def place_order(self, order_data: dict) -> dict:
        order = await self._create_order(order_data)

        # ✓ Uses abstraction; doesn't care about concrete type
        await self.notifier.send(
            order_data["email"],
            f"Order {order['id']} confirmed"
        )
        return order

# Benefits:
# - OrderService is independent of notification details
# - Easy to test: inject mock notifier
# - Easy to extend: add new notifier without changing OrderService
# - Easy to swap: use SMS instead of email
```

### Dependency Injection: The Key to DIP

```python
# Dependency injection: inject abstraction at creation
def get_order_service(
    notifier: NotificationsService = Depends(get_notifier),
) -> OrderService:
    """Factory: creates OrderService with injected notifier."""
    return OrderService(notifier=notifier)

# Select concrete implementation based on config
def get_notifier() -> NotificationsService:
    """Select notifier based on environment."""
    if get_settings().notification_channel == "email":
        return EmailNotifier()
    elif get_settings().notification_channel == "sms":
        return SmsNotifier()
    elif get_settings().notification_channel == "slack":
        return SlackNotifier()
    else:
        raise ValueError("Unknown notification channel")

# FastAPI routes depend on abstraction
@app.post("/orders")
async def create_order(
    order_data: OrderCreate,
    service: OrderService = Depends(get_order_service),
) -> dict:
    """Route uses service with injected notifier."""
    return await service.place_order(order_data.dict())

# Testing: inject mock notifier
class MockNotifier(NotificationsService):
    async def send(self, recipient: str, message: str) -> dict:
        return {"status": "sent", "channel": "mock"}

async def test_place_order():
    mock_notifier = MockNotifier()
    service = OrderService(notifier=mock_notifier)
    result = await service.place_order({"email": "test@example.com"})
    assert result["status"] == "created"
    # No real emails sent!
```

### DIP with FastAPI Services

```python
# ✓ Service depends on abstractions
class PaymentProcessor(ABC):
    @abstractmethod
    async def charge(self, amount: float) -> dict:
        pass

class AuditLogger(ABC):
    @abstractmethod
    async def log(self, action: str, details: dict) -> None:
        pass

# High-level service: depends on abstractions
class CheckoutService:
    def __init__(
        self,
        processor: PaymentProcessor,
        audit_logger: AuditLogger,
    ):
        self.processor = processor
        self.audit_logger = audit_logger

    async def checkout(self, order_data: dict) -> dict:
        # Uses abstractions; doesn't care about details
        payment = await self.processor.charge(order_data["amount"])
        await self.audit_logger.log("checkout", order_data)
        return payment

# Dependency configuration (one place to change)
def get_checkout_service(
    processor: PaymentProcessor = Depends(get_payment_processor),
    logger: AuditLogger = Depends(get_audit_logger),
) -> CheckoutService:
    return CheckoutService(processor=processor, audit_logger=logger)

@app.post("/checkout")
async def checkout(
    order_data: OrderData,
    service: CheckoutService = Depends(get_checkout_service),
) -> dict:
    return await service.checkout(order_data.dict())
```

### DIP Checklist

- [ ] High-level modules don't import low-level concrete classes
- [ ] Both depend on abstractions (interfaces, base classes)
- [ ] Dependencies injected at construction or via dependency injection
- [ ] Easy to swap implementations (testing, config-based selection)
- [ ] No circular dependencies (high → low → high)
- [ ] Configuration/wiring centralized in one place (factory functions)
- [ ] Services testable without concrete implementations (mock injections)

---

## SOLID in data-pipeline-async

### Example: Applying SOLID to Scenario 1

**Single Responsibility:**

- `UserService`: User CRUD only
- `OrderService`: Order management only
- `NotificationService`: Notifications only

**Open-Closed:**

- New order types added via `OrderProcessor` subclasses
- New payment methods added via `PaymentMethod` subclasses

**Liskov Substitution:**

- All `OrderProcessor` implementations honor the processing contract
- All `PaymentMethod` implementations honor the charging contract

**Interface Segregation:**

- `OrderCreator`, `DiscountApplier`, `DeliveryScheduler` as separate interfaces
- Offline orders implement only what they need

**Dependency Inversion:**

- `CheckoutService` depends on `PaymentProcessor` abstraction, not `CreditCardProcessor`
- `OrderService` depends on `NotificationService` abstraction, not `EmailService`
- Implementations selected via dependency injection

---

## SOLID Violations Checklist

### Red Flags to Watch For

- [ ] Class/function name includes "Service", "Manager", "Processor", "Controller" (>1
      responsibility?)
- [ ] Giant if-elif chains instead of polymorphism
- [ ] Subclass throws `NotImplementedError` or `raise NotImplemented`
- [ ] Class implements methods it doesn't use
- [ ] Service creates its own dependencies (`self.dependency = DependencyClass()`)
- [ ] High-level code imports and uses low-level concrete classes
- [ ] Tests require complex setup of multiple mocked services
- [ ] Changes to one service break other services
- [ ] Reusing code requires copying-and-pasting

### When Something Smells Wrong

**Question to ask:**

1. Does this class have multiple reasons to change? → SRP violation
2. Would adding a new feature require modifying this class? → OCP violation
3. Would substituting this subtype break the program? → LSP violation
4. Does this class implement methods it doesn't use? → ISP violation
5. Does this depend on concrete details instead of abstractions? → DIP violation

**Fix approach:**

1. Extract responsibilities into separate classes (SRP)
2. Use polymorphism instead of conditionals (OCP)
3. Fix the class hierarchy or use composition (LSP)
4. Split the interface into smaller contracts (ISP)
5. Inject abstractions instead of creating concrete instances (DIP)

---

## Integration with Design Patterns

SOLID principles complement design patterns:

| Pattern   | Primary SOLID Principle |
| --------- | ----------------------- |
| Factory   | SRP, OCP, DIP           |
| Strategy  | OCP, DIP                |
| Decorator | OCP                     |
| Adapter   | OCP, LSP                |
| Proxy     | DIP                     |
| Observer  | DIP                     |
| Command   | DIP, ISP                |
| State     | OCP                     |

---

## Practical Guidelines

1. **Start with SRP:** Make sure each class does one thing.
2. **Then apply OCP:** When changes come, extend (don't modify).
3. **Ensure LSP:** All subtypes are safe substitutes.
4. **Keep ISP in mind:** Don't force unnecessary dependencies.
5. **End with DIP:** Depend on abstractions, inject concrete details.

**Order of Application:** Start with dependencies (DIP) → Shape interfaces (ISP) → Define behaviors
(OCP) → Structure hierarchies (LSP) → Isolate responsibilities (SRP).

---

## Quick Checklist: Code Review

- [ ] **S**: Each class has one reason to change
- [ ] **O**: New features addable without modifying existing classes
- [ ] **L**: Subtypes safely substitutable for base types
- [ ] **I**: Classes depend only on methods they use
- [ ] **D**: High-level depends on abstractions, not low-level concretions
- [ ] **Tests**: Testable with minimal mocking/setup
- [ ] **Reusability**: Services reusable in different contexts
- [ ] **Maintenance**: Changes don't cascade unpredictably
