# Plane Tracker Deployment Guide

Complete guide to deploying your plane tracking system from scratch.

## Overview

This system consists of three main components:
1. **ESP32 Device** - CircuitPython tracker on your plane
2. **Supabase Backend** - Database and edge function
3. **React Portal** - Web interface for management

## Step 1: Set Up Supabase

### Create Project

1. Go to [supabase.com](https://supabase.com) and sign up
2. Create a new project
3. Wait for project to finish provisioning
4. Note your project URL and anon key

### Run Database Migration

1. Go to SQL Editor in Supabase Dashboard
2. Copy contents from `supa_sym/migrations/001_initial_schema.sql`
3. Paste and run the SQL
4. Verify tables created: `planes`, `devices`, `sessions`

### Deploy Edge Function

#### Option A: Using Supabase CLI (Recommended)

```bash
# Install Supabase CLI
npm install -g supabase

# Login
supabase login

# Link to your project
supabase link --project-ref your-project-ref

# Deploy edge function
cd supa_sym
supabase functions deploy ingest
```

#### Option B: Manual Deployment

1. Go to Edge Functions in Supabase Dashboard
2. Click "Create a new function"
3. Name it `ingest`
4. Copy contents from `supa_sym/functions/ingest/index.ts`
5. Paste and deploy

### Get Service Role Key

1. Go to Project Settings > API
2. Copy the `service_role` key (keep this secret!)
3. The edge function needs this - it's auto-configured in Supabase

## Step 2: Configure ESP32

### Flash CircuitPython

1. Download CircuitPython for ESP32 from [circuitpython.org](https://circuitpython.org)
2. Flash to your ESP32 using esptool or web installer
3. Board will appear as USB drive

### Install Required Libraries

Copy these libraries to ESP32's `lib` folder:
- `adafruit_ntp.mpy`
- `adafruit_requests.mpy`

Download from [CircuitPython Bundle](https://circuitpython.org/libraries)

### Create settings.toml

Connect to ESP32 serial console and run:
```python
f = open('settings.toml', 'w') 
f.write('CIRCUITPY_WIFI_SSID = "your-wifi-name"\n') 
f.write('CIRCUITPY_WIFI_PASSWORD = "your-wifi-password"\n')
f.close()
```

### Create secrets.py

Copy `secrets.py.example` to `secrets.py` and update:
```python
secrets = {
    "ingest_url": "https://your-project.supabase.co/functions/v1/ingest",
    "access_token": "",
}
```

### Upload code.py

1. Copy `code.py` to the ESP32
2. Device will reboot and generate a UUID
3. Check serial console for the UUID
4. Note this UUID - you'll need it for the portal

## Step 3: Deploy React Portal

### Local Development

```bash
cd site_sym
npm install
```

Create `.env`:
```
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key
```

Test locally:
```bash
npm run dev
```

### Deploy to GitHub Pages

1. **Setup GitHub Secrets**
   - Go to Settings > Secrets and variables > Actions
   - Add `VITE_SUPABASE_URL` with your Supabase URL
   - Add `VITE_SUPABASE_ANON_KEY` with your anon key

2. **Enable GitHub Pages**
   - Go to Settings > Pages
   - Source: GitHub Actions

3. **Deploy**
   - Push to main branch
   - GitHub Actions will automatically build and deploy
   - Site will be live at `https://username.github.io/plane-tracker/`

### Alternative: Manual Deploy

```bash
cd site_sym
npm run build
npm run deploy
```

## Step 4: First Use

### Register Account

1. Open your deployed portal
2. Click "Register"
3. Create account with email/password

### Add Your First Plane

1. Go to "Planes" section
2. Click "Add Plane"
3. Enter tail number (e.g., N12345)
4. Add model and manufacturer
5. Save

### Register Your Device

1. Go to "Devices" section
2. Click "Add Device"
3. Enter the UUID from your ESP32
4. Give it a friendly name
5. Assign it to a plane
6. Save

### Watch Data Flow

1. ESP32 will start sending data every few minutes
2. Go to "Sessions" to see tracking data
3. Dashboard shows real-time stats
4. Device "Last Seen" updates automatically

## Troubleshooting

### ESP32 Not Connecting

- Check WiFi credentials in `settings.toml`
- Verify network is 2.4GHz (ESP32 doesn't support 5GHz)
- Check serial console for error messages

### No Data in Portal

- Verify edge function is deployed
- Check ESP32 serial console for POST errors
- Confirm device UUID matches in portal
- Check Supabase logs for edge function errors

### Portal Not Loading

- Verify environment variables are set
- Check browser console for errors
- Confirm Supabase project is running
- Check that database tables exist

### GitHub Pages Not Deploying

- Verify secrets are set correctly
- Check Actions tab for build errors
- Confirm Pages is enabled in settings
- Check that base URL in vite.config.ts matches repo name

## Security Notes

- **Never commit** `.env` or `secrets.py` files
- **Service role key** stays on Supabase backend only
- **Anon key** is safe for frontend (RLS policies protect data)
- **WiFi password** stays on ESP32 device only

## Monitoring

### Check Edge Function Logs

1. Go to Edge Functions in Supabase
2. Click on `ingest` function
3. View Logs tab for incoming requests

### Check Device Status

1. Go to Devices in portal
2. "Last Seen" shows last successful POST
3. If > 5 minutes, device may be offline

### Check Database

1. Go to Table Editor in Supabase
2. Browse `sessions` table
3. Verify data is being inserted

## Backup

### Export Session Data

1. Go to Sessions in portal
2. Click "Export CSV"
3. Save for your records

### Backup Database

1. Use Supabase Dashboard
2. Project Settings > Database
3. Connection string for pg_dump

## Scaling

This system handles:
- **Unlimited devices** per account
- **Unlimited planes** per account
- **Millions of sessions** (Supabase free tier: 500MB)
- **Automatic cleanup** (oldest acked sessions pruned)

## Support

- Check device serial console first
- Review Supabase function logs
- Check browser console for frontend errors
- Open GitHub issue for bugs

