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
        self,
        production_branch: Optional[str] = None,
        test_branch_id: Optional[str] = None
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
        results['bucket_comparison'] = self._compare_buckets(
            production_branch, test_branch_id
        )

        # Level 2: Table comparison
        st.markdown("---")
        st.markdown("## Step 2: Table Comparison")
        results['table_comparison'] = self._compare_tables(
            production_branch, test_branch_id, results['bucket_comparison']
        )

        # Level 3: Metadata comparison
        st.markdown("---")
        st.markdown("## Step 3: Metadata Comparison")
        results['metadata_comparison'] = self._compare_metadata(
            production_branch, test_branch_id, results['table_comparison']
        )

        # Level 4: Row-level comparison
        st.markdown("---")
        st.markdown("## Step 4: Row-Level Data Comparison")
        results['row_differences'] = self._compare_row_data(
            production_branch, test_branch_id, results['metadata_comparison']
        )

        # Generate summary
        st.markdown("---")
        st.markdown("## 📊 Generating Summary")
        results['summary'] = self._generate_summary(results)

        st.markdown("---")
        st.success("✅ Comparison complete!")

        return results

    def _compare_buckets(
        self,
        prod_branch: Optional[str],
        test_branch: Optional[str]
    ) -> Dict[str, Any]:
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
            'production_only': prod_only,
            'test_only': test_only,
            'common': common,
            'status': 'match' if prod_buckets == test_buckets else 'differ',
            '_debug': {
                'production_buckets': sorted(prod_buckets),
                'test_buckets': sorted(test_buckets),
                'production_branch_id': prod_branch,
                'test_branch_id': test_branch
            }
        }

    def _compare_tables(
        self,
        prod_branch: Optional[str],
        test_branch: Optional[str],
        bucket_comparison: Dict[str, Any]
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

        if not bucket_comparison['common']:
            st.warning("⚠️ No common buckets to compare tables")
            return {}

        results = {}

        for bucket in bucket_comparison['common']:
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
                'production_only': prod_only,
                'test_only': test_only,
                'common': common,
                'status': 'match' if prod_tables == test_tables else 'differ'
            }

        return results

    def _compare_metadata(
        self,
        prod_branch: Optional[str],
        test_branch: Optional[str],
        table_comparison: Dict[str, Any]
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
        total_common_tables = sum(len(comp['common']) for comp in table_comparison.values())
        st.info(f"Comparing metadata for {total_common_tables} common table(s)...")

        for bucket, comparison in table_comparison.items():
            for table in comparison['common']:
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
                        pk_comparison['match'] and
                        col_comparison['match'] and
                        type_comparison['match'] and
                        count_comparison['match']
                    )

                    results[table_id] = {
                        'primary_keys': pk_comparison,
                        'columns': col_comparison,
                        'data_types': type_comparison,
                        'row_count': count_comparison,
                        'status': 'match' if all_match else 'differ'
                    }

                    # Show success for this table
                    if all_match:
                        st.success(f"✅ Table `{table_id}`: All metadata matches")
                    else:
                        st.warning(f"⚠️ Table `{table_id}`: Metadata differences found")

                except Exception as e:
                    st.error(f"❌ Error comparing metadata for table `{table_id}`: {str(e)}")
                    results[table_id] = {
                        'status': 'error',
                        'error': str(e)
                    }

        return results

    def _compare_primary_keys(self, prod_meta: Dict, test_meta: Dict) -> Dict[str, Any]:
        """Compare primary keys."""
        prod_pks = prod_meta.get('primaryKey', [])
        test_pks = test_meta.get('primaryKey', [])

        return {
            'match': prod_pks == test_pks,
            'production': prod_pks,
            'test': test_pks
        }

    def _compare_columns(self, prod_meta: Dict, test_meta: Dict) -> Dict[str, Any]:
        """Compare column names."""
        prod_cols = set([col['name'] for col in prod_meta.get('columns', [])])
        test_cols = set([col['name'] for col in test_meta.get('columns', [])])

        return {
            'match': prod_cols == test_cols,
            'production_only': sorted(prod_cols - test_cols),
            'test_only': sorted(test_cols - prod_cols),
            'common': sorted(prod_cols & test_cols)
        }

    def _compare_data_types(self, prod_meta: Dict, test_meta: Dict) -> Dict[str, Any]:
        """Compare data types for common columns."""
        prod_types = {col['name']: col.get('type', 'STRING') for col in prod_meta.get('columns', [])}
        test_types = {col['name']: col.get('type', 'STRING') for col in test_meta.get('columns', [])}

        differences = {}
        for col in set(prod_types.keys()) & set(test_types.keys()):
            if prod_types[col] != test_types[col]:
                differences[col] = (prod_types[col], test_types[col])

        return {
            'match': len(differences) == 0,
            'differences': differences
        }

    def _compare_row_counts(self, prod_meta: Dict, test_meta: Dict) -> Dict[str, Any]:
        """Compare row counts."""
        prod_count = prod_meta.get('rowsCount', 0)
        test_count = test_meta.get('rowsCount', 0)

        return {
            'match': prod_count == test_count,
            'production': prod_count,
            'test': test_count
        }

    def _compare_row_data(
        self,
        prod_branch: Optional[str],
        test_branch: Optional[str],
        metadata_comparison: Dict[str, Any],
        row_limit: int = 10000
    ) -> Dict[str, Any]:
        """
        Compare actual row data for tables with matching metadata.

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
            if meta.get('status') == 'error':
                results[table_id] = {
                    'status': 'skipped',
                    'reason': f"Metadata error: {meta.get('error')}"
                }
                continue

            # Skip if columns don't match
            if not meta['columns']['match']:
                results[table_id] = {
                    'status': 'skipped',
                    'reason': 'Column mismatch'
                }
                continue

            try:
                # Load data from both branches
                prod_data = self.client.query_table_data(table_id, prod_branch, limit=row_limit)
                test_data = self.client.query_table_data(table_id, test_branch, limit=row_limit)

                # Compare DataFrames
                comparison = self._detailed_dataframe_comparison(
                    prod_data,
                    test_data,
                    meta['primary_keys']['production']
                )

                results[table_id] = comparison

            except Exception as e:
                results[table_id] = {
                    'status': 'error',
                    'error': str(e),
                    'message': 'Failed to compare row data'
                }

        return results

    def _detailed_dataframe_comparison(
        self,
        df_prod: pd.DataFrame,
        df_test: pd.DataFrame,
        primary_keys: List[str]
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
            # Sort columns alphabetically for consistent comparison
            df_prod = df_prod.reindex(sorted(df_prod.columns), axis=1)
            df_test = df_test.reindex(sorted(df_test.columns), axis=1)

            # Set index if primary keys exist
            if primary_keys and len(primary_keys) > 0:
                # Check if all PKs exist in both DataFrames
                if all(pk in df_prod.columns for pk in primary_keys) and \
                   all(pk in df_test.columns for pk in primary_keys):
                    df_prod = df_prod.set_index(primary_keys).sort_index()
                    df_test = df_test.set_index(primary_keys).sort_index()

            # Use pandas compare method
            differences_df = df_prod.compare(df_test, keep_equal=False, result_names=('production', 'test'))

            # Analyze differences
            diff_summary = {
                'total_rows_compared': len(df_prod),
                'differing_rows': len(differences_df) if not differences_df.empty else 0,
                'identical_rows': len(df_prod) - (len(differences_df) if not differences_df.empty else 0),
                'column_differences': {},
                'sample_differences': []
            }

            if not differences_df.empty:
                # Count differences per column
                for col in differences_df.columns.get_level_values(0).unique():
                    count = differences_df[col].notna().any(axis=1).sum()
                    diff_summary['column_differences'][col] = count

                # Get sample differences (first 10)
                sample_rows = differences_df.head(10)
                for idx in sample_rows.index:
                    for col in differences_df.columns.get_level_values(0).unique():
                        try:
                            prod_val = sample_rows.loc[idx, (col, 'production')]
                            test_val = sample_rows.loc[idx, (col, 'test')]

                            if pd.notna(prod_val) or pd.notna(test_val):
                                # Build primary key dict
                                if isinstance(idx, tuple):
                                    pk_dict = {pk: idx[i] for i, pk in enumerate(primary_keys)}
                                else:
                                    pk_dict = {primary_keys[0]: idx} if primary_keys else {'row': idx}

                                diff_summary['sample_differences'].append({
                                    'primary_key': pk_dict,
                                    'column': col,
                                    'production_value': str(prod_val) if pd.notna(prod_val) else None,
                                    'test_value': str(test_val) if pd.notna(test_val) else None
                                })
                        except:
                            continue

            diff_summary['status'] = 'match' if len(differences_df) == 0 else 'differ'
            return diff_summary

        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'message': 'Failed to compare DataFrames'
            }

    def _generate_summary(self, comparison_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate executive summary from detailed comparisons.

        Args:
            comparison_results: Full comparison results

        Returns:
            Summary dictionary
        """
        bucket_comp = comparison_results['bucket_comparison']
        table_comp = comparison_results['table_comparison']
        meta_comp = comparison_results['metadata_comparison']
        row_comp = comparison_results['row_differences']

        # Count totals
        total_buckets = len(bucket_comp['common']) + \
                       len(bucket_comp['production_only']) + \
                       len(bucket_comp['test_only'])
        matching_buckets = len(bucket_comp['common']) if bucket_comp['status'] == 'match' else 0

        # Count tables
        total_tables = sum(
            len(comp['common']) + len(comp['production_only']) + len(comp['test_only'])
            for comp in table_comp.values()
        )
        matching_tables = sum(
            len(comp['common']) if comp['status'] == 'match' else 0
            for comp in table_comp.values()
        )

        # Count differences
        tables_with_metadata_diffs = sum(
            1 for meta in meta_comp.values()
            if meta.get('status') == 'differ'
        )

        tables_with_row_diffs = sum(
            1 for row in row_comp.values()
            if row.get('status') == 'differ'
        )

        # Generate key findings
        key_findings = []

        if bucket_comp['production_only']:
            key_findings.append(
                f"{len(bucket_comp['production_only'])} bucket(s) only in production: {', '.join(bucket_comp['production_only'][:3])}"
            )

        if bucket_comp['test_only']:
            key_findings.append(
                f"{len(bucket_comp['test_only'])} bucket(s) only in test: {', '.join(bucket_comp['test_only'][:3])}"
            )

        if tables_with_metadata_diffs > 0:
            key_findings.append(f"{tables_with_metadata_diffs} table(s) have metadata differences")

        if tables_with_row_diffs > 0:
            key_findings.append(f"{tables_with_row_diffs} table(s) have row-level differences")

        # Determine overall status
        overall_status = 'match' if (
            bucket_comp['status'] == 'match' and
            all(t['status'] == 'match' for t in table_comp.values()) and
            tables_with_metadata_diffs == 0 and
            tables_with_row_diffs == 0
        ) else 'differ'

        return {
            'overall_status': overall_status,
            'total_buckets': total_buckets,
            'matching_buckets': matching_buckets,
            'total_tables': total_tables,
            'matching_tables': matching_tables,
            'tables_with_metadata_differences': tables_with_metadata_diffs,
            'tables_with_row_differences': tables_with_row_diffs,
            'key_findings': key_findings if key_findings else ['All outputs match perfectly!']
        }
