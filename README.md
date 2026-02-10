# Keboola Component Output Comparison Tool

A Streamlit data app for comparing Keboola component outputs between two different image tags to validate component upgrades.

## Overview

This tool automates the validation of component upgrades by:

1. Taking a production component configuration and a test image tag as input
2. Creating a duplicate configuration with the test image tag
3. Running both configurations in parallel (production in default branch, test in development branch)
4. Performing comprehensive multi-level comparison:
   - **Bucket Level**: Which buckets exist in each output
   - **Table Level**: Which tables exist in each bucket
   - **Metadata Level**: Primary keys, columns, data types, row counts
   - **Row Level**: Actual data values with detailed difference tracking
5. Displaying results in an interactive dashboard with export capabilities

## Features

- **Automated Configuration Duplication**: Automatically creates test configurations with modified image tags
- **Parallel Execution**: Runs production and test configurations simultaneously for faster results
- **Multi-Level Comparison**: Four levels of comparison from buckets down to individual cell values
- **Real-Time Monitoring**: Live progress tracking with status updates and progress bars
- **Detailed Reporting**: Comprehensive breakdown of all differences with visual charts and tables
- **Export Functionality**: Download row-level differences as CSV for further analysis
- **Development Branch Isolation**: Test runs execute in isolated development branches to avoid affecting production

## Prerequisites

- Python 3.9 or higher
- Keboola project with Storage API access
- Workspace created in your Keboola project
- Storage API token with appropriate permissions

## Setup

### Local Development

1. **Clone the repository:**
   ```bash
   git clone https://github.com/keboola/app-compare-image-tags.git
   cd app-compare-image-tags
   ```

2. **Install dependencies:**
   ```bash
   uv sync
   ```

3. **Configure environment:**
   ```bash
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   ```

   Edit `.streamlit/secrets.toml` with your Keboola connection details:
   ```toml
   KBC_URL = "https://connection.<region>.<provider>.keboola.com"
   ```

   **Important Notes:**
   - Never commit `.streamlit/secrets.toml` to git!
   - **Tokens are provided via UI**: You'll enter your Keboola Storage API token in the app when you use it (not stored in secrets)
   - **Workspace URL (optional)**: For full SQL-level comparisons, provide your workspace URL in the UI. Without it, comparisons use row limits and in-app comparison (safer for large tables)
   - **Branch Creation**: If your token doesn't have branch creation permissions, you can provide an admin token through the UI when needed (see Execution page)
   - **In production**: The app automatically uses the logged-in user's token from environment variables

4. **Run the application:**
   ```bash
   uv run streamlit run streamlit_app.py
   ```

   The app will open in your browser at `http://localhost:8501`

### Local Tests

Get token to the project https://connection.us-east4.gcp.keboola.com/admin/projects/4214 where test tables are 

Run KBC_TOKEN=__token__ pytest tests/test_functional_scenarios.py

### Deployment to Keboola

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for detailed deployment instructions.

## Usage

### Step 1: Input Configuration

1. Navigate to the **Input** page
2. Enter:
   - **Keboola Storage API Token**: Your personal Keboola token for accessing configurations
   - **Configuration ID or URL**: The full URL or just the ID of your existing production configuration
   - **Workspace URL (Optional)**: Your Keboola workspace URL for full SQL-level comparisons. Without it, comparisons are limited by row count.
   - **Production Image Tag**: Current/production image tag (default: "latest")
   - **Test Image Tag**: The new image tag you want to test (e.g., "2.0.0")
   - **Development Branch Name**: Optional name for the test branch (default: "comparison-test")
3. Click **Validate Configuration**
4. Once validated, proceed to the Execution page

**Finding Your Workspace URL:**
1. Go to Keboola → Workspaces
2. Open your workspace
3. Copy the URL from your browser (e.g., `https://connection.keboola.com/admin/projects/12345/workspaces/01kg...`)

### Step 2: Execution & Monitoring

1. Navigate to the **Execution** page
2. The setup phase will:
   - Create or select development branches (production and test)
   - **Admin Token (Optional)**: If your user doesn't have branch creation permissions, provide a token with admin access in the "Admin Token" field
   - Create test configurations with your specified image tags
3. Click **Start Comparison Runs** to trigger both jobs
4. Monitor real-time progress for both production and test runs
5. Once both jobs complete successfully, click **Proceed to Comparison**

### Step 3: Review Results

1. Navigate to the **Results** page
2. Review results across three tabs:

   **Summary Tab:**
   - Overall status (match or differ)
   - Key metrics (total buckets, tables, match rates)
   - Detailed breakdown of differences
   - Key findings summary

   **Structure & Metadata Tab:**
   - Bucket comparison (common, production-only, test-only)
   - Table comparison per bucket
   - Metadata differences (PKs, columns, types, row counts)

   **Row Differences Tab:**
   - Select specific tables to view row-level differences
   - Visual charts showing differences by column
   - Sample differing rows with production vs. test values
   - Export differences to CSV

## Project Structure

```
app-compare-image-tags/
├── streamlit_app.py              # Main entry point
├── pyproject.toml                # Project config & dependencies
├── uv.lock                       # Dependency lock file
├── .streamlit/
│   ├── config.toml              # Streamlit configuration
│   └── secrets.toml.example     # Credentials template
├── utils/
│   ├── config.py                # Configuration management
│   ├── keboola_client.py        # Keboola API client
│   ├── comparison_engine.py     # Comparison logic
│   └── visualization.py         # Display components
├── page_modules/
│   ├── input_page.py            # Configuration input
│   ├── orchestration_page.py    # Job execution & monitoring
│   └── results_page.py          # Results display
├── tests/                        # Unit tests
└── docs/                         # Documentation
```

## Architecture

The application follows a three-phase workflow:

1. **Input Phase**: Collect and validate configuration ID and test image tag
2. **Orchestration Phase**: Create test configuration, trigger parallel runs, monitor progress
3. **Results Phase**: Execute multi-level comparison and display results

For detailed architecture information, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## API Integration

The app integrates with three Keboola APIs:

- **Storage API**: Configuration management, branch operations, metadata access
- **Queue API**: Job triggering and monitoring
- **Workspace API**: Data queries for row-level comparison

For API usage examples, see [docs/API_REFERENCE.md](docs/API_REFERENCE.md).

## Troubleshooting

### "Configuration not found"
- Verify the configuration ID/URL is correct
- Ensure the token you entered has access to the component
- Try entering the full configuration URL instead of just the ID

### "Failed to create branch" (403 Forbidden)
- **Solution**: Use the **Admin Token** field in the Execution page to provide a token with branch creation permissions
- **How to get an admin token**:
  1. Go to Keboola UI → Your Profile → Tokens → Create New Token
  2. Ensure the token has admin permissions
  3. Copy the token and paste it into the "Admin Token (optional)" field in the app
- **Note**: This applies to both local development and production environments
- Verify the Development Branches feature is enabled for your project (it's in public beta)

### "Workspace query failed"
- Ensure you've provided a valid Workspace URL in the input form
- Verify the workspace exists and is accessible with your token
- Check that tables exist in the specified branches
- **Without Workspace URL**: Comparisons will use row limits and in-app comparison (safer for large tables but may not compare all data)

### Jobs stuck in "waiting" status
- This is normal for queued jobs; wait for available workers
- Check Keboola platform status if delays are unusual

## Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch
3. Make your changes with clear commit messages
4. Add tests for new functionality
5. Submit a pull request

## License

MIT License - See LICENSE file for details

## Support

For issues or questions:
- Open an issue on GitHub
- Contact the development team
- Consult the Keboola documentation at https://developers.keboola.com
