"""
Unified Keboola API client for Storage, Queue, and Workspace APIs.

This module provides a comprehensive client for interacting with Keboola platform,
including configuration management, branch operations, job execution, and data queries.
"""

import json
import time
from typing import Optional, Dict, List, Any
from urllib.parse import urlencode
import requests
import pandas as pd
import streamlit as st

from .config import get_config


class KeboolaAPIClient:
    """Unified client for all Keboola API interactions."""

    def __init__(self, token_override: str = None):
        """
        Initialize the Keboola API client with credentials from config.

        Args:
            token_override: Optional token to use instead of config token (for admin operations)
        """
        self.storage_url = get_config("KBC_URL")
        self.token = token_override if token_override else get_config("KBC_TOKEN")
        self.workspace_id = get_config("KBC_WORKSPACE_ID")

        if not self.storage_url:
            raise ValueError("KBC_URL must be configured")

        if not self.token:
            raise ValueError("KBC_TOKEN must be configured or provided via token_override")

        # Trim trailing slashes from storage URL
        self.storage_url = self.storage_url.rstrip('/')

        # Derive queue URL from storage URL
        # Example: https://connection.north-europe.azure.keboola.com -> https://queue.north-europe.azure.keboola.com
        region_part = self.storage_url.split("//")[1]  # "connection.north-europe.azure.keboola.com"
        self.queue_url = f"https://queue.{'.'.join(region_part.split('.')[1:])}"

        self.headers = {
            "X-StorageApi-Token": self.token
        }

    # ==================== Configuration Management ====================

    @st.cache_data(ttl=3600)
    def get_configuration_direct(_self, component_id: str, config_id: str) -> Dict[str, Any]:
        """
        Get configuration details by component ID and config ID directly.

        Args:
            component_id: Component ID
            config_id: Configuration ID

        Returns:
            Configuration dictionary with all details
        """
        url = f"{_self.storage_url}/v2/storage/components/{component_id}/configs/{config_id}"
        response = requests.get(url, headers=_self.headers)
        response.raise_for_status()

        config = response.json()
        config['component'] = component_id
        return config

    @st.cache_data(ttl=3600)
    def get_configuration(_self, config_id: str) -> Dict[str, Any]:
        """
        Get configuration details by ID (searches through all components).

        Args:
            config_id: Configuration ID

        Returns:
            Configuration dictionary with all details
        """
        # First, we need to find which component this config belongs to
        # We'll search through components
        url = f"{_self.storage_url}/v2/storage/components"
        response = requests.get(url, headers=_self.headers)
        response.raise_for_status()

        components = response.json()

        # Search for the config across all components
        for component in components:
            component_id = component['id']
            config_url = f"{_self.storage_url}/v2/storage/components/{component_id}/configs/{config_id}"
            try:
                config_response = requests.get(config_url, headers=_self.headers)
                if config_response.status_code == 200:
                    config = config_response.json()
                    config['component'] = component_id
                    return config
            except:
                continue

        raise ValueError(f"Configuration {config_id} not found in any component")

    def create_configuration(self, component_id: str, name: str, description: str, configuration: Dict, branch_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a new configuration.

        Args:
            component_id: Component ID
            name: Configuration name
            description: Configuration description
            configuration: Configuration data dictionary
            branch_id: Branch ID (None for default branch)

        Returns:
            Created configuration dictionary
        """
        # Use branch-specific URL path when branch_id is provided
        if branch_id:
            url = f"{self.storage_url}/v2/storage/branch/{branch_id}/components/{component_id}/configs"
        else:
            url = f"{self.storage_url}/v2/storage/components/{component_id}/configs"

        data = {
            'name': name,
            'description': description,
            'configuration': json.dumps(configuration)
        }

        response = requests.post(
            url,
            headers=self.headers,
            data=data
        )

        if not response.ok:
            try:
                error_detail = response.json()
                raise ValueError(f"Configuration creation failed ({response.status_code}): {error_detail.get('error', error_detail.get('message', response.text))}")
            except ValueError:
                raise
            except:
                raise ValueError(f"Configuration creation failed with status {response.status_code}: {response.text}")

        return response.json()

    def update_configuration(self, component_id: str, config_id: str, configuration: Dict, branch_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Update an existing configuration.

        Args:
            component_id: Component ID
            config_id: Configuration ID
            configuration: Updated configuration data dictionary
            branch_id: Branch ID (None for default branch)

        Returns:
            Updated configuration dictionary
        """
        # Use branch-specific URL path when branch_id is provided
        if branch_id:
            url = f"{self.storage_url}/v2/storage/branch/{branch_id}/components/{component_id}/configs/{config_id}"
        else:
            url = f"{self.storage_url}/v2/storage/components/{component_id}/configs/{config_id}"

        data = {
            'configuration': json.dumps(configuration)
        }

        response = requests.put(
            url,
            headers=self.headers,
            data=data
        )
        response.raise_for_status()
        return response.json()

    def update_configuration_tag(self, component_id: str, config_id: str, config_data: Dict, new_tag: str, branch_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Update an existing configuration's image tag in a branch.

        Args:
            component_id: Component ID
            config_id: Configuration ID
            config_data: Current configuration data
            new_tag: New image tag to use
            branch_id: Branch ID (None for default branch)

        Returns:
            Updated configuration dictionary
        """
        import copy
        updated_config = copy.deepcopy(config_data)

        # Ensure runtime object exists and set image_tag
        if 'runtime' not in updated_config:
            updated_config['runtime'] = {}

        updated_config['runtime']['image_tag'] = new_tag

        return self.update_configuration(
            component_id=component_id,
            config_id=config_id,
            configuration=updated_config,
            branch_id=branch_id
        )

    def duplicate_configuration_with_tag(self, original_config: Dict, new_tag: str, branch_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Duplicate a configuration with a new image tag.

        Args:
            original_config: Original configuration dictionary
            new_tag: New image tag to use
            branch_id: Branch ID to create config in (None for default branch)

        Returns:
            Created configuration dictionary
        """
        import copy
        component_id = original_config['component']
        config_data = copy.deepcopy(original_config['configuration'])

        # Ensure runtime object exists and set image_tag
        if 'runtime' not in config_data:
            config_data['runtime'] = {}

        config_data['runtime']['image_tag'] = new_tag

        # Create new configuration
        new_name = f"{original_config['name']} - Test ({new_tag})"
        new_description = f"Test configuration for image tag comparison: {new_tag}"

        return self.create_configuration(
            component_id=component_id,
            name=new_name,
            description=new_description,
            configuration=config_data,
            branch_id=branch_id
        )

    # ==================== Branch Management ====================
    """
    KEBOOLA BRANCH API PATTERN:

    When working with development branches in Keboola:

    1. **Branch Creation**: POST /v2/storage/dev-branches
       - Creates a new dev branch
       - Automatically copies ALL configurations from main branch

    2. **Working with Branches**: Use branch-specific URL paths
       - Branch endpoints use: /v2/storage/branch/{branch_id}/...
       - Default branch can use: /v2/storage/branch/default/... OR /v2/storage/...
       - Each branch has isolated configurations and storage namespace

    3. **Configuration Operations in Branches**:
       - LIST: GET /v2/storage/branch/{branch_id}/components/{component_id}/configs
         → Lists configs in the specified branch

       - CREATE: POST /v2/storage/branch/{branch_id}/components/{component_id}/configs
         → Creates config in the specified branch

       - READ: GET /v2/storage/branch/{branch_id}/components/{component_id}/configs/{config_id}
         → Reads config from the specified branch

       - UPDATE: PUT /v2/storage/branch/{branch_id}/components/{component_id}/configs/{config_id}
         → Updates the auto-copied config in the specified branch

    4. **Running Jobs in Branches**:
       - POST /jobs with branchId in payload
       - The job runs the configuration from that branch context

    5. **Data Access in Branches**:
       - Buckets, tables, and data queries also use branch URL paths
       - Example: GET /v2/storage/branch/{branch_id}/buckets
    """

    @st.cache_data(ttl=300)
    def list_branches(_self) -> List[Dict[str, Any]]:
        """
        List all development branches.

        Returns:
            List of branch dictionaries
        """
        url = f"{_self.storage_url}/v2/storage/dev-branches"
        response = requests.get(url, headers=_self.headers)
        response.raise_for_status()
        return response.json()

    def get_branch(self, branch_id: str) -> Dict[str, Any]:
        """
        Get a specific branch's details.

        Args:
            branch_id: Branch ID

        Returns:
            Branch dictionary
        """
        url = f"{self.storage_url}/v2/storage/dev-branches/{branch_id}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def get_configuration_in_branch(self, component_id: str, config_id: str, branch_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get configuration from a specific branch (for verification).

        Args:
            component_id: Component ID
            config_id: Configuration ID
            branch_id: Branch ID (None for default branch)

        Returns:
            Configuration dictionary from the specified branch
        """
        # Use branch-specific URL path when branch_id is provided
        if branch_id:
            url = f"{self.storage_url}/v2/storage/branch/{branch_id}/components/{component_id}/configs/{config_id}"
        else:
            url = f"{self.storage_url}/v2/storage/components/{component_id}/configs/{config_id}"

        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def wait_for_branch_ready(self, branch_id: str, timeout: int = 600, poll_interval: int = 5) -> Dict[str, Any]:
        """
        Wait for a branch to be fully created and ready.

        Args:
            branch_id: Branch ID
            timeout: Maximum wait time in seconds (default: 10 minutes)
            poll_interval: Polling interval in seconds

        Returns:
            Branch details when ready
        """
        start_time = time.time()

        while True:
            branch = self.get_branch(branch_id)

            # Check if branch is ready (no longer in creating state)
            # Branch is ready when it has metadata populated
            if branch.get('isDefault') is not None:
                return branch

            if time.time() - start_time > timeout:
                raise TimeoutError(f"Branch {branch_id} did not become ready within {timeout} seconds")

            time.sleep(poll_interval)

    def create_branch(self, name: str, description: str = None) -> Dict[str, Any]:
        """
        Create a new development branch.

        Args:
            name: Branch name
            description: Branch description (optional)

        Returns:
            Created branch dictionary
        """
        url = f"{self.storage_url}/v2/storage/dev-branches"

        payload = {'name': name}
        if description:
            payload['description'] = description

        headers = self.headers.copy()
        headers['Content-Type'] = 'application/json'

        response = requests.post(
            url,
            headers=headers,
            json=payload
        )

        if not response.ok:
            try:
                error_detail = response.json()
                raise ValueError(f"Branch creation failed: {error_detail.get('error', error_detail.get('message', response.text))}")
            except:
                raise ValueError(f"Branch creation failed with status {response.status_code}: {response.text}")

        return response.json()

    def get_or_create_branch(self, name: str) -> Dict[str, Any]:
        """
        Get branch by name or create if it doesn't exist.

        Args:
            name: Branch name

        Returns:
            Branch dictionary
        """
        branches = self.list_branches()

        # Check if branch exists
        for branch in branches:
            if branch['name'] == name:
                return branch

        # Create if doesn't exist
        return self.create_branch(name, f"Comparison test branch created by data app")

    # ==================== Metadata Access ====================

    @st.cache_data(ttl=0)  # Disabled caching temporarily for debugging
    def list_buckets(_self, branch_id: Optional[str] = None) -> List[str]:
        """
        List all buckets in a branch.

        Dev branch buckets are prefixed with {branch_id}-, e.g. "12345-in.c-bucket"
        This method filters buckets by prefix and returns them without the prefix.

        Args:
            branch_id: Branch ID (None for default branch) - can be int or str

        Returns:
            List of bucket IDs (without branch prefix for dev branches)
        """
        # CRITICAL FIX: Convert branch_id to string if provided
        if branch_id is not None:
            branch_id = str(branch_id)

        # Always use the regular buckets endpoint (no branch in URL)
        url = f"{_self.storage_url}/v2/storage/buckets"

        response = requests.get(url, headers=_self.headers)
        response.raise_for_status()

        all_buckets = response.json()
        bucket_ids = [bucket['id'] for bucket in all_buckets]

        # Debug: Show what we got
        import streamlit as st
        st.write(f"🔍 **Total buckets in project:** {len(bucket_ids)}")
        st.write(f"🔍 **Branch ID (type={type(branch_id).__name__}):** {branch_id}")

        if branch_id:
            # Dev branch bucket pattern: {stage}.c-{branch_id}-{bucket_name}
            # Example: in.c-20533-keboola-ex-instagram-v2-01kcrfjxt5wvms53ds3vy6x5h1
            # We need to filter for pattern and strip the branch ID from the middle

            import re
            pattern = re.compile(rf'^(in|out)\.c-{branch_id}-(.+)$')
            st.write(f"🔍 **Looking for pattern:** `{{stage}}.c-{branch_id}-{{bucket_name}}`")

            # Show which buckets match
            matching = [bid for bid in bucket_ids if branch_id in bid]
            st.write(f"🔍 **Buckets containing '{branch_id}' anywhere:** {len(matching)}")
            if matching:
                st.write(f"🔍 **Matching bucket examples:**")
                for bid in matching[:10]:
                    st.text(f"  - {bid}")

            # Filter and strip branch ID from middle
            filtered_buckets = []
            for bucket_id in bucket_ids:
                match = pattern.match(bucket_id)
                if match:
                    stage = match.group(1)
                    bucket_name = match.group(2)
                    # Return as: {stage}.c-{bucket_name} (without branch ID)
                    filtered_buckets.append(f"{stage}.c-{bucket_name}")

            st.write(f"🔍 **Buckets matching pattern:** {len(filtered_buckets)}")
            st.write(f"🔍 **Filtered bucket IDs (branch ID stripped):** {filtered_buckets}")
            return filtered_buckets
        else:
            # For default branch, return buckets without any numeric prefix pattern
            import re
            default_buckets = [
                bucket_id for bucket_id in bucket_ids
                if not re.match(r'^\d+-', bucket_id)
            ]
            st.write(f"🔍 **Default branch buckets:** {len(default_buckets)}")
            return default_buckets

    @st.cache_data(ttl=300)
    def list_tables_in_bucket(_self, bucket_id: str, branch_id: Optional[str] = None) -> List[str]:
        """
        List all tables in a bucket.

        Args:
            bucket_id: Bucket ID (without branch prefix)
            branch_id: Branch ID (None for default branch) - can be int or str

        Returns:
            List of table names (without bucket prefix)
        """
        # CRITICAL FIX: Convert branch_id to string if provided
        if branch_id is not None:
            branch_id = str(branch_id)

        # Add branch ID to bucket_id if in dev branch
        # Pattern: bucket_id="in.c-mybucket" -> full_bucket_id="in.c-20533-mybucket"
        if branch_id:
            # Split bucket_id: "in.c-mybucket" -> "in.c-" + "mybucket"
            parts = bucket_id.split('.c-', 1)
            if len(parts) == 2:
                stage = parts[0]  # "in" or "out"
                bucket_name = parts[1]  # "mybucket"
                full_bucket_id = f"{stage}.c-{branch_id}-{bucket_name}"
            else:
                # Fallback if format is unexpected
                full_bucket_id = f"{branch_id}-{bucket_id}"
        else:
            full_bucket_id = bucket_id

        url = f"{_self.storage_url}/v2/storage/buckets/{full_bucket_id}"

        response = requests.get(url, headers=_self.headers)
        response.raise_for_status()

        bucket = response.json()
        return [table['name'] for table in bucket.get('tables', [])]

    @st.cache_data(ttl=300)
    def get_table_detail(_self, table_id: str, branch_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get detailed table metadata.

        Args:
            table_id: Full table ID without branch prefix (e.g., "in.c-bucket.table")
            branch_id: Branch ID (None for default branch) - can be int or str

        Returns:
            Table metadata dictionary including columns, PKs, types, row count
        """
        # CRITICAL FIX: Convert branch_id to string if provided
        if branch_id is not None:
            branch_id = str(branch_id)

        # Add branch ID to table_id if in dev branch
        # Pattern: "in.c-bucket.table" -> "in.c-20533-bucket.table"
        if branch_id:
            # Split: "in.c-bucket.table" -> ["in", "c-bucket", "table"]
            parts = table_id.split('.')
            if len(parts) == 3 and parts[1].startswith('c-'):
                stage = parts[0]  # "in" or "out"
                bucket_name = parts[1][2:]  # "bucket" (strip "c-")
                table_name = parts[2]  # "table"
                full_table_id = f"{stage}.c-{branch_id}-{bucket_name}.{table_name}"
            else:
                # Fallback
                full_table_id = f"{branch_id}-{table_id}"
        else:
            full_table_id = table_id

        url = f"{_self.storage_url}/v2/storage/tables/{full_table_id}"

        response = requests.get(url, headers=_self.headers)
        response.raise_for_status()

        result = response.json()

        # Debug: Verify we got a dict
        if not isinstance(result, dict):
            import streamlit as st
            st.error(f"❌ API returned non-dict for table {full_table_id}: {type(result)}")
            st.write("Response:", result)
            raise ValueError(f"get_table_detail expected dict, got {type(result)}: {result}")

        return result

    # ==================== Job Management ====================

    def run_component(self, component_id: str, config_id: str, branch_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Trigger a component run.

        Args:
            component_id: Component ID
            config_id: Configuration ID
            branch_id: Branch ID (None for default branch)

        Returns:
            Job information dictionary with job ID
        """
        url = f"{self.queue_url}/jobs"

        payload = {
            "mode": "run",
            "component": component_id,
            "config": config_id
        }

        if branch_id:
            payload["branchId"] = str(branch_id)

        response = requests.post(
            url,
            headers={**self.headers, "Content-Type": "application/json"},
            json=payload
        )

        if not response.ok:
            try:
                error_detail = response.json()
                raise ValueError(f"Job creation failed: {error_detail.get('error', error_detail.get('message', response.text))}")
            except ValueError:
                raise
            except:
                raise ValueError(f"Job creation failed with status {response.status_code}: {response.text}")

        return response.json()

    @st.cache_data(ttl=5)
    def get_job_status(_self, job_id: str) -> Dict[str, Any]:
        """
        Get job status.

        Args:
            job_id: Job ID

        Returns:
            Job status dictionary
        """
        url = f"{_self.queue_url}/jobs/{job_id}"

        response = requests.get(url, headers=_self.headers)
        response.raise_for_status()

        return response.json()

    def wait_for_job(self, job_id: str, timeout: int = 3600, poll_interval: int = 5) -> Dict[str, Any]:
        """
        Wait for job to complete.

        Args:
            job_id: Job ID
            timeout: Maximum wait time in seconds
            poll_interval: Polling interval in seconds

        Returns:
            Final job status dictionary
        """
        start_time = time.time()

        while True:
            status = self.get_job_status(job_id)

            if status['status'] in ['success', 'error', 'cancelled', 'terminated']:
                return status

            if time.time() - start_time > timeout:
                raise TimeoutError(f"Job {job_id} did not complete within {timeout} seconds")

            time.sleep(poll_interval)

    # ==================== Data Queries ====================

    @st.cache_data(ttl=300)
    def query_table_data(
        _self,
        table_id: str,
        branch_id: Optional[str] = None,
        limit: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Query table data via Workspace API.

        Args:
            table_id: Full table ID without branch prefix (e.g., "in.c-bucket.table")
            branch_id: Branch ID (None for default branch) - can be int or str
            limit: Maximum number of rows to fetch

        Returns:
            DataFrame with table data
        """
        if not _self.workspace_id:
            raise ValueError("KBC_WORKSPACE_ID must be configured for data queries")

        # CRITICAL FIX: Convert branch_id to string if provided
        if branch_id is not None:
            branch_id = str(branch_id)

        url = f"{_self.storage_url}/v2/storage/workspaces/{_self.workspace_id}/query"

        # Add branch ID to table_id if in dev branch
        # Pattern: "in.c-bucket.table" -> "in.c-20533-bucket.table"
        if branch_id:
            # Split: "in.c-bucket.table" -> ["in", "c-bucket", "table"]
            parts = table_id.split('.')
            if len(parts) == 3 and parts[1].startswith('c-'):
                stage = parts[0]  # "in" or "out"
                bucket_name = parts[1][2:]  # "bucket" (strip "c-")
                table_name = parts[2]  # "table"
                full_table_id = f"{stage}.c-{branch_id}-{bucket_name}.{table_name}"
            else:
                # Fallback
                full_table_id = f"{branch_id}-{table_id}"
        else:
            full_table_id = table_id

        # Build SQL query with prefixed table ID
        parts = full_table_id.split('.')
        if len(parts) == 3:
            bucket, table = parts[1], parts[2]
            qualified_name = f'"{parts[0]}"."{bucket}"."{table}"'
        else:
            qualified_name = f'"{full_table_id}"'

        query = f'SELECT * FROM {qualified_name}'
        if limit:
            query += f' LIMIT {limit}'

        headers = _self.headers.copy()
        headers['Content-Type'] = 'application/json'

        response = requests.post(
            url,
            headers=headers,
            json={"query": query}
        )
        response.raise_for_status()

        result = response.json()

        # Convert to DataFrame
        if 'rows' in result:
            df = pd.DataFrame(result['rows'], columns=result.get('columns', []))
            return df
        else:
            return pd.DataFrame()
