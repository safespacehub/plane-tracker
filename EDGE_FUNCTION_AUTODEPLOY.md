# Supabase Edge Function Auto-Deploy Setup

Complete guide to automatically deploying your edge functions when you push code.

## Step 1: Get Your Supabase Access Token

1. Go to [https://supabase.com/dashboard/account/tokens](https://supabase.com/dashboard/account/tokens)
2. Click "Generate New Token"
3. Give it a name like "GitHub Actions"
4. Copy the token (you won't see it again!)

## Step 2: Get Your Project Reference

Two ways to find it:

**Option A: From URL**
- Go to your Supabase project dashboard
- Look at the URL: `https://supabase.com/dashboard/project/YOUR-PROJECT-REF`
- Copy the `YOUR-PROJECT-REF` part

**Option B: From Settings**
- Go to Project Settings
- General tab
- Look for "Reference ID"

For your project, it should be: `leupyxqprbzcdjzosfew`

## Step 3: Add GitHub Secrets

1. Go to your GitHub repo
2. Settings → Secrets and variables → Actions
3. Click "New repository secret"
4. Add these two secrets:

**Secret 1:**
- Name: `SUPABASE_ACCESS_TOKEN`
- Value: (paste the token from Step 1)

**Secret 2:**
- Name: `SUPABASE_PROJECT_REF`
- Value: `leupyxqprbzcdjzosfew`

## Step 4: Create GitHub Actions Workflow

Create file: `.github/workflows/deploy-edge-functions.yml`

```yaml
name: Deploy Supabase Edge Functions

on:
  push:
    branches:
      - main
      - master
    paths:
      - 'supa_sym/functions/**'
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Setup Supabase CLI
        uses: supabase/setup-cli@v1
        with:
          version: latest

      - name: Deploy ingest function
        run: |
          supabase functions deploy ingest \
            --project-ref ${{ secrets.SUPABASE_PROJECT_REF }} \
            --no-verify-jwt
        working-directory: ./supa_sym
        env:
          SUPABASE_ACCESS_TOKEN: ${{ secrets.SUPABASE_ACCESS_TOKEN }}
```

## Step 5: Test It

**Option A: Push a change**
```bash
# Make a tiny change to the edge function
cd supa_sym/functions/ingest
# Edit index.ts (add a comment or something)
git add .
git commit -m "test: trigger edge function deploy"
git push
```

**Option B: Manual trigger**
1. Go to Actions tab in GitHub
2. Click "Deploy Supabase Edge Functions"
3. Click "Run workflow"

## Troubleshooting

### Error: "Invalid access token"

**Fix:**
1. Generate a NEW token at [supabase.com/dashboard/account/tokens](https://supabase.com/dashboard/account/tokens)
2. Update the `SUPABASE_ACCESS_TOKEN` secret in GitHub
3. Make sure you copied the ENTIRE token (they're long!)

### Error: "Project not found"

**Fix:**
1. Double-check your project ref: `leupyxqprbzcdjzosfew`
2. Make sure the `SUPABASE_PROJECT_REF` secret is set correctly
3. No extra spaces or quotes around the value

### Error: "Function not found" or "No functions to deploy"

**Fix:**
The workflow needs to run from the correct directory. Make sure your folder structure is:
```
supa_sym/
  functions/
    ingest/
      index.ts
```

### Error: "supabase: command not found"

**Fix:**
This means the Supabase CLI didn't install. The workflow should handle this, but if it fails:
- Check the Actions log
- Make sure you're using `supabase/setup-cli@v1`

### Still not working?

**Check the logs:**
1. Go to Actions tab
2. Click on the failed workflow run
3. Click on the "deploy" job
4. Expand each step to see detailed logs

**Common issues:**
- Token expired (generate a new one)
- Wrong project ref (should be `leupyxqprbzcdjzosfew`)
- File paths wrong (should be `supa_sym/functions/ingest/index.ts`)
- Secrets not set in GitHub (double-check Settings → Secrets)

## Verify Deployment

After successful deployment:

1. Go to your Supabase dashboard
2. Click "Edge Functions"
3. You should see "ingest" function
4. Click on it to see deployment details
5. Check the "Invocations" tab for incoming requests

Test it:
```bash
curl -X POST https://leupyxqprbzcdjzosfew.supabase.co/functions/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "device_uuid": "test-uuid",
    "session_start": "2025-10-26T10:00:00Z",
    "run_seconds": 100,
    "last_update": "2025-10-26T10:01:40Z",
    "status": "open",
    "msg_id": "test-uuid:2025-10-26T10:00:00Z:100"
  }'
```

Should return:
```json
{
  "success": true,
  "message": "Session data recorded"
}
```

## Manual Deployment (Backup Method)

If auto-deploy doesn't work, deploy manually:

```bash
# Install Supabase CLI
npm install -g supabase

# Login
supabase login

# Link to your project
supabase link --project-ref leupyxqprbzcdjzosfew

# Deploy
cd supa_sym
supabase functions deploy ingest
```

## What Triggers Auto-Deploy

The workflow triggers when:
- You push to `main` or `master` branch
- AND files in `supa_sym/functions/**` changed
- OR you manually trigger it from Actions tab

## Quick Checklist

- [ ] Generated Supabase access token
- [ ] Added `SUPABASE_ACCESS_TOKEN` secret to GitHub
- [ ] Added `SUPABASE_PROJECT_REF` secret to GitHub (value: `leupyxqprbzcdjzosfew`)
- [ ] Created `.github/workflows/deploy-edge-functions.yml`
- [ ] Pushed the workflow file to GitHub
- [ ] Verified secrets are set correctly (no typos)
- [ ] Tested by pushing a change to `supa_sym/functions/ingest/index.ts`
- [ ] Checked Actions tab for success/failure

## Pro Tips

**Only deploy when edge function changes:**
The workflow uses `paths: ['supa_sym/functions/**']` so it ONLY runs when you actually change the edge function code. This saves build minutes.

**Manual trigger:**
The `workflow_dispatch` lets you manually trigger deployment from the Actions tab without making a commit.

**Multiple functions:**
If you add more functions later, add them to the deploy step:
```yaml
- name: Deploy functions
  run: |
    supabase functions deploy ingest --project-ref ${{ secrets.SUPABASE_PROJECT_REF }}
    supabase functions deploy another-function --project-ref ${{ secrets.SUPABASE_PROJECT_REF }}
```

**Check deployment in Supabase:**
After each push, check the Edge Functions page in Supabase to see the new deployment timestamp.

## Need Help?

1. Check GitHub Actions logs (Actions tab → failed run → expand steps)
2. Check Supabase Edge Function logs (Edge Functions → ingest → Logs)
3. Verify secrets are set correctly (they should show as `***` in settings)
4. Make sure token hasn't expired (regenerate if needed)

That's it! Your edge functions should now deploy automatically on every push. 🚀

