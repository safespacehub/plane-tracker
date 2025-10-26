# Quick Start Guide

Get your plane tracker up and running in 10 minutes.

## Prerequisites

- ESP32 with CircuitPython installed
- Supabase account (free)
- GitHub account (for portal hosting)

## Step 1: Supabase Setup (3 minutes)

1. Create project at [supabase.com](https://supabase.com)
2. Go to SQL Editor
3. Copy/paste contents of `supa_sym/migrations/001_initial_schema.sql`
4. Run it
5. Go to Edge Functions, create function named `ingest`
6. Copy/paste contents of `supa_sym/functions/ingest/index.ts`
7. Deploy it
8. Note your project URL and anon key

## Step 2: ESP32 Setup (5 minutes)

1. Copy these files to your ESP32:
   - `code.py`
   - `secrets.py` (create from `secrets.py.example`)

2. Edit `secrets.py`:
```python
secrets = {
    "ingest_url": "https://YOUR-PROJECT.supabase.co/functions/v1/ingest",
    "access_token": "",
}
```

3. Create `settings.toml` on ESP32:
```toml
CIRCUITPY_WIFI_SSID = "your-wifi"
CIRCUITPY_WIFI_PASSWORD = "your-password"
```

4. Reboot ESP32 and note the UUID from serial console

## Step 3: Deploy Portal (2 minutes)

1. Fork/clone this repo
2. Go to Settings > Secrets > Actions
3. Add secrets:
   - `VITE_SUPABASE_URL`: Your Supabase URL
   - `VITE_SUPABASE_ANON_KEY`: Your anon key
4. Enable GitHub Pages (Settings > Pages > Source: GitHub Actions)
5. Push to main branch
6. Portal deploys automatically

## Step 4: First Use

1. Open your portal: `https://yourusername.github.io/plane-tracker/`
2. Register an account
3. Add a plane (e.g., N12345)
4. Add device (use UUID from Step 2)
5. Assign device to plane
6. Watch data flow in!

## Verification

- **ESP32**: Serial console shows "POST acknowledged"
- **Portal**: Dashboard shows device with "Last Seen" updating
- **Supabase**: Check `sessions` table for data

## Next Steps

- Add more devices
- Export session data as CSV
- View flight time analytics
- Set up mobile access

## Troubleshooting

**ESP32 not connecting?**
- Check WiFi is 2.4GHz
- Verify credentials
- Check serial console

**No data in portal?**
- Verify device UUID matches
- Check edge function deployed
- Look at Supabase logs

**Portal not deploying?**
- Check GitHub Actions tab
- Verify secrets are set
- Confirm Pages enabled

## Full Documentation

- `DEPLOYMENT.md` - Complete deployment guide
- `site_sym/README.md` - Portal documentation
- `supa_sym/README.md` - Backend documentation
- `README.md` - System overview

## Support

Check serial console → Check Supabase logs → Check browser console → Open GitHub issue

Ready to fly! ✈️

