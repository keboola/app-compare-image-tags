"""
Multi-level comparison engine for Keboola component outputs.

This module implements comprehensive comparison logic across multiple levels:
- Bucket comparison (which buckets exist)
- Table comparison (which tables exist in each bucket)
- Metadata comparison (PKs, columns, data types, row counts)
- Row-level comparison (actual data differences)
"""

from typing import Dict, List, Optional, Any
import pandas as pd
import streamlit as st

from .keboola_client import KeboolaAPIClient


class ComparisonEngine:
    """Executes bucket, table, metadata, and row-level comparisons."""

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
            "status": "match" if prod_buckets == test_buckets else "differ",
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
                "status": "match" if prod_tables == test_tables else "differ",
            }

        return results

    def _compare_metadata(
        self, prod_branch: Optional[str], test_branch: Optional[str], table_comparison: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compare table metadata (PKs, columns, types, row counts).

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
        total_common_tables = sum(len(comp["common"]) for comp in table_comparison.values())
        st.info(f"Comparing metadata for {total_common_tables} common table(s)...")

        for bucket, comparison in table_comparison.items():
            for table in comparison["common"]:
                table_id = f"{bucket}.{table}"

                try:
                    prod_meta = self.client.get_table_detail(table_id, prod_branch)
                    test_meta = self.client.get_table_detail(table_id, test_branch)

                    # Debug: Check what we got back
                    if not isinstance(prod_meta, dict):
                        st.error(f"❌ Production metadata for {table_id} is not a dict: {type(prod_meta)}")
                        st.write("Production metadata:", prod_meta)
                        raise ValueError(f"Expected dict, got {type(prod_meta)}: {prod_meta}")

                    if not isinstance(test_meta, dict):
                        st.error(f"❌ Test metadata for {table_id} is not a dict: {type(test_meta)}")
                        st.write("Test metadata:", test_meta)
                        raise ValueError(f"Expected dict, got {type(test_meta)}: {test_meta}")

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
                        "status": "match" if all_match else "differ",
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
                    results[table_id] = {"status": "error", "error": str(e)}

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
        row_limit: int = 10000,
    ) -> Dict[str, Any]:
        """
        Compare actual row data for tables with matching metadata.

        Uses SQL-based comparison for efficiency when possible, falls back to pandas.

        Args:
            prod_branch: Production branch ID
            test_branch: Test branch ID
            metadata_comparison: Metadata comparison results
            row_limit: Maximum rows to compare per table

        Returns:
            Row-level difference results per table
        """
        results = {}

        for table_id, meta in metadata_comparison.items():
            # Skip if metadata doesn't match or error occurred
            if meta.get("status") == "error":
                results[table_id] = {"status": "skipped", "reason": f"Metadata error: {meta.get('error')}"}
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

                # Note: Row count mismatch is NOT a reason to skip row comparison

                results[table_id] = {"status": "skipped", "reason": f"Metadata mismatch: {', '.join(mismatch_reasons)}"}
                st.info(f"ℹ️ Skipping row comparison for `{table_id}`: metadata differs ({', '.join(mismatch_reasons)})")
                continue

            try:
                # Try SQL-based comparison first (much faster!)
                st.write(f"🔍 Comparing `{table_id}` using SQL...")
                comparison = self._sql_based_comparison(
                    table_id,
                    prod_branch,
                    test_branch,
                    meta["primary_keys"]["production"],
                    meta["columns"]["common"],
                    row_limit,
                )

                results[table_id] = comparison

            except Exception as e:
                # Log SQL comparison failure
                st.warning(f"⚠️ SQL comparison failed for `{table_id}`, using pandas fallback: {str(e)}")

                # Fallback to pandas comparison
                try:
                    prod_data = self.client.query_table_data(table_id, prod_branch, limit=row_limit)
                    test_data = self.client.query_table_data(table_id, test_branch, limit=row_limit)

                    comparison = self._detailed_dataframe_comparison(
                        prod_data, test_data, meta["primary_keys"]["production"]
                    )

                    results[table_id] = comparison

                except Exception as fallback_error:
                    results[table_id] = {
                        "status": "error",
                        "error": str(fallback_error),
                        "message": "Failed to compare row data",
                    }

        return results

    def _sql_based_comparison(
        self,
        table_id: str,
        prod_branch: Optional[str],
        test_branch: Optional[str],
        primary_keys: List[str],
        columns: List[str],
        row_limit: int = 10000,
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
            row_limit: Maximum rows to compare

        Returns:
            Comparison results dictionary
        """
        # Get qualified table names
        prod_table = self.client.get_qualified_table_name(table_id, prod_branch)
        test_table = self.client.get_qualified_table_name(table_id, test_branch)

        # Build column list (sorted for consistency)
        column_list = ", ".join([f'"{col}"' for col in sorted(columns)])

        # Strategy: Use EXCEPT to find rows that differ
        # EXCEPT returns rows in first query that are not in second query
        # This catches both:
        # 1. Rows that exist in one table but not the other (by primary key)
        # 2. Rows with same PK but different values in any column

        # Step 1: Find rows in production but not in test (including different values)
        # These are rows that either don't exist in test OR have different values
        query_prod_not_in_test = f"""
        SELECT {column_list}
        FROM {prod_table}
        EXCEPT
        SELECT {column_list}
        FROM {test_table}
        LIMIT {row_limit}
        """

        # Step 2: Find rows in test but not in production (including different values)
        # These are rows that either don't exist in production OR have different values
        query_test_not_in_prod = f"""
        SELECT {column_list}
        FROM {test_table}
        EXCEPT
        SELECT {column_list}
        FROM {prod_table}
        LIMIT {row_limit}
        """

        # Step 3: Get total row counts
        query_prod_count = f"SELECT COUNT(*) as count FROM {prod_table}"
        query_test_count = f"SELECT COUNT(*) as count FROM {test_table}"

        # Execute queries
        prod_only_df = self.client.execute_query(query_prod_not_in_test)
        test_only_df = self.client.execute_query(query_test_not_in_prod)
        prod_count_df = self.client.execute_query(query_prod_count)
        test_count_df = self.client.execute_query(query_test_count)

        prod_count = prod_count_df.iloc[0]["count"] if not prod_count_df.empty else 0
        test_count = test_count_df.iloc[0]["count"] if not test_count_df.empty else 0

        # Calculate differences
        prod_only_count = len(prod_only_df)
        test_only_count = len(test_only_df)
        total_differences = prod_only_count + test_only_count

        # Build result
        result = {
            "total_rows_compared": max(prod_count, test_count),
            "production_row_count": prod_count,
            "test_row_count": test_count,
            "differing_rows": total_differences,
            "identical_rows": min(prod_count, test_count) - (total_differences // 2 if prod_count == test_count else 0),
            "rows_only_in_production": prod_only_count,
            "rows_only_in_test": test_only_count,
            "sample_differences": [],
            "comparison_method": "sql",
            "sql_queries": {
                "production_not_in_test": query_prod_not_in_test,
                "test_not_in_production": query_test_not_in_prod,
                "production_count": query_prod_count,
                "test_count": query_test_count,
            },
        }

        # If tables match perfectly
        if total_differences == 0 and prod_count == test_count:
            result["status"] = "match"
            st.success(f"✅ Table `{table_id}`: Perfect match ({prod_count:,} rows)")
            return result

        # Tables differ
        result["status"] = "differ"

        # Generate sample differences for display
        if not prod_only_df.empty or not test_only_df.empty:
            # Get sample rows with primary keys if available
            if primary_keys and all(pk in prod_only_df.columns for pk in primary_keys):
                sample_prod = prod_only_df.head(5)
                for idx, row in sample_prod.iterrows():
                    pk_dict = {pk: row[pk] for pk in primary_keys}
                    result["sample_differences"].append(
                        {
                            "primary_key": pk_dict,
                            "source": "production_only",
                            "values": {col: str(row[col]) for col in row.index if col not in primary_keys},
                        }
                    )

            if primary_keys and all(pk in test_only_df.columns for pk in primary_keys):
                sample_test = test_only_df.head(5)
                for idx, row in sample_test.iterrows():
                    pk_dict = {pk: row[pk] for pk in primary_keys}
                    result["sample_differences"].append(
                        {
                            "primary_key": pk_dict,
                            "source": "test_only",
                            "values": {col: str(row[col]) for col in row.index if col not in primary_keys},
                        }
                    )

        st.warning(f"⚠️ Table `{table_id}`: Found {total_differences:,} difference(s)")

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
            print("\n--- DEBUG DATA COMPARISON ---")
            print(f"Primary Keys: {primary_keys} (type: {[type(k) for k in primary_keys]})")
            print(f"Prod Columns: {df_prod.columns.tolist()}")
            print(f"Prod Data Sample: {df_prod.head(2).to_dict(orient='records')}")

            # SAFETY: Ensure all columns are strings to prevent sorting errors
            df_prod.columns = df_prod.columns.astype(str)
            df_test.columns = df_test.columns.astype(str)

            # Sort columns alphabetically for consistent comparison
            try:
                sorted_prod_cols = sorted(df_prod.columns)
                sorted_test_cols = sorted(df_test.columns)
            except TypeError as e:
                print(f"ERROR SORTING COLUMNS: {e}")
                print(f"Prod Cols Type: {[type(c) for c in df_prod.columns]}")
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
                sample_prod = df_prod.loc[prod_only_idx].head(5)
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
                sample_test = df_test.loc[test_only_idx].head(5)
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
                sample_rows = differences_df.head(10)
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
                        except:
                            continue

            diff_summary["status"] = "match" if total_differences == 0 else "differ"
            return diff_summary

        except Exception as e:
            import traceback

            print("\n--- PANDAS FALLBACK ERROR ---")
            traceback.print_exc()
            return {"status": "error", "error": str(e), "message": "Failed to compare DataFrames"}

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
                "status": "match" if prod_set == test_set else "differ",
            }

            if result["status"] == "match":
                st.success("✅ Job logs match perfectly")
            else:
                st.warning(
                    f"⚠️ Job logs differ: {len(prod_only_messages)} production-only, {len(test_only_messages)} test-only"
                )

            return result

        except Exception as e:
            st.error(f"❌ Failed to compare job logs: {str(e)}")
            st.exception(e)
            return {"status": "error", "error": str(e)}

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
        matching_buckets = len(bucket_comp["common"]) if bucket_comp["status"] == "match" else 0

        # Count tables
        total_tables = sum(
            len(comp["common"]) + len(comp["production_only"]) + len(comp["test_only"]) for comp in table_comp.values()
        )
        matching_tables = sum(len(comp["common"]) if comp["status"] == "match" else 0 for comp in table_comp.values())

        # Count differences
        tables_with_metadata_diffs = sum(1 for meta in meta_comp.values() if meta.get("status") == "differ")

        tables_with_row_diffs = sum(1 for row in row_comp.values() if row.get("status") == "differ")

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
            "match"
            # Buckets: Match OR Skipped (don't fail if skipped)
            if (
                (bucket_comp["status"] == "match" or bucket_comp["status"] == "skipped")
                and all(t["status"] == "match" for t in table_comp.values())
                and tables_with_metadata_diffs == 0
                and tables_with_row_diffs == 0
            )
            else "differ"
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
            "status": "skipped",
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
                        "status": "match",
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
                    "status": "match" if all_match else "differ",
                }

                if all_match:
                    st.success(f"✅ Table `{table_id}`: All metadata matches")
                else:
                    st.warning(f"⚠️ Table `{table_id}`: Metadata differences found")

            except Exception as e:
                st.error(f"❌ Error comparing metadata for table `{table_id}`: {str(e)}")
                results["metadata_comparison"][table_id] = {"status": "error", "error": str(e)}

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
            bucket_ids: List of bucket IDs to compare

        Returns:
            Comparison results dictionary
        """
        st.markdown("## 🔍 Starting Bucket-Specific Comparison")
        st.info(f"""
        **Comparing:**
        - 🔵 Production Branch ID: `{production_branch}`
        - 🟢 Test Branch ID: `{test_branch_id}`
        - 🗂️ Buckets: {len(bucket_ids)}
        """)

        results = {}

        # Level 1: Mock bucket comparison (we already know which buckets to compare)
        st.markdown("---")
        st.markdown("## Step 1: Bucket Validation")
        results["bucket_comparison"] = {
            "production_only": [],
            "test_only": [],
            "common": bucket_ids,  # We're explicitly comparing these buckets
            "status": "match",
            "_mode": "buckets",
        }
        st.success(f"✅ Comparing {len(bucket_ids)} specified bucket(s)")

        # Level 2: Table comparison within specified buckets
        st.markdown("---")
        st.markdown("## Step 2: Table Comparison")
        results["table_comparison"] = {}
        for bucket_id in bucket_ids:
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
                    "status": "match" if prod_tables == test_tables else "differ",
                }
            except Exception as e:
                st.error(f"❌ Error comparing tables in bucket `{bucket_id}`: {str(e)}")
                results["table_comparison"][bucket_id] = {
                    "production_only": [],
                    "test_only": [],
                    "common": [],
                    "status": "error",
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
            "status": "skipped",
            "_mode": "tables_direct",
        }

        # 2. Table Comparison - Mocked structure for consistency
        # We treat this as a single "common" table pair, even if IDs differ
        results["table_comparison"] = {
            "virtual_bucket": {
                "production_only": [],
                "test_only": [],
                "common": [f"{table_id_1} vs {table_id_2}"],
                "status": "match",
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
                "status": "match" if all_match else "differ",
            }

            if all_match:
                st.success(f"✅ Metadata matches between `{table_id_1}` and `{table_id_2}`")
            else:
                st.warning(f"⚠️ Metadata differences found between `{table_id_1}` and `{table_id_2}`")

        except Exception as e:
            import traceback

            st.error(f"❌ Error comparing metadata: {str(e)}")
            # Use print to ensure visibility in pytest output
            print(f"\n--- METADATA ERROR TRACEBACK START ---\n")
            print(traceback.format_exc())
            print(f"\n--- METADATA ERROR TRACEBACK END ---\n")
            results["metadata_comparison"][virtual_id] = {"status": "error", "error": str(e)}

        # 4. Data Comparison
        st.markdown("---")
        st.markdown("## Step 2: Row-Level Data Comparison")

        meta = results["metadata_comparison"][virtual_id]
        if meta.get("status") == "error":
            results["row_differences"] = {virtual_id: {"status": "skipped", "reason": "Metadata error"}}

        # Check standard gating (PKs/Columns/Types must match)
        elif not meta["primary_keys"]["match"] or not meta["columns"]["match"] or not meta["data_types"]["match"]:
            results["row_differences"] = {
                virtual_id: {"status": "skipped", "reason": "Metadata mismatch (PKs, Columns, or Types)"}
            }
            st.info("ℹ️ Skipping row comparison: Critical metadata differs")
        else:
            try:
                # Get qualified names (default branch)
                t1_qualified = self.client.get_qualified_table_name(table_id_1, None)
                t2_qualified = self.client.get_qualified_table_name(table_id_2, None)

                common_cols = meta["columns"]["common"]

                column_list = ", ".join([f'"{col}"' for col in sorted(common_cols)])

                # SQL EXCEPT logic for different tables
                query_1_not_2 = f"""
                SELECT {column_list} FROM {t1_qualified} 
                EXCEPT 
                SELECT {column_list} FROM {t2_qualified} 
                LIMIT 1000
                """

                query_2_not_1 = f"""
                SELECT {column_list} FROM {t2_qualified} 
                EXCEPT 
                SELECT {column_list} FROM {t1_qualified} 
                LIMIT 1000
                """

                df_1_not_2 = self.client.execute_query(query_1_not_2)
                df_2_not_1 = self.client.execute_query(query_2_not_1)

                # Get counts
                c1_df = self.client.execute_query(f"SELECT COUNT(*) as c FROM {t1_qualified}")
                c2_df = self.client.execute_query(f"SELECT COUNT(*) as c FROM {t2_qualified}")

                c1 = c1_df.iloc[0]["c"] if not c1_df.empty else 0
                c2 = c2_df.iloc[0]["c"] if not c2_df.empty else 0

                total_diffs = len(df_1_not_2) + len(df_2_not_1)

                res = {
                    "total_rows_compared": max(c1, c2),
                    "production_row_count": c1,  # Table 1
                    "test_row_count": c2,  # Table 2
                    "differing_rows": total_diffs,
                    "identical_rows": min(c1, c2) - (total_diffs // 2 if c1 == c2 else 0),
                    "status": "match" if total_diffs == 0 and c1 == c2 else "differ",
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
                st.warning(
                    f"⚠️ SQL comparison failed (likely due to missing Workspace config), attempting Pandas fallback: {str(e)}"
                )

                try:
                    # Fallback to pandas using data-preview (no workspace required)
                    # Note: limit is usually small (100) for preview, but let's try 1000 if API allows
                    prod_data = self.client.get_table_data_preview(table_id_1, branch_id=None, limit=1000)
                    test_data = self.client.get_table_data_preview(table_id_2, branch_id=None, limit=1000)

                    pks = meta["primary_keys"]["production"]

                    comparison = self._detailed_dataframe_comparison(prod_data, test_data, pks)
                    results["row_differences"] = {virtual_id: comparison}

                    if comparison.get("status") == "match":
                        st.success(f"✅ Data matches perfectly (Pandas comparison, {len(prod_data)} rows)")
                    else:
                        diff_rows = comparison.get("differing_rows", "unknown")
                        st.warning(f"⚠️ Found differences in data ({diff_rows} rows)")

                except Exception as fallback_e:
                    st.error(f"❌ Data comparison failed (both SQL and Pandas): {str(fallback_e)}")
                    results["row_differences"] = {virtual_id: {"status": "error", "error": str(fallback_e)}}

        # Generate summary
        st.markdown("---")
        st.markdown("## 📊 Generating Summary")
        results["summary"] = self._generate_summary(results)

        st.markdown("---")
        st.success("✅ Comparison complete!")

        return results
