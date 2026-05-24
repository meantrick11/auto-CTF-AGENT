# Filter module — Data Washer
# Hook: after_execute
# See README.md for full documentation.

from filter.cleaner import filter_worker_output  # noqa: F401 — registers hook
