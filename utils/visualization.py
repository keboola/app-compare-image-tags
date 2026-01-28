"""
Reusable visualization components for displaying comparison results.

This module provides functions for displaying comparison data in various formats:
metrics, charts, tables, and status indicators.
"""

from typing import Any, Dict

import pandas as pd
import plotly.express as px
import streamlit as st


def display_status_indicator(status: str) -> str:
    """
    Get status indicator emoji and color.

    Args:
        status: Status string ('match', 'differ', 'error', 'skipped')

    Returns:
        Emoji string
    """
    status_map = {"match": "✅", "differ": "⚠️", "error": "❌", "skipped": "⏭️"}
    return status_map.get(status, "❓")


def display_bucket_comparison(comparison: Dict[str, Any]):
    """
    Display bucket-level comparison results.

    Args:
        comparison: Bucket comparison dictionary
    """
    st.markdown(f"**Status:** {display_status_indicator(comparison['status'])} {comparison['status'].upper()}")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Common Buckets", len(comparison["common"]))
        if comparison["common"]:
            with st.expander("View common buckets"):
                for bucket in comparison["common"]:
                    st.text(f"✅ {bucket}")

    with col2:
        st.metric("Production Only", len(comparison["production_only"]))
        if comparison["production_only"]:
            with st.expander("View production-only buckets"):
                for bucket in comparison["production_only"]:
                    st.text(f"🔵 {bucket}")

    with col3:
        st.metric("Test Only", len(comparison["test_only"]))
        if comparison["test_only"]:
            with st.expander("View test-only buckets"):
                for bucket in comparison["test_only"]:
                    st.text(f"🟢 {bucket}")


def display_table_comparison(comparison: Dict[str, Any]):
    """
    Display table-level comparison results.

    Args:
        comparison: Table comparison dictionary (per bucket)
    """
    for bucket, tables in comparison.items():
        with st.expander(f"📂 {bucket} - {display_status_indicator(tables['status'])} {tables['status'].upper()}"):
            if not tables["common"] and not tables["production_only"] and not tables["test_only"]:
                st.info("No tables in this bucket")
                continue

            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown("**Common Tables**")
                if tables["common"]:
                    for table in tables["common"]:
                        st.text(f"✅ {table}")
                else:
                    st.text("None")

            with col2:
                st.markdown("**Production Only**")
                if tables["production_only"]:
                    for table in tables["production_only"]:
                        st.text(f"🔵 {table}")
                else:
                    st.text("None")

            with col3:
                st.markdown("**Test Only**")
                if tables["test_only"]:
                    for table in tables["test_only"]:
                        st.text(f"🟢 {table}")
                else:
                    st.text("None")


def display_metadata_differences(comparison: Dict[str, Any]):
    """
    Display metadata comparison differences.

    Args:
        comparison: Metadata comparison dictionary (per table)
    """
    # Filter tables with differences
    differing_tables = {table_id: meta for table_id, meta in comparison.items() if meta.get("status") == "differ"}

    if not differing_tables:
        st.success("✅ All table metadata matches perfectly!")
        return

    st.warning(f"⚠️ {len(differing_tables)} table(s) have metadata differences")

    for table_id, meta in differing_tables.items():
        with st.expander(f"📊 {table_id}"):
            # Primary Keys
            if not meta["primary_keys"]["match"]:
                st.markdown("**🔑 Primary Keys Differ:**")
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("*Production:*")
                    prod_pks = meta["primary_keys"]["production"]
                    if prod_pks:
                        st.code(", ".join(prod_pks))
                    else:
                        st.code("(No primary keys)")
                with col2:
                    st.markdown("*Test:*")
                    test_pks = meta["primary_keys"]["test"]
                    if test_pks:
                        st.code(", ".join(test_pks))
                    else:
                        st.code("(No primary keys)")

                # Show what's different
                prod_set = set(meta["primary_keys"]["production"])
                test_set = set(meta["primary_keys"]["test"])
                only_in_prod = prod_set - test_set
                only_in_test = test_set - prod_set

                if only_in_prod or only_in_test:
                    st.markdown("**Differences:**")
                    if only_in_prod:
                        st.error(f"❌ Only in production: {', '.join(only_in_prod)}")
                    if only_in_test:
                        st.warning(f"⚠️ Only in test: {', '.join(only_in_test)}")

            # Columns
            if not meta["columns"]["match"]:
                st.markdown("**Column Differences:**")
                col1, col2 = st.columns(2)
                with col1:
                    if meta["columns"]["production_only"]:
                        st.markdown("*Production Only:*")
                        for col in meta["columns"]["production_only"]:
                            st.text(f"🔵 {col}")
                with col2:
                    if meta["columns"]["test_only"]:
                        st.markdown("*Test Only:*")
                        for col in meta["columns"]["test_only"]:
                            st.text(f"🟢 {col}")

            # Data Types
            if not meta["data_types"]["match"]:
                st.markdown("**Data Type Differences:**")
                type_diffs = meta["data_types"]["differences"]

                # Handle both old format (tuple) and new format (dict)
                type_rows = []
                for col, type_info in type_diffs.items():
                    if isinstance(type_info, dict):
                        # New format: {"production": "STRING", "test": "INTEGER"}
                        type_rows.append(
                            {
                                "Column": col,
                                "Production Type": type_info.get("production", "UNKNOWN"),
                                "Test Type": type_info.get("test", "UNKNOWN"),
                            }
                        )
                    elif isinstance(type_info, tuple) and len(type_info) == 2:
                        # Old format: ("STRING", "INTEGER")
                        type_rows.append({"Column": col, "Production Type": type_info[0], "Test Type": type_info[1]})

                if type_rows:
                    type_df = pd.DataFrame(type_rows)
                    st.dataframe(type_df, use_container_width=True)
                else:
                    st.info("No data type differences to display")

            # Row Count
            if not meta["row_count"]["match"]:
                st.markdown("**Row Count Difference:**")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Production", meta["row_count"]["production"])
                with col2:
                    st.metric("Test", meta["row_count"]["test"])
                with col3:
                    diff = meta["row_count"]["test"] - meta["row_count"]["production"]
                    st.metric("Difference", diff, delta=diff)


def display_row_differences(differences: Dict[str, Any]):
    """
    Display row-level differences for a single table.

    Handles both SQL-based and pandas-based comparison results.

    Args:
        differences: Row differences dictionary for one table
    """
    if differences.get("status") == "skipped":
        st.info(f"ℹ️ Row comparison skipped: {differences.get('reason')}")
        return

    if differences.get("status") == "error":
        st.error(f"❌ Error comparing rows: {differences.get('error')}")
        return

    show_advanced = st.session_state.get("show_advanced", False)

    # Show comparison method used
    comparison_method = differences.get("comparison_method", "pandas")
    if comparison_method == "sql":
        st.caption("🚀 Compared using efficient SQL queries")

        # Display SQL queries in an expander
        if differences.get("sql_queries") and show_advanced:
            with st.expander("🔍 View SQL Queries Used", expanded=False):
                sql_queries = differences["sql_queries"]

                st.markdown("**Query 1: Rows in Production but not in Test**")
                st.code(sql_queries.get("production_not_in_test", "N/A"), language="sql")

                st.markdown("**Query 2: Rows in Test but not in Production**")
                st.code(sql_queries.get("test_not_in_production", "N/A"), language="sql")

                st.markdown("**Query 3: Production Row Count**")
                st.code(sql_queries.get("production_count", "N/A"), language="sql")

                st.markdown("**Query 4: Test Row Count**")
                st.code(sql_queries.get("test_count", "N/A"), language="sql")
    else:
        st.caption("🐼 Compared using pandas DataFrames")

    if differences.get("status") == "match":
        st.success("✅ All rows match perfectly!")
        total_rows = differences.get("total_rows_compared", 0)
        if total_rows > 0:
            st.info(f"📊 Compared {total_rows:,} rows with perfect match")
        return

    # Display summary metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Rows Compared", f"{differences.get('total_rows_compared', 0):,}")
    with col2:
        st.metric("Identical Rows", f"{differences.get('identical_rows', 0):,}")
    with col3:
        st.metric("Differing Rows", f"{differences.get('differing_rows', 0):,}")
    with col4:
        match_rate = (differences.get("identical_rows", 0) / differences.get("total_rows_compared", 1)) * 100
        st.metric("Match Rate", f"{match_rate:.1f}%")

    # SQL-specific metrics
    if comparison_method == "sql":
        st.markdown("---")
        st.markdown("### Row Count Analysis")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Production Rows", f"{differences.get('production_row_count', 0):,}")
        with col2:
            st.metric("Test Rows", f"{differences.get('test_row_count', 0):,}")
        with col3:
            row_diff = abs(differences.get("production_row_count", 0) - differences.get("test_row_count", 0))
            st.metric("Row Count Difference", f"{row_diff:,}")

        if differences.get("rows_only_in_production", 0) > 0 or differences.get("rows_only_in_test", 0) > 0:
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Rows Only in Production", f"{differences.get('rows_only_in_production', 0):,}")
            with col2:
                st.metric("Rows Only in Test", f"{differences.get('rows_only_in_test', 0):,}")

    st.markdown("---")

    # Column differences chart (pandas comparison only)
    if differences.get("column_differences"):
        st.markdown("### Differences by Column")

        df = pd.DataFrame(
            [{"Column": col, "Differing Rows": count} for col, count in differences["column_differences"].items()]
        ).sort_values("Differing Rows", ascending=False)

        fig = px.bar(
            df,
            x="Column",
            y="Differing Rows",
            title="Number of Differing Rows per Column",
            color="Differing Rows",
            color_continuous_scale="Reds",
        )
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    # Sample differences table
    if differences.get("sample_differences"):
        st.markdown("### Sample Differences")
        st.caption(f"Showing first {len(differences['sample_differences'])} differences")

        # Convert to DataFrame for display
        sample_data = []
        for diff in differences["sample_differences"]:
            if comparison_method == "sql":
                # SQL format: {primary_key: {}, source: 'production_only'/'test_only', values: {}}
                pk_str = ", ".join([f"{k}={v}" for k, v in diff.get("primary_key", {}).items()])
                sample_data.append(
                    {
                        "Primary Key": pk_str,
                        "Source": diff.get("source", "unknown"),
                        "Values": str(diff.get("values", {})),
                    }
                )
            else:
                # Pandas format: {primary_key: {}, column: '', production_value: '', test_value: ''}
                pk_str = ", ".join([f"{k}={v}" for k, v in diff.get("primary_key", {}).items()])
                sample_data.append(
                    {
                        "Primary Key": pk_str,
                        "Column": diff.get("column", ""),
                        "Production Value": diff.get("production_value", ""),
                        "Test Value": diff.get("test_value", ""),
                    }
                )

        sample_df = pd.DataFrame(sample_data)
        st.dataframe(sample_df, use_container_width=True)

        # Export option
        csv = sample_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Differences as CSV", data=csv, file_name="row_differences.csv", mime="text/csv"
        )
    else:
        st.info("No sample differences available")


def display_summary_metrics(summary: Dict[str, Any]):
    """
    Display summary metrics in a grid layout.

    Args:
        summary: Summary dictionary
    """
    # Additional metrics
    col1, col2, col3 = st.columns(3)

    with col1:
        if summary["tables_with_metadata_differences"] > 0:
            st.metric("Tables with Metadata Differences", summary["tables_with_metadata_differences"], delta=None)

    with col2:
        if summary["tables_with_row_differences"] > 0:
            st.metric("Tables with Row Differences", summary["tables_with_row_differences"], delta=None)

    with col3:
        match_rate = (summary["matching_tables"] / summary["total_tables"] * 100) if summary["total_tables"] > 0 else 0
        st.metric("Table Match Rate", f"{match_rate:.1f}%")


def display_comparison_progress(production_status: str, test_status: str):
    """
    Display job comparison progress with visual indicators.

    Args:
        production_status: Production job status
        test_status: Test job status
    """
    status_icons = {
        "waiting": "⏳",
        "processing": "⚙️",
        "success": "✅",
        "error": "❌",
        "cancelled": "🚫",
        "terminated": "🛑",
    }

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Production Run")
        st.markdown(f"{status_icons.get(production_status, '❓')} **{production_status.upper()}**")

    with col2:
        st.markdown("### Test Run")
        st.markdown(f"{status_icons.get(test_status, '❓')} **{test_status.upper()}**")


def display_log_comparison(log_comparison: Dict[str, Any]):
    """
    Display job log comparison results in git-diff style.

    Args:
        log_comparison: Log comparison dictionary containing production and test logs
    """
    if not log_comparison or log_comparison.get("status") == "error":
        st.error(f"❌ Log comparison failed: {log_comparison.get('error', 'Unknown error')}")
        return

    # Show overview metrics
    st.markdown(f"**Status:** {display_status_indicator(log_comparison['status'])} {log_comparison['status'].upper()}")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Production Messages", log_comparison.get("production_message_count", 0))
        st.caption(f"{log_comparison.get('production_unique_message_count', 0)} unique")

    with col2:
        st.metric("Test Messages", log_comparison.get("test_message_count", 0))
        st.caption(f"{log_comparison.get('test_unique_message_count', 0)} unique")

    with col3:
        st.metric("Common Messages", len(log_comparison.get("common_messages", [])))

    st.markdown("---")

    # Display differences in git-diff style
    prod_only = log_comparison.get("production_only_messages", [])
    test_only = log_comparison.get("test_only_messages", [])

    if not prod_only and not test_only:
        st.success("✅ All log messages are identical!")
        return

    # Create tabs for different views
    tab1, tab2, tab3, tab4 = st.tabs(["Diff View", "Production Only", "Test Only", "All Logs (Side by Side)"])

    with tab1:
        st.markdown("### 📝 Log Differences (Git-Style)")

        if prod_only:
            st.markdown("#### ➖ Removed from Production (not in Test)")
            for msg in prod_only:
                # Display in red with minus prefix (git-style)
                st.markdown(
                    f'<div style="background-color: #ffebe9; padding: 5px; border-left: 3px solid #d73a49; margin-bottom: 2px;"><code style="color: #d73a49;">- {msg}</code></div>',
                    unsafe_allow_html=True,
                )

        if test_only:
            st.markdown("#### ➕ Added in Test (not in Production)")
            for msg in test_only:
                # Display in green with plus prefix (git-style)
                st.markdown(
                    f'<div style="background-color: #d4edda; padding: 5px; border-left: 3px solid #28a745; margin-bottom: 2px;"><code style="color: #28a745;">+ {msg}</code></div>',
                    unsafe_allow_html=True,
                )

    with tab2:
        st.markdown("### Production-Only Messages")
        if prod_only:
            st.info(f"Found {len(prod_only)} message(s) only in production logs")
            for i, msg in enumerate(prod_only, 1):
                st.text(f"{i:4d} | {msg}")
        else:
            st.success("No production-only messages")

    with tab3:
        st.markdown("### Test-Only Messages")
        if test_only:
            st.info(f"Found {len(test_only)} message(s) only in test logs")
            for i, msg in enumerate(test_only, 1):
                st.text(f"{i:4d} | {msg}")
        else:
            st.success("No test-only messages")

    with tab4:
        st.markdown("### All Logs (Side by Side)")

        # Get all production and test messages from the log_comparison data
        prod_all_messages = []
        test_all_messages = []

        # Reconstruct all messages from the event data
        if log_comparison.get("production_events"):
            for event in log_comparison["production_events"]:
                if event.get("message"):
                    prod_all_messages.append(event.get("message"))

        if log_comparison.get("test_events"):
            for event in log_comparison["test_events"]:
                if event.get("message"):
                    test_all_messages.append(event.get("message"))

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Production Logs** ({} messages)".format(len(prod_all_messages)))
            for i, msg in enumerate(prod_all_messages, 1):
                st.text(f"{i:4d} | {msg}")

        with col2:
            st.markdown("**Test Logs** ({} messages)".format(len(test_all_messages)))
            for i, msg in enumerate(test_all_messages, 1):
                st.text(f"{i:4d} | {msg}")

    # Show detailed event data in advanced mode
    if st.session_state.get("show_advanced", False):
        st.markdown("---")
        st.markdown("### 🔧 Full Event Data")

        col1, col2 = st.columns(2)

        with col1:
            with st.expander("Production Events (JSON)"):
                st.json(log_comparison.get("production_events", []))

        with col2:
            with st.expander("Test Events (JSON)"):
                st.json(log_comparison.get("test_events", []))
