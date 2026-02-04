"""
Multi-level comparison engine for Keboola component outputs.

This module implements comprehensive comparison logic across multiple levels:
- Bucket comparison (which buckets exist)
- Table comparison (which tables exist in each bucket)
- Metadata comparison (PKs, columns, data types, row counts)
- Row-level comparison (actual data differences)
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
import streamlit as st

from .keboola_client import KeboolaAPIClient

logger = logging.getLogger(__name__)


class ComparisonStatus(str, Enum):
    """Status enum for comparison results."""

    MATCH = "match"
    DIFFER = "differ"
    SKIPPED = "skipped"
    ERROR = "error"


def _sanitize_sql_identifier(name: str) -> str:
    """Validate and quote SQL identifier to prevent injection."""
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
        # For identifiers with special chars, escape internal quotes
        escaped = name.replace('"', '""')
        return f'"{escaped}"'
    return f'"{name}"'


def _validate_table_id(table_id: str) -> bool:
    """Validate table ID format."""
    return bool(re.match(r"^(in|out)\.c-[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+$", table_id))


def _normalize_bucket_id(bucket_id: str) -> str:
    """
    Normalize a bucket ID by stripping any embedded branch ID.

    Bucket IDs from dev branches have the format: {stage}.c-{branch_id}-{bucket_name}
    This function returns the canonical form: {stage}.c-{bucket_name}

    Args:
        bucket_id: Bucket ID that may contain an embedded branch ID

    Returns:
        Canonical bucket ID without branch ID prefix
    """
    # Pattern: in.c-{numeric_branch_id}-{rest} or out.c-{numeric_branch_id}-{rest}
    # Example: in.c-27406-keboola-ex-instagram -> in.c-keboola-ex-instagram
    match = re.match(r"^(in|out)\.c-(\d+)-(.+)$", bucket_id)
    if match:
        stage = match.group(1)
        # branch_id = match.group(2)  # Not needed, we're stripping it
        bucket_name = match.group(3)
        return f"{stage}.c-{bucket_name}"
    # Already canonical or unexpected format - return as-is
    return bucket_id


class ComparisonEngine:
    """Executes bucket, table, metadata, and row-level comparisons."""

    # Configuration constants
    DEFAULT_ROW_LIMIT = 1000
    MAX_ROW_LIMIT = 100_000
    PREVIEW_ROW_LIMIT = 1_000
    SAMPLE_DISPLAY_LIMIT = 5
    SAMPLE_DIFF_LIMIT = 10

    def __init__(self, client: KeboolaAPIClient):
        """
        Initialize comparison engine.

        Args:
            client: Keboola API client instance
        """
        self.client = client

    def compare_outputs(
        self, production_branch: Optional[str] = None, test_branch_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute full comparison workflow across all levels.

        Args:
            production_branch: Production branch ID (None for default branch)
            test_branch_id: Test branch ID

        Returns:
            Comprehensive comparison results dictionary
        """
        st.markdown("## 🔍 Starting Multi-Level Comparison")
        st.info(f"""
        **Comparing:**
        - 🔵 Production Branch ID: `{production_branch}`
        - 🟢 Test Branch ID: `{test_branch_id}`
        """)

        results = {}

        # Level 1: Bucket comparison
        st.markdown("---")
        st.markdown("## Step 1: Bucket Comparison")
        results["bucket_comparison"] = self._compare_buckets(production_branch, test_branch_id)

        # Level 2: Table comparison
        st.markdown("---")
        st.markdown("## Step 2: Table Comparison")
        results["table_comparison"] = self._compare_tables(
            production_branch, test_branch_id, results["bucket_comparison"]
        )

        # Level 3: Metadata comparison
        st.markdown("---")
        st.markdown("## Step 3: Metadata Comparison")
        results["metadata_comparison"] = self._compare_metadata(
            production_branch, test_branch_id, results["table_comparison"]
        )

        # Level 4: Row-level comparison
        st.markdown("---")
        st.markdown("## Step 4: Row-Level Data Comparison")
        results["row_differences"] = self._compare_row_data(
            production_branch, test_branch_id, results["metadata_comparison"]
        )

        # Level 5: Job logs comparison (only for config mode)
        if st.session_state.get("comparison_mode") == "config":
            st.markdown("---")
            st.markdown("## Step 5: Job Logs Comparison")
            results["log_comparison"] = self._compare_job_logs()
        else:
            results["log_comparison"] = None

        # Generate summary
        st.markdown("---")
        st.markdown("## 📊 Generating Summary")
        results["summary"] = self._generate_summary(results)

        st.markdown("---")
        st.success("✅ Comparison complete!")

        return results

    def _compare_buckets(self, prod_branch: Optional[str], test_branch: Optional[str]) -> Dict[str, Any]:
        """
        Compare buckets between branches.

        Args:
            prod_branch: Production branch ID
            test_branch: Test branch ID

        Returns:
            Bucket comparison results
        """
        st.markdown("### 🪣 Bucket Comparison")

        # Get buckets with debug info
        try:
            prod_buckets = set(self.client.list_buckets(prod_branch))
            st.success(f"✅ **Production Branch (ID: {prod_branch})**: Found {len(prod_buckets)} bucket(s)")
            if prod_buckets:
                with st.expander(f"View {len(prod_buckets)} production bucket(s)", expanded=len(prod_buckets) <= 5):
                    for bucket in sorted(prod_buckets):
                        st.text(f"  • {bucket}")
        except Exception as e:
            st.error(f"❌ Error listing production buckets: {str(e)}")
            st.exception(e)
            prod_buckets = set()

        try:
            test_buckets = set(self.client.list_buckets(test_branch))
            st.success(f"✅ **Test Branch (ID: {test_branch})**: Found {len(test_buckets)} bucket(s)")
            if test_buckets:
                with st.expander(f"View {len(test_buckets)} test bucket(s)", expanded=len(test_buckets) <= 5):
                    for bucket in sorted(test_buckets):
                        st.text(f"  • {bucket}")
        except Exception as e:
            st.error(f"❌ Error listing test buckets: {str(e)}")
            st.exception(e)
            test_buckets = set()

        # Show comparison results
        common = sorted(prod_buckets & test_buckets)
        prod_only = sorted(prod_buckets - test_buckets)
        test_only = sorted(test_buckets - prod_buckets)

        st.markdown("---")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Common Buckets", len(common))
            if common:
                with st.expander(f"View {len(common)} common bucket(s)"):
                    for bucket in common:
                        st.text(f"  ✅ {bucket}")
        with col2:
            st.metric("Production Only", len(prod_only))
            if prod_only:
                with st.expander(f"View {len(prod_only)} production-only bucket(s)"):
                    for bucket in prod_only:
                        st.text(f"  🔵 {bucket}")
        with col3:
            st.metric("Test Only", len(test_only))
            if test_only:
                with st.expander(f"View {len(test_only)} test-only bucket(s)"):
                    for bucket in test_only:
                        st.text(f"  🟢 {bucket}")

        return {
            "production_only": prod_only,
            "test_only": test_only,
            "common": common,
            "status": ComparisonStatus.MATCH if prod_buckets == test_buckets else ComparisonStatus.DIFFER,
            "_debug": {
                "production_buckets": sorted(prod_buckets),
                "test_buckets": sorted(test_buckets),
                "production_branch_id": prod_branch,
                "test_branch_id": test_branch,
            },
        }

    def _compare_tables(
        self, prod_branch: Optional[str], test_branch: Optional[str], bucket_comparison: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compare tables within common buckets.

        Args:
            prod_branch: Production branch ID
            test_branch: Test branch ID
            bucket_comparison: Bucket comparison results

        Returns:
            Table comparison results per bucket
        """
        st.markdown("### 📊 Table Comparison")

        if not bucket_comparison["common"]:
            st.warning("⚠️ No common buckets to compare tables")
            return {}

        results = {}

        for bucket in bucket_comparison["common"]:
            st.markdown(f"#### Bucket: `{bucket}`")

            prod_tables = set(self.client.list_tables_in_bucket(bucket, prod_branch))
            test_tables = set(self.client.list_tables_in_bucket(bucket, test_branch))

            common = sorted(prod_tables & test_tables)
            prod_only = sorted(prod_tables - test_tables)
            test_only = sorted(test_tables - prod_tables)

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Common Tables", len(common))
                if common:
                    with st.expander(f"View {len(common)} common table(s)"):
                        for table in common:
                            st.text(f"  ✅ {table}")
            with col2:
                st.metric("Production Only", len(prod_only))
                if prod_only:
                    with st.expander(f"View {len(prod_only)} production-only table(s)"):
                        for table in prod_only:
                            st.text(f"  🔵 {table}")
            with col3:
                st.metric("Test Only", len(test_only))
                if test_only:
                    with st.expander(f"View {len(test_only)} test-only table(s)"):
                        for table in test_only:
                            st.text(f"  🟢 {table}")

            results[bucket] = {
                "production_only": prod_only,
                "test_only": test_only,
                "common": common,
                "status": ComparisonStatus.MATCH if prod_tables == test_tables else ComparisonStatus.DIFFER,
            }

        return results

    def _fetch_table_metadata(
        self, table_id: str, branch: Optional[str], branch_name: str
    ) -> Tuple[str, str, Optional[Dict], Optional[str]]:
        """
        Fetch metadata for a single table (used for parallel execution).

        Uses thread-safe _get_table_detail_raw() method to avoid Streamlit
        ScriptRunContext warnings when called from ThreadPoolExecutor.

        Args:
            table_id: Table ID to fetch
            branch: Branch ID
            branch_name: Human-readable branch name (for error messages)

        Returns:
            Tuple of (table_id, branch_name, metadata_dict or None, error_message or None)
        """
        try:
            # Use thread-safe method (no Streamlit decorators/calls)
            meta = self.client._get_table_detail_raw(table_id, branch)
            if not isinstance(meta, dict):
                return (table_id, branch_name, None, f"Expected dict, got {type(meta)}: {meta}")
            return (table_id, branch_name, meta, None)
        except Exception as e:
            return (table_id, branch_name, None, str(e))

    def _compare_metadata(
        self, prod_branch: Optional[str], test_branch: Optional[str], table_comparison: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compare table metadata (PKs, columns, types, row counts).

        Uses parallel fetching for improved performance.

        Args:
            prod_branch: Production branch ID
            test_branch: Test branch ID
            table_comparison: Table comparison results

        Returns:
            Metadata comparison results per table
        """
        st.markdown("### 📋 Metadata Comparison")

        if not table_comparison:
            st.warning("⚠️ No common tables to compare metadata")
            return {}

        results = {}

        # Collect all table IDs to compare
        table_ids = []
        for bucket, comparison in table_comparison.items():
            for table in comparison["common"]:
                table_ids.append(f"{bucket}.{table}")

        total_common_tables = len(table_ids)
        st.info(f"Comparing metadata for {total_common_tables} common table(s) in parallel...")

        # Phase 1: Fetch all metadata in parallel
        metadata_cache: Dict[str, Dict[str, Any]] = {}  # table_id -> {"prod": meta, "test": meta}
        fetch_errors: Dict[str, str] = {}

        # Use ThreadPoolExecutor to fetch all table metadata in parallel
        # Each table needs 2 fetches (prod and test), so we create tasks for all
        max_workers = min(20, total_common_tables * 2)  # Cap at 20 concurrent requests

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}

            # Submit all fetch tasks
            for table_id in table_ids:
                # Fetch production metadata
                future_prod = executor.submit(
                    self._fetch_table_metadata, table_id, prod_branch, "production"
                )
                futures[future_prod] = (table_id, "prod")

                # Fetch test metadata
                future_test = executor.submit(
                    self._fetch_table_metadata, table_id, test_branch, "test"
                )
                futures[future_test] = (table_id, "test")

            # Collect results as they complete
            for future in as_completed(futures):
                table_id, branch_type = futures[future]
                try:
                    _, _, meta, error = future.result()
                    if table_id not in metadata_cache:
                        metadata_cache[table_id] = {}

                    if error:
                        fetch_errors[f"{table_id}_{branch_type}"] = error
                    else:
                        metadata_cache[table_id][branch_type] = meta
                except Exception as e:
                    fetch_errors[f"{table_id}_{branch_type}"] = str(e)

        # Phase 2: Process results
        for table_id in table_ids:
            cache_entry = metadata_cache.get(table_id, {})
            prod_meta = cache_entry.get("prod")
            test_meta = cache_entry.get("test")

            # Check for fetch errors
            prod_error = fetch_errors.get(f"{table_id}_prod")
            test_error = fetch_errors.get(f"{table_id}_test")

            if prod_error or test_error:
                error_msg = f"Fetch errors - "
                if prod_error:
                    error_msg += f"prod: {prod_error}"
                if test_error:
                    error_msg += f"{', ' if prod_error else ''}test: {test_error}"
                st.error(f"❌ Error fetching metadata for table `{table_id}`: {error_msg}")
                results[table_id] = {"status": ComparisonStatus.ERROR, "error": error_msg}
                continue

            if not prod_meta or not test_meta:
                st.error(f"❌ Missing metadata for table `{table_id}`")
                results[table_id] = {"status": ComparisonStatus.ERROR, "error": "Missing metadata"}
                continue

            try:
                pk_comparison = self._compare_primary_keys(prod_meta, test_meta)
                col_comparison = self._compare_columns(prod_meta, test_meta)
                type_comparison = self._compare_data_types(prod_meta, test_meta)
                count_comparison = self._compare_row_counts(prod_meta, test_meta)

                # Determine overall status
                all_match = (
                    pk_comparison["match"]
                    and col_comparison["match"]
                    and type_comparison["match"]
                    and count_comparison["match"]
                )

                results[table_id] = {
                    "primary_keys": pk_comparison,
                    "columns": col_comparison,
                    "data_types": type_comparison,
                    "row_count": count_comparison,
                    "status": ComparisonStatus.MATCH if all_match else ComparisonStatus.DIFFER,
                }

                # Show detailed success/warning for this table
                if all_match:
                    st.success(f"✅ Table `{table_id}`: All metadata matches")
                else:
                    # Create detailed mismatch message
                    mismatch_details = []
                    if not pk_comparison["match"]:
                        prod_pks = pk_comparison["production"]
                        test_pks = pk_comparison["test"]
                        mismatch_details.append(f"Primary Keys differ (prod: {prod_pks}, test: {test_pks})")
                    if not col_comparison["match"]:
                        prod_only = col_comparison.get("production_only", [])
                        test_only = col_comparison.get("test_only", [])
                        if prod_only:
                            mismatch_details.append(f"Columns only in prod: {prod_only}")
                        if test_only:
                            mismatch_details.append(f"Columns only in test: {test_only}")
                    if not type_comparison["match"]:
                        type_diffs = type_comparison.get("differences", {})
                        mismatch_details.append(f"Type differences in {len(type_diffs)} column(s)")
                    if not count_comparison["match"]:
                        mismatch_details.append(
                            f"Row count differs (prod: {count_comparison['production']}, test: {count_comparison['test']})"
                        )

                    st.warning(f"⚠️ Table `{table_id}`: {'; '.join(mismatch_details)}")

            except Exception as e:
                st.error(f"❌ Error comparing metadata for table `{table_id}`: {str(e)}")
                results[table_id] = {"status": ComparisonStatus.ERROR, "error": str(e)}

        return results

    def _compare_primary_keys(self, prod_meta: Dict, test_meta: Dict) -> Dict[str, Any]:
        """Compare primary keys."""
        # Handle None values explicitly
        prod_pks = prod_meta.get("primaryKey") or []
        test_pks = test_meta.get("primaryKey") or []

        # Ensure we're comparing lists (handle any unexpected data types)
        if not isinstance(prod_pks, list):
            prod_pks = [prod_pks] if prod_pks else []
        if not isinstance(test_pks, list):
            test_pks = [test_pks] if test_pks else []

        # Compare as sorted lists to handle order differences
        matches = sorted(prod_pks) == sorted(test_pks)

        return {
            "match": matches,
            "production": prod_pks,
            "test": test_pks,
            "production_sorted": sorted(prod_pks),
            "test_sorted": sorted(test_pks),
        }

    def _compare_columns(self, prod_meta: Dict, test_meta: Dict) -> Dict[str, Any]:
        """Compare column names."""
        # Extract column names safely
        prod_columns = prod_meta.get("columns", [])
        test_columns = test_meta.get("columns", [])

        # Handle edge cases where columns might not be a list
        if not isinstance(prod_columns, list):
            prod_columns = []
        if not isinstance(test_columns, list):
            test_columns = []

        # Get column names (handle both string and dict formats)
        prod_cols = set()

        # Prefer definition.columns if available (as per user hint)
        if "definition" in prod_meta and "columns" in prod_meta["definition"]:
            for col in prod_meta["definition"]["columns"]:
                prod_cols.add(col.get("name", ""))
        else:
            for col in prod_columns:
                if isinstance(col, dict):
                    prod_cols.add(col.get("name", ""))
                elif isinstance(col, str):
                    prod_cols.add(col)

        test_cols = set()
        if "definition" in test_meta and "columns" in test_meta["definition"]:
            for col in test_meta["definition"]["columns"]:
                test_cols.add(col.get("name", ""))
        else:
            for col in test_columns:
                if isinstance(col, dict):
                    test_cols.add(col.get("name", ""))
                elif isinstance(col, str):
                    test_cols.add(col)

        # Remove empty strings if any
        prod_cols.discard("")
        test_cols.discard("")

        return {
            "match": prod_cols == test_cols,
            "production_only": sorted(prod_cols - test_cols),
            "test_only": sorted(test_cols - prod_cols),
            "common": sorted(prod_cols & test_cols),
        }

    def _compare_data_types(self, prod_meta: Dict, test_meta: Dict) -> Dict[str, Any]:
        """Compare data types for common columns."""
        # Extract column info safely
        prod_columns = prod_meta.get("columns", [])
        test_columns = test_meta.get("columns", [])

        # Handle edge cases
        if not isinstance(prod_columns, list):
            prod_columns = []
        if not isinstance(test_columns, list):
            test_columns = []

        # Build type dictionaries with safe access
        prod_types = {}

        # Prefer definition.columns if available
        if "definition" in prod_meta and "columns" in prod_meta["definition"]:
            for col in prod_meta["definition"]["columns"]:
                # Type might be in definition.type or definition.baseType
                col_name = col.get("name", "")
                if "definition" in col and "type" in col["definition"]:
                    prod_types[col_name] = col["definition"]["type"]
                elif "basetype" in col:
                    prod_types[col_name] = col["basetype"]
                else:
                    prod_types[col_name] = col.get("type", "STRING")
        else:
            for col in prod_columns:
                if isinstance(col, dict) and "name" in col:
                    prod_types[col["name"]] = col.get("type", "STRING")
                elif isinstance(col, str):
                    prod_types[col] = "STRING"

        test_types = {}
        if "definition" in test_meta and "columns" in test_meta["definition"]:
            for col in test_meta["definition"]["columns"]:
                col_name = col.get("name", "")
                if "definition" in col and "type" in col["definition"]:
                    test_types[col_name] = col["definition"]["type"]
                elif "basetype" in col:
                    test_types[col_name] = col["basetype"]
                else:
                    test_types[col_name] = col.get("type", "STRING")
        else:
            for col in test_columns:
                if isinstance(col, dict) and "name" in col:
                    test_types[col["name"]] = col.get("type", "STRING")
                elif isinstance(col, str):
                    test_types[col] = "STRING"

        # Find differences only in common columns
        differences = {}
        for col in set(prod_types.keys()) & set(test_types.keys()):
            if prod_types[col] != test_types[col]:
                differences[col] = {"production": prod_types[col], "test": test_types[col]}

        return {"match": len(differences) == 0, "differences": differences}

    def _compare_row_counts(self, prod_meta: Dict, test_meta: Dict) -> Dict[str, Any]:
        """Compare row counts."""
        prod_count = prod_meta.get("rowsCount", 0)
        test_count = test_meta.get("rowsCount", 0)

        return {"match": prod_count == test_count, "production": prod_count, "test": test_count}

    def _compare_row_data(
        self,
        prod_branch: Optional[str],
        test_branch: Optional[str],
        metadata_comparison: Dict[str, Any],
        row_limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Compare actual row data for tables with matching metadata.

        Uses batched SQL queries for efficiency - collects queries for all tables
        and executes them in a single batch call.

        Args:
            prod_branch: Production branch ID
            test_branch: Test branch ID
            metadata_comparison: Metadata comparison results
            row_limit: Maximum rows to compare per table (reads from session state if None)

        Returns:
            Row-level difference results per table
        """
        # Read row_limit from session state if not provided
        if row_limit is None:
            row_limit = st.session_state.get("comparison_row_limit", self.DEFAULT_ROW_LIMIT)
        row_limit = max(1, min(int(row_limit), self.MAX_ROW_LIMIT))

        results = {}

        # Check if workspace is available for SQL comparison
        use_sql = bool(self.client.workspace_id)
        if not use_sql:
            st.info("ℹ️ Using pandas-based comparison (no workspace configured). Row limit applies.")

        # Phase 1: Identify tables to compare and collect queries
        tables_to_compare = []  # List of (table_id, meta, queries_dict)
        all_queries = []  # Flat list of all queries (only used when use_sql=True)
        query_index_map = {}  # Maps table_id -> (start_idx, end_idx) in all_queries

        for table_id, meta in metadata_comparison.items():
            # Skip if metadata doesn't match or error occurred
            if meta.get("status") == ComparisonStatus.ERROR:
                results[table_id] = {"status": ComparisonStatus.SKIPPED, "reason": f"Metadata error: {meta.get('error')}"}
                continue

            # Skip if ANY metadata doesn't match (primary keys, columns, data types)
            # We explicitly ALLOW row count differences to proceed to row comparison
            if (
                not meta.get("primary_keys", {}).get("match", True)
                or not meta.get("columns", {}).get("match", True)
                or not meta.get("data_types", {}).get("match", True)
            ):
                mismatch_reasons = []
                if not meta.get("primary_keys", {}).get("match", True):
                    mismatch_reasons.append("primary keys")
                if not meta.get("columns", {}).get("match", True):
                    mismatch_reasons.append("columns")
                if not meta.get("data_types", {}).get("match", True):
                    mismatch_reasons.append("data types")

                results[table_id] = {"status": ComparisonStatus.SKIPPED, "reason": f"Metadata mismatch: {', '.join(mismatch_reasons)}"}
                st.info(f"ℹ️ Skipping row comparison for `{table_id}`: metadata differs ({', '.join(mismatch_reasons)})")
                continue

            # Validate table ID format
            if not _validate_table_id(table_id):
                results[table_id] = {"status": ComparisonStatus.ERROR, "error": f"Invalid table ID format: {table_id}"}
                continue

            # Check if explicit table IDs are provided (for bucket pairs mode)
            table_pair = meta.get("_table_pair", {})
            prod_table_id = table_pair.get("table_a_id")
            test_table_id = table_pair.get("table_b_id")

            if use_sql:
                # Build queries for SQL comparison
                try:
                    queries = self._build_sql_comparison_queries(
                        table_id, prod_branch, test_branch, meta["columns"]["common"], row_limit,
                        prod_table_id=prod_table_id, test_table_id=test_table_id,
                    )

                    # Track query indices
                    start_idx = len(all_queries)
                    all_queries.extend([
                        queries["prod_not_in_test"],
                        queries["test_not_in_prod"],
                        queries["prod_count"],
                        queries["test_count"],
                    ])
                    end_idx = len(all_queries)

                    query_index_map[table_id] = (start_idx, end_idx)
                    tables_to_compare.append((table_id, meta, queries, prod_table_id, test_table_id))

                except Exception as e:
                    results[table_id] = {"status": ComparisonStatus.ERROR, "error": f"Failed to build queries: {str(e)}"}
            else:
                # For pandas comparison, we don't need queries
                tables_to_compare.append((table_id, meta, None, prod_table_id, test_table_id))

        # Phase 2: Execute all SQL queries in batch (only when using SQL)
        all_results = None
        if use_sql and all_queries:
            st.write(f"🚀 Executing {len(all_queries)} SQL queries in batch for {len(tables_to_compare)} table(s)...")
            try:
                all_results = self.client.execute_queries_batch(all_queries)
            except Exception as batch_error:
                st.warning(f"⚠️ Batch SQL execution failed: {str(batch_error)}. Falling back to individual queries...")
                all_results = None

        # Phase 3: Process results
        for table_id, meta, queries, prod_table_id, test_table_id in tables_to_compare:
            try:
                if use_sql:
                    # SQL-based comparison
                    start_idx, end_idx = query_index_map.get(table_id, (0, 0))
                    if all_results is not None:
                        # Use batched results
                        table_results = all_results[start_idx:end_idx]
                        comparison = self._process_sql_comparison_results(
                            table_id,
                            table_results[0],  # prod_only_df
                            table_results[1],  # test_only_df
                            table_results[2],  # prod_count_df
                            table_results[3],  # test_count_df
                            meta["primary_keys"]["production"],
                            queries,
                        )
                    else:
                        # Fallback: execute individually
                        st.write(f"🔍 Comparing `{table_id}` using SQL...")
                        comparison = self._sql_based_comparison(
                            table_id,
                            prod_branch,
                            test_branch,
                            meta["primary_keys"]["production"],
                            meta["columns"]["common"],
                            row_limit,
                        )

                    # Display status messages
                    if comparison["status"] == ComparisonStatus.MATCH:
                        st.success(f"✅ Table `{table_id}`: Perfect match ({comparison['production_row_count']:,} rows)")
                    else:
                        st.warning(f"⚠️ Table `{table_id}`: Found {comparison['differing_rows']:,} difference(s)")

                    results[table_id] = comparison

                else:
                    # Pandas-based comparison (no workspace configured)
                    comparison = self._pandas_based_comparison(
                        table_id,
                        prod_branch,
                        test_branch,
                        meta,
                        row_limit,
                        prod_table_id,
                        test_table_id,
                    )
                    results[table_id] = comparison

            except Exception as e:
                if use_sql:
                    # Log SQL comparison failure and try pandas fallback
                    st.warning(f"⚠️ SQL comparison failed for `{table_id}`, using pandas fallback: {str(e)}")

                    try:
                        comparison = self._pandas_based_comparison(
                            table_id,
                            prod_branch,
                            test_branch,
                            meta,
                            row_limit,
                            prod_table_id,
                            test_table_id,
                        )
                        results[table_id] = comparison

                    except Exception as fallback_error:
                        results[table_id] = {
                            "status": ComparisonStatus.ERROR,
                            "error": str(fallback_error),
                            "message": "Failed to compare row data",
                        }
                else:
                    results[table_id] = {
                        "status": ComparisonStatus.ERROR,
                        "error": str(e),
                        "message": "Failed to compare row data",
                    }

        return results

    def _pandas_based_comparison(
        self,
        table_id: str,
        prod_branch: Optional[str],
        test_branch: Optional[str],
        meta: Dict[str, Any],
        row_limit: int,
        prod_table_id: Optional[str] = None,
        test_table_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Compare row data using pandas DataFrame comparison.

        Args:
            table_id: Table identifier
            prod_branch: Production branch ID
            test_branch: Test branch ID
            meta: Metadata comparison results for this table
            row_limit: Maximum rows to compare
            prod_table_id: Optional explicit production table ID
            test_table_id: Optional explicit test table ID

        Returns:
            Comparison results dictionary
        """
        preview_limit = min(row_limit, self.PREVIEW_ROW_LIMIT)
        prod_row_count = meta.get("row_count", {}).get("production", 0)
        test_row_count = meta.get("row_count", {}).get("test", 0)
        actual_count = max(prod_row_count, test_row_count)

        if preview_limit < actual_count:
            st.info(
                f"ℹ️ Comparing first {preview_limit:,} rows for `{table_id}` "
                f"(table has {actual_count:,} rows total)."
            )

        # Use explicit table IDs if provided, otherwise use table_id with branch
        actual_prod_id = prod_table_id if prod_table_id else table_id
        actual_test_id = test_table_id if test_table_id else table_id
        actual_prod_branch = None if prod_table_id else prod_branch
        actual_test_branch = None if test_table_id else test_branch

        prod_data = self.client.get_table_data_preview(actual_prod_id, actual_prod_branch, limit=preview_limit)
        test_data = self.client.get_table_data_preview(actual_test_id, actual_test_branch, limit=preview_limit)

        comparison = self._detailed_dataframe_comparison(
            prod_data, test_data, meta["primary_keys"]["production"]
        )

        if preview_limit < actual_count:
            comparison["truncation_warning"] = f"Compared {preview_limit:,} of {actual_count:,} rows"

        # Display status messages
        if comparison["status"] == ComparisonStatus.MATCH:
            st.success(f"✅ Table `{table_id}`: Perfect match ({comparison.get('production_row_count', len(prod_data)):,} rows)")
        else:
            st.warning(f"⚠️ Table `{table_id}`: Found {comparison.get('differing_rows', 'unknown')} difference(s)")

        return comparison

    def _build_sql_comparison_queries(
        self,
        table_id: str,
        prod_branch: Optional[str],
        test_branch: Optional[str],
        columns: List[str],
        row_limit: int,
        prod_table_id: Optional[str] = None,
        test_table_id: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Build SQL queries for table comparison without executing them.

        Args:
            table_id: Table ID to compare (used when prod/test_table_id not provided)
            prod_branch: Production branch ID
            test_branch: Test branch ID
            columns: List of common columns to compare
            row_limit: Maximum rows to compare
            prod_table_id: Optional explicit production table ID (for bucket pairs)
            test_table_id: Optional explicit test table ID (for bucket pairs)

        Returns:
            Dictionary with query names as keys and SQL strings as values
        """
        # Get qualified table names - use explicit IDs if provided, otherwise build from table_id + branch
        if prod_table_id:
            prod_table = self.client.get_qualified_table_name(prod_table_id, None)
        else:
            prod_table = self.client.get_qualified_table_name(table_id, prod_branch)

        if test_table_id:
            test_table = self.client.get_qualified_table_name(test_table_id, None)
        else:
            test_table = self.client.get_qualified_table_name(table_id, test_branch)

        # Build column list (sorted for consistency) with sanitization
        column_list = ", ".join([_sanitize_sql_identifier(col) for col in sorted(columns)])

        return {
            "prod_not_in_test": f"""
                SELECT {column_list}
                FROM {prod_table}
                EXCEPT
                SELECT {column_list}
                FROM {test_table}
                LIMIT {row_limit}
            """,
            "test_not_in_prod": f"""
                SELECT {column_list}
                FROM {test_table}
                EXCEPT
                SELECT {column_list}
                FROM {prod_table}
                LIMIT {row_limit}
            """,
            "prod_count": f"SELECT COUNT(*) as count FROM {prod_table}",
            "test_count": f"SELECT COUNT(*) as count FROM {test_table}",
        }

    def _process_sql_comparison_results(
        self,
        table_id: str,
        prod_only_df: pd.DataFrame,
        test_only_df: pd.DataFrame,
        prod_count_df: pd.DataFrame,
        test_count_df: pd.DataFrame,
        primary_keys: List[str],
        queries: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Process SQL query results into comparison result dictionary.

        Args:
            table_id: Table ID being compared
            prod_only_df: DataFrame with rows only in production
            test_only_df: DataFrame with rows only in test
            prod_count_df: DataFrame with production row count
            test_count_df: DataFrame with test row count
            primary_keys: List of primary key columns
            queries: Dictionary of SQL queries used

        Returns:
            Comparison results dictionary
        """
        # Use positional access to avoid column name case sensitivity issues
        prod_count = prod_count_df.iloc[0, 0] if not prod_count_df.empty else 0
        test_count = test_count_df.iloc[0, 0] if not test_count_df.empty else 0

        # Calculate differences
        prod_only_count = len(prod_only_df)
        test_only_count = len(test_only_df)
        total_differences = prod_only_count + test_only_count

        # Calculate identical_rows with honest reporting
        if primary_keys:
            identical_rows = min(prod_count, test_count) - max(prod_only_count, test_only_count)
            identical_rows_note = "Estimated based on row counts"
        else:
            identical_rows = None
            identical_rows_note = "Cannot calculate without primary keys"

        # Build result
        result = {
            "table_id": table_id,
            "total_rows_compared": max(prod_count, test_count),
            "production_row_count": prod_count,
            "test_row_count": test_count,
            "differing_rows": total_differences,
            "identical_rows": identical_rows,
            "identical_rows_note": identical_rows_note,
            "rows_only_in_production": prod_only_count,
            "rows_only_in_test": test_only_count,
            "sample_differences": [],
            "comparison_method": "sql",
            "sql_queries": {
                "production_not_in_test": queries["prod_not_in_test"],
                "test_not_in_production": queries["test_not_in_prod"],
                "production_count": queries["prod_count"],
                "test_count": queries["test_count"],
            },
        }

        # If tables match perfectly
        if total_differences == 0 and prod_count == test_count:
            result["status"] = ComparisonStatus.MATCH
            return result

        # Tables differ
        result["status"] = ComparisonStatus.DIFFER

        # Generate sample differences for display
        # Match rows by PK to show actual column-level changes (like pandas compare)
        if not prod_only_df.empty or not test_only_df.empty:
            if primary_keys and all(pk in prod_only_df.columns for pk in primary_keys):
                # Index both DataFrames by PK for matching
                prod_indexed = prod_only_df.set_index(primary_keys) if not prod_only_df.empty else pd.DataFrame()
                test_indexed = test_only_df.set_index(primary_keys) if not test_only_df.empty else pd.DataFrame()

                # Find PKs that exist in both (these are actual value changes)
                if not prod_indexed.empty and not test_indexed.empty:
                    common_pks = prod_indexed.index.intersection(test_indexed.index)
                    prod_only_pks = prod_indexed.index.difference(test_indexed.index)
                    test_only_pks = test_indexed.index.difference(prod_indexed.index)
                else:
                    common_pks = pd.Index([])
                    prod_only_pks = prod_indexed.index if not prod_indexed.empty else pd.Index([])
                    test_only_pks = test_indexed.index if not test_indexed.empty else pd.Index([])

                # Update counts for truly unique rows vs changed rows
                result["rows_with_value_changes"] = len(common_pks)
                result["rows_only_in_production"] = len(prod_only_pks)
                result["rows_only_in_test"] = len(test_only_pks)

                # Show column-level differences for rows that exist in both (value changes)
                sample_count = 0
                for pk in list(common_pks)[: self.SAMPLE_DISPLAY_LIMIT]:
                    prod_row = prod_indexed.loc[pk]
                    test_row = test_indexed.loc[pk]

                    # Build PK dict
                    if isinstance(pk, tuple):
                        pk_dict = {k: v for k, v in zip(primary_keys, pk)}
                    else:
                        pk_dict = {primary_keys[0]: pk}

                    # Find columns that differ
                    changed_columns = {}
                    for col in prod_row.index:
                        prod_val = prod_row[col]
                        test_val = test_row[col]
                        if str(prod_val) != str(test_val):
                            changed_columns[col] = {
                                "production": str(prod_val),
                                "test": str(test_val),
                            }

                    if changed_columns:
                        result["sample_differences"].append(
                            {
                                "primary_key": pk_dict,
                                "source": "value_changed",
                                "changed_columns": changed_columns,
                            }
                        )
                        sample_count += 1

                # Show truly unique rows (only in prod)
                remaining_slots = self.SAMPLE_DISPLAY_LIMIT - sample_count
                for pk in list(prod_only_pks)[:remaining_slots]:
                    prod_row = prod_indexed.loc[pk]
                    if isinstance(pk, tuple):
                        pk_dict = {k: v for k, v in zip(primary_keys, pk)}
                    else:
                        pk_dict = {primary_keys[0]: pk}
                    result["sample_differences"].append(
                        {
                            "primary_key": pk_dict,
                            "source": "production_only",
                            "values": {col: str(prod_row[col]) for col in prod_row.index},
                        }
                    )

                # Show truly unique rows (only in test)
                for pk in list(test_only_pks)[:remaining_slots]:
                    test_row = test_indexed.loc[pk]
                    if isinstance(pk, tuple):
                        pk_dict = {k: v for k, v in zip(primary_keys, pk)}
                    else:
                        pk_dict = {primary_keys[0]: pk}
                    result["sample_differences"].append(
                        {
                            "primary_key": pk_dict,
                            "source": "test_only",
                            "values": {col: str(test_row[col]) for col in test_row.index},
                        }
                    )

            else:
                # No PKs - can't match rows, just show samples from each side
                if not prod_only_df.empty:
                    for _, row in prod_only_df.head(self.SAMPLE_DISPLAY_LIMIT).iterrows():
                        result["sample_differences"].append(
                            {
                                "source": "production_only",
                                "values": {col: str(row[col]) for col in row.index},
                            }
                        )
                if not test_only_df.empty:
                    for _, row in test_only_df.head(self.SAMPLE_DISPLAY_LIMIT).iterrows():
                        result["sample_differences"].append(
                            {
                                "source": "test_only",
                                "values": {col: str(row[col]) for col in row.index},
                            }
                        )

        return result

    def _sql_based_comparison(
        self,
        table_id: str,
        prod_branch: Optional[str],
        test_branch: Optional[str],
        primary_keys: List[str],
        columns: List[str],
        row_limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Compare tables using SQL EXCEPT queries for maximum efficiency.

        This method compares tables entirely in the database without loading data to memory.

        Args:
            table_id: Table ID to compare
            prod_branch: Production branch ID
            test_branch: Test branch ID
            primary_keys: List of primary key columns
            columns: List of common columns to compare
            row_limit: Maximum rows to compare (reads from session state if None)

        Returns:
            Comparison results dictionary
        """
        # Validate table ID format
        if not _validate_table_id(table_id):
            raise ValueError(f"Invalid table ID format: {table_id}")

        # Read row_limit from session state if not provided, then validate
        if row_limit is None:
            row_limit = st.session_state.get("comparison_row_limit", self.DEFAULT_ROW_LIMIT)
        row_limit = max(1, min(int(row_limit), self.MAX_ROW_LIMIT))

        # Build queries
        queries = self._build_sql_comparison_queries(
            table_id, prod_branch, test_branch, columns, row_limit
        )

        # Execute queries in batch (4 queries at once)
        query_list = [
            queries["prod_not_in_test"],
            queries["test_not_in_prod"],
            queries["prod_count"],
            queries["test_count"],
        ]
        results_list = self.client.execute_queries_batch(query_list)

        # Process results using shared method
        result = self._process_sql_comparison_results(
            table_id,
            results_list[0],  # prod_only_df
            results_list[1],  # test_only_df
            results_list[2],  # prod_count_df
            results_list[3],  # test_count_df
            primary_keys,
            queries,
        )

        # Display status messages
        if result["status"] == ComparisonStatus.MATCH:
            st.success(f"✅ Table `{table_id}`: Perfect match ({result['production_row_count']:,} rows)")
        else:
            st.warning(f"⚠️ Table `{table_id}`: Found {result['differing_rows']:,} difference(s)")

        return result

    def _detailed_dataframe_comparison(
        self, df_prod: pd.DataFrame, df_test: pd.DataFrame, primary_keys: List[str]
    ) -> Dict[str, Any]:
        """
        Detailed DataFrame comparison using pandas.

        Args:
            df_prod: Production DataFrame
            df_test: Test DataFrame
            primary_keys: List of primary key columns

        Returns:
            Detailed comparison results
        """
        try:
            # Debugging info
            logger.debug("DEBUG DATA COMPARISON")
            logger.debug("Primary Keys: %s (type: %s)", primary_keys, [type(k) for k in primary_keys])
            logger.debug("Prod Columns: %s", df_prod.columns.tolist())
            logger.debug("Prod Data Sample: %s", df_prod.head(2).to_dict(orient="records"))

            # SAFETY: Ensure all columns are strings to prevent sorting errors
            df_prod.columns = df_prod.columns.astype(str)
            df_test.columns = df_test.columns.astype(str)

            # Sort columns alphabetically for consistent comparison
            try:
                sorted_prod_cols = sorted(df_prod.columns)
                sorted_test_cols = sorted(df_test.columns)
            except TypeError as e:
                logger.error("ERROR SORTING COLUMNS: %s", e)
                logger.error("Prod Cols Type: %s", [type(c) for c in df_prod.columns])
                raise e

            df_prod = df_prod.reindex(sorted_prod_cols, axis=1)
            df_test = df_test.reindex(sorted_test_cols, axis=1)

            # Set index if primary keys exist
            if primary_keys and len(primary_keys) > 0:
                # Check if all PKs exist in both DataFrames
                if all(pk in df_prod.columns for pk in primary_keys) and all(
                    pk in df_test.columns for pk in primary_keys
                ):
                    df_prod = df_prod.set_index(primary_keys).sort_index()
                    df_test = df_test.set_index(primary_keys).sort_index()

            # Align indices safely
            # We need to find common indices and unique indices
            common_idx = df_prod.index.intersection(df_test.index)
            prod_only_idx = df_prod.index.difference(df_test.index)
            test_only_idx = df_test.index.difference(df_prod.index)

            # DataFrames for common rows
            df_prod_common = df_prod.loc[common_idx]
            df_test_common = df_test.loc[common_idx]

            # Use pandas compare method ONLY on common rows
            if not df_prod_common.empty:
                differences_df = df_prod_common.compare(
                    df_test_common, keep_equal=False, result_names=("production", "test")
                )
            else:
                differences_df = pd.DataFrame()

            # Analyze differences
            # Base stats
            n_common = len(common_idx)
            n_prod_only = len(prod_only_idx)
            n_test_only = len(test_only_idx)
            n_diff_common = len(differences_df)

            total_differences = n_prod_only + n_test_only + n_diff_common

            diff_summary = {
                "total_rows_compared": max(len(df_prod), len(df_test)),
                "differing_rows": total_differences,
                "identical_rows": n_common - n_diff_common,
                "rows_only_in_production": n_prod_only,
                "rows_only_in_test": n_test_only,
                "column_differences": {},
                "sample_differences": [],
            }

            # Add unique rows to sample differences
            if n_prod_only > 0:
                sample_prod = df_prod.loc[prod_only_idx].head(self.SAMPLE_DISPLAY_LIMIT)
                for idx, row in sample_prod.iterrows():
                    # Build PK dict
                    if isinstance(idx, tuple):
                        pk_dict = {pk: idx[i] for i, pk in enumerate(primary_keys)}
                    elif primary_keys:
                        pk_dict = {primary_keys[0]: idx}
                    else:
                        pk_dict = {"row": idx}

                    diff_summary["sample_differences"].append(
                        {
                            "primary_key": pk_dict,
                            "source": "production_only",
                            "values": {str(k): str(v) for k, v in row.items()},
                        }
                    )

            if n_test_only > 0:
                sample_test = df_test.loc[test_only_idx].head(self.SAMPLE_DISPLAY_LIMIT)
                for idx, row in sample_test.iterrows():
                    # Build PK dict
                    if isinstance(idx, tuple):
                        pk_dict = {pk: idx[i] for i, pk in enumerate(primary_keys)}
                    elif primary_keys:
                        pk_dict = {primary_keys[0]: idx}
                    else:
                        pk_dict = {"row": idx}

                    diff_summary["sample_differences"].append(
                        {
                            "primary_key": pk_dict,
                            "source": "test_only",
                            "values": {str(k): str(v) for k, v in row.items()},
                        }
                    )

            if not differences_df.empty:
                # Count differences per column
                for col in differences_df.columns.get_level_values(0).unique():
                    count = differences_df[col].notna().any(axis=1).sum()
                    diff_summary["column_differences"][col] = count

                # Get sample differences (first 10)
                sample_rows = differences_df.head(self.SAMPLE_DIFF_LIMIT)
                for idx in sample_rows.index:
                    for col in differences_df.columns.get_level_values(0).unique():
                        try:
                            prod_val = sample_rows.loc[idx, (col, "production")]
                            test_val = sample_rows.loc[idx, (col, "test")]

                            if pd.notna(prod_val) or pd.notna(test_val):
                                # Build primary key dict
                                if isinstance(idx, tuple):
                                    pk_dict = {pk: idx[i] for i, pk in enumerate(primary_keys)}
                                else:
                                    pk_dict = {primary_keys[0]: idx} if primary_keys else {"row": idx}

                                diff_summary["sample_differences"].append(
                                    {
                                        "primary_key": pk_dict,
                                        "column": col,
                                        "production_value": str(prod_val) if pd.notna(prod_val) else None,
                                        "test_value": str(test_val) if pd.notna(test_val) else None,
                                    }
                                )
                        except (KeyError, IndexError, TypeError):
                            continue

            diff_summary["status"] = ComparisonStatus.MATCH if total_differences == 0 else ComparisonStatus.DIFFER
            return diff_summary

        except Exception as e:
            logger.exception("PANDAS FALLBACK ERROR: %s", e)
            return {"status": ComparisonStatus.ERROR, "error": str(e), "message": "Failed to compare DataFrames"}

    def _compare_job_logs(self) -> Optional[Dict[str, Any]]:
        """
        Compare job logs/events between production and test runs.

        Returns:
            Log comparison results dictionary or None if not applicable
        """
        st.markdown("### 📝 Job Logs Comparison")

        # Get job IDs from session state
        prod_job_id = st.session_state.get("production_job_id")
        test_job_id = st.session_state.get("test_job_id")

        if not prod_job_id or not test_job_id:
            st.info("ℹ️ Job IDs not available - skipping log comparison")
            return None

        try:
            # Fetch job events/logs
            st.info(f"Fetching logs for production job: {prod_job_id}")
            prod_events = self.client.get_job_events(prod_job_id)

            st.info(f"Fetching logs for test job: {test_job_id}")
            test_events = self.client.get_job_events(test_job_id)

            # Show debug info about event types
            prod_event_types = {}
            for event in prod_events:
                event_type = event.get("event", "unknown")
                prod_event_types[event_type] = prod_event_types.get(event_type, 0) + 1

            st.info(f"Production event types: {prod_event_types}")

            test_event_types = {}
            for event in test_events:
                event_type = event.get("event", "unknown")
                test_event_types[event_type] = test_event_types.get(event_type, 0) + 1

            st.info(f"Test event types: {test_event_types}")

            # Show sample events in advanced mode
            if st.session_state.get("show_advanced", False):
                with st.expander("🔧 Sample Production Event (first non-storage event)"):
                    for event in prod_events[:20]:  # Check first 20
                        if not event.get("event", "").startswith("storage."):
                            st.json(event)
                            break

                with st.expander("🔧 Sample Test Event (first non-storage event)"):
                    for event in test_events[:20]:
                        if not event.get("event", "").startswith("storage."):
                            st.json(event)
                            break

            # Filter to only component output logs (typically "info" events with component output)
            # Skip system events like "storage.*", "job.*", etc.
            def is_component_log(event):
                event_type = event.get("event", "")
                # Include only standard log events, exclude storage/system events
                return not event_type.startswith(("storage.", "job."))

            prod_log_events = [e for e in prod_events if is_component_log(e)]
            test_log_events = [e for e in test_events if is_component_log(e)]

            # Extract log messages from filtered events
            prod_messages = [event.get("message", "") for event in prod_log_events if event.get("message")]
            test_messages = [event.get("message", "") for event in test_log_events if event.get("message")]

            st.success(
                f"✅ Fetched {len(prod_messages)} production log messages and {len(test_messages)} test log messages (filtered from {len(prod_events)} and {len(test_events)} total events)"
            )

            # Compare log messages
            prod_set = set(prod_messages)
            test_set = set(test_messages)

            common_messages = sorted(prod_set & test_set)
            prod_only_messages = sorted(prod_set - test_set)
            test_only_messages = sorted(test_set - prod_set)

            # Build detailed comparison
            result = {
                "production_job_id": prod_job_id,
                "test_job_id": test_job_id,
                "production_message_count": len(prod_messages),
                "test_message_count": len(test_messages),
                "production_unique_message_count": len(prod_set),
                "test_unique_message_count": len(test_set),
                "common_messages": common_messages,
                "production_only_messages": prod_only_messages,
                "test_only_messages": test_only_messages,
                "production_events": prod_events,  # Full event data
                "test_events": test_events,  # Full event data
                "status": ComparisonStatus.MATCH if prod_set == test_set else ComparisonStatus.DIFFER,
            }

            if result["status"] == ComparisonStatus.MATCH:
                st.success("✅ Job logs match perfectly")
            else:
                st.warning(
                    f"⚠️ Job logs differ: {len(prod_only_messages)} production-only, {len(test_only_messages)} test-only"
                )

            return result

        except Exception as e:
            st.error(f"❌ Failed to compare job logs: {str(e)}")
            st.exception(e)
            return {"status": ComparisonStatus.ERROR, "error": str(e)}

    def _generate_summary(self, comparison_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate executive summary from detailed comparisons.

        Args:
            comparison_results: Full comparison results

        Returns:
            Summary dictionary
        """
        bucket_comp = comparison_results["bucket_comparison"]
        table_comp = comparison_results["table_comparison"]
        meta_comp = comparison_results["metadata_comparison"]
        row_comp = comparison_results["row_differences"]

        # Count totals
        total_buckets = len(bucket_comp["common"]) + len(bucket_comp["production_only"]) + len(bucket_comp["test_only"])
        matching_buckets = len(bucket_comp["common"]) if bucket_comp["status"] == ComparisonStatus.MATCH else 0

        # Count tables
        total_tables = sum(
            len(comp["common"]) + len(comp["production_only"]) + len(comp["test_only"]) for comp in table_comp.values()
        )
        matching_tables = sum(len(comp["common"]) if comp["status"] == ComparisonStatus.MATCH else 0 for comp in table_comp.values())

        # Count differences
        tables_with_metadata_diffs = sum(1 for meta in meta_comp.values() if meta.get("status") == ComparisonStatus.DIFFER)

        tables_with_row_diffs = sum(1 for row in row_comp.values() if row.get("status") == ComparisonStatus.DIFFER)

        # Generate key findings
        key_findings = []

        if bucket_comp["production_only"]:
            key_findings.append(
                f"{len(bucket_comp['production_only'])} bucket(s) only in production: {', '.join(bucket_comp['production_only'][:3])}"
            )

        if bucket_comp["test_only"]:
            key_findings.append(
                f"{len(bucket_comp['test_only'])} bucket(s) only in test: {', '.join(bucket_comp['test_only'][:3])}"
            )

        if tables_with_metadata_diffs > 0:
            key_findings.append(f"{tables_with_metadata_diffs} table(s) have metadata differences")

        if tables_with_row_diffs > 0:
            key_findings.append(f"{tables_with_row_diffs} table(s) have row-level differences")

        # Determine overall status
        overall_status = (
            ComparisonStatus.MATCH
            # Buckets: Match OR Skipped (don't fail if skipped)
            if (
                (bucket_comp["status"] == ComparisonStatus.MATCH or bucket_comp["status"] == ComparisonStatus.SKIPPED)
                and all(t["status"] == ComparisonStatus.MATCH for t in table_comp.values())
                and tables_with_metadata_diffs == 0
                and tables_with_row_diffs == 0
            )
            else ComparisonStatus.DIFFER
        )

        return {
            "overall_status": overall_status,
            "total_buckets": total_buckets,
            "matching_buckets": matching_buckets,
            "total_tables": total_tables,
            "matching_tables": matching_tables,
            "tables_with_metadata_differences": tables_with_metadata_diffs,
            "tables_with_row_differences": tables_with_row_diffs,
            "key_findings": key_findings if key_findings else ["All outputs match perfectly!"],
        }

    def compare_specific_tables(
        self, production_branch: Optional[str], test_branch_id: Optional[str], table_ids: List[str]
    ) -> Dict[str, Any]:
        """
        Compare specific tables between two branches.

        Args:
            production_branch: Production branch ID (None for default branch)
            test_branch_id: Test branch ID
            table_ids: List of table IDs to compare

        Returns:
            Comparison results dictionary
        """
        st.markdown("## 🔍 Starting Table-Specific Comparison")
        st.info(f"""
        **Comparing:**
        - 🔵 Production Branch ID: `{production_branch}`
        - 🟢 Test Branch ID: `{test_branch_id}`
        - 📊 Tables: {len(table_ids)}
        """)

        results = {}

        # Create mock bucket comparison (tables mode doesn't compare buckets)
        results["bucket_comparison"] = {
            "production_only": [],
            "test_only": [],
            "common": [],
            "status": ComparisonStatus.SKIPPED,
            "_mode": "tables",
        }

        # Create mock table comparison structure using provided table IDs
        results["table_comparison"] = {}
        for table_id in table_ids:
            # Extract bucket from table ID (format: bucket.table)
            parts = table_id.rsplit(".", 1)
            if len(parts) == 2:
                bucket_id = parts[0]
                if bucket_id not in results["table_comparison"]:
                    results["table_comparison"][bucket_id] = {
                        "production_only": [],
                        "test_only": [],
                        "common": [],
                        "status": ComparisonStatus.MATCH,
                    }
                results["table_comparison"][bucket_id]["common"].append(parts[1])

        # Level 3: Metadata comparison for specified tables
        st.markdown("---")
        st.markdown("## Step 1: Metadata Comparison")
        results["metadata_comparison"] = {}
        for table_id in table_ids:
            try:
                prod_meta = self.client.get_table_detail(table_id, production_branch)
                test_meta = self.client.get_table_detail(table_id, test_branch_id)

                pk_comparison = self._compare_primary_keys(prod_meta, test_meta)
                col_comparison = self._compare_columns(prod_meta, test_meta)
                type_comparison = self._compare_data_types(prod_meta, test_meta)
                count_comparison = self._compare_row_counts(prod_meta, test_meta)

                all_match = (
                    pk_comparison["match"]
                    and col_comparison["match"]
                    and type_comparison["match"]
                    and count_comparison["match"]
                )

                results["metadata_comparison"][table_id] = {
                    "primary_keys": pk_comparison,
                    "columns": col_comparison,
                    "data_types": type_comparison,
                    "row_count": count_comparison,
                    "status": ComparisonStatus.MATCH if all_match else ComparisonStatus.DIFFER,
                }

                if all_match:
                    st.success(f"✅ Table `{table_id}`: All metadata matches")
                else:
                    st.warning(f"⚠️ Table `{table_id}`: Metadata differences found")

            except Exception as e:
                st.error(f"❌ Error comparing metadata for table `{table_id}`: {str(e)}")
                results["metadata_comparison"][table_id] = {"status": ComparisonStatus.ERROR, "error": str(e)}

        # Level 4: Row-level comparison
        st.markdown("---")
        st.markdown("## Step 2: Row-Level Data Comparison")
        results["row_differences"] = self._compare_row_data(
            production_branch, test_branch_id, results["metadata_comparison"]
        )

        # Generate summary
        st.markdown("---")
        st.markdown("## 📊 Generating Summary")
        results["summary"] = self._generate_summary(results)

        st.markdown("---")
        st.success("✅ Comparison complete!")

        return results

    def compare_specific_buckets(
        self, production_branch: Optional[str], test_branch_id: Optional[str], bucket_ids: List[str]
    ) -> Dict[str, Any]:
        """
        Compare all tables in specific buckets between two branches.

        Args:
            production_branch: Production branch ID (None for default branch)
            test_branch_id: Test branch ID
            bucket_ids: List of bucket IDs to compare (may contain embedded branch IDs)

        Returns:
            Comparison results dictionary
        """
        # Normalize bucket IDs to strip any embedded branch IDs
        # Users may enter bucket IDs copied from Keboola UI which include branch IDs
        # e.g., "in.c-27406-mybucket" -> "in.c-mybucket"
        normalized_bucket_ids = [_normalize_bucket_id(bid) for bid in bucket_ids]

        st.markdown("## 🔍 Starting Bucket-Specific Comparison")
        st.info(f"""
        **Comparing:**
        - 🔵 Production Branch ID: `{production_branch}`
        - 🟢 Test Branch ID: `{test_branch_id}`
        - 🗂️ Buckets: {len(normalized_bucket_ids)}
        """)

        # Show normalization info if any bucket IDs were modified
        if normalized_bucket_ids != bucket_ids:
            with st.expander("ℹ️ Bucket ID Normalization", expanded=False):
                st.write("Bucket IDs were normalized to remove embedded branch IDs:")
                for orig, norm in zip(bucket_ids, normalized_bucket_ids):
                    if orig != norm:
                        st.text(f"  {orig} → {norm}")

        results = {}

        # Level 1: Mock bucket comparison (we already know which buckets to compare)
        st.markdown("---")
        st.markdown("## Step 1: Bucket Validation")
        results["bucket_comparison"] = {
            "production_only": [],
            "test_only": [],
            "common": normalized_bucket_ids,  # We're explicitly comparing these buckets
            "status": ComparisonStatus.MATCH,
            "_mode": "buckets",
        }
        st.success(f"✅ Comparing {len(normalized_bucket_ids)} specified bucket(s)")

        # Level 2: Table comparison within specified buckets
        st.markdown("---")
        st.markdown("## Step 2: Table Comparison")
        results["table_comparison"] = {}
        for bucket_id in normalized_bucket_ids:
            st.markdown(f"#### Bucket: `{bucket_id}`")

            try:
                prod_tables = set(self.client.list_tables_in_bucket(bucket_id, production_branch))
                test_tables = set(self.client.list_tables_in_bucket(bucket_id, test_branch_id))

                common = sorted(prod_tables & test_tables)
                prod_only = sorted(prod_tables - test_tables)
                test_only = sorted(test_tables - prod_tables)

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Common Tables", len(common))
                with col2:
                    st.metric("Production Only", len(prod_only))
                with col3:
                    st.metric("Test Only", len(test_only))

                results["table_comparison"][bucket_id] = {
                    "production_only": prod_only,
                    "test_only": test_only,
                    "common": common,
                    "status": ComparisonStatus.MATCH if prod_tables == test_tables else ComparisonStatus.DIFFER,
                }
            except Exception as e:
                st.error(f"❌ Error comparing tables in bucket `{bucket_id}`: {str(e)}")
                results["table_comparison"][bucket_id] = {
                    "production_only": [],
                    "test_only": [],
                    "common": [],
                    "status": ComparisonStatus.ERROR,
                    "error": str(e),
                }

        # Level 3: Metadata comparison
        st.markdown("---")
        st.markdown("## Step 3: Metadata Comparison")
        results["metadata_comparison"] = self._compare_metadata(
            production_branch, test_branch_id, results["table_comparison"]
        )

        # Level 4: Row-level comparison
        st.markdown("---")
        st.markdown("## Step 4: Row-Level Data Comparison")
        results["row_differences"] = self._compare_row_data(
            production_branch, test_branch_id, results["metadata_comparison"]
        )

        # Generate summary
        st.markdown("---")
        st.markdown("## 📊 Generating Summary")
        results["summary"] = self._generate_summary(results)

        st.markdown("---")
        st.success("✅ Comparison complete!")

        return results

    def compare_bucket_pairs(self, bucket_pairs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Compare buckets using pre-parsed URL information.

        Each bucket pair contains bucket_a and bucket_b with:
        - branch_id: Branch ID (None for production)
        - bucket_id: Full bucket ID as it appears in the API
        - canonical_bucket_id: Display name without branch prefix

        Args:
            bucket_pairs: List of bucket pair dictionaries from parse_bucket_url

        Returns:
            Comparison results dictionary
        """
        st.markdown("## 🔍 Starting Bucket Comparison")

        # Display what we're comparing
        for idx, pair in enumerate(bucket_pairs):
            bucket_a = pair["bucket_a"]
            bucket_b = pair["bucket_b"]
            branch_a = f"Branch {bucket_a['branch_id']}" if bucket_a["branch_id"] else "Production"
            branch_b = f"Branch {bucket_b['branch_id']}" if bucket_b["branch_id"] else "Production"

            st.info(f"""
            **Pair {idx + 1}:**
            - 🔵 {branch_a}: `{bucket_a['canonical_bucket_id']}`
            - 🟢 {branch_b}: `{bucket_b['canonical_bucket_id']}`
            """)

        results = {
            "bucket_comparison": {
                "production_only": [],
                "test_only": [],
                "common": [p["bucket_a"]["canonical_bucket_id"] for p in bucket_pairs],
                "status": ComparisonStatus.MATCH,
                "_mode": "bucket_pairs",
            },
            "table_comparison": {},
            "metadata_comparison": {},
            "row_differences": {},
        }

        # Process each bucket pair
        st.markdown("---")
        st.markdown("## Step 1: Table Comparison")

        all_table_pairs = []  # Collect table pairs for metadata/row comparison

        for pair_idx, pair in enumerate(bucket_pairs):
            bucket_a = pair["bucket_a"]
            bucket_b = pair["bucket_b"]

            pair_key = bucket_a["canonical_bucket_id"]
            st.markdown(f"### Pair {pair_idx + 1}: `{pair_key}`")

            try:
                # List tables using the full bucket IDs directly (no transformation needed)
                # The bucket_id from URL is exactly what the API expects
                tables_a = set(self._list_tables_direct(bucket_a["bucket_id"]))
                tables_b = set(self._list_tables_direct(bucket_b["bucket_id"]))

                common = sorted(tables_a & tables_b)
                a_only = sorted(tables_a - tables_b)
                b_only = sorted(tables_b - tables_a)

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Common Tables", len(common))
                with col2:
                    st.metric("Bucket A Only", len(a_only))
                with col3:
                    st.metric("Bucket B Only", len(b_only))

                results["table_comparison"][pair_key] = {
                    "production_only": a_only,
                    "test_only": b_only,
                    "common": common,
                    "status": ComparisonStatus.MATCH if tables_a == tables_b else ComparisonStatus.DIFFER,
                }

                # Collect table pairs for subsequent comparison
                for table_name in common:
                    all_table_pairs.append({
                        "table_name": table_name,
                        "table_a_id": f"{bucket_a['bucket_id']}.{table_name}",
                        "table_b_id": f"{bucket_b['bucket_id']}.{table_name}",
                        "branch_a": bucket_a["branch_id"],
                        "branch_b": bucket_b["branch_id"],
                        "display_key": f"{pair_key}.{table_name}",
                    })

            except Exception as e:
                st.error(f"❌ Error comparing tables in pair {pair_idx + 1}: {str(e)}")
                results["table_comparison"][pair_key] = {
                    "production_only": [],
                    "test_only": [],
                    "common": [],
                    "status": ComparisonStatus.ERROR,
                    "error": str(e),
                }

        # Step 2: Metadata comparison for all table pairs
        st.markdown("---")
        st.markdown("## Step 2: Metadata Comparison")

        if not all_table_pairs:
            st.warning("⚠️ No common tables to compare metadata")
        else:
            st.info(f"Comparing metadata for {len(all_table_pairs)} common table(s)...")
            results["metadata_comparison"] = self._compare_table_pairs_metadata(all_table_pairs)

        # Step 3: Row-level comparison - reuse the existing method
        st.markdown("---")
        st.markdown("## Step 3: Row-Level Data Comparison")

        if not results["metadata_comparison"]:
            st.warning("⚠️ No tables to compare at row level")
        else:
            # Reuse _compare_row_data - it will use _table_pair info from metadata for explicit table IDs
            results["row_differences"] = self._compare_row_data(
                None, None, results["metadata_comparison"]
            )

        # Generate summary
        st.markdown("---")
        st.markdown("## 📊 Generating Summary")
        results["summary"] = self._generate_summary(results)

        st.markdown("---")
        st.success("✅ Comparison complete!")

        return results

    def _list_tables_direct(self, full_bucket_id: str) -> List[str]:
        """
        List tables in a bucket using the full bucket ID directly.

        Args:
            full_bucket_id: Full bucket ID as it appears in the API (e.g., in.c-27405-mybucket)

        Returns:
            List of table names
        """
        url = f"{self.client.storage_url}/v2/storage/buckets/{full_bucket_id}"
        response = requests.get(url, headers=self.client.headers)
        response.raise_for_status()
        bucket = response.json()
        return [table["name"] for table in bucket.get("tables", [])]

    def _compare_table_pairs_metadata(self, table_pairs: List[Dict]) -> Dict[str, Any]:
        """
        Compare metadata for table pairs using parallel fetching.

        Args:
            table_pairs: List of table pair info dicts

        Returns:
            Metadata comparison results keyed by display_key
        """
        results = {}

        if not table_pairs:
            return results

        st.info(f"Fetching metadata for {len(table_pairs)} table pair(s) in parallel...")

        # Phase 1: Fetch all metadata in parallel using ThreadPoolExecutor
        metadata_cache: Dict[str, Dict[str, Any]] = {}  # display_key -> {"a": meta, "b": meta}
        fetch_errors: Dict[str, str] = {}

        def fetch_metadata(table_id: str, key: str, side: str):
            """Thread-safe metadata fetch."""
            try:
                url = f"{self.client.storage_url}/v2/storage/tables/{table_id}"
                response = requests.get(url, headers=self.client.headers)
                response.raise_for_status()
                return (key, side, response.json(), None)
            except Exception as e:
                return (key, side, None, str(e))

        max_workers = min(20, len(table_pairs) * 2)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []

            for pair in table_pairs:
                display_key = pair["display_key"]
                # Fetch both sides in parallel
                futures.append(executor.submit(fetch_metadata, pair["table_a_id"], display_key, "a"))
                futures.append(executor.submit(fetch_metadata, pair["table_b_id"], display_key, "b"))

            # Collect results
            for future in as_completed(futures):
                key, side, meta, error = future.result()
                if key not in metadata_cache:
                    metadata_cache[key] = {}
                if error:
                    fetch_errors[f"{key}_{side}"] = error
                else:
                    metadata_cache[key][side] = meta

        # Phase 2: Process results
        for pair in table_pairs:
            display_key = pair["display_key"]
            cache_entry = metadata_cache.get(display_key, {})
            meta_a = cache_entry.get("a")
            meta_b = cache_entry.get("b")

            # Check for fetch errors
            error_a = fetch_errors.get(f"{display_key}_a")
            error_b = fetch_errors.get(f"{display_key}_b")

            if error_a or error_b:
                error_msg = f"Fetch errors - a: {error_a}, b: {error_b}"
                st.error(f"❌ Error fetching metadata for `{display_key}`: {error_msg}")
                results[display_key] = {
                    "status": ComparisonStatus.ERROR,
                    "error": error_msg,
                    "_table_pair": pair,
                }
                continue

            if not meta_a or not meta_b:
                st.error(f"❌ Missing metadata for `{display_key}`")
                results[display_key] = {
                    "status": ComparisonStatus.ERROR,
                    "error": "Missing metadata",
                    "_table_pair": pair,
                }
                continue

            try:
                pk_comparison = self._compare_primary_keys(meta_a, meta_b)
                col_comparison = self._compare_columns(meta_a, meta_b)
                type_comparison = self._compare_data_types(meta_a, meta_b)
                count_comparison = self._compare_row_counts(meta_a, meta_b)

                all_match = (
                    pk_comparison["match"]
                    and col_comparison["match"]
                    and type_comparison["match"]
                    and count_comparison["match"]
                )

                results[display_key] = {
                    "primary_keys": pk_comparison,
                    "columns": col_comparison,
                    "data_types": type_comparison,
                    "row_count": count_comparison,
                    "status": ComparisonStatus.MATCH if all_match else ComparisonStatus.DIFFER,
                    "_table_pair": pair,
                }

                if all_match:
                    st.success(f"✅ Table `{display_key}`: All metadata matches")
                else:
                    st.warning(f"⚠️ Table `{display_key}`: Metadata differences found")

            except Exception as e:
                st.error(f"❌ Error comparing metadata for `{display_key}`: {str(e)}")
                results[display_key] = {
                    "status": ComparisonStatus.ERROR,
                    "error": str(e),
                    "_table_pair": pair,
                }

        return results

    def compare_two_tables(self, table_id_1: str, table_id_2: str) -> Dict[str, Any]:
        """
        Compare two specific tables (A vs B).

        Args:
            table_id_1: First table ID (Production/Base)
            table_id_2: Second table ID (Test/Target)

        Returns:
            Comparison results dictionary
        """
        st.markdown("## 🔍 Starting Table Comparison (A vs B)")
        st.info(f"""
        **Comparing:**
        - 🔵 Table 1 (Production/Base): `{table_id_1}`
        - 🟢 Table 2 (Test/Target): `{table_id_2}`
        """)

        results = {}

        # 1. Bucket Comparison - Skipped
        results["bucket_comparison"] = {
            "production_only": [],
            "test_only": [],
            "common": [],
            "status": ComparisonStatus.SKIPPED,
            "_mode": "tables_direct",
        }

        # 2. Table Comparison - Mocked structure for consistency
        # We treat this as a single "common" table pair, even if IDs differ
        results["table_comparison"] = {
            "virtual_bucket": {
                "production_only": [],
                "test_only": [],
                "common": [f"{table_id_1} vs {table_id_2}"],
                "status": ComparisonStatus.MATCH,
            }
        }

        # 3. Metadata Comparison
        st.markdown("---")
        st.markdown("## Step 1: Metadata Comparison")
        results["metadata_comparison"] = {}

        # Use a virtual table ID for results
        virtual_id = f"{table_id_1}_vs_{table_id_2}"

        try:
            # Fetch from default branch (None) unless we want to support cross-branch + distinct tables later
            prod_meta = self.client.get_table_detail(table_id_1, branch_id=None)
            test_meta = self.client.get_table_detail(table_id_2, branch_id=None)

            pk_comparison = self._compare_primary_keys(prod_meta, test_meta)
            col_comparison = self._compare_columns(prod_meta, test_meta)
            type_comparison = self._compare_data_types(prod_meta, test_meta)
            count_comparison = self._compare_row_counts(prod_meta, test_meta)

            all_match = (
                pk_comparison["match"]
                and col_comparison["match"]
                and type_comparison["match"]
                and count_comparison["match"]
            )

            results["metadata_comparison"][virtual_id] = {
                "primary_keys": pk_comparison,
                "columns": col_comparison,
                "data_types": type_comparison,
                "row_count": count_comparison,
                "status": ComparisonStatus.MATCH if all_match else ComparisonStatus.DIFFER,
            }

            if all_match:
                st.success(f"✅ Metadata matches between `{table_id_1}` and `{table_id_2}`")
            else:
                st.warning(f"⚠️ Metadata differences found between `{table_id_1}` and `{table_id_2}`")

        except Exception as e:
            st.error(f"❌ Error comparing metadata: {str(e)}")
            logger.exception("METADATA ERROR for %s: %s", virtual_id, e)
            results["metadata_comparison"][virtual_id] = {"status": ComparisonStatus.ERROR, "error": str(e)}

        # 4. Data Comparison
        st.markdown("---")
        st.markdown("## Step 2: Row-Level Data Comparison")

        meta = results["metadata_comparison"][virtual_id]
        if meta.get("status") == ComparisonStatus.ERROR:
            results["row_differences"] = {virtual_id: {"status": ComparisonStatus.SKIPPED, "reason": "Metadata error"}}

        # Check standard gating (PKs/Columns/Types must match)
        elif not meta["primary_keys"]["match"] or not meta["columns"]["match"] or not meta["data_types"]["match"]:
            results["row_differences"] = {
                virtual_id: {"status": ComparisonStatus.SKIPPED, "reason": "Metadata mismatch (PKs, Columns, or Types)"}
            }
            st.info("ℹ️ Skipping row comparison: Critical metadata differs")
        else:
            # Check if workspace is available for SQL comparison
            use_sql = bool(self.client.workspace_id)
            if not use_sql:
                st.info("ℹ️ Using pandas-based comparison (no workspace configured). Row limit applies.")

            if use_sql:
                try:
                    # Get qualified names (default branch)
                    t1_qualified = self.client.get_qualified_table_name(table_id_1, None)
                    t2_qualified = self.client.get_qualified_table_name(table_id_2, None)

                    common_cols = meta["columns"]["common"]

                    column_list = ", ".join([_sanitize_sql_identifier(col) for col in sorted(common_cols)])

                    # SQL EXCEPT logic for different tables
                    query_1_not_2 = f"""
                    SELECT {column_list} FROM {t1_qualified}
                    EXCEPT
                    SELECT {column_list} FROM {t2_qualified}
                    LIMIT {self.PREVIEW_ROW_LIMIT}
                    """

                    query_2_not_1 = f"""
                    SELECT {column_list} FROM {t2_qualified}
                    EXCEPT
                    SELECT {column_list} FROM {t1_qualified}
                    LIMIT {self.PREVIEW_ROW_LIMIT}
                    """

                    df_1_not_2 = self.client.execute_query(query_1_not_2)
                    df_2_not_1 = self.client.execute_query(query_2_not_1)

                    # Get counts
                    c1_df = self.client.execute_query(f"SELECT COUNT(*) as c FROM {t1_qualified}")
                    c2_df = self.client.execute_query(f"SELECT COUNT(*) as c FROM {t2_qualified}")

                    # Use positional access to avoid column name case sensitivity issues
                    c1 = c1_df.iloc[0, 0] if not c1_df.empty else 0
                    c2 = c2_df.iloc[0, 0] if not c2_df.empty else 0

                    total_diffs = len(df_1_not_2) + len(df_2_not_1)

                    # Calculate identical_rows with honest reporting
                    pks = meta["primary_keys"]["production"]
                    if pks:
                        identical_rows = min(c1, c2) - max(len(df_1_not_2), len(df_2_not_1))
                        identical_rows_note = "Estimated based on row counts"
                    else:
                        identical_rows = None
                        identical_rows_note = "Cannot calculate without primary keys"

                    res = {
                        "total_rows_compared": max(c1, c2),
                        "production_row_count": c1,  # Table 1
                        "test_row_count": c2,  # Table 2
                        "differing_rows": total_diffs,
                        "identical_rows": identical_rows,
                        "identical_rows_note": identical_rows_note,
                        "status": ComparisonStatus.MATCH if total_diffs == 0 and c1 == c2 else ComparisonStatus.DIFFER,
                        "sample_differences": [],
                    }

                    if total_diffs > 0:
                        st.warning(f"⚠️ Found differences in data ({total_diffs} rows sampled)")
                        if not df_1_not_2.empty:
                            res["sample_differences"].append(
                                {"source": f"{table_id_1} only", "rows": f"{len(df_1_not_2)} sampled"}
                            )
                        if not df_2_not_1.empty:
                            res["sample_differences"].append(
                                {"source": f"{table_id_2} only", "rows": f"{len(df_2_not_1)} sampled"}
                            )
                    else:
                        st.success(f"✅ Data matches perfectly ({c1} rows)")

                    results["row_differences"] = {virtual_id: res}

                except Exception as e:
                    st.warning(f"⚠️ SQL comparison failed, attempting Pandas fallback: {str(e)}")
                    use_sql = False  # Fall through to pandas comparison

            if not use_sql:
                try:
                    # Use pandas data-preview comparison (no workspace required)
                    preview_limit = self.PREVIEW_ROW_LIMIT

                    # Check for truncation and warn user
                    prod_row_count = meta.get("row_count", {}).get("production", 0)
                    test_row_count = meta.get("row_count", {}).get("test", 0)
                    actual_count = max(prod_row_count, test_row_count)
                    if preview_limit < actual_count:
                        st.info(
                            f"ℹ️ Comparing first {preview_limit:,} rows "
                            f"(tables have up to {actual_count:,} rows total)."
                        )

                    prod_data = self.client.get_table_data_preview(table_id_1, branch_id=None, limit=preview_limit)
                    test_data = self.client.get_table_data_preview(table_id_2, branch_id=None, limit=preview_limit)

                    pks = meta["primary_keys"]["production"]

                    comparison = self._detailed_dataframe_comparison(prod_data, test_data, pks)

                    # Add truncation warning to result if applicable
                    if preview_limit < actual_count:
                        comparison["truncation_warning"] = f"Compared {preview_limit:,} of {actual_count:,} rows"

                    results["row_differences"] = {virtual_id: comparison}

                    if comparison.get("status") == ComparisonStatus.MATCH:
                        st.success(f"✅ Data matches perfectly (Pandas comparison, {len(prod_data)} rows)")
                    else:
                        diff_rows = comparison.get("differing_rows", "unknown")
                        st.warning(f"⚠️ Found differences in data ({diff_rows} rows)")

                except Exception as fallback_e:
                    st.error(f"❌ Data comparison failed: {str(fallback_e)}")
                    results["row_differences"] = {virtual_id: {"status": ComparisonStatus.ERROR, "error": str(fallback_e)}}

        # Generate summary
        st.markdown("---")
        st.markdown("## 📊 Generating Summary")
        results["summary"] = self._generate_summary(results)

        st.markdown("---")
        st.success("✅ Comparison complete!")

        return results
