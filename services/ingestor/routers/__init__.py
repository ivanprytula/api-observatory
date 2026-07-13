"""Route modules for each resource.

Modules are imported on demand by ``services.ingestor.main`` rather
than eagerly at package-import time, so that optional third-party
dependencies (openai, pandas, …) don't block unit-test bootstrapping.
"""
