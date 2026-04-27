"""
Configuration Limits

Centralized numeric constants for tunable operational parameters.
"""


class Workers:
    DEFAULT = 2
    MIN = 1
    MAX = 8


class BatchSize:
    DEFAULT = 100
    MIN = 1
    MAX = 500


class QueryTimeout:
    QUERY_TASK = 600  # seconds


class HttpTimeout:
    CONNECT = 10   # seconds
    READ = 60      # seconds


class Retry:
    # Exponential backoff — used by sf_error_handler.py
    # loop: range(max_retries + 1) → MAX_RETRIES_API=3 means 4 total attempts
    MAX_RETRIES_API = 3
    BASE_DELAY = 1.0
    MAX_DELAY = 60.0
    BACKOFF_FACTOR = 2.0
    # Linear two-step delay — used by thread_pool.py
    # loop: range(1, max_retries + 1) → MAX_RETRIES_THREAD=3 means 3 total attempts
    MAX_RETRIES_THREAD = 3
    DELAY_FIRST = 2
    DELAY_SUBSEQUENT = 5


class Progress:
    MIN_UPDATE_INTERVAL = 0.1
    RICH_REFRESH_RATE = 4          # Hz
    DEBOUNCE_INTERVAL = 0.05
    ENABLE_DEBOUNCING = True       # maps to ProgressConfig.enable_update_debouncing
    CALLBACK_COPY_TIMEOUT = 1.0
    SELECTION_CACHE_TTL = 30.0    # maps to RendererRegistry._selection_cache_ttl
    RENDERER_SELECTION_TIMEOUT = 5.0


class Buffers:
    MAX_BUFFERED_LOG_MESSAGES = 50
    MAX_RESPONSE_HISTORY = 1000


class ApiMonitoring:
    # Numerically equal to LOG_MILESTONE_CALLS — kept separate (different semantics)
    NEAR_LIMIT_CALLS = 100
    LOG_MILESTONE_CALLS = 100

    # Error rate thresholds — three distinct call sites, see usage_monitor.py
    ALERT_ERROR_RATE = 0.1       # track_call: real-time warning if error_rate > 0.1
    HIGH_ERROR_RATE = 0.05       # _generate_insights: label "High error rate" if > 0.05
    MODERATE_ERROR_RATE = 0.01   # _generate_insights: label "Moderate error rate" if > 0.01

    MIN_CALLS_FOR_ANALYSIS = 10
    SLOW_RESPONSE_THRESHOLD = 5.0
    MODERATE_RESPONSE_THRESHOLD = 1.0
    RECOMMENDATION_RESPONSE_THRESHOLD = 2.0  # health_checker diagnostics
    HEAVY_USAGE_RATIO = 0.8


class FileSystem:
    MAX_FILENAME_LENGTH = 255    # character limit used in sanitize_filename
    DEFAULT_PARENT_ID = 'NO_PARENT'  # domain sentinel (no ParentId), not a filesystem limit
    TMP_DIR_NAME = '.tmp_downloads'
    DOWNLOAD_CHUNK_SIZE = 8192  # bytes


class ConnectionPool:
    MIN_POOL_SIZE = 10  # mirrors requests.Session default pool_maxsize
    TIMEOUT = 30


