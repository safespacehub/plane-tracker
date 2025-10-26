# Admin System

Super simple admin system. Admins can see all devices, planes, and sessions across all users.

## Setup

### 1. Run the migration

In Supabase SQL Editor, run:
```
supa_sym/supabase/migrations/002_admin_users.sql
```

### 2. Make yourself admin

In Supabase SQL Editor, run this (replace the email):
```sql
INSERT INTO admin_users (user_id, notes)
SELECT id, 'Initial admin user'
FROM auth.users
WHERE email = 'your-email@example.com';
```

### 3. Log out and back in

You'll see an "Admin" link in the sidebar. Click it to see all devices in the system.

## What You Get

- **Admin page** - View all devices with UUIDs, owners, planes, and last seen times
- **Search & filter** - Find devices fast
- **Copy UUIDs** - One click to copy device UUIDs
- **God mode** - Admins can see everything (read-only)

## How It Works

- `admin_users` table = who's an admin
- RLS policies updated = admins bypass user restrictions
- `get_admin_devices()` function = fetches device data with owner emails
- Sidebar checks if you're admin and shows the link

That's it. Simple. Works.

