# Device Assignment Workflow Changes

## Overview

The device management workflow has been completely revamped. Previously, users could "claim" devices by entering a UUID. Now, **admins assign devices to users**, and users can only manage their assigned devices.

## What Changed

### 1. Admin Panel (Admin.tsx)
**New Features:**
- ✅ Admins can now assign devices to users
- ✅ New "Assign User" button for unassigned devices
- ✅ "Edit" button for already-assigned devices
- ✅ Modal to select user from dropdown and set device name
- ✅ Fetches all registered users via new `get_admin_users()` RPC function
- ✅ Updated info panel text to explain the new workflow

### 2. User Devices Page (DeviceList.tsx)
**Removed:**
- ❌ "Add Device" button and modal
- ❌ Device claiming functionality (users can't assign themselves devices)

**Kept:**
- ✅ Edit device functionality (name and plane assignment)
- ✅ Device listing (filtered by user_id - users only see their devices)
- ✅ Delete device functionality

**Updated:**
- Updated header text: "Contact an admin to get devices assigned to your account."
- Updated empty state: Shows message to contact admin

### 3. Database Migration (005_add_admin_user_management.sql)
**New SQL Functions:**
- `get_admin_users()` - Returns all registered users (admin-only)

**Updated RLS Policies:**
- Devices UPDATE policy now allows admins to update any device
- Users can still update their own devices (name and plane_id)

## New Workflow

### For Admins:
1. ESP32 sends data → Device auto-created with `user_id: NULL`
2. Admin sees unassigned device in Admin panel
3. Admin clicks "Assign User" button
4. Admin selects user from dropdown and optionally sets device name
5. Admin clicks "Assign Device"
6. User now sees device in their Devices page

### For Users:
1. Wait for admin to assign device to their account
2. Once assigned, device appears in Devices page
3. Edit device to:
   - Set/change device name
   - Assign device to a plane
4. Cannot change device ownership (user_id is set by admin only)

## How to Deploy

### Step 1: Run the New Migration
```bash
# In Supabase SQL Editor or via CLI
cd supa_sym
supabase db push
```

Or manually run the SQL from:
`supa_sym/supabase/migrations/005_add_admin_user_management.sql`

### Step 2: Deploy Frontend
The React components are already updated. Just deploy:
```bash
npm run build
# Deploy to your hosting (GitHub Pages, etc.)
```

### Step 3: Test the Workflow
1. **As Admin:**
   - Go to Admin panel
   - Find an unassigned device (or wait for ESP32 to create one)
   - Click "Assign User"
   - Select a user and click "Assign Device"

2. **As User:**
   - Go to Devices page
   - Verify assigned device shows up
   - Click "Edit" to change name or assign to plane
   - Verify you cannot change the device UUID

## Benefits

1. **Security** - Users can't claim devices they don't own
2. **Control** - Admins have full control over device ownership
3. **Clarity** - Clear separation between admin and user responsibilities
4. **Simplicity** - Users don't need to know device UUIDs

## Troubleshooting

### Device not showing up for user?
- Check Admin panel - is device assigned to correct user?
- Check user is logged in with correct account

### Admin can't assign devices?
- Verify admin user exists in `admin_users` table
- Check RLS policy: `get_admin_users()` requires admin privileges

### User trying to add device gets confused?
- Old "Add Device" UI is removed
- Update user documentation to direct them to contact admin

## Files Changed

1. `supa_sym/supabase/migrations/005_add_admin_user_management.sql` - New migration
2. `site_sym/src/components/Dashboard/Admin.tsx` - Added assignment modal
3. `site_sym/src/components/Dashboard/DeviceList.tsx` - Removed add device functionality

---

**Note:** This is a breaking change for users who were manually claiming devices. They will need to contact an admin to have devices assigned to them going forward.

