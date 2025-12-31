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
   git clone <repository-url>
   cd app-compare-image-tags
   ```

2. **Install dependencies:**
   ```bash
   uv sync
   ```

3. **Configure credentials:**
   ```bash
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   ```

   Edit `.streamlit/secrets.toml` with your Keboola credentials:
   ```toml
   KBC_URL = "https://connection.<region>.<provider>.keboola.com"
   KBC_TOKEN = "your-storage-api-token"
   KBC_WORKSPACE_ID = "your-workspace-id"
   ```

   **Important:** Never commit `.streamlit/secrets.toml` to git!

4. **Run the application:**
   ```bash
   uv run streamlit run streamlit_app.py
   ```

   The app will open in your browser at `http://localhost:8501`

### Deployment to Keboola

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for detailed deployment instructions.

## Usage

### Step 1: Input Configuration

1. Navigate to the **Input** page
2. Enter:
   - **Production Configuration ID**: The numeric ID of your existing production configuration
   - **Test Image Tag**: The new image tag you want to test (e.g., "2.0.0", "latest")
   - **Development Branch Name**: Optional name for the test branch (default: "comparison-test")
3. Click **Validate Configuration**
4. Once validated, proceed to the Execution page

### Step 2: Execution & Monitoring

1. Navigate to the **Execution** page
2. The setup phase will:
   - Create or select a development branch
   - Create a test configuration with your specified image tag
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
- Verify the configuration ID is correct
- Ensure your Storage API token has access to the component

### "Failed to create branch"
- Check that your token has permissions to create development branches
- Verify the branch name doesn't already exist with conflicts

### "Workspace query failed"
- Ensure `KBC_WORKSPACE_ID` is correctly configured
- Verify the workspace exists and is accessible
- Check that tables exist in the specified branches

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
