"""
Input Page - Multi-mode comparison input interface.

This page allows users to choose between three comparison modes:
1. Configuration Comparison - Compare two image tags of the same configuration
2. Table Comparison - Compare specific tables between production and test branches
3. Bucket Comparison - Compare all tables in specific buckets
"""

import streamlit as st

from utils.keboola_client import KeboolaAPIClient, parse_bucket_url, parse_workspace_url, validate_workspace


def create_input_page():
    """Create and display the input page."""
    st.title("📝 Comparison Input")

    show_advanced = st.session_state.get("show_advanced", False)

    st.markdown("Choose a comparison mode and provide the required details.")
    with st.expander("What gets compared", expanded=show_advanced):
        st.markdown("The app compares outputs at bucket, table, metadata, and row levels.")

    st.markdown("---")

    # Check if we already have validated input
    if st.session_state.get("comparison_mode") and st.session_state.get("input_validated"):
        display_validated_input()
        return

    # Select comparison mode
    modes = ["🔧 Configuration", "📊 Tables", "🗂️ Buckets"]
    mode_map = {"config": 0, "tables": 1, "buckets": 2}

    # Determine default index
    current_mode = st.session_state.get("comparison_mode")
    default_index = mode_map.get(current_mode, 0)

    selected_mode_label = st.radio("Select Comparison Mode", modes, index=default_index, horizontal=True)

    # Advanced Settings (shared across all modes)
    with st.expander("⚙️ Advanced Settings", expanded=False):
        st.number_input(
            "Row Comparison Limit",
            min_value=100,
            max_value=100000,
            value=st.session_state.get("comparison_row_limit", 1000),
            step=100,
            help="Maximum rows to compare per table. Lower values are faster but may miss differences.",
            key="comparison_row_limit",
        )

    st.markdown("---")

    if selected_mode_label == modes[0]:
        create_config_comparison_form()
    elif selected_mode_label == modes[1]:
        create_table_comparison_form()
    elif selected_mode_label == modes[2]:
        create_bucket_comparison_form()


def display_validated_input():
    """Display validated input summary and allow changing input."""
    mode = st.session_state.get("comparison_mode")

    # Display row limit for all modes
    row_limit = st.session_state.get("comparison_row_limit", 1000)

    # Check workspace status
    workspace_id = st.session_state.get("workspace_id")
    comparison_mode_label = "Full SQL" if workspace_id else "Row-limited in-app"

    if mode == "config":
        st.success("✅ Configuration Comparison Mode")
        st.info(f"**Configuration:** {st.session_state['original_config']['name']}")
        st.info(f"**Component:** {st.session_state['component_id']}")
        st.info(f"**Production Tag:** {st.session_state['production_image_tag']}")
        st.info(f"**Test Tag:** {st.session_state['test_image_tag']}")
        st.info(f"**Job Mode:** {st.session_state.get('job_mode', 'run')}")
        st.info(f"**Comparison Mode:** {comparison_mode_label}")
        if not workspace_id:
            st.info(f"**Row Limit:** {row_limit:,}")

    elif mode == "tables":
        st.success("✅ Table Comparison Mode")
        st.info("**Branch:** default (main branch)")
        table_ids = st.session_state["table_ids_to_compare"]
        st.info(f"**Table 1:** {table_ids[0]}")
        st.info(f"**Table 2:** {table_ids[1]}")
        st.info(f"**Comparison Mode:** {comparison_mode_label}")
        if not workspace_id:
            st.info(f"**Row Limit:** {row_limit:,}")

    elif mode == "buckets":
        st.success("✅ Bucket Comparison Mode")
        bucket_pairs = st.session_state.get("bucket_pairs", [])
        if bucket_pairs:
            st.info(f"**Bucket Pairs:** {len(bucket_pairs)}")
            st.info(f"**Comparison Mode:** {comparison_mode_label}")
            if not workspace_id:
                st.info(f"**Row Limit:** {row_limit:,}")
            with st.expander("View bucket pairs"):
                for idx, pair in enumerate(bucket_pairs):
                    bucket_a = pair["bucket_a"]
                    bucket_b = pair["bucket_b"]
                    branch_a = f"Branch {bucket_a['branch_id']}" if bucket_a["branch_id"] else "Production"
                    branch_b = f"Branch {bucket_b['branch_id']}" if bucket_b["branch_id"] else "Production"
                    st.markdown(f"**Pair {idx + 1}:**")
                    st.text(f"  🔵 {branch_a}: {bucket_a['canonical_bucket_id']}")
                    st.text(f"  🟢 {branch_b}: {bucket_b['canonical_bucket_id']}")
        else:
            # Legacy format fallback
            st.info(f"**Production Branch:** {st.session_state.get('production_branch_name', 'N/A')}")
            st.info(f"**Test Branch:** {st.session_state.get('test_branch_name', 'N/A')}")
            bucket_ids = st.session_state.get("bucket_ids_to_compare", [])
            st.info(f"**Buckets to Compare:** {len(bucket_ids)}")
            st.info(f"**Comparison Mode:** {comparison_mode_label}")
            if not workspace_id:
                st.info(f"**Row Limit:** {row_limit:,}")
            with st.expander("View bucket list"):
                for bucket_id in bucket_ids:
                    st.text(f"  • {bucket_id}")

    if st.button("🔄 Change Input"):
        # Clear current input and allow re-entry
        clear_input_session_state()
        st.rerun()

    st.markdown("---")
    st.info("👉 Navigate to **⚙️ Execution** in the sidebar to continue")


def clear_input_session_state():
    """Clear all input-related session state variables."""
    keys_to_clear = [
        # Reset validation state
        "input_validated",
        # Clear computed/parsed values, but KEEP raw inputs
        "config_id",
        "original_config",
        "component_id",
        # "production_image_tag",  <-- KEEP
        # "test_image_tag",        <-- KEEP
        "table_ids_to_compare",
        # "table_id_1",            <-- KEEP
        # "table_id_2",            <-- KEEP
        "bucket_ids_to_compare",
        "bucket_pairs",
        # "bucket_urls_input",     <-- KEEP
        # "production_branch_name", <-- KEEP
        # "test_branch_name",       <-- KEEP
        "production_branch_id",
        "test_branch_id",
        # Workspace (clear ID but keep URL for re-validation)
        "workspace_id",
        # "workspace_url",         <-- KEEP
        # Execution and Results
        "comparison_results",
        "comparison_triggered",
        "production_job_id",
        "test_job_id",
        "production_job_status",
        "test_job_status",
        "production_config_updated",
        "test_config_updated",
        "jobs_completion_logged",
        # Logs
        "branch_creation_logs",
        "config_production_logs",
        "config_test_logs",
        "job_execution_logs",
        "job_monitoring_logs",
        "comparison_logs",
    ]

    # Also find and clear any dynamic keys (like one-time flags)
    extra_keys = [k for k in st.session_state.keys() if k.startswith("job_monitoring_logged_")]
    keys_to_clear.extend(extra_keys)

    for key in keys_to_clear:
        st.session_state.pop(key, None)


def create_config_comparison_form():
    """Create form for configuration comparison mode."""
    show_advanced = st.session_state.get("show_advanced", False)

    st.markdown("### Compare Configuration with Different Image Tags")
    st.caption("Runs the same configuration twice with different image tags and compares outputs.")
    with st.expander("How this works", expanded=show_advanced):
        st.markdown("""
        The app will:
        1. Create two development branches
        2. Update configurations with different image tags
        3. Run both configurations in parallel
        4. Compare all outputs
        """)

    with st.form("config_input_form"):
        user_token = st.text_input(
            "Keboola Admin Token",
            type="password",
            value=st.session_state.get("user_token", ""),
            key="user_token_config",
            help="Your Keboola admin token (must have permissions to create development branches)",
            placeholder="Enter your admin token here",
        )

        config_input = st.text_input(
            "Production Configuration URL",
            value=st.session_state.get("config_input", ""),
            key="widget_config_input",
            help="Paste the PRODUCTION configuration URL from Keboola (full URL required)",
            placeholder="e.g., https://connection.keboola.com/admin/projects/12345/components/keboola.ex-instagram-v2/01kcrfjxt5wvms53ds3vy6x5h1",
        )

        workspace_url = st.text_input(
            "Workspace URL (Optional)",
            value=st.session_state.get("workspace_url", ""),
            key="widget_workspace_url_config",
            help=(
                "Optional: Your Keboola workspace URL. If provided, enables full SQL-level comparison of tables. "
                "Without this, comparisons use a row limit and in-app comparison (safer for large tables). "
                "Find it in Keboola: Workspaces > your workspace > copy URL from browser."
            ),
            placeholder="e.g., https://connection.keboola.com/admin/projects/12345/workspaces/01kg4cky9chn32aqaxq7ejnrzj",
        )

        col1, col2 = st.columns(2)

        with col1:
            production_tag = st.text_input(
                "Production Image Tag",
                value=st.session_state.get("production_image_tag", "latest"),
                key="widget_production_image_tag",
                help="Current/production image tag to compare from (default: 'latest')",
                placeholder="e.g., latest",
            )

        with col2:
            test_tag = st.text_input(
                "Test Image Tag",
                value=st.session_state.get("test_image_tag", ""),
                key="widget_test_image_tag",
                help="New image tag to test against production",
                placeholder="e.g., 2.0.0",
            )

        branch_name = st.text_input(
            "Development Branch Name (optional)",
            value=st.session_state.get("branch_name", "comparison-test"),
            key="widget_branch_name",
            help="Name for dev branch (will create if doesn't exist)",
        )

        job_mode = st.selectbox(
            "Job Mode",
            options=["run", "debug"],
            index=0 if st.session_state.get("job_mode", "run") == "run" else 1,
            key="widget_job_mode",
            help="'run' executes normally, 'debug' provides more detailed logs but may behave differently",
        )

        st.markdown("---")

        auto_run = st.checkbox(
            "🚀 Auto-run to completion",
            value=st.session_state.get("auto_run", False),
            help="Automatically execute all steps without manual clicks (create branches, run jobs, wait for completion, run comparison)",
        )

        submitted = st.form_submit_button("Validate Configuration & Start", type="primary")

    if submitted:
        if not user_token:
            st.error("❌ Please provide your Keboola Admin Token")
            return

        if not config_input or not production_tag or not test_tag:
            st.error("❌ Please provide Configuration ID/URL and both image tags")
            return

        # Parse config ID and component ID from URL or direct input
        config_id, component_id = parse_config_url(config_input)
        if not config_id:
            st.error("❌ Invalid configuration ID or URL format")
            return

        validate_config_comparison(
            config_id, component_id, config_input, production_tag, test_tag, branch_name, user_token, auto_run, job_mode, workspace_url
        )


def create_table_comparison_form():
    """Create form for direct table comparison mode."""
    show_advanced = st.session_state.get("show_advanced", False)

    st.markdown("### Compare Two Specific Tables")
    st.caption("Compare two tables from the default branch.")
    with st.expander("How this works", expanded=show_advanced):
        st.markdown("""
        Provide table IDs in the format: `bucket_id.table_name`

        **Example:** `in.c-my-bucket.customers`
        """)

    with st.form("table_input_form"):
        user_token = st.text_input(
            "Keboola Admin Token",
            type="password",
            value=st.session_state.get("user_token", ""),
            key="user_token_tables",
            help="Your Keboola admin token",
            placeholder="Enter your admin token here",
        )

        kbc_url = st.text_input(
            "Keboola Connection URL",
            value=st.session_state.get("kbc_url", ""),
            key="kbc_url_tables",
            help="Your Keboola connection URL (e.g., https://connection.keboola.com)",
            placeholder="e.g., https://connection.keboola.com",
        )

        workspace_url = st.text_input(
            "Workspace URL (Optional)",
            value=st.session_state.get("workspace_url", ""),
            key="widget_workspace_url_tables",
            help=(
                "Optional: Your Keboola workspace URL. If provided, enables full SQL-level comparison of tables. "
                "Without this, comparisons use a row limit and in-app comparison (safer for large tables). "
                "Find it in Keboola: Workspaces > your workspace > copy URL from browser."
            ),
            placeholder="e.g., https://connection.keboola.com/admin/projects/12345/workspaces/01kg4cky9chn32aqaxq7ejnrzj",
        )

        col1, col2 = st.columns(2)

        with col1:
            table_id_1 = st.text_input(
                "First Table ID",
                value=st.session_state.get("table_id_1", ""),
                key="widget_table_id_1",
                help="Enter table ID in format: bucket_id.table_name",
                placeholder="e.g., in.c-my-bucket.customers",
            )

        with col2:
            table_id_2 = st.text_input(
                "Second Table ID",
                value=st.session_state.get("table_id_2", ""),
                key="widget_table_id_2",
                help="Enter table ID in format: bucket_id.table_name",
                placeholder="e.g., out.c-results.processed_data",
            )

        st.markdown("---")

        auto_run = st.checkbox(
            "🚀 Auto-run to completion",
            value=st.session_state.get("auto_run", False),
            help="Automatically execute comparison without manual clicks",
        )

        submitted = st.form_submit_button("Validate Tables & Start", type="primary")

    if submitted:
        if not user_token:
            st.error("❌ Please provide your Keboola Admin Token")
            return

        if not kbc_url:
            st.error("❌ Please provide Keboola Connection URL")
            return

        if not table_id_1.strip() or not table_id_2.strip():
            st.error("❌ Please provide both table IDs")
            return

        # Create table IDs list
        table_ids = [table_id_1.strip(), table_id_2.strip()]

        validate_table_comparison(user_token, kbc_url, table_ids, auto_run, workspace_url)


def create_bucket_comparison_form():
    """Create form for bucket comparison mode using bucket URLs."""
    show_advanced = st.session_state.get("show_advanced", False)

    st.markdown("### Compare Buckets Using URLs")
    st.caption("Compare buckets by pasting their URLs directly from Keboola.")
    with st.expander("How this works", expanded=show_advanced):
        st.markdown("""
        **Paste bucket URLs directly from Keboola** (one per line).

        The URL contains all the information needed: connection, branch, and bucket ID.

        **Examples:**
        - Production bucket:
          `https://connection.us-east4.gcp.keboola.com/admin/projects/4214/storage/in.c-mybucket/overview`
        - Dev branch bucket:
          `https://connection.us-east4.gcp.keboola.com/admin/projects/4214/branch/27405/storage/in.c-27405-mybucket/overview`

        **Comparison pairs:** URLs are compared in pairs (1st with 2nd, 3rd with 4th, etc.)
        - Enter 2 URLs to compare one bucket pair
        - Enter 4 URLs to compare two bucket pairs
        - And so on...
        """)

    with st.form("bucket_input_form"):
        user_token = st.text_input(
            "Keboola Admin Token",
            type="password",
            value=st.session_state.get("user_token", ""),
            key="user_token_buckets",
            help="Your Keboola admin token",
            placeholder="Enter your admin token here",
        )

        workspace_url = st.text_input(
            "Workspace URL (Optional)",
            value=st.session_state.get("workspace_url", ""),
            key="widget_workspace_url_buckets",
            help=(
                "Optional: Your Keboola workspace URL. If provided, enables full SQL-level comparison of tables. "
                "Without this, comparisons use a row limit and in-app comparison (safer for large tables). "
                "Find it in Keboola: Workspaces > your workspace > copy URL from browser."
            ),
            placeholder="e.g., https://connection.keboola.com/admin/projects/12345/workspaces/01kg4cky9chn32aqaxq7ejnrzj",
        )

        bucket_urls_input = st.text_area(
            "Bucket URLs to Compare (one per line, in pairs)",
            value=st.session_state.get("bucket_urls_input", ""),
            key="widget_bucket_urls_input",
            help="Paste bucket URLs from Keboola. URLs are compared in pairs (1st vs 2nd, 3rd vs 4th, etc.)",
            placeholder="https://connection.../admin/projects/123/storage/in.c-mybucket/overview\nhttps://connection.../admin/projects/123/branch/456/storage/in.c-456-mybucket/overview",
            height=150,
        )

        st.markdown("---")

        auto_run = st.checkbox(
            "🚀 Auto-run to completion",
            value=st.session_state.get("auto_run", False),
            help="Automatically execute comparison without manual clicks",
        )

        submitted = st.form_submit_button("Validate Buckets & Start", type="primary")

    if submitted:
        if not user_token:
            st.error("❌ Please provide your Keboola Admin Token")
            return

        if not bucket_urls_input.strip():
            st.error("❌ Please provide at least two bucket URLs")
            return

        # Parse bucket URLs
        bucket_urls = [line.strip() for line in bucket_urls_input.strip().split("\n") if line.strip()]

        if len(bucket_urls) < 2:
            st.error("❌ Please provide at least two bucket URLs to compare")
            return

        if len(bucket_urls) % 2 != 0:
            st.error("❌ Please provide bucket URLs in pairs (even number of URLs required)")
            return

        validate_bucket_comparison(user_token, bucket_urls, auto_run, workspace_url)


def parse_config_url(input_str: str) -> tuple:
    """
    Parse configuration and component IDs from either direct ID or full Keboola URL.

    Args:
        input_str: Configuration ID or full URL

    Returns:
        Tuple of (config_id, component_id or None)

    Examples:
        "01kcrfjxt5wvms53ds3vy6x5h1" -> ("01kcrfjxt5wvms53ds3vy6x5h1", None)
        "https://.../components/keboola.ex-instagram-v2/01kcrfjxt5wvms53ds3vy6x5h1"
            -> ("01kcrfjxt5wvms53ds3vy6x5h1", "keboola.ex-instagram-v2")
    """
    input_str = input_str.strip()

    # If it's a URL, extract component ID and config ID
    if input_str.startswith("http://") or input_str.startswith("https://"):
        parts = input_str.rstrip("/").split("/")
        if len(parts) >= 2 and "components" in parts:
            # Find the components index
            try:
                comp_idx = parts.index("components")
                if comp_idx + 2 < len(parts):
                    component_id = parts[comp_idx + 1]
                    config_id = parts[comp_idx + 2]
                    return (config_id, component_id)
            except (ValueError, IndexError):
                pass

        # Fallback: just get the last part as config ID
        if parts:
            return (parts[-1], None)
        return ("", None)

    # Otherwise, treat as direct config ID
    return (input_str, None)


def validate_config_comparison(
    config_id: str,
    component_id: str,
    config_input: str,
    production_tag: str,
    test_tag: str,
    branch_name: str,
    user_token: str,
    auto_run: bool,
    job_mode: str = "run",
    workspace_url: str = "",
):
    """
    Validate configuration comparison inputs and prepare for execution.

    Args:
        config_id: Parsed configuration ID
        component_id: Component ID (if parsed from URL, else None)
        config_input: Original input (for display)
        production_tag: Production image tag
        test_tag: Test image tag
        branch_name: Development branch name
        user_token: User's Keboola admin token (with branch creation permissions)
        auto_run: Whether to automatically run all steps to completion
        job_mode: Job execution mode - "run" (default) or "debug"
        workspace_url: Optional workspace URL for SQL-level comparisons
    """
    with st.spinner("Validating configuration..."):
        try:
            # Extract KBC URL from config input if it's a URL
            kbc_url = None
            if config_input and config_input.startswith("http"):
                parts = config_input.split("/")
                if len(parts) >= 3:
                    kbc_url = f"{parts[0]}//{parts[2]}"

            # Validate workspace URL if provided (fail fast)
            workspace_id = None
            if workspace_url and workspace_url.strip():
                try:
                    ws_base_url, ws_config_id = parse_workspace_url(workspace_url)
                    # Validate workspace exists
                    workspace_data = validate_workspace(
                        kbc_url if kbc_url else ws_base_url,
                        user_token,
                        ws_config_id
                    )
                    workspace_id = str(workspace_data["id"])
                    st.success(f"✅ Workspace validated: **{workspace_data.get('name', 'Unknown')}**")
                except ValueError as e:
                    st.error(f"❌ Invalid workspace URL: {str(e)}")
                    return

            client = KeboolaAPIClient(token_override=user_token, kbc_url_override=kbc_url, workspace_id=workspace_id)

            # Fetch config to validate it exists
            if component_id:
                # If we have component ID from URL, fetch directly
                config = client.get_configuration_direct(component_id, config_id)
            else:
                # Otherwise search through all components
                config = client.get_configuration(config_id)
                component_id = config["component"]

            st.success(f"✅ Found configuration: **{config['name']}**")
            st.info(f"**Component:** {component_id}")
            st.info(f"**Production Tag:** {production_tag}")
            st.info(f"**Test Tag:** {test_tag}")

            # Store in session state
            st.session_state.comparison_mode = "config"
            st.session_state.input_validated = True
            st.session_state.user_token = user_token
            st.session_state.config_id = config_id
            st.session_state.config_input = config_input
            st.session_state.production_image_tag = production_tag
            st.session_state.test_image_tag = test_tag
            st.session_state.branch_name = branch_name
            st.session_state.original_config = config
            st.session_state.component_id = component_id
            st.session_state.auto_run = auto_run
            st.session_state.job_mode = job_mode
            st.session_state.workspace_url = workspace_url
            st.session_state.workspace_id = workspace_id  # None if not provided

            st.success("✅ Configuration validated successfully!")
            if auto_run:
                st.success("🚀 Auto-run enabled - will proceed automatically to completion")
            else:
                st.info("👉 Navigate to **⚙️ Execution** in the sidebar to continue")

            # Brief pause before rerun to show success messages
            import time

            time.sleep(1)
            st.rerun()

        except ValueError as e:
            st.error(f"❌ Configuration not found: {str(e)}")
            st.info("Please check the configuration ID/URL and try again.")

        except Exception as e:
            st.error(f"❌ Failed to validate configuration: {str(e)}")
            st.exception(e)


def validate_table_comparison(user_token: str, kbc_url: str, table_ids: list, auto_run: bool, workspace_url: str = ""):
    """
    Validate table comparison inputs and prepare for execution.

    Args:
        user_token: Keboola admin token
        kbc_url: Keboola connection URL
        table_ids: List of table IDs to compare (always 2 tables)
        auto_run: Whether to automatically run all steps to completion
        workspace_url: Optional workspace URL for SQL-level comparisons
    """
    with st.spinner("Validating tables..."):
        try:
            # Validate workspace URL if provided (fail fast)
            workspace_id = None
            if workspace_url and workspace_url.strip():
                try:
                    ws_base_url, ws_config_id = parse_workspace_url(workspace_url)
                    # Use provided kbc_url if available, otherwise use the one from workspace URL
                    effective_kbc_url = kbc_url if kbc_url else ws_base_url
                    # Validate workspace exists
                    workspace_data = validate_workspace(
                        effective_kbc_url,
                        user_token,
                        ws_config_id
                    )
                    workspace_id = str(workspace_data["id"])
                    st.success(f"✅ Workspace validated: **{workspace_data.get('name', 'Unknown')}**")
                except ValueError as e:
                    st.error(f"❌ Invalid workspace URL: {str(e)}")
                    return

            # Validate credentials by attempting to create client
            KeboolaAPIClient(token_override=user_token, kbc_url_override=kbc_url, workspace_id=workspace_id)

            st.success(f"✅ Validated {len(table_ids)} table(s) for comparison")
            st.info("**Branch:** default (main branch)")
            st.info(f"**Table 1:** {table_ids[0]}")
            st.info(f"**Table 2:** {table_ids[1]}")

            # Store in session state - using default branch (None)
            st.session_state.comparison_mode = "tables"
            st.session_state.input_validated = True
            st.session_state.user_token = user_token
            st.session_state.kbc_url = kbc_url
            st.session_state.production_branch_id = None  # Default branch
            st.session_state.test_branch_id = None  # Default branch
            st.session_state.table_ids_to_compare = table_ids
            # Persist raw table IDs for form restoration
            st.session_state.table_id_1 = table_ids[0]
            st.session_state.table_id_2 = table_ids[1]
            st.session_state.auto_run = auto_run
            st.session_state.workspace_url = workspace_url
            st.session_state.workspace_id = workspace_id  # None if not provided

            st.success("✅ Tables validated successfully!")
            if auto_run:
                st.success("🚀 Auto-run enabled - will proceed automatically to completion")
            else:
                st.info("👉 Navigate to **⚙️ Execution** in the sidebar to continue")

            # Brief pause before rerun to show success messages
            import time

            time.sleep(1)
            st.rerun()

        except Exception as e:
            st.error(f"❌ Failed to validate tables: {str(e)}")
            st.exception(e)


def validate_bucket_comparison(user_token: str, bucket_urls: list, auto_run: bool, workspace_url: str = ""):
    """
    Validate bucket comparison inputs using bucket URLs.

    Args:
        user_token: Keboola admin token
        bucket_urls: List of bucket URLs to compare (in pairs)
        auto_run: Whether to automatically run all steps to completion
        workspace_url: Optional workspace URL for SQL-level comparisons
    """
    with st.spinner("Validating bucket URLs..."):
        try:
            # Parse all bucket URLs
            parsed_buckets = []
            for url in bucket_urls:
                try:
                    parsed = parse_bucket_url(url)
                    parsed_buckets.append(parsed)
                except ValueError as e:
                    st.error(f"❌ Invalid bucket URL: {str(e)}")
                    return

            # Extract KBC URL from first bucket (all should be same project)
            kbc_url = parsed_buckets[0]["base_url"]

            # Validate workspace URL if provided (fail fast)
            workspace_id = None
            if workspace_url and workspace_url.strip():
                try:
                    ws_base_url, ws_config_id = parse_workspace_url(workspace_url)
                    # Validate workspace exists
                    workspace_data = validate_workspace(
                        kbc_url,
                        user_token,
                        ws_config_id
                    )
                    workspace_id = str(workspace_data["id"])
                    st.success(f"✅ Workspace validated: **{workspace_data.get('name', 'Unknown')}**")
                except ValueError as e:
                    st.error(f"❌ Invalid workspace URL: {str(e)}")
                    return

            # Create bucket pairs for comparison
            bucket_pairs = []
            for i in range(0, len(parsed_buckets), 2):
                bucket_a = parsed_buckets[i]
                bucket_b = parsed_buckets[i + 1]
                bucket_pairs.append({
                    "bucket_a": bucket_a,
                    "bucket_b": bucket_b,
                })

            # Display parsed info
            st.success(f"✅ Parsed {len(bucket_urls)} bucket URL(s) → {len(bucket_pairs)} comparison pair(s)")

            for idx, pair in enumerate(bucket_pairs):
                bucket_a = pair["bucket_a"]
                bucket_b = pair["bucket_b"]
                branch_a_display = f"Branch {bucket_a['branch_id']}" if bucket_a["branch_id"] else "Production"
                branch_b_display = f"Branch {bucket_b['branch_id']}" if bucket_b["branch_id"] else "Production"

                st.info(f"""
                **Pair {idx + 1}:**
                - 🔵 {branch_a_display}: `{bucket_a['canonical_bucket_id']}`
                - 🟢 {branch_b_display}: `{bucket_b['canonical_bucket_id']}`
                """)

            # Store in session state
            st.session_state.comparison_mode = "buckets"
            st.session_state.input_validated = True
            st.session_state.user_token = user_token
            st.session_state.kbc_url = kbc_url
            st.session_state.bucket_pairs = bucket_pairs  # New: structured bucket pair info
            st.session_state.bucket_urls_input = "\n".join(bucket_urls)  # For form restoration
            st.session_state.auto_run = auto_run
            st.session_state.workspace_url = workspace_url
            st.session_state.workspace_id = workspace_id

            # For backward compatibility with orchestration page (use first pair)
            if bucket_pairs:
                first_pair = bucket_pairs[0]
                st.session_state.production_branch_id = first_pair["bucket_a"]["branch_id"]
                st.session_state.test_branch_id = first_pair["bucket_b"]["branch_id"]
                st.session_state.production_branch_name = (
                    f"Branch {first_pair['bucket_a']['branch_id']}"
                    if first_pair["bucket_a"]["branch_id"]
                    else "Production"
                )
                st.session_state.test_branch_name = (
                    f"Branch {first_pair['bucket_b']['branch_id']}"
                    if first_pair["bucket_b"]["branch_id"]
                    else "Production"
                )

            st.success("✅ Buckets validated successfully!")
            if auto_run:
                st.success("🚀 Auto-run enabled - will proceed automatically to completion")
            else:
                st.info("👉 Navigate to **⚙️ Execution** in the sidebar to continue")

            # Brief pause before rerun to show success messages
            import time

            time.sleep(1)
            st.rerun()

        except Exception as e:
            st.error(f"❌ Failed to validate buckets: {str(e)}")
            st.exception(e)


def resolve_branch_id(client: KeboolaAPIClient, branch_identifier: str) -> str:
    """
    Resolve branch name to branch ID, or return as-is if already an ID.

    Args:
        client: Keboola API client
        branch_identifier: Branch name or ID

    Returns:
        Branch ID (None for 'default' branch)
    """
    # Handle default branch
    if branch_identifier.lower() in ["default", "main"]:
        return None

    # Check if it's already a numeric ID
    if branch_identifier.isdigit():
        return branch_identifier

    # Try to find branch by name
    try:
        branches = client.list_branches()
        for branch in branches:
            if branch["name"] == branch_identifier:
                return str(branch["id"])
    except (KeyError, TypeError, AttributeError):
        pass

    # If not found, assume it's an ID
    return branch_identifier
