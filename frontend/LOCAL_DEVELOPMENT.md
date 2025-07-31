# Local Development Setup

This document explains how to configure Suna frontend for local development, including how to bypass authentication.

## Authentication Bypass for Local Development

For local development, you can disable authentication to avoid the need to set up Supabase authentication or log in repeatedly during development.

### How to Disable Authentication

1. **Create a `.env.local` file** in the `suna/frontend` directory:

```bash
# Create the file
touch suna/frontend/.env.local
```

2. **Add the following environment variables** to your `.env.local` file:

```bash
# Disable authentication for local development
NEXT_PUBLIC_DISABLE_AUTH=true

# Backend API URL (should match your running backend service)
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000

# Environment mode
NEXT_PUBLIC_ENV_MODE=local

# Supabase configuration (still required for other services)
NEXT_PUBLIC_SUPABASE_URL=your_supabase_project_url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key
```

3. **Restart your development server** to pick up the new environment variables:

```bash
cd suna/frontend
npm run dev
```

### What Happens When Authentication is Disabled

When `NEXT_PUBLIC_DISABLE_AUTH=true`, the following changes occur:

- **Middleware**: Skips all authentication checks and redirects
- **AuthProvider**: Provides a mock user with these details:
  - ID: `dev-user-id`
  - Email: `dev@local.dev`
  - Name: `Development User`
- **All protected routes**: Become accessible without login
- **User context**: Available throughout the app with mock user data

### Mock User Details

```typescript
{
  id: 'dev-user-id',
  email: 'dev@local.dev',
  user_metadata: {
    name: 'Development User',
    email: 'dev@local.dev',
  },
  // ... other standard Supabase user fields
}
```

### Re-enabling Authentication

To re-enable authentication for testing or production deployment:

1. **Set the environment variable to false** or remove it:
```bash
NEXT_PUBLIC_DISABLE_AUTH=false
```

2. **Or comment it out**:
```bash
# NEXT_PUBLIC_DISABLE_AUTH=true
```

3. **Restart your development server**

### Security Notes

- ⚠️ **Never use `NEXT_PUBLIC_DISABLE_AUTH=true` in production**
- ⚠️ **The `.env.local` file should not be committed to git**
- ✅ **Authentication is only bypassed when explicitly enabled**
- ✅ **Default behavior is secure (authentication required)**

### Environment Variables Reference

| Variable | Purpose | Example |
|----------|---------|---------|
| `NEXT_PUBLIC_DISABLE_AUTH` | Bypass authentication | `true` or `false` |
| `NEXT_PUBLIC_ENV_MODE` | Environment mode | `local`, `staging`, `production` |
| `NEXT_PUBLIC_BACKEND_URL` | Backend API URL | `http://localhost:8000` |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL | `https://your-project.supabase.co` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anonymous key | `eyJ...` |

### Troubleshooting

If authentication bypass isn't working:

1. **Check the browser console** for logs:
   - Should see: `🔓 Auth disabled - skipping middleware authentication checks`
   - Should see: `🔓 Auth disabled - providing mock user for development`

2. **Verify environment variables are loaded**:
   - Check Network tab in DevTools
   - Look for the config logs in browser console

3. **Restart the development server** after changing `.env.local`

4. **Clear browser cache and localStorage** if needed

### Example Local Development Workflow

```bash
# 1. Navigate to frontend directory
cd suna/frontend

# 2. Create or update .env.local
echo "NEXT_PUBLIC_DISABLE_AUTH=true" > .env.local
echo "NEXT_PUBLIC_BACKEND_URL=http://localhost:8000" >> .env.local
echo "NEXT_PUBLIC_ENV_MODE=local" >> .env.local

# 3. Start development server
npm run dev

# 4. Open browser to http://localhost:3000
# You should be automatically "logged in" with the mock user
```

This setup allows you to develop and test the Suna frontend without dealing with authentication flows while maintaining security by default.
