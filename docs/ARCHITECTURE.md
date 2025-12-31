# Architecture Documentation

This document provides a detailed technical overview of the Component Output Comparison Tool architecture.

## System Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Streamlit Data App                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ Input Page   │→ │ Orchestration│→ │ Comparison   │         │
│  │              │  │ Engine       │  │ Engine       │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│         │                  │                  │                 │
└─────────┼──────────────────┼──────────────────┼─────────────────┘
          │                  │                  │
          ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Keboola Platform                             │
├──────────────────┬──────────────────┬──────────────────────────┤
│  Storage API     │  Queue API       │  Dev Branch Storage      │
│  - Get configs   │  - Trigger jobs  │  - Branch data           │
│  - Create config │  - Monitor status│  - Production data       │
│  - Get metadata  │  - Job results   │  - Workspace queries     │
└──────────────────┴──────────────────┴──────────────────────────┘
```

## Component Architecture

### 1. Core Utilities Layer

#### `utils/config.py`
- **Purpose**: Environment-agnostic configuration management
- **Responsibilities**:
  - Load configuration from `.streamlit/secrets.toml` (local)
  - Fall back to environment variables (production)
  - Provide unified interface for config access

#### `utils/keboola_client.py`
- **Purpose**: Unified API client for all Keboola interactions
- **Responsibilities**:
  - Configuration management (get, create, duplicate)
  - Branch operations (list, create, get-or-create)
  - Metadata access (buckets, tables, table details)
  - Job management (run, monitor, wait)
  - Data queries (workspace SQL execution)
- **Design Pattern**: Single Responsibility Principle - one client for all APIs
- **Caching Strategy**:
  - Configuration: 3600s TTL (rarely changes)
  - Job status: 5s TTL (frequent polling)
  - Metadata: 300s TTL (moderate changes)

#### `utils/comparison_engine.py`
- **Purpose**: Multi-level comparison logic
- **Responsibilities**:
  - Level 1: Bucket comparison (set operations)
  - Level 2: Table comparison (per bucket)
  - Level 3: Metadata comparison (PKs, columns, types, counts)
  - Level 4: Row-level comparison (pandas DataFrame diff)
  - Summary generation (aggregate results)
- **Algorithm**:
  ```
  compare_outputs():
    1. List buckets in both branches → compare sets
    2. For common buckets, list tables → compare sets
    3. For common tables, get metadata → compare attributes
    4. For compatible tables, query data → compare rows
    5. Aggregate all levels → generate summary
  ```

#### `utils/visualization.py`
- **Purpose**: Reusable display components
- **Responsibilities**:
  - Status indicators (emoji + text)
  - Metric displays (cards with values)
  - Comparison tables (side-by-side)
  - Difference charts (plotly visualizations)
  - Export functionality (CSV downloads)

### 2. Page Modules Layer

#### `page_modules/input_page.py`
- **Purpose**: Configuration input and validation
- **Flow**:
  ```
  Display form
    ↓
  User submits config ID + test tag
    ↓
  Call keboola_client.get_configuration()
    ↓
  If found: Store in session_state
    ↓
  Enable navigation to Execution page
  ```
- **State Management**: Stores `config_id`, `test_image_tag`, `original_config`, `component_id`

#### `page_modules/orchestration_page.py`
- **Purpose**: Job orchestration and monitoring
- **Three Sub-Phases**:

  **Setup Phase**:
  ```
  1. Create/select dev branch
     → Call get_or_create_branch()
     → Store branch_id

  2. Create test configuration
     → Call duplicate_configuration_with_tag()
     → Store test_config_id
  ```

  **Execution Phase**:
  ```
  1. Trigger production run (default branch)
     → Call run_component(config_id, branch_id=None)
     → Store production_job_id

  2. Trigger test run (dev branch)
     → Call run_component(test_config_id, branch_id=branch_id)
     → Store test_job_id
  ```

  **Monitoring Phase**:
  ```
  Loop every 5 seconds:
    1. Poll both job statuses
    2. Display progress bars
    3. Check for completion

  When both complete:
    → Call comparison_engine.compare_outputs()
    → Store comparison_results
  ```

#### `page_modules/results_page.py`
- **Purpose**: Display comparison results
- **Three Tabs**:

  **Summary Tab**: Executive overview with key metrics
  **Structure Tab**: Bucket/table/metadata comparisons
  **Differences Tab**: Row-level differences with export

### 3. Main Application Layer

#### `streamlit_app.py`
- **Purpose**: Application entry point and navigation
- **Responsibilities**:
  - Page configuration
  - Session state initialization
  - Navigation routing
  - Phase detection
  - Reset functionality

## Data Flow

### Complete Workflow

```
1. USER INPUT
   User enters: config_id, test_tag
   ↓
   Validate config exists
   ↓
   Store in session_state

2. SETUP
   Create dev branch
   ↓
   Duplicate config with test_tag
   ↓
   Store branch_id, test_config_id

3. EXECUTION
   Trigger production run (default branch)
   ‖  (parallel)
   Trigger test run (dev branch)
   ↓
   Poll status every 5s
   ↓
   Wait for both complete

4. COMPARISON
   List buckets (prod vs test)
   ↓
   List tables per bucket
   ↓
   Get table metadata
   ↓
   Query table data (workspace)
   ↓
   Compare with pandas
   ↓
   Generate summary

5. DISPLAY
   Show results in 3 tabs
   ↓
   Allow export to CSV
```

## State Management

### Session State Schema

```python
st.session_state = {
    # Input Phase
    'config_id': str,              # Production config ID
    'test_image_tag': str,         # Test tag
    'branch_name': str,            # Dev branch name
    'component_id': str,           # Component ID
    'original_config': dict,       # Full config object

    # Setup Phase
    'branch_id': str,              # Created branch ID
    'test_config_id': str,         # Created test config ID

    # Execution Phase
    'production_job_id': str,      # Production job ID
    'test_job_id': str,            # Test job ID
    'production_job_status': str,  # Current status
    'test_job_status': str,        # Current status

    # Results Phase
    'comparison_results': {
        'summary': {...},
        'bucket_comparison': {...},
        'table_comparison': {...},
        'metadata_comparison': {...},
        'row_differences': {...}
    }
}
```

### State Transitions

```
Empty → Input → Execution → Results
  ↑                              |
  └──────────── Reset ───────────┘
```

## API Integration

### Storage API Endpoints

| Operation | Endpoint | Method | Purpose |
|-----------|----------|--------|---------|
| List Components | `/v2/storage/components` | GET | Find component for config |
| Get Config | `/v2/storage/components/{id}/configs/{cid}` | GET | Fetch config details |
| Create Config | `/v2/storage/components/{id}/configs` | POST | Create test config |
| List Branches | `/v2/storage/dev-branches` | GET | Get available branches |
| Create Branch | `/v2/storage/dev-branches` | POST | Create dev branch |
| List Buckets | `/v2/storage/buckets` | GET | List buckets in branch |
| Get Bucket | `/v2/storage/buckets/{id}` | GET | Get bucket with tables |
| Get Table | `/v2/storage/tables/{id}` | GET | Get table metadata |

### Queue API Endpoints

| Operation | Endpoint | Method | Purpose |
|-----------|----------|--------|---------|
| Create Job | `/jobs` | POST | Trigger component run |
| Get Job | `/jobs/{id}` | GET | Poll job status |

### Workspace API Endpoints

| Operation | Endpoint | Method | Purpose |
|-----------|----------|--------|---------|
| Query Data | `/v2/storage/workspaces/{id}/query` | POST | Execute SQL query |

### Authentication

All API requests use the `X-StorageApi-Token` header:

```python
headers = {
    "X-StorageApi-Token": token,
    "Content-Type": "application/json"  # for JSON payloads
}
```

For branch-specific requests, add:

```python
headers["X-KBC-BranchId"] = branch_id
```

## Comparison Algorithm

### Level 1: Bucket Comparison

```python
prod_buckets = set(list_buckets(prod_branch))
test_buckets = set(list_buckets(test_branch))

result = {
    'production_only': prod_buckets - test_buckets,
    'test_only': test_buckets - prod_buckets,
    'common': prod_buckets & test_buckets
}
```

### Level 2: Table Comparison

```python
for bucket in common_buckets:
    prod_tables = set(list_tables(bucket, prod_branch))
    test_tables = set(list_tables(bucket, test_branch))

    results[bucket] = {
        'production_only': prod_tables - test_tables,
        'test_only': test_tables - prod_tables,
        'common': prod_tables & test_tables
    }
```

### Level 3: Metadata Comparison

```python
for table in common_tables:
    prod_meta = get_table_detail(table, prod_branch)
    test_meta = get_table_detail(table, test_branch)

    compare:
        - primary_keys: prod_meta['primaryKey'] == test_meta['primaryKey']
        - columns: set(prod_cols) == set(test_cols)
        - data_types: prod_types[col] == test_types[col] for all cols
        - row_count: prod_meta['rowsCount'] == test_meta['rowsCount']
```

### Level 4: Row-Level Comparison

```python
prod_data = query_table_data(table, prod_branch, limit=10000)
test_data = query_table_data(table, test_branch, limit=10000)

# Use pandas compare
differences = prod_data.compare(test_data, keep_equal=False)

# Analyze differences
for col in differences.columns:
    count_diffs_per_column[col] = differences[col].notna().sum()

# Collect samples
sample_diffs = differences.head(10)
```

## Performance Optimizations

### Caching Strategy

| Data Type | TTL | Rationale |
|-----------|-----|-----------|
| Configuration | 3600s | Rarely changes |
| Job Status | 5s | Frequent polling during monitoring |
| Metadata | 300s | Moderate change frequency |
| Comparison Results | 3600s | Expensive to compute |

### Query Optimization

- **Limit row comparisons**: Default 10k rows, configurable
- **Skip incompatible tables**: Don't compare if columns differ
- **Use SQL aggregation**: Push counts/filters to database
- **Chunk large tables**: Process in batches if needed

### UI Optimization

- **Lazy loading**: Only load data when tab is opened
- **Streaming display**: Show results as they compute
- **Progressive rendering**: Display summary before details

## Security Considerations

### Credential Management

- **Local**: `.streamlit/secrets.toml` (gitignored)
- **Production**: Environment variables (Keboola-provided)
- **Never committed**: Secrets file excluded via `.gitignore`

### API Token Scope

Required permissions:
- **Read**: All buckets and tables
- **Write**: Development branches only
- **Execute**: Component configurations

### Branch Isolation

- Production runs in **default branch**
- Test runs in **development branch**
- No cross-contamination of data

## Error Handling

### Graceful Degradation

- If job fails → Allow retry
- If comparison fails → Show partial results
- If metadata missing → Skip that table
- If row query fails → Mark as error, continue

### User-Friendly Errors

```python
try:
    operation()
except SpecificError as e:
    st.error(f"❌ Friendly message: {str(e)}")
    st.exception(e)  # Show details in expander
```

## Extensibility

### Adding New Comparison Levels

1. Add method to `ComparisonEngine`:
   ```python
   def _compare_new_level(self, ...):
       # Comparison logic
       return results
   ```

2. Call in `compare_outputs()`:
   ```python
   results['new_level'] = self._compare_new_level(...)
   ```

3. Add display in `results_page.py`:
   ```python
   def display_new_level(results):
       # Display logic
   ```

### Adding New Visualization Types

1. Add function to `visualization.py`:
   ```python
   def display_new_viz(data):
       # Plotly/Streamlit visualization
   ```

2. Use in results page:
   ```python
   display_new_viz(results['data'])
   ```

## Testing Strategy

### Unit Tests

- `test_keboola_client.py`: Mock API responses
- `test_comparison_engine.py`: Sample DataFrames

### Integration Tests

- End-to-end workflow with test data
- Verify all state transitions
- Check error handling paths

### Manual Testing

- Test with real Keboola project
- Verify different comparison scenarios
- Check UI responsiveness

## Future Enhancements

- **Historical Tracking**: Store comparison results over time
- **Scheduled Comparisons**: Trigger automatically
- **Email Notifications**: Alert on differences
- **Custom Exclusions**: Ignore specific columns
- **Approval Workflow**: Mark differences as expected
