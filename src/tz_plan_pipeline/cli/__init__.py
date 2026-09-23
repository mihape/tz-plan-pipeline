"""Command-line interface module for TZ Plan Pipeline."""

# Avoid importing main directly at top-level to prevent runpy RuntimeWarning
# when running python -m tz_plan_pipeline.cli.main

def get_app():
    from tz_plan_pipeline.cli.main import app
    return app
