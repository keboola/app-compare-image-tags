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

    def __init__(self):
        """Initialize the Keboola API client with credentials from config."""
        self.storage_url = get_config("KBC_URL")
        self.token = get_config("KBC_TOKEN")
        self.workspace_id = get_config("KBC_WORKSPACE_ID")

        if not self.storage_url or not self.token:
            raise ValueError("KBC_URL and KBC_TOKEN must be configured")

        # Derive queue URL from storage URL
        # Example: https://connection.north-europe.azure.keboola.com -> https://queue.north-europe.azure.keboola.com
        region_part = self.storage_url.split("//")[1]  # "connection.north-europe.azure.keboola.com"
        self.queue_url = f"https://queue.{'.'.join(region_part.split('.')[1:])}"

        self.headers = {
            "X-StorageApi-Token": self.token
        }

    # ==================== Configuration Management ====================

    @st.cache_data(ttl=3600)
    def get_configuration(_self, config_id: str) -> Dict[str, Any]:
        """
        Get configuration details by ID.

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

    def create_configuration(self, component_id: str, name: str, description: str, configuration: Dict) -> Dict[str, Any]:
        """
        Create a new configuration.

        Args:
            component_id: Component ID
            name: Configuration name
            description: Configuration description
            configuration: Configuration data dictionary

        Returns:
            Created configuration dictionary
        """
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
        response.raise_for_status()
        return response.json()

    def duplicate_configuration_with_tag(self, original_config: Dict, new_tag: str) -> Dict[str, Any]:
        """
        Duplicate a configuration with a new image tag.

        Args:
            original_config: Original configuration dictionary
            new_tag: New image tag to use

        Returns:
            Created configuration dictionary
        """
        component_id = original_config['component']
        config_data = original_config['configuration']

        # Modify the image tag in the configuration
        if 'runtime' in config_data and 'image_tag' in config_data['runtime']:
            config_data['runtime']['image_tag'] = new_tag
        elif 'image_tag' in config_data:
            config_data['image_tag'] = new_tag

        # Create new configuration
        new_name = f"{original_config['name']} - Test ({new_tag})"
        new_description = f"Test configuration for image tag comparison: {new_tag}"

        return self.create_configuration(
            component_id=component_id,
            name=new_name,
            description=new_description,
            configuration=config_data
        )

    # ==================== Branch Management ====================

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

        data = {'name': name}
        if description:
            data['description'] = description

        response = requests.post(
            url,
            headers=self.headers,
            data=data
        )
        response.raise_for_status()
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

    @st.cache_data(ttl=300)
    def list_buckets(_self, branch_id: Optional[str] = None) -> List[str]:
        """
        List all buckets in a branch.

        Args:
            branch_id: Branch ID (None for default branch)

        Returns:
            List of bucket IDs
        """
        url = f"{_self.storage_url}/v2/storage/buckets"

        headers = _self.headers.copy()
        if branch_id:
            headers['X-KBC-BranchId'] = str(branch_id)

        response = requests.get(url, headers=headers)
        response.raise_for_status()

        buckets = response.json()
        return [bucket['id'] for bucket in buckets]

    @st.cache_data(ttl=300)
    def list_tables_in_bucket(_self, bucket_id: str, branch_id: Optional[str] = None) -> List[str]:
        """
        List all tables in a bucket.

        Args:
            bucket_id: Bucket ID
            branch_id: Branch ID (None for default branch)

        Returns:
            List of table names (without bucket prefix)
        """
        url = f"{_self.storage_url}/v2/storage/buckets/{bucket_id}"

        headers = _self.headers.copy()
        if branch_id:
            headers['X-KBC-BranchId'] = str(branch_id)

        response = requests.get(url, headers=headers)
        response.raise_for_status()

        bucket = response.json()
        return [table['name'] for table in bucket.get('tables', [])]

    @st.cache_data(ttl=300)
    def get_table_detail(_self, table_id: str, branch_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get detailed table metadata.

        Args:
            table_id: Full table ID (e.g., "in.c-bucket.table")
            branch_id: Branch ID (None for default branch)

        Returns:
            Table metadata dictionary including columns, PKs, types, row count
        """
        url = f"{_self.storage_url}/v2/storage/tables/{table_id}"

        headers = _self.headers.copy()
        if branch_id:
            headers['X-KBC-BranchId'] = str(branch_id)

        response = requests.get(url, headers=headers)
        response.raise_for_status()

        return response.json()

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
        response.raise_for_status()

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
            table_id: Full table ID (e.g., "in.c-bucket.table")
            branch_id: Branch ID (None for default branch)
            limit: Maximum number of rows to fetch

        Returns:
            DataFrame with table data
        """
        if not _self.workspace_id:
            raise ValueError("KBC_WORKSPACE_ID must be configured for data queries")

        url = f"{_self.storage_url}/v2/storage/workspaces/{_self.workspace_id}/query"

        # Build SQL query
        parts = table_id.split('.')
        if len(parts) == 3:
            bucket, table = parts[1], parts[2]
            qualified_name = f'"{parts[0]}"."{bucket}"."{table}"'
        else:
            qualified_name = f'"{table_id}"'

        query = f'SELECT * FROM {qualified_name}'
        if limit:
            query += f' LIMIT {limit}'

        headers = _self.headers.copy()
        headers['Content-Type'] = 'application/json'

        if branch_id:
            headers['X-KBC-BranchId'] = str(branch_id)

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
