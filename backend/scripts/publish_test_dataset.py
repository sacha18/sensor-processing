#!/usr/bin/env python3
"""
Script to publish a test dataset to the metadata database
"""
import sys
import duckdb
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.api.services import metadata

def publish_tms_dataset(csv_path: str):
    """Publish a TMS production CSV as a test dataset"""

    # Read the CSV to get metadata
    conn = duckdb.connect()
    df = conn.execute(f"SELECT * FROM read_csv_auto('{csv_path}')").df()

    # Get basic stats
    sensor_ids = df['sensor_id'].unique().tolist()
    row_count = len(df)

    # Ensure timestamp column is datetime
    import pandas as pd
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    # Mock config (since this is already processed data)
    config = {
        "pipeline_type": "tms",
        "source": "test_import",
        "processing_date": "2026-08-26",
        "steps_applied": [
            "load",
            "initial_qc",
            "calibration",
            "production",
            "final_qc"
        ]
    }

    # Publish the dataset
    dataset_id = metadata.save_published_dataset(
        title="TMS Agroforestry Test Dataset",
        description=f"Test dataset with sensor {sensor_ids[0]} - imported for UI testing",
        pipeline_type="tms",
        created_by="test_user",
        config=config,
        output_df=df,
        tags=["test", "tms", "agroforestry"],
        raw_data_source="data_94951005_2024_10_18_0.csv"
    )

    print(f"✅ Published dataset: {dataset_id}")
    print(f"   Sensors: {len(sensor_ids)}")
    print(f"   Rows: {row_count:,}")

    return dataset_id

if __name__ == "__main__":
    csv_path = "/app/backend/scripts/tms_production.csv"
    publish_tms_dataset(csv_path)
