"""
Reusable visualization components for displaying comparison results.

This module provides functions for displaying comparison data in various formats:
metrics, charts, tables, and status indicators.
"""

import html
from typing import Any, Dict, List

import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components


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
                    st.dataframe(type_df, width="stretch")
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

                st.markdown("**Query 1: Production Row Count**")
                st.code(sql_queries.get("prod_count", "N/A"), language="sql")

                st.markdown("**Query 2: Test Row Count**")
                st.code(sql_queries.get("test_count", "N/A"), language="sql")

                st.markdown("**Query 3: PKs Only in Production (removed/missing rows)**")
                st.code(sql_queries.get("prod_only_pks_count", "N/A"), language="sql")

                st.markdown("**Query 4: PKs Only in Test (added rows)**")
                st.code(sql_queries.get("test_only_pks_count", "N/A"), language="sql")

                st.markdown("**Query 5: Value Changes Count (same PK, different values)**")
                st.code(sql_queries.get("value_changes_count", "N/A"), language="sql")

                st.markdown("**Query 6: Value Changes Sample**")
                st.code(sql_queries.get("value_changes_sample", "N/A"), language="sql")
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

        # Show breakdown: value changes vs truly unique rows
        value_changes = differences.get("rows_with_value_changes", 0)
        prod_only = differences.get("rows_only_in_production", 0)
        test_only = differences.get("rows_only_in_test", 0)

        if value_changes > 0 or prod_only > 0 or test_only > 0:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(
                    "Rows with Value Changes",
                    f"{value_changes:,}",
                    help="Rows that exist in both but have different values",
                )
            with col2:
                st.metric(
                    "Rows Only in Production",
                    f"{prod_only:,}",
                    help="Rows that exist only in production (deleted or new in test)",
                )
            with col3:
                st.metric(
                    "Rows Only in Test",
                    f"{test_only:,}",
                    help="Rows that exist only in test (new rows)",
                )

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
        st.plotly_chart(fig, width="stretch")

    # Sample differences table
    if differences.get("sample_differences"):
        st.markdown("### Sample Differences")
        st.caption(f"Showing first {len(differences['sample_differences'])} differences")

        # Convert to DataFrame for display
        sample_data = []
        for diff in differences["sample_differences"]:
            pk_str = ", ".join([f"{k}={v}" for k, v in diff.get("primary_key", {}).items()])
            source = diff.get("source", "unknown")

            if source == "value_changed" and "changed_columns" in diff:
                # New SQL format with column-level detail: show each changed column as a row
                for col, vals in diff["changed_columns"].items():
                    sample_data.append(
                        {
                            "Primary Key": pk_str,
                            "Source": "value_changed",
                            "Column": col,
                            "Production Value": vals.get("production", ""),
                            "Test Value": vals.get("test", ""),
                        }
                    )
            elif comparison_method == "sql" or "values" in diff:
                # SQL format: {primary_key: {}, source: 'production_only'/'test_only', values: {}}
                sample_data.append(
                    {
                        "Primary Key": pk_str,
                        "Source": source,
                        "Column": "(all columns)",
                        "Production Value": str(diff.get("values", {})) if source == "production_only" else "",
                        "Test Value": str(diff.get("values", {})) if source == "test_only" else "",
                    }
                )
            else:
                # Pandas format: {primary_key: {}, column: '', production_value: '', test_value: ''}
                sample_data.append(
                    {
                        "Primary Key": pk_str,
                        "Source": "value_changed",
                        "Column": diff.get("column", ""),
                        "Production Value": diff.get("production_value", ""),
                        "Test Value": diff.get("test_value", ""),
                    }
                )

        sample_df = pd.DataFrame(sample_data)
        st.dataframe(sample_df, width="stretch")

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


def _build_diff_rows_html(aligned_diff: List[Dict[str, Any]]) -> Dict[str, str]:
    """Build HTML rows for production and test panels in synchronized scroll view."""
    prod_rows = []
    test_rows = []

    for i, row in enumerate(aligned_diff):
        status = row.get("status", "match")
        row_class = {
            "match": "row-match",
            "differ": "row-differ",
            "prod_only": "row-prod-only",
            "test_only": "row-test-only",
        }.get(status, "row-match")

        # Production side
        if row.get("prod_msg") is not None:
            prod_content = html.escape(str(row["prod_msg"]))
            prod_line = (row.get("prod_idx") or i) + 1
            prod_rows.append(
                f'<div class="log-row {row_class}" data-row="{i}">'
                f'<span class="line-num">{prod_line}</span>'
                f'<span class="line-content">{prod_content}</span>'
                f"</div>"
            )
        else:
            prod_rows.append(
                f'<div class="log-row row-empty" data-row="{i}">'
                f'<span class="line-num">-</span>'
                f'<span class="line-content">(no line)</span>'
                f"</div>"
            )

        # Test side
        if row.get("test_msg") is not None:
            test_content = html.escape(str(row["test_msg"]))
            test_line = (row.get("test_idx") or i) + 1
            test_rows.append(
                f'<div class="log-row {row_class}" data-row="{i}">'
                f'<span class="line-num">{test_line}</span>'
                f'<span class="line-content">{test_content}</span>'
                f"</div>"
            )
        else:
            test_rows.append(
                f'<div class="log-row row-empty" data-row="{i}">'
                f'<span class="line-num">-</span>'
                f'<span class="line-content">(no line)</span>'
                f"</div>"
            )

    return {"production": "\n".join(prod_rows), "test": "\n".join(test_rows)}


def render_synchronized_log_viewer(
    aligned_diff: List[Dict[str, Any]], title: str = "Log Comparison", height: int = 500
) -> None:
    """
    Render a synchronized scrolling side-by-side log viewer.

    Uses custom HTML/CSS/JS embedded via st.components.v1.html() to provide
    a Beyond Compare-style synchronized scrolling experience.

    Args:
        aligned_diff: List of aligned diff rows from comparison engine
        title: Title for the viewer
        height: Height of the viewer in pixels
    """
    if not aligned_diff:
        st.info("No log data to display")
        return

    rows_html = _build_diff_rows_html(aligned_diff)

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
            .sync-container {{
                display: flex;
                width: 100%;
                height: {height}px;
                font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', 'Consolas', monospace;
                font-size: 12px;
                border: 1px solid #ddd;
                border-radius: 4px;
                overflow: hidden;
            }}
            .log-panel {{
                flex: 1;
                overflow-y: auto;
                background: #fafafa;
            }}
            .log-panel:first-child {{
                border-right: 2px solid #666;
            }}
            .panel-header {{
                position: sticky;
                top: 0;
                background: linear-gradient(to bottom, #f0f0f0, #e0e0e0);
                padding: 10px 12px;
                font-weight: bold;
                font-size: 13px;
                border-bottom: 1px solid #ccc;
                z-index: 10;
            }}
            .panel-header.prod {{ color: #d73a49; }}
            .panel-header.test {{ color: #28a745; }}
            .log-content {{
                padding: 0;
            }}
            .log-row {{
                display: flex;
                padding: 3px 8px;
                border-bottom: 1px solid #eee;
                min-height: 24px;
                align-items: flex-start;
            }}
            .line-num {{
                min-width: 45px;
                color: #888;
                text-align: right;
                padding-right: 10px;
                user-select: none;
                font-size: 11px;
            }}
            .line-content {{
                flex: 1;
                white-space: pre-wrap;
                word-break: break-word;
                line-height: 1.4;
            }}
            /* Status-based coloring */
            .row-match {{ background-color: #fff; }}
            .row-differ {{ background-color: #fff3cd; }}
            .row-prod-only {{ background-color: #ffebe9; }}
            .row-test-only {{ background-color: #d4edda; }}
            .row-empty {{ background-color: #f5f5f5; color: #999; font-style: italic; }}

            /* Highlight on hover */
            .log-row:hover {{
                background-color: #e8f4fc !important;
            }}

            /* Legend */
            .legend {{
                display: flex;
                gap: 15px;
                padding: 8px 12px;
                background: #f8f9fa;
                border-bottom: 1px solid #ddd;
                font-size: 11px;
            }}
            .legend-item {{
                display: flex;
                align-items: center;
                gap: 5px;
            }}
            .legend-color {{
                width: 14px;
                height: 14px;
                border-radius: 2px;
                border: 1px solid #ccc;
            }}
        </style>
    </head>
    <body>
        <div class="legend">
            <div class="legend-item"><div class="legend-color" style="background:#fff;"></div> Match</div>
            <div class="legend-item"><div class="legend-color" style="background:#fff3cd;"></div> Different</div>
            <div class="legend-item"><div class="legend-color" style="background:#ffebe9;"></div> Production Only</div>
            <div class="legend-item"><div class="legend-color" style="background:#d4edda;"></div> Test Only</div>
        </div>
        <div class="sync-container">
            <div class="log-panel" id="panel-prod">
                <div class="panel-header prod">Production Logs</div>
                <div class="log-content" id="content-prod">
                    {rows_html['production']}
                </div>
            </div>
            <div class="log-panel" id="panel-test">
                <div class="panel-header test">Test Logs</div>
                <div class="log-content" id="content-test">
                    {rows_html['test']}
                </div>
            </div>
        </div>

        <script>
            // Synchronized scrolling
            const panelProd = document.getElementById('panel-prod');
            const panelTest = document.getElementById('panel-test');

            let isScrolling = false;

            function syncScroll(source, target) {{
                if (isScrolling) return;
                isScrolling = true;

                // Calculate scroll percentage
                const maxScroll = source.scrollHeight - source.clientHeight;
                if (maxScroll > 0) {{
                    const scrollPercent = source.scrollTop / maxScroll;
                    const targetMaxScroll = target.scrollHeight - target.clientHeight;
                    target.scrollTop = scrollPercent * targetMaxScroll;
                }}

                requestAnimationFrame(() => {{ isScrolling = false; }});
            }}

            panelProd.addEventListener('scroll', () => syncScroll(panelProd, panelTest));
            panelTest.addEventListener('scroll', () => syncScroll(panelTest, panelProd));
        </script>
    </body>
    </html>
    """

    components.html(html_content, height=height + 80, scrolling=False)


def _display_unified_diff(aligned_diff: List[Dict[str, Any]]) -> None:
    """Display logs in unified diff format (git-style)."""
    if not aligned_diff:
        st.info("No differences to display")
        return

    for row in aligned_diff:
        status = row.get("status")

        if status == "match":
            st.text(f"  {row.get('prod_msg', '')}")
        elif status == "prod_only":
            st.markdown(
                f'<div style="background-color: #ffebe9; padding: 2px 8px; margin: 1px 0; border-radius: 2px;">'
                f'<code style="color: #d73a49;">- {html.escape(str(row.get("prod_msg", "")))}</code></div>',
                unsafe_allow_html=True,
            )
        elif status == "test_only":
            st.markdown(
                f'<div style="background-color: #d4edda; padding: 2px 8px; margin: 1px 0; border-radius: 2px;">'
                f'<code style="color: #28a745;">+ {html.escape(str(row.get("test_msg", "")))}</code></div>',
                unsafe_allow_html=True,
            )
        elif status == "differ":
            if row.get("prod_msg"):
                st.markdown(
                    f'<div style="background-color: #ffebe9; padding: 2px 8px; margin: 1px 0; border-radius: 2px;">'
                    f'<code style="color: #d73a49;">- {html.escape(str(row.get("prod_msg", "")))}</code></div>',
                    unsafe_allow_html=True,
                )
            if row.get("test_msg"):
                st.markdown(
                    f'<div style="background-color: #d4edda; padding: 2px 8px; margin: 1px 0; border-radius: 2px;">'
                    f'<code style="color: #28a745;">+ {html.escape(str(row.get("test_msg", "")))}</code></div>',
                    unsafe_allow_html=True,
                )


def _display_log_section(log_data: Dict[str, Any], title: str, description: str) -> None:
    """Display a single log comparison section with sync scroll viewer."""
    st.markdown(f"#### {title}")
    st.caption(description)

    if not log_data:
        st.info("No log data available")
        return

    stats = log_data.get("stats", {})
    status = log_data.get("status", "unknown")

    # Status banner
    if status == "match":
        st.success(f"✅ All {stats.get('total', 0)} log entries match")
    else:
        st.warning(
            f"⚠️ Differences found: {stats.get('matching', 0)} matching, "
            f"{stats.get('prod_only', 0)} production-only, "
            f"{stats.get('test_only', 0)} test-only, "
            f"{stats.get('differing', 0)} different"
        )

    # View mode selector
    view_mode = st.radio(
        "View Mode",
        ["Synchronized Side-by-Side", "Unified Diff", "Raw Logs"],
        horizontal=True,
        key=f"view_mode_{title.replace(' ', '_').lower()}",
    )

    aligned_diff = log_data.get("aligned_diff", [])

    if view_mode == "Synchronized Side-by-Side":
        if aligned_diff:
            render_synchronized_log_viewer(aligned_diff, title, height=400)
        else:
            st.info("No aligned diff data available")

    elif view_mode == "Unified Diff":
        _display_unified_diff(aligned_diff)

    elif view_mode == "Raw Logs":
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Production Logs**")
            for i, msg in enumerate(log_data.get("production_messages", [])[:100], 1):
                st.text(f"{i:4d} | {msg}")
            if len(log_data.get("production_messages", [])) > 100:
                st.caption("... (showing first 100 messages)")
        with col2:
            st.markdown("**Test Logs**")
            for i, msg in enumerate(log_data.get("test_messages", [])[:100], 1):
                st.text(f"{i:4d} | {msg}")
            if len(log_data.get("test_messages", [])) > 100:
                st.caption("... (showing first 100 messages)")


def display_log_comparison_v2(log_comparison: Dict[str, Any]) -> None:
    """
    Display enhanced log comparison with separate sections for storage and component logs.

    This provides a synchronized scrolling side-by-side view similar to Beyond Compare.

    Args:
        log_comparison: Log comparison dictionary from comparison engine
    """
    if not log_comparison or log_comparison.get("status") == "error":
        st.error(f"❌ Log comparison failed: {log_comparison.get('error', 'Unknown error')}")
        return

    # Get stats
    component_stats = log_comparison.get("component_logs", {}).get("stats", {})
    storage_events_stats = log_comparison.get("storage_events", {}).get("stats", {})

    # Overview metrics
    st.markdown("### Log Comparison Overview")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Component Logs (Prod)", component_stats.get("production_count", 0))
    with col2:
        st.metric("Component Logs (Test)", component_stats.get("test_count", 0))
    with col3:
        st.metric("Storage Events (Prod)", storage_events_stats.get("production_count", 0))
    with col4:
        st.metric("Storage Events (Test)", storage_events_stats.get("test_count", 0))

    st.markdown("---")

    # Check if we have any component logs
    has_component_logs = component_stats.get("production_count", 0) > 0 or component_stats.get("test_count", 0) > 0

    # Tab navigation - show Component Logs only if available
    if has_component_logs:
        tab1, tab2 = st.tabs(["Component Logs", "Storage Events"])

        with tab1:
            _display_log_section(
                log_comparison.get("component_logs", {}),
                "Component Logs",
                "STDOUT/STDERR output from the component container",
            )

        with tab2:
            _display_log_section(
                log_comparison.get("storage_events", {}),
                "Storage Events",
                "Storage API events (table loads, metadata changes)",
            )
    else:
        # Only Storage Events tab when no component logs
        st.info(
            "ℹ️ **Component Logs not available.** "
            "This may be due to event retention (events are kept for 6 months) or token permissions. "
            "Showing Storage Events below."
        )
        _display_log_section(
            log_comparison.get("storage_events", {}),
            "Storage Events",
            "Storage API events (table loads, metadata changes)",
        )
