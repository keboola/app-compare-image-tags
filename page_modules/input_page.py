"""
Input Page - Configuration ID and test image tag collection.

This page allows users to input the production configuration ID and test image tag,
validates the configuration exists, and stores it in session state for the next phase.
"""

import streamlit as st
from utils.keboola_client import KeboolaAPIClient


def create_input_page():
    """Create and display the input page."""
    st.title("📝 Configuration Input")

    st.markdown("""
    Enter the production configuration ID and the test image tag you want to compare.
    The app will:
    1. Create a test configuration with the new image tag
    2. Run both configurations in parallel (production in default branch, test in dev branch)
    3. Compare outputs at bucket, table, metadata, and row levels
    """)

    st.markdown("---")

    # Check if we already have validated input
    if st.session_state.get('config_id') and st.session_state.get('original_config'):
        st.success("✅ Configuration validated!")
        st.info(f"**Configuration:** {st.session_state['original_config']['name']}")
        st.info(f"**Component:** {st.session_state['component_id']}")
        st.info(f"**Test Tag:** {st.session_state['test_image_tag']}")

        if st.button("🔄 Change Configuration"):
            # Clear current config and allow re-entry
            st.session_state.pop('config_id', None)
            st.session_state.pop('original_config', None)
            st.session_state.pop('component_id', None)
            st.session_state.pop('test_image_tag', None)
            st.rerun()

        st.markdown("---")
        st.info("👉 Navigate to **⚙️ Execution** in the sidebar to continue")
        return

    # Input form
    with st.form("config_input_form"):
        user_token = st.text_input(
            "Keboola Admin Token",
            type="password",
            value=st.session_state.get('user_token', ''),
            help="Your Keboola admin token (must have permissions to create development branches)",
            placeholder="Enter your admin token here"
        )

        config_input = st.text_input(
            "Production Configuration URL",
            value=st.session_state.get('config_input', ''),
            help="Paste the PRODUCTION configuration URL from Keboola (full URL required)",
            placeholder="e.g., https://connection.keboola.com/admin/projects/12345/components/keboola.ex-instagram-v2/01kcrfjxt5wvms53ds3vy6x5h1"
        )

        col1, col2 = st.columns(2)

        with col1:
            production_tag = st.text_input(
                "Production Image Tag",
                value=st.session_state.get('production_image_tag', 'latest'),
                help="Current/production image tag to compare from (default: 'latest')",
                placeholder="e.g., latest"
            )

        with col2:
            test_tag = st.text_input(
                "Test Image Tag",
                value=st.session_state.get('test_image_tag', ''),
                help="New image tag to test against production",
                placeholder="e.g., 2.0.0"
            )

        branch_name = st.text_input(
            "Development Branch Name (optional)",
            value=st.session_state.get('branch_name', 'comparison-test'),
            help="Name for dev branch (will create if doesn't exist)"
        )

        st.markdown("---")

        auto_run = st.checkbox(
            "🚀 Auto-run to completion",
            value=st.session_state.get('auto_run', False),
            help="Automatically execute all steps without manual clicks (create branches, run jobs, wait for completion, run comparison)"
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

        validate_and_proceed(config_id, component_id, config_input, production_tag, test_tag, branch_name, user_token, auto_run)


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
        parts = input_str.rstrip('/').split('/')
        if len(parts) >= 2 and 'components' in parts:
            # Find the components index
            try:
                comp_idx = parts.index('components')
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


def validate_and_proceed(
    config_id: str,
    component_id: str,
    config_input: str,
    production_tag: str,
    test_tag: str,
    branch_name: str,
    user_token: str,
    auto_run: bool
):
    """
    Validate inputs and prepare for execution.

    Args:
        config_id: Parsed configuration ID
        component_id: Component ID (if parsed from URL, else None)
        config_input: Original input (for display)
        production_tag: Production image tag
        test_tag: Test image tag
        branch_name: Development branch name
        user_token: User's Keboola admin token (with branch creation permissions)
        auto_run: Whether to automatically run all steps to completion
    """
    with st.spinner("Validating configuration..."):
        try:
            # Extract KBC URL from config input if it's a URL
            kbc_url = None
            if config_input and config_input.startswith('http'):
                parts = config_input.split('/')
                if len(parts) >= 3:
                    kbc_url = f"{parts[0]}//{parts[2]}"

            client = KeboolaAPIClient(token_override=user_token, kbc_url_override=kbc_url)

            # Fetch config to validate it exists
            if component_id:
                # If we have component ID from URL, fetch directly
                config = client.get_configuration_direct(component_id, config_id)
            else:
                # Otherwise search through all components
                config = client.get_configuration(config_id)
                component_id = config['component']

            st.success(f"✅ Found configuration: **{config['name']}**")
            st.info(f"**Component:** {component_id}")
            st.info(f"**Production Tag:** {production_tag}")
            st.info(f"**Test Tag:** {test_tag}")

            # Store in session state
            st.session_state.user_token = user_token
            st.session_state.config_id = config_id
            st.session_state.config_input = config_input
            st.session_state.production_image_tag = production_tag
            st.session_state.test_image_tag = test_tag
            st.session_state.branch_name = branch_name
            st.session_state.original_config = config
            st.session_state.component_id = component_id
            st.session_state.auto_run = auto_run

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
