"""
Unit tests for comparison engine methods.
"""

import pytest
import pandas as pd
from unittest.mock import MagicMock
from utils.comparison_engine import ComparisonEngine


class MockClient:
    """Mock Keboola client for testing."""

    def get_table_detail(self, table_id, branch_id=None):
        """Mock table detail response."""
        return {}

    def get_qualified_table_name(self, table_id, branch_id=None):
        return f'"{table_id}"'  # Simplified mock

    def execute_query(self, query):
        """Mock query execution."""
        if "COUNT(*)" in query:
            return pd.DataFrame({"c": [100]})
        # Default empty DF for differences
        return pd.DataFrame()


def test_compare_primary_keys_with_differences():
    """Test that primary key differences are detected."""
    client = MockClient()
    engine = ComparisonEngine(client)

    # Test case 1: Different primary keys
    prod_meta = {"primaryKey": ["id", "name"]}
    test_meta = {"primaryKey": ["id"]}

    result = engine._compare_primary_keys(prod_meta, test_meta)

    assert result["match"] is False
    assert set(result["production"]) == {"id", "name"}
    assert set(result["test"]) == {"id"}


def test_compare_primary_keys_with_match():
    """Test that matching primary keys are detected."""
    client = MockClient()
    engine = ComparisonEngine(client)

    # Test case: Same primary keys
    prod_meta = {"primaryKey": ["id", "timestamp"]}
    test_meta = {"primaryKey": ["id", "timestamp"]}

    result = engine._compare_primary_keys(prod_meta, test_meta)

    assert result["match"] is True
    assert result["production"] == ["id", "timestamp"]
    assert result["test"] == ["id", "timestamp"]


def test_compare_primary_keys_order_independence():
    """Test that primary key order doesn't matter."""
    client = MockClient()
    engine = ComparisonEngine(client)

    # Test case: Same PKs in different order
    prod_meta = {"primaryKey": ["timestamp", "id"]}
    test_meta = {"primaryKey": ["id", "timestamp"]}

    result = engine._compare_primary_keys(prod_meta, test_meta)

    assert result["match"] is True


def test_compare_primary_keys_with_empty():
    """Test comparison with empty/missing primary keys."""
    client = MockClient()
    engine = ComparisonEngine(client)

    # Test case 1: Both empty
    prod_meta = {"primaryKey": []}
    test_meta = {"primaryKey": []}

    result = engine._compare_primary_keys(prod_meta, test_meta)
    assert result["match"] is True

    # Test case 2: One empty, one with keys
    prod_meta = {"primaryKey": ["id"]}
    test_meta = {"primaryKey": []}

    result = engine._compare_primary_keys(prod_meta, test_meta)
    assert result["match"] is False

    # Test case 3: Missing primaryKey field
    prod_meta = {}
    test_meta = {"primaryKey": ["id"]}

    result = engine._compare_primary_keys(prod_meta, test_meta)
    assert result["match"] is False


def test_compare_columns_with_differences():
    """Test that column differences are detected."""
    client = MockClient()
    engine = ComparisonEngine(client)

    prod_meta = {
        "columns": [
            {"name": "id", "type": "STRING"},
            {"name": "name", "type": "STRING"},
            {"name": "age", "type": "INTEGER"},
        ]
    }
    test_meta = {
        "columns": [
            {"name": "id", "type": "STRING"},
            {"name": "name", "type": "STRING"},
            {"name": "email", "type": "STRING"},
        ]
    }

    result = engine._compare_columns(prod_meta, test_meta)

    assert result["match"] is False
    assert "age" in result["production_only"]
    assert "email" in result["test_only"]
    assert set(result["common"]) == {"id", "name"}


def test_compare_data_types_with_differences():
    """Test that data type differences are detected."""
    client = MockClient()
    engine = ComparisonEngine(client)

    prod_meta = {
        "columns": [
            {"name": "id", "type": "STRING"},
            {"name": "age", "type": "INTEGER"},
        ]
    }
    test_meta = {
        "columns": [
            {"name": "id", "type": "STRING"},
            {"name": "age", "type": "STRING"},
        ]
    }

    result = engine._compare_data_types(prod_meta, test_meta)

    assert result["match"] is False
    assert "age" in result["differences"]
    assert result["differences"]["age"]["production"] == "INTEGER"
    assert result["differences"]["age"]["test"] == "STRING"


def test_compare_row_counts():
    """Test row count comparison."""
    client = MockClient()
    engine = ComparisonEngine(client)

    # Test case 1: Different counts
    prod_meta = {"rowsCount": 100}
    test_meta = {"rowsCount": 150}

    result = engine._compare_row_counts(prod_meta, test_meta)

    assert result["match"] is False
    assert result["production"] == 100
    assert result["test"] == 150

    # Test case 2: Same counts
    prod_meta = {"rowsCount": 100}
    test_meta = {"rowsCount": 100}

    result = engine._compare_row_counts(prod_meta, test_meta)

    assert result["match"] is True


def test_compare_row_data_with_row_count_mismatch():
    """
    Test that data comparison PROCEEDS even when row counts differ,
    as long as schema (PKs, columns, types) matches.
    """
    client = MockClient()
    engine = ComparisonEngine(client)

    # Mock the SQL comparison method to avoid DB calls
    engine._sql_based_comparison = MagicMock(return_value={"status": "differ", "differing_rows": 10})

    # Prepare metadata with matching schema but mismatching row count
    # Overall 'status' is 'differ' because of row count, but crucial fields match
    metadata_comparison = {
        "in.c-bucket.table": {
            "status": "differ",
            "primary_keys": {"match": True, "production": ["id"]},
            "columns": {"match": True, "common": ["id", "val"]},
            "data_types": {"match": True},
            "row_count": {"match": False, "production": 100, "test": 90},
        }
    }

    # Run comparison
    results = engine._compare_row_data(prod_branch="123", test_branch="456", metadata_comparison=metadata_comparison)

    # Assertions
    table_result = results.get("in.c-bucket.table")
    assert table_result is not None

    # It should NOT be skipped
    assert table_result.get("status") != "skipped"

    # It should have called the comparison method
    engine._sql_based_comparison.assert_called_once()


def test_compare_two_tables_integration():
    """
    Test the new compare_two_tables method directly.
    """
    client = MockClient()
    # Mock specific metadata responses for different tables
    client.get_table_detail = MagicMock(
        return_value={
            "name": "table",
            "primaryKey": ["id"],
            "columns": [{"name": "id", "type": "STRING"}],
            "rowsCount": 100,
        }
    )

    engine = ComparisonEngine(client)

    results = engine.compare_two_tables("table_A", "table_B")

    # Check structure
    assert "bucket_comparison" in results
    assert results["bucket_comparison"]["status"] == "skipped"

    assert "table_comparison" in results
    assert "virtual_bucket" in results["table_comparison"]

    assert "metadata_comparison" in results
    assert "table_A_vs_table_B" in results["metadata_comparison"]

    assert "row_differences" in results
    assert "table_A_vs_table_B" in results["row_differences"]

    assert "summary" in results
    # With mocked data (identical), overall status should be match
    # Because buckets are skipped (which we patched to allow match)
    assert results["summary"]["overall_status"] == "match"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
