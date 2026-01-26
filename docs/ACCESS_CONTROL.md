# Access Control

## Roles
- `viewer`: view reports only
- `operator`: run pipeline + view reports
- `admin`: run pipeline, view reports, and modify policy

## Auth Tokens
Provide tokens via:
- Config: `auth_tokens = { "token-1" = "admin" }`
- Environment: `WAVEOS_AUTH_TOKENS=token1=admin,token2=operator`

## CLI Usage
```
waveos --role operator --token <token> run --in ./demo_data/run --baseline ./demo_data/baseline --out ./out
```

## Audit Logging
Auth decisions are logged with:
- principal
- role
- permission
- allowed/denied
