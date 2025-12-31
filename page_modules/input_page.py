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
        col1, col2 = st.columns(2)

        with col1:
            config_id = st.text_input(
                "Production Configuration ID",
                value=st.session_state.get('config_id', ''),
                help="Numeric ID of existing production configuration",
                placeholder="e.g., 123456"
            )

        with col2:
            test_tag = st.text_input(
                "Test Image Tag",
                value=st.session_state.get('test_image_tag', ''),
                help="Image tag to test (e.g., '2.0.0', 'latest')",
                placeholder="e.g., 2.0.0"
            )

        branch_name = st.text_input(
            "Development Branch Name (optional)",
            value=st.session_state.get('branch_name', 'comparison-test'),
            help="Name for dev branch (will create if doesn't exist)"
        )

        submitted = st.form_submit_button("Validate Configuration", type="primary")

    if submitted:
        if not config_id or not test_tag:
            st.error("❌ Please provide both Configuration ID and Test Image Tag")
            return

        validate_and_proceed(config_id, test_tag, branch_name)


def validate_and_proceed(config_id: str, test_tag: str, branch_name: str):
    """
    Validate inputs and prepare for execution.

    Args:
        config_id: Configuration ID
        test_tag: Test image tag
        branch_name: Development branch name
    """
    with st.spinner("Validating configuration..."):
        try:
            client = KeboolaAPIClient()

            # Fetch config to validate it exists
            config = client.get_configuration(config_id)
            component_id = config['component']

            st.success(f"✅ Found configuration: **{config['name']}**")
            st.info(f"**Component:** {component_id}")
            st.info(f"**Test Tag:** {test_tag}")

            # Store in session state
            st.session_state.config_id = config_id
            st.session_state.test_image_tag = test_tag
            st.session_state.branch_name = branch_name
            st.session_state.original_config = config
            st.session_state.component_id = component_id

            st.success("✅ Configuration validated successfully!")
            st.info("👉 Navigate to **⚙️ Execution** in the sidebar to continue")

            # Brief pause before rerun to show success messages
            import time
            time.sleep(1)
            st.rerun()

        except ValueError as e:
            st.error(f"❌ Configuration not found: {str(e)}")
            st.info("Please check the configuration ID and try again.")

        except Exception as e:
            st.error(f"❌ Failed to validate configuration: {str(e)}")
            st.exception(e)
