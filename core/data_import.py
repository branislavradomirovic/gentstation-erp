import pandas as pd
import logging
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from core.models import Station
from core.database import get_session, sync_identity_sequences

logger = logging.getLogger("gentstation.data_import")

def process_station_import(file_stream, progress_callback=None) -> Dict[str, Any]:
    """
    Processes a CSV file and imports stations into the database using chunking.
    """
    results = {"total": 0, "success": 0, "errors": []}
    chunk_size = 500 # Process 500 rows at a time to save memory

    try:
        # 1. Peek at the file to get total row count for progress bar
        # We do this without loading the whole file into memory
        total_rows = sum(1 for _ in file_stream) - 1 # Subtract header
        file_stream.seek(0) # Reset stream for reading

        if total_rows <= 0:
            return results

        results["total"] = total_rows

        # 2. Read in chunks
        chunks = pd.read_csv(
            file_stream,
            chunksize=chunk_size,
            # Explicitly define dtypes to save RAM and avoid guessing errors
            dtype={
                "name": str,
                "physical_address": str,
                "email": str,
                "lat": float,
                "lon": float,
                "region_id": "Int64" # Support nullable integers
            }
        )

        processed_rows = 0
        with get_session() as session:
            for chunk in chunks:
                for index, row in chunk.iterrows():
                    processed_rows += 1
                    try:
                        # Minimal validation
                        if pd.isna(row['name']) or not str(row['name']).strip():
                            raise ValueError(f"Row {processed_rows}: Name is missing")

                        new_station = Station(
                            name=str(row['name']).strip(),
                            region_id=row['region_id'] if not pd.isna(row['region_id']) else None,
                            physical_address=row['physical_address'] if not pd.isna(row['physical_address']) else None,
                            email=row['email'] if not pd.isna(row['email']) else None,
                            lat=row['lat'] if not pd.isna(row['lat']) else None,
                            lon=row['lon'] if not pd.isna(row['lon']) else None,
                            category="Retail"
                        )
                        session.add(new_station)
                        results["success"] += 1
                    except Exception as e:
                        results["errors"].append(str(e))

                # Flush changes to DB after every chunk
                session.flush()
                if progress_callback:
                    progress_callback(processed_rows / total_rows)

            # commit is handled by get_session context manager

        # 3. CRITICAL: Sync identity sequences after bulk load
        sync_identity_sequences()

    except Exception as e:
        logger.error(f"Import failed: {e}")
        results["errors"].append(f"Fatal Error: {str(e)}")

    return results
