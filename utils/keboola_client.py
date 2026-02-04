"""
Unified Keboola API client for Storage, Queue, and Workspace APIs.

This module provides a comprehensive client for interacting with Keboola platform,
including configuration management, branch operations, job execution, and data queries.
"""

import json
import time
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
import streamlit as st

from .config import get_config


class KeboolaAPIClient:
    """Unified client for all Keboola API interactions."""

    def __init__(self, token_override: str = None, kbc_url_override: str = None):
        """
        Initialize the Keboola API client with credentials from config.

        Args:
            token_override: Optional token to use instead of config token (for admin operations)
            kbc_url_override: Optional KBC URL to use instead of config URL
        """
        self.storage_url = kbc_url_override if kbc_url_override else get_config("KBC_URL", default=None)
        self.token = token_override if token_override else get_config("KBC_TOKEN", default=None)
        self.workspace_id = get_config("KBC_WORKSPACE_ID", default=None)

        # If storage_url not provided, try to derive from session state config_input
        if not self.storage_url:
            try:
                import streamlit as st

                config_input = st.session_state.get("config_input", "")
                if config_input and config_input.startswith("http"):
                    # Extract base URL from config URL
                    # e.g., https://connection.keboola.com/admin/projects/... -> https://connection.keboola.com
                    parts = config_input.split("/")
                    if len(parts) >= 3:
                        self.storage_url = f"{parts[0]}//{parts[2]}"
            except Exception:
                pass

        if not self.storage_url:
            raise ValueError(
                "KBC_URL must be configured in secrets.toml or provided via kbc_url_override, or pass a full configuration URL through the UI"
            )

        if not self.token:
            raise ValueError("KBC_TOKEN must be configured in secrets.toml or provided via token_override")

        # Trim trailing slashes from storage URL
        self.storage_url = self.storage_url.rstrip("/")

        # Derive queue URL from storage URL
        # Example: https://connection.north-europe.azure.keboola.com -> https://queue.north-europe.azure.keboola.com
        region_part = self.storage_url.split("//")[1]  # "connection.north-europe.azure.keboola.com"
        self.queue_url = f"https://queue.{'.'.join(region_part.split('.')[1:])}"

        # Query Service is regional (same pattern as other services)
        # Example: https://connection.us-east4.gcp.keboola.com -> https://query.us-east4.gcp.keboola.com
        self.query_service_url = f"https://query.{'.'.join(region_part.split('.')[1:])}"

        self.headers = {"X-StorageApi-Token": self.token}

    def _normalize_branch_id(self, branch_id: Optional[str]) -> Optional[str]:
        """Normalize branch_id to string or None."""
        return str(branch_id) if branch_id is not None else None

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
        config["component"] = component_id
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
            component_id = component["id"]
            config_url = f"{_self.storage_url}/v2/storage/components/{component_id}/configs/{config_id}"
            try:
                config_response = requests.get(config_url, headers=_self.headers)
                if config_response.status_code == 200:
                    config = config_response.json()
                    config["component"] = component_id
                    return config
            except requests.RequestException:
                continue

        raise ValueError(f"Configuration {config_id} not found in any component")

    def create_configuration(
        self, component_id: str, name: str, description: str, configuration: Dict, branch_id: Optional[str] = None
    ) -> Dict[str, Any]:
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

        data = {"name": name, "description": description, "configuration": json.dumps(configuration)}

        response = requests.post(url, headers=self.headers, data=data)

        if not response.ok:
            try:
                error_detail = response.json()
                raise ValueError(
                    f"Configuration creation failed ({response.status_code}): {error_detail.get('error', error_detail.get('message', response.text))}"
                )
            except ValueError:
                raise
            except (json.JSONDecodeError, KeyError, TypeError):
                raise ValueError(f"Configuration creation failed with status {response.status_code}: {response.text}")

        return response.json()

    def update_configuration(
        self, component_id: str, config_id: str, configuration: Dict, branch_id: Optional[str] = None
    ) -> Dict[str, Any]:
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

        data = {"configuration": json.dumps(configuration)}

        response = requests.put(url, headers=self.headers, data=data)
        response.raise_for_status()
        return response.json()

    def update_configuration_tag(
        self, component_id: str, config_id: str, config_data: Dict, new_tag: str, branch_id: Optional[str] = None
    ) -> Dict[str, Any]:
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
        if "runtime" not in updated_config:
            updated_config["runtime"] = {}

        updated_config["runtime"]["image_tag"] = new_tag

        return self.update_configuration(
            component_id=component_id, config_id=config_id, configuration=updated_config, branch_id=branch_id
        )

    def duplicate_configuration_with_tag(
        self, original_config: Dict, new_tag: str, branch_id: Optional[str] = None
    ) -> Dict[str, Any]:
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

        component_id = original_config["component"]
        config_data = copy.deepcopy(original_config["configuration"])

        # Ensure runtime object exists and set image_tag
        if "runtime" not in config_data:
            config_data["runtime"] = {}

        config_data["runtime"]["image_tag"] = new_tag

        # Create new configuration
        new_name = f"{original_config['name']} - Test ({new_tag})"
        new_description = f"Test configuration for image tag comparison: {new_tag}"

        return self.create_configuration(
            component_id=component_id,
            name=new_name,
            description=new_description,
            configuration=config_data,
            branch_id=branch_id,
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

    def get_configuration_in_branch(
        self, component_id: str, config_id: str, branch_id: Optional[str] = None
    ) -> Dict[str, Any]:
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
            if branch.get("isDefault") is not None:
                return branch

            if time.time() - start_time > timeout:
                raise TimeoutError(f"Branch {branch_id} did not become ready within {timeout} seconds")

            time.sleep(poll_interval)

    def create_branch(self, name: str, description: str = None) -> Dict[str, Any]:
        """
        Create a new development branch and wait for creation to complete.

        Args:
            name: Branch name
            description: Branch description (optional)

        Returns:
            Created branch dictionary (not the job response!)
        """
        url = f"{self.storage_url}/v2/storage/dev-branches"

        payload = {"name": name}
        if description:
            payload["description"] = description

        headers = self.headers.copy()
        headers["Content-Type"] = "application/json"

        response = requests.post(url, headers=headers, json=payload)

        if not response.ok:
            try:
                error_detail = response.json()
                raise ValueError(
                    f"Branch creation failed: {error_detail.get('error', error_detail.get('message', response.text))}"
                )
            except (json.JSONDecodeError, KeyError, TypeError):
                raise ValueError(f"Branch creation failed with status {response.status_code}: {response.text}")

        # The response is a JOB, not the branch!
        job_response = response.json()
        job_id = job_response["id"]

        # Wait for the branch creation job to complete and find the branch
        max_attempts = 300  # 300 * 2 seconds = 10 minutes
        for attempt in range(max_attempts):
            time.sleep(2)

            # Clear cache and get fresh branch list
            st.cache_data.clear()
            branches = self.list_branches()

            # Debug: Log polling attempt (every 10 seconds)
            if attempt % 5 == 0:
                try:
                    with st.expander(
                        f"🔍 Branch creation polling attempt {attempt + 1}/{max_attempts}", expanded=False
                    ):
                        st.write(f"Job ID: {job_id}")
                        st.write(f"Looking for branch: '{name}'")
                        st.write(f"Found {len(branches)} total branches")
                        branch_names = [b.get("name") for b in branches]
                        st.write(f"Branch names: {branch_names}")
                except Exception:
                    pass  # Ignore if we can't show debug info

            # Look for the branch by name
            for branch in branches:
                if branch["name"] == name:
                    return branch

        # If we get here, branch creation timed out
        raise TimeoutError(f"Branch creation job {job_id} completed but branch '{name}' not found after 10 minutes")

    def get_or_create_branch(self, name: str) -> Dict[str, Any]:
        """
        Get branch by name or create if it doesn't exist.

        Args:
            name: Branch name

        Returns:
            Branch dictionary
        """
        # Clear cache to ensure we get fresh branch list
        st.cache_data.clear()

        branches = self.list_branches()

        # Check if branch exists
        for branch in branches:
            if branch["name"] == name:
                return branch

        # Try to create, but handle case where it already exists
        try:
            return self.create_branch(name, "Comparison test branch created by data app")
        except ValueError as e:
            if "duplicateName" in str(e):
                # Branch was just created, fetch the fresh list again
                st.cache_data.clear()
                branches = self.list_branches()
                for branch in branches:
                    if branch["name"] == name:
                        return branch
                # If still not found, re-raise the error
                raise
            else:
                raise

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
        branch_id = _self._normalize_branch_id(branch_id)

        # Always use the regular buckets endpoint (no branch in URL)
        url = f"{_self.storage_url}/v2/storage/buckets"

        response = requests.get(url, headers=_self.headers)
        response.raise_for_status()

        all_buckets = response.json()
        bucket_ids = [bucket["id"] for bucket in all_buckets]

        # Debug output only when advanced mode is enabled
        import re

        show_debug = st.session_state.get("show_advanced", False)
        if show_debug:
            with st.expander("🔧 Debug: Bucket listing", expanded=False):
                st.write(f"Total buckets in project: {len(bucket_ids)}")
                st.write(f"Branch ID (type={type(branch_id).__name__}): {branch_id}")

        if branch_id:
            # Dev branch bucket pattern: {stage}.c-{branch_id}-{bucket_name}
            # Example: in.c-20533-keboola-ex-instagram-v2-01kcrfjxt5wvms53ds3vy6x5h1
            # We need to filter for pattern and strip the branch ID from the middle
            pattern = re.compile(rf"^(in|out)\.c-{branch_id}-(.+)$")

            if show_debug:
                with st.expander("🔧 Debug: Branch bucket filtering", expanded=False):
                    st.write(f"Looking for pattern: `{{stage}}.c-{branch_id}-{{bucket_name}}`")
                    # Show which buckets match
                    matching = [bid for bid in bucket_ids if branch_id in bid]
                    st.write(f"Buckets containing '{branch_id}' anywhere: {len(matching)}")
                    if matching:
                        st.write("Matching bucket examples:")
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

            if show_debug:
                with st.expander("🔧 Debug: Filtered buckets", expanded=False):
                    st.write(f"Buckets matching pattern: {len(filtered_buckets)}")
                    st.write(f"Filtered bucket IDs (branch ID stripped): {filtered_buckets}")
            return filtered_buckets
        else:
            # For default branch, return buckets without any numeric prefix pattern
            default_buckets = [bucket_id for bucket_id in bucket_ids if not re.match(r"^\d+-", bucket_id)]
            if show_debug:
                with st.expander("🔧 Debug: Default branch buckets", expanded=False):
                    st.write(f"Default branch buckets: {len(default_buckets)}")
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
        branch_id = _self._normalize_branch_id(branch_id)

        # Add branch ID to bucket_id if in dev branch
        # Pattern: bucket_id="in.c-mybucket" -> full_bucket_id="in.c-20533-mybucket"
        if branch_id:
            # Split bucket_id: "in.c-mybucket" -> "in.c-" + "mybucket"
            parts = bucket_id.split(".c-", 1)
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
        return [table["name"] for table in bucket.get("tables", [])]

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
        branch_id = _self._normalize_branch_id(branch_id)

        # Add branch ID to table_id if in dev branch
        # Pattern: "in.c-bucket.table" -> "in.c-20533-bucket.table"
        if branch_id:
            # Split: "in.c-bucket.table" -> ["in", "c-bucket", "table"]
            parts = table_id.split(".")
            if len(parts) == 3 and parts[1].startswith("c-"):
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

        try:
            result = response.json()
        except ValueError as e:
            import streamlit as st

            error_msg = f"❌ API returned invalid JSON for table {full_table_id}. Status: {response.status_code}, Content: {response.text[:200]}..."
            st.error(error_msg)
            # Re-raise with a clear message
            raise ValueError(error_msg) from e

        # Debug: Verify we got a dict
        if not isinstance(result, dict):
            import streamlit as st

            st.error(f"❌ API returned non-dict for table {full_table_id}: {type(result)}")
            st.write("Response:", result)
            raise ValueError(f"get_table_detail expected dict, got {type(result)}: {result}")

        return result

    # ==================== Job Management ====================

    def run_component(
        self, component_id: str, config_id: str, branch_id: Optional[str] = None, mode: str = "run"
    ) -> Dict[str, Any]:
        """
        Trigger a component run.

        Args:
            component_id: Component ID
            config_id: Configuration ID
            branch_id: Branch ID (None for default branch)
            mode: Job mode - "run" (default) or "debug"

        Returns:
            Job information dictionary with job ID
        """
        url = f"{self.queue_url}/jobs"

        payload = {"mode": mode, "component": component_id, "config": config_id}

        if branch_id:
            payload["branchId"] = str(branch_id)

        response = requests.post(url, headers={**self.headers, "Content-Type": "application/json"}, json=payload)

        if not response.ok:
            try:
                error_detail = response.json()
                raise ValueError(
                    f"Job creation failed: {error_detail.get('error', error_detail.get('message', response.text))}"
                )
            except ValueError:
                raise
            except (json.JSONDecodeError, KeyError, TypeError):
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

            if status["status"] in ["success", "error", "cancelled", "terminated"]:
                return status

            if time.time() - start_time > timeout:
                raise TimeoutError(f"Job {job_id} did not complete within {timeout} seconds")

            time.sleep(poll_interval)

    def get_job_events(self, job_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Get events/logs for a specific job.

        Args:
            job_id: Job ID
            limit: Maximum number of events to retrieve (default 1000)

        Returns:
            List of event dictionaries containing log messages
        """
        # First get the job to extract the runId
        job_status = self.get_job_status(job_id)
        run_id = job_status.get("runId")

        if not run_id:
            raise ValueError(f"Job {job_id} does not have a runId")

        # Query events using runId
        url = f"{self.storage_url}/v2/storage/events"
        params = {"runId": run_id, "limit": limit}

        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()

        events = response.json()
        return events

    # ==================== Data Queries ====================

    @st.cache_data(ttl=3600)
    def get_default_branch_id(_self) -> str:
        """
        Get the numeric ID of the default (Main) branch.

        Returns:
            Numeric branch ID as string
        """
        # List all dev branches and find the "Main" branch
        url = f"{_self.storage_url}/v2/storage/dev-branches"
        response = requests.get(url, headers=_self.headers)
        response.raise_for_status()

        branches = response.json()

        # Find the Main branch (isDefault=True or name="Main")
        for branch in branches:
            if branch.get("isDefault", False) or branch.get("name") == "Main":
                return str(branch["id"])

        raise ValueError("Could not find Main/default branch in dev-branches list")

    def _resolve_branch_id(self, branch_id: Optional[str]) -> str:
        """
        Resolve branch ID to numeric ID. Query Service requires numeric IDs, not 'default'.

        Args:
            branch_id: Branch ID (None or string) - can be numeric ID or None for default

        Returns:
            Numeric branch ID as string
        """
        if branch_id is None:
            return self.get_default_branch_id()
        return str(branch_id)

    @st.cache_data(ttl=300)
    def query_table_data(
        _self, table_id: str, branch_id: Optional[str] = None, limit: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Query table data via Keboola Query Service API (async job-based).

        Args:
            table_id: Full table ID without branch prefix (e.g., "in.c-bucket.table")
            branch_id: Branch ID (None for default branch) - must be numeric
            limit: Maximum number of rows to fetch

        Returns:
            DataFrame with table data
        """
        if not _self.workspace_id:
            raise ValueError("KBC_WORKSPACE_ID must be configured for data queries")

        # Resolve to numeric branch ID (Query Service requires numeric, not "default")
        numeric_branch_id = _self._resolve_branch_id(branch_id)

        # For dev branches, table IDs are prefixed with branch ID
        # Pattern: "in.c-bucket.table" -> "in.c-20533-bucket.table"
        if branch_id is not None:
            parts = table_id.split(".")
            if len(parts) == 3 and parts[1].startswith("c-"):
                stage = parts[0]  # "in" or "out"
                bucket_name = parts[1][2:]  # "bucket" (strip "c-")
                table_name = parts[2]  # "table"
                full_table_id = f"{stage}.c-{branch_id}-{bucket_name}.{table_name}"
            else:
                full_table_id = f"{branch_id}-{table_id}"
        else:
            full_table_id = table_id

        # Build SQL query with fully qualified table name
        # Keboola table ID format: "stage.c-bucket.table" (e.g., "in.c-mybucket.mytable")
        # In Snowflake: schema = "stage.c-bucket", table = "table"
        # So qualified name = "in.c-mybucket"."mytable"
        parts = full_table_id.split(".")
        if len(parts) == 3:
            schema = f"{parts[0]}.{parts[1]}"  # e.g., "in.c-mybucket"
            table = parts[2]  # e.g., "mytable"
            qualified_name = f'"{schema}"."{table}"'
        else:
            qualified_name = f'"{full_table_id}"'

        query = f"SELECT * FROM {qualified_name}"
        if limit:
            query += f" LIMIT {limit}"

        # Execute query via Query Service
        return _self._execute_query_service_query(query, numeric_branch_id)

    def _execute_query_service_query(_self, query: str, numeric_branch_id: str) -> pd.DataFrame:
        """
        Execute a query via Keboola Query Service (async job-based API).

        Args:
            query: SQL query to execute
            numeric_branch_id: Numeric branch ID (NOT "default")

        Returns:
            DataFrame with query results
        """
        headers = _self.headers.copy()
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"

        # Step 1: Submit query job
        # POST /api/v1/branches/{branchId}/workspaces/{workspaceId}/queries
        submit_url = (
            f"{_self.query_service_url}/api/v1/branches/{numeric_branch_id}/workspaces/{_self.workspace_id}/queries"
        )

        payload = {"statements": [query]}

        response = requests.post(submit_url, headers=headers, json=payload)
        response.raise_for_status()

        job_data = response.json()
        query_job_id = job_data.get("queryJobId")

        if not query_job_id:
            raise ValueError(f"Query Service did not return a queryJobId: {job_data}")

        # Step 2: Poll for job completion
        # GET /api/v1/queries/{queryJobId}
        status_url = f"{_self.query_service_url}/api/v1/queries/{query_job_id}"

        max_attempts = 60  # 60 * 2 seconds = 2 minutes timeout
        status_data = None
        for _ in range(max_attempts):
            status_response = requests.get(status_url, headers=headers)
            status_response.raise_for_status()

            status_data = status_response.json()
            status = status_data.get("status")

            if status == "completed":
                break
            elif status in ["failed", "cancelled", "canceled"]:
                error_msg = status_data.get("error", {}).get("message", "Unknown error")
                raise ValueError(f"Query job failed: {error_msg}")
            elif status in ["created", "enqueued", "processing"]:
                time.sleep(2)
            else:
                # Unknown status, wait and retry
                time.sleep(2)
        else:
            raise TimeoutError(f"Query job {query_job_id} did not complete within timeout")

        # Step 3: Get results
        # GET /api/v1/queries/{queryJobId}/{statementId}/results
        statements = status_data.get("statements", [])
        if not statements:
            return pd.DataFrame()

        statement_id = statements[0].get("id", 0)
        results_url = f"{_self.query_service_url}/api/v1/queries/{query_job_id}/{statement_id}/results"

        results_response = requests.get(results_url, headers=headers)
        results_response.raise_for_status()

        result_data = results_response.json()

        # Parse results into DataFrame
        columns = [col.get("name", f"col_{i}") for i, col in enumerate(result_data.get("columns", []))]
        rows = result_data.get("rows", [])

        if rows and columns:
            return pd.DataFrame(rows, columns=columns)

        return pd.DataFrame()

    def _execute_query_service_batch(_self, queries: List[str], numeric_branch_id: str) -> List[pd.DataFrame]:
        """
        Execute multiple queries via Keboola Query Service in a single batch.

        Args:
            queries: List of SQL queries to execute
            numeric_branch_id: Numeric branch ID (NOT "default")

        Returns:
            List of DataFrames with query results (one per query)
        """
        if not queries:
            return []

        headers = _self.headers.copy()
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"

        # Step 1: Submit batch query job
        submit_url = (
            f"{_self.query_service_url}/api/v1/branches/{numeric_branch_id}/workspaces/{_self.workspace_id}/queries"
        )

        payload = {"statements": queries}

        response = requests.post(submit_url, headers=headers, json=payload)
        response.raise_for_status()

        job_data = response.json()
        query_job_id = job_data.get("queryJobId")

        if not query_job_id:
            raise ValueError(f"Query Service did not return a queryJobId: {job_data}")

        # Step 2: Poll for job completion
        status_url = f"{_self.query_service_url}/api/v1/queries/{query_job_id}"

        max_attempts = 60  # 60 * 2 seconds = 2 minutes timeout
        status_data = None
        for _ in range(max_attempts):
            status_response = requests.get(status_url, headers=headers)
            status_response.raise_for_status()

            status_data = status_response.json()
            status = status_data.get("status")

            if status == "completed":
                break
            elif status in ["failed", "cancelled", "canceled"]:
                error_msg = status_data.get("error", {}).get("message", "Unknown error")
                raise ValueError(f"Query job failed: {error_msg}")
            elif status in ["created", "enqueued", "processing"]:
                time.sleep(2)
            else:
                time.sleep(2)
        else:
            raise TimeoutError(f"Query job {query_job_id} did not complete within timeout")

        # Step 3: Get results for each statement
        statements = status_data.get("statements", [])
        results = []

        for i, stmt in enumerate(statements):
            statement_id = stmt.get("id", i)
            results_url = f"{_self.query_service_url}/api/v1/queries/{query_job_id}/{statement_id}/results"

            results_response = requests.get(results_url, headers=headers)
            results_response.raise_for_status()

            result_data = results_response.json()

            # Parse results into DataFrame
            columns = [col.get("name", f"col_{j}") for j, col in enumerate(result_data.get("columns", []))]
            rows = result_data.get("rows", [])

            if rows and columns:
                results.append(pd.DataFrame(rows, columns=columns))
            else:
                results.append(pd.DataFrame())

        return results

    def execute_queries_batch(
        _self, queries: List[str], branch_id: Optional[str] = None, batch_size: int = 50
    ) -> List[pd.DataFrame]:
        """
        Execute multiple SQL queries in batches via Keboola Query Service.

        Args:
            queries: List of SQL queries to execute
            branch_id: Branch ID (None for default branch)
            batch_size: Maximum statements per batch (default 50)

        Returns:
            List of DataFrames with query results (one per query, in same order)
        """
        if not _self.workspace_id:
            raise ValueError("KBC_WORKSPACE_ID must be configured for queries")

        if not queries:
            return []

        # Resolve to numeric branch ID
        numeric_branch_id = _self._resolve_branch_id(branch_id)

        # Execute in batches
        all_results = []
        for i in range(0, len(queries), batch_size):
            batch = queries[i : i + batch_size]
            batch_results = _self._execute_query_service_batch(batch, numeric_branch_id)
            all_results.extend(batch_results)

        return all_results

    def execute_query(_self, query: str, branch_id: Optional[str] = None, return_dataframe: bool = True):
        """
        Execute a custom SQL query via Keboola Query Service API.

        Args:
            query: SQL query to execute
            branch_id: Branch ID (None for default branch)
            return_dataframe: If True, returns DataFrame; if False, returns raw result dict

        Returns:
            DataFrame or dict with query results
        """
        if not _self.workspace_id:
            raise ValueError("KBC_WORKSPACE_ID must be configured for queries")

        # Resolve to numeric branch ID
        numeric_branch_id = _self._resolve_branch_id(branch_id)

        if return_dataframe:
            return _self._execute_query_service_query(query, numeric_branch_id)
        else:
            df = _self._execute_query_service_query(query, numeric_branch_id)
            return {"columns": df.columns.tolist(), "rows": df.values.tolist()}

    def get_table_data_preview(self, table_id: str, branch_id: Optional[str] = None, limit: int = 100) -> pd.DataFrame:
        """
        Get table data preview (Storage API, no workspace required).

        Args:
            table_id: Table ID
            branch_id: Branch ID
            limit: Rows limit (max 1000 usually)

        Returns:
            DataFrame with preview data
        """
        branch_id = self._normalize_branch_id(branch_id)

        # Handle branch logic for table ID
        if branch_id:
            # Logic to construct full ID if needed, similar to other methods
            # But data-preview endpoint usually takes the ID as known in that context?
            # Wait, storage API for branches handles components/configs, but for tables/buckets?
            # Actually, simpler: Use standard table detail logic to get full ID, then call preview

            # Re-use logic from get_table_detail to build full_table_id
            # Pattern: "in.c-bucket.table" -> "in.c-20533-bucket.table"
            parts = table_id.split(".")
            if len(parts) == 3 and parts[1].startswith("c-"):
                stage = parts[0]
                bucket_name = parts[1][2:]
                table_name = parts[2]
                full_table_id = f"{stage}.c-{branch_id}-{bucket_name}.{table_name}"
            else:
                full_table_id = f"{branch_id}-{table_id}"
        else:
            full_table_id = table_id

        url = f"{self.storage_url}/v2/storage/tables/{full_table_id}/data-preview"
        params = {"limit": limit, "format": "json"}

        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()

        data = response.json()

        # Convert to DataFrame
        # Response format: {"columns": ["col1", "col2"], "rows": [{"col1": "val1", ...}]}
        if "rows" in data and len(data["rows"]) > 0:
            # Rows can be list of dicts (JSON) or list of lists (JSON arrays)
            rows = data["rows"]
            flattened_rows = []

            first_row = rows[0]

            if isinstance(first_row, dict):
                # Handle list of dicts
                for row in rows:
                    flat_row = {}
                    for key, val in row.items():
                        if isinstance(val, dict) and "value" in val:
                            flat_row[key] = val["value"]
                        else:
                            flat_row[key] = val
                    flattened_rows.append(flat_row)
            elif isinstance(first_row, list):
                # Handle list of lists
                for row in rows:
                    flat_row = []
                    for val in row:
                        if isinstance(val, dict) and "value" in val:
                            flat_row.append(val["value"])
                        else:
                            flat_row.append(val)
                    flattened_rows.append(flat_row)
            else:
                # Fallback for simple values
                flattened_rows = rows

            if "columns" in data:
                # Extract column names safely (handle if they are dicts)
                columns = []
                for col in data["columns"]:
                    if isinstance(col, dict):
                        columns.append(col.get("name", str(col)))
                    else:
                        columns.append(str(col))

                # Ensure correct column order
                return pd.DataFrame(flattened_rows, columns=columns)
            else:
                return pd.DataFrame(flattened_rows)
        return pd.DataFrame()

    def get_qualified_table_name(_self, table_id: str, branch_id: Optional[str] = None) -> str:
        """
        Get fully qualified table name for SQL queries.

        Args:
            table_id: Table ID without branch prefix (e.g., "in.c-bucket.table")
            branch_id: Branch ID (None for default branch)

        Returns:
            Qualified table name for SQL queries (e.g., "in.c-20533-bucket"."table")
        """
        branch_id = _self._normalize_branch_id(branch_id)

        # Add branch ID to table_id if in dev branch
        if branch_id:
            parts = table_id.split(".")
            if len(parts) == 3 and parts[1].startswith("c-"):
                stage = parts[0]  # "in" or "out"
                bucket_name = parts[1][2:]  # "bucket" (strip "c-")
                table_name = parts[2]  # "table"
                full_table_id = f"{stage}.c-{branch_id}-{bucket_name}.{table_name}"
            else:
                # Fallback
                full_table_id = f"{branch_id}-{table_id}"
        else:
            full_table_id = table_id

        # Build qualified name: "schema"."table"
        # Keboola table ID format: "stage.c-bucket.table" -> schema = "stage.c-bucket", table = "table"
        parts = full_table_id.split(".")
        if len(parts) == 3:
            schema = f"{parts[0]}.{parts[1]}"  # e.g., "in.c-mybucket"
            table = parts[2]  # e.g., "mytable"
            return f'"{schema}"."{table}"'
        else:
            return f'"{full_table_id}"'
