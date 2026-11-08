"""Shared test settings.

The tests never touch the real warehouse: they use their own database
(retail_test by default) and a temporary landing folder. These environment
variables must be set before retail_pipeline.config is imported, which is why
they are set here, at the very top of the test session.
"""
import os
import tempfile

os.environ["POSTGRES_DB"] = os.environ.get("TEST_POSTGRES_DB", "retail_test")
os.environ["LANDING_DIR"] = tempfile.mkdtemp(prefix="retail_landing_")
