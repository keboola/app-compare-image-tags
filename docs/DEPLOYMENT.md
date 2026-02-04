# Deployment Guide

This guide explains how to deploy the Component Output Comparison tool to Keboola as a Data App.

## Prerequisites

- Keboola project with Data Apps enabled
- GitHub repository with your code
- Workspace created in your Keboola project

## Step 1: Prepare Your Repository

Ensure your repository contains:

- `streamlit_app.py` - Main entry point
- `pyproject.toml` - Project configuration with dependencies
- `uv.lock` - Locked dependency versions
- All source code in proper structure

**Important**: Do NOT include `.streamlit/secrets.toml` in your repository. This file contains sensitive credentials and should only be used locally.

## Step 2: Create Workspace

If you haven't already created a workspace:

1. Log into your Keboola project
2. Navigate to **Workspaces** in the left sidebar
3. Click **New Workspace**
4. Select **Python** as the workspace type
5. Note the Workspace ID - you'll need this for configuration

## Step 3: Create Data App in Keboola

1. **Navigate to Data Apps:**
   - In your Keboola project, go to **Components → Applications → Data Apps**

2. **Create New Data App:**
   - Click **New Data App**
   - Fill in the form:
     - **Name**: Component Output Comparison
     - **Description**: Compare component outputs between image tags
     - **Git Repository**: Your repository URL (e.g., `https://github.com/your-org/app-compare-image-tags`)
     - **Git Branch**: `main` (or your default branch)
     - **Entry Point**: `streamlit_app.py`

3. **Configure Environment Variables:**

   The following are automatically provided by Keboola:
   - `KBC_URL`: Connection URL for your project
   - `KBC_TOKEN`: Storage API token with appropriate permissions

   **Note**: Workspace configuration is now provided via the UI. Users can optionally provide their Workspace URL in the input form for full SQL-level comparisons.

4. **Deploy:**
   - Click **Create & Deploy**
   - Keboola will:
     - Clone your repository
     - Install dependencies using `uv sync`
     - Start the Streamlit application with `uv run streamlit run streamlit_app.py`
     - Provide a URL for accessing the app

## Step 4: Verify Deployment

1. **Access the App:**
   - Click on the provided URL
   - You should see the Input page

2. **Test Basic Functionality:**
   - Enter a valid configuration ID
   - Validate the configuration
   - Ensure no errors appear

3. **Check Logs:**
   - In the Data App interface, view logs for any errors
   - Common issues:
     - Missing dependencies (check `requirements.txt`)
     - Invalid workspace ID
     - Permission errors (check token scope)

## Step 5: Configure Permissions

Ensure your Storage API token has the following permissions:

- **Read**: All buckets and tables
- **Write**: Development branches
- **Execute**: Component configurations

To verify permissions:
1. Go to **Settings → API Tokens** in Keboola
2. Find the token used by the Data App
3. Verify it has sufficient scope

## CI/CD with GitHub Actions (Optional)

You can set up automated deployment on every push to your repository.

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Keboola

on:
  push:
    branches:
      - main

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v2

      - name: Trigger Keboola Deploy
        run: |
          echo "Keboola will auto-deploy on detecting changes"
          # Add Keboola API call to trigger redeploy if needed
```

Keboola Data Apps typically auto-deploy when repository changes are detected.

## Updating the App

To update your deployed app:

1. **Make Changes Locally:**
   - Modify code in your repository
   - Test locally with `streamlit run streamlit_app.py`
   - Commit and push changes

2. **Redeploy:**
   - Keboola will automatically detect changes and redeploy
   - Or manually trigger redeploy in the Data App interface

3. **Verify Update:**
   - Check the deployment logs
   - Test the updated functionality

## Troubleshooting Deployment Issues

### App Fails to Start

**Symptoms**: Deployment completes but app doesn't load

**Solutions**:
- Check deployment logs for Python errors
- Verify all dependencies in `pyproject.toml` are correct versions
- Ensure `streamlit_app.py` is at the repository root
- Check that all imports are relative and correct
- Ensure `uv.lock` is committed to the repository

### "Module not found" Errors

**Symptoms**: Import errors in logs

**Solutions**:
- Add missing packages to `pyproject.toml` dependencies
- Run `uv sync` to update `uv.lock`
- Verify package names are correct (PyPI names)
- Check for typos in import statements

### Authentication Errors

**Symptoms**: "Failed to authenticate" or "Token invalid"

**Solutions**:
- Verify `KBC_TOKEN` is provided by Keboola
- Check token has sufficient permissions
- Ensure `KBC_URL` matches your project region

### Workspace Query Failures

**Symptoms**: "Workspace not found" or query errors

**Solutions**:
- Ensure you've provided a valid Workspace URL in the input form
- Verify the workspace exists and is accessible with your token
- Check workspace type is compatible (Snowflake/BigQuery)
- **Without Workspace URL**: Comparisons will use row limits and in-app comparison (safer for large tables but may not compare all data)

### Performance Issues

**Symptoms**: App is slow or times out

**Solutions**:
- Increase caching TTL values in code
- Limit row comparison to smaller datasets initially
- Use streaming data loading for large tables
- Consider optimizing SQL queries

## Best Practices

1. **Use Version Tags**: Tag releases in Git for easy rollback
2. **Test Locally First**: Always test changes locally before deploying
3. **Monitor Logs**: Regularly check deployment logs for warnings
4. **Document Changes**: Keep CHANGELOG.md updated with version changes
5. **Backup Configs**: Export configurations before testing in dev branches

## Security Considerations

- **Never commit secrets** to the repository
- **Limit token scope** to minimum required permissions
- **Use development branches** for testing (don't affect production)
- **Audit access logs** regularly in Keboola
- **Rotate tokens** periodically

## Support

If you encounter deployment issues:

1. Check Keboola status page for platform issues
2. Review deployment logs in Data App interface
3. Consult Keboola documentation: https://developers.keboola.com
4. Contact Keboola support through your project
