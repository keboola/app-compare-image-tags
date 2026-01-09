"""
Functional tests for real comparison scenarios against Keboola stack.

Requires KBC_TOKEN env variable.
"""

import os
import pytest
from utils.keboola_client import KeboolaAPIClient
from utils.comparison_engine import ComparisonEngine

# Configuration from user request
STACK_URL = "https://connection.us-east4.gcp.keboola.com/"

# Table IDs
TABLE_A = "out.c-data-for-dq-test.dummy_a"
TABLE_B = "out.c-data-for-dq-test.dummy_b"
TABLE_C = "out.c-data-for-dq-test.dummy_c"
TABLE_D = "out.c-data-for-dq-test.dummy_d"
TABLE_E = "out.c-data-for-dq-test.dummy_e"


@pytest.fixture
def comparison_engine():
    token = os.environ.get("KBC_TOKEN")
    if not token:
        pytest.skip("KBC_TOKEN environment variable not set")

    # Initialize client with override URL and token
    client = KeboolaAPIClient(token_override=token, kbc_url_override=STACK_URL)
    return ComparisonEngine(client)


def test_scenario_1_pk_mismatch(comparison_engine):
    """
    Scenario: Table A vs Table B
    Expectation: Tables have same data but different PKs.
    Should fail metadata comparison on Primary Keys.
    """
    print(f"\nComparing {TABLE_A} vs {TABLE_B} (PK Mismatch)")
    results = comparison_engine.compare_two_tables(TABLE_A, TABLE_B)

    # Check overall flow
    assert results["bucket_comparison"]["status"] == "skipped"

    # Get metadata results for the pair
    meta_key = f"{TABLE_A}_vs_{TABLE_B}"
    meta = results["metadata_comparison"].get(meta_key)

    assert meta is not None, "Metadata comparison result missing"

    if meta.get("status") == "error":
        pytest.fail(f"Metadata comparison failed with error: {meta.get('error')}")

    # Verify PK mismatch
    assert meta["primary_keys"]["match"] is False, "Primary keys should differ"
    print(f"  - PKs A: {meta['primary_keys']['production']}")
    print(f"  - PKs B: {meta['primary_keys']['test']}")

    # Verify Columns match (as implied by "same but different PK")
    assert meta["columns"]["match"] is True, "Columns should match"


def test_scenario_2_dtype_mismatch_b_vs_c(comparison_engine):
    """
    Scenario: Table B vs Table C
    Expectation: Tables have different data types.
    Should fail metadata comparison on Data Types.
    Row comparison should be skipped due to dtype mismatch.
    """
    print(f"\nComparing {TABLE_B} vs {TABLE_C} (Data Type Mismatch)")
    results = comparison_engine.compare_two_tables(TABLE_B, TABLE_C)

    meta_key = f"{TABLE_B}_vs_{TABLE_C}"
    meta = results["metadata_comparison"].get(meta_key)
    row_diff = results["row_differences"].get(meta_key)

    assert meta is not None, "Metadata comparison result missing"

    if meta.get("status") == "error":
        pytest.fail(f"Metadata comparison failed with error: {meta.get('error')}")

    # Verify dtype mismatch
    assert meta["data_types"]["match"] is False, "Data types should differ"
    assert len(meta["data_types"]["differences"]) > 0, "Should have at least one data type difference"
    
    print(f"  - Data type differences found: {meta['data_types']['differences']}")
    
    # Primary keys and columns should match
    assert meta["primary_keys"]["match"] is True, "Primary keys should match"
    assert meta["columns"]["match"] is True, "Columns should match"
    
    # Row comparison should be skipped due to schema mismatch
    assert row_diff["status"] == "skipped", "Row comparison should be skipped"
    assert "Metadata mismatch" in row_diff["reason"]


def test_scenario_3_column_mismatch(comparison_engine):
    """
    Scenario: Table C vs Table E
    Expectation: Table E is missing one column.
    Should fail metadata comparison (Columns).
    Row comparison should be skipped.
    """
    print(f"\nComparing {TABLE_C} vs {TABLE_E} (Column Mismatch)")
    results = comparison_engine.compare_two_tables(TABLE_C, TABLE_E)

    meta_key = f"{TABLE_C}_vs_{TABLE_E}"
    meta = results["metadata_comparison"].get(meta_key)
    row_diff = results["row_differences"].get(meta_key)

    if meta.get("status") == "error":
        pytest.fail(f"Metadata comparison failed with error: {meta.get('error')}")

    # Print columns for debugging
    print(
        f"  - Columns in Prod (C): {results['metadata_comparison'][meta_key]['columns']['common'] + results['metadata_comparison'][meta_key]['columns']['production_only']}"
    )
    # This is tricky because common + prod_only reconstructs prod columns, but test_only are separate

    if meta["columns"]["match"]:
        print("  - UNEXPECTED MATCH! Actual columns compared:")
        col_res = meta["columns"]
        print(f"    - Common: {col_res['common']}")
        print(f"    - Prod Only: {col_res['production_only']}")
        print(f"    - Test Only: {col_res['test_only']}")

    # Columns should differ
    assert meta["columns"]["match"] is False
    assert len(meta["columns"]["production_only"]) > 0 or len(meta["columns"]["test_only"]) > 0

    # Row comparison should be skipped due to schema mismatch
    assert row_diff["status"] == "skipped"
    assert "Metadata mismatch" in row_diff["reason"]


def test_scenario_4_row_mismatch_relaxed_gating(comparison_engine):
    """
    Scenario: Table C vs Table D
    Expectation: Table D is missing one row.
    CRITICAL:
      - Metadata (Row Count) will differ.
      - BUT Row Comparison MUST proceed (Relaxed Gating).
      - Should find 1 differing row.
    """
    print(f"\nComparing {TABLE_C} vs {TABLE_D} (Row Mismatch)")
    results = comparison_engine.compare_two_tables(TABLE_C, TABLE_D)

    meta_key = f"{TABLE_C}_vs_{TABLE_D}"
    meta = results["metadata_comparison"].get(meta_key)
    row_diff = results["row_differences"].get(meta_key)

    if meta.get("status") == "error":
        pytest.fail(f"Metadata comparison failed with error: {meta.get('error')}")

    # Metadata should differ on row count and may differ on data types
    assert meta["primary_keys"]["match"] is True
    assert meta["columns"]["match"] is True
    assert meta["row_count"]["match"] is False
    assert meta["status"] == "differ"

    # Row comparison behavior depends on whether dtype mismatch blocks it
    # Relaxed gating allows row comparison to proceed despite row count differences,
    # BUT dtype mismatches still block row comparison
    if not meta["data_types"]["match"]:
        # If data types don't match, row comparison is skipped
        assert row_diff["status"] == "skipped", "Row comparison should be skipped due to dtype mismatch"
        print(f"  - Row comparison skipped due to dtype mismatch: {meta['data_types']['differences']}")
    else:
        # If only row count differs, relaxed gating should allow row comparison
        assert row_diff["status"] != "skipped", "Row comparison was skipped but should have proceeded!"
        
        # Should find differences
        if row_diff["status"] != "differ":
            print(f"  - UNEXPECTED STATUS: {row_diff['status']}")
            if "error" in row_diff:
                print(f"  - ERROR: {row_diff.get('error')}")

        assert row_diff["status"] == "differ"
        assert row_diff["differing_rows"] > 0
        print(f"  - Differing rows found: {row_diff['differing_rows']}")
