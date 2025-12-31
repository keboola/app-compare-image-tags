"""
Environment-agnostic configuration management.

This module provides configuration loading that works in both local development
(using .streamlit/secrets.toml) and production (using environment variables).
"""

import os
import streamlit as st


def get_config(key: str, default=None):
    """
    Get configuration value from secrets (local) or environment (production).

    Args:
        key: Configuration key to retrieve
        default: Default value if key not found

    Returns:
        Configuration value or default
    """
    # Try Streamlit secrets first (local development)
    try:
        if key in st.secrets:
            return st.secrets[key]
    except FileNotFoundError:
        pass  # secrets.toml doesn't exist (production environment)

    # Fall back to environment variables (production)
    return os.environ.get(key, default)
