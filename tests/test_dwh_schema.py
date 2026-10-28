import unittest
from src.utils.db_connector import DBConnector


class TestDWHExtendedSchema(unittest.TestCase):
    def test_extended_columns_exist(self):
        conn = DBConnector.get_raw_connection()
        try:
            with conn.cursor() as cur:
                # Check dim_location
                cur.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name = 'dim_location' AND column_name IN ('country_code', 'region', 'data_source');
                """)
                loc_cols = {r[0] for r in cur.fetchall()}
                self.assertEqual(loc_cols, {'country_code', 'region', 'data_source'})

                # Check fact_measurement
                cur.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name = 'fact_measurement' AND column_name IN ('temperature', 'humidity');
                """)
                fact_cols = {r[0] for r in cur.fetchall()}
                self.assertEqual(fact_cols, {'temperature', 'humidity'})

                # Check staging_measurement
                cur.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name = 'staging_measurement' AND column_name IN ('country_code', 'region', 'data_source', 'temperature', 'humidity');
                """)
                stg_cols = {r[0] for r in cur.fetchall()}
                self.assertEqual(stg_cols, {'country_code', 'region', 'data_source', 'temperature', 'humidity'})

                # Check fact measurements count is accessible
                cur.execute("SELECT count(*) FROM fact_measurement;")
                fact_count = cur.fetchone()[0]
                self.assertGreaterEqual(fact_count, 0, "Fact table co the truy van count.")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
