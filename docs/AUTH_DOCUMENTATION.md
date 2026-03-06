# Authentication

## Authentication Strategy

Delta uses a dual-token authentication system:

1. **Access Token**: Short lived PASETO (1 hour) for API requests
2. **Refresh Token**: Long lived PASETO (7 days) for refreshing access tokens

Both tokens are stored as httponly cookies to prevent XSS attacks.

> **NOTE**: Refreshing of the Access token cookie is handled automatically by the backend when a protected endpoint is accessed.

## Token Structure

**Access Token Payload:**
```json
{
  "sub": "user-uuid",
  "type": "access",
  "exp": 1234567890
}
```

**Refresh Token Payload:**
```json
{
  "sub": "user-uuid",
  "type": "refresh",
  "exp": 1234567890
}
```

## Password Hashing

Passwords are first hashed via SHA-256 into a 64-character hexadecimal string before being re-hashed using Bcrypt with automatic salt generation:

```python
from app.core.security import get_hash, verify_hash

# Hash password
password_hash = get_hash("user_password_hash")

# Verify password
is_valid = verify_hash("user_password_hash", password_hash)
```

> **NOTE**: The password is also hashed in the frontend before it is sent during signup / login to the backend to ensure the actual password is never stored or transported at any point of time.

## Protected Endpoints

The `get_current_user` dependency can be used to protect endpoints:

```python
from app.deps import get_current_user
from app.models.user import User

@router.get("/protected")
def protected_endpoint(current_user: User = Depends(get_current_user)):
    # Endpoint code
    ...

```
