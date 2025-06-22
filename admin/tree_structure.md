# Project Structure
Last updated: 2025-06-22 14:29:37

```
Alpha_V1/
│   ├── .env
│   ├── README.md # Project documentation
│   ├── git_commit_push.py
│   ├── git_latest_pull_replace.py
│   ├── start_server.bat
│   ├── admin/
│   │   ├── tree_structure.md
│   │   ├── update_tree.py
│   ├── electron/
│   │   ├── README.md # Project documentation
│   │   ├── create-symlink.bat
│   │   ├── main.js
│   │   ├── package-lock.json
│   │   ├── package.json
│   │   ├── preload.js
│   │   ├── test-window-config.js
│   │   ├── config/
│   │   │   ├── app.config.js
│   │   │   ├── shortcuts.config.js
│   │   │   ├── window.config.js
│   │   ├── src/
│   │   │   ├── main/
│   │   │   │   ├── AppUpdater.js
│   │   │   │   ├── IPCHandler.js
│   │   │   │   ├── MenuBuilder.js
│   │   │   │   ├── StateManager.js
│   │   │   │   ├── WindowManager.js
│   │   │   ├── renderer/
│   │   │   │   ├── bridge.js
│   │   │   │   ├── index.html
│   │   │   │   ├── index.js
│   ├── perspective/
│   ├── polygon/
│   │   ├── README.md # Project documentation
│   │   ├── __init__.py
│   │   ├── api_validator.py
│   │   ├── config.py # Configuration settings
│   │   ├── core.py
│   │   ├── exceptions.py
│   │   ├── fetcher.py
│   │   ├── rate_limiter.py
│   │   ├── storage.py
│   │   ├── utils.py
│   │   ├── websocket.py
│   │   ├── data/
│   │   │   ├── rate_limit_stats.json
│   │   │   ├── cache/
│   │   │   │   ├── polygon_cache.db
│   │   │   ├── logs/
│   │   │   │   ├── polygon.log
│   │   │   ├── parquet/
│   │   │   │   ├── symbols/
│   │   │   │   │   ├── AAPL/
│   │   │   │   │   │   ├── AAPL_15min.parquet
│   │   │   │   │   │   ├── AAPL_1day.parquet
│   │   │   │   │   │   ├── AAPL_1hour.parquet
│   │   │   │   │   │   ├── AAPL_1min.parquet
│   │   │   │   │   │   ├── AAPL_5min.parquet
│   │   │   │   │   ├── AMD/
│   │   │   │   │   │   ├── AMD_15min.parquet
│   │   │   │   │   │   ├── AMD_1day.parquet
│   │   │   │   │   │   ├── AMD_1hour.parquet
│   │   │   │   │   │   ├── AMD_1min.parquet
│   │   │   │   │   ├── AMZN/
│   │   │   │   │   │   ├── AMZN_1day.parquet
│   │   │   │   │   │   ├── AMZN_1min.parquet
│   │   │   │   │   ├── GOOG/
│   │   │   │   │   │   ├── GOOG_15min.parquet
│   │   │   │   │   │   ├── GOOG_1day.parquet
│   │   │   │   │   │   ├── GOOG_1min.parquet
│   │   │   │   │   ├── GOOGL/
│   │   │   │   │   │   ├── GOOGL_1day.parquet
│   │   │   │   │   ├── MSFT/
│   │   │   │   │   │   ├── MSFT_1day.parquet
│   │   │   │   │   │   ├── MSFT_1min.parquet
│   │   │   │   │   ├── NVDA/
│   │   │   │   │   │   ├── NVDA_15min.parquet
│   │   │   │   │   │   ├── NVDA_1day.parquet
│   │   │   │   │   │   ├── NVDA_1hour.parquet
│   │   │   │   │   │   ├── NVDA_1min.parquet
│   │   │   │   │   ├── OKLO/
│   │   │   │   │   │   ├── OKLO_15min.parquet
│   │   │   │   │   │   ├── OKLO_1day.parquet
│   │   │   │   │   │   ├── OKLO_1hour.parquet
│   │   │   │   │   │   ├── OKLO_1min.parquet
│   │   │   │   │   ├── PLTR/
│   │   │   │   │   │   ├── PLTR_15min.parquet
│   │   │   │   │   │   ├── PLTR_1day.parquet
│   │   │   │   │   │   ├── PLTR_1hour.parquet
│   │   │   │   │   │   ├── PLTR_1min.parquet
│   │   │   │   │   ├── SPY/
│   │   │   │   │   │   ├── SPY_5min.parquet
│   │   │   │   │   ├── TSLA/
│   │   │   │   │   │   ├── TSLA_15min.parquet
│   │   │   │   │   │   ├── TSLA_1day.parquet
│   │   │   │   │   │   ├── TSLA_1hour.parquet
│   │   │   │   │   │   ├── TSLA_1min.parquet
│   │   ├── docs/
│   │   │   ├── config_overview.txt
│   │   │   ├── core_overview.txt
│   │   │   ├── exceptions_overview.txt
│   │   │   ├── fetcher_overview.txt
│   │   │   ├── polygon_components_breakdown.txt
│   │   │   ├── polygon_pre_synopsis.txt
│   │   │   ├── polygon_structure.txt
│   │   │   ├── rate_limiter.txt
│   │   │   ├── storage_overview.txt
│   │   │   ├── utils_overview.txt
│   │   │   ├── validators_overview.txt
│   │   │   ├── websocket.txt
│   │   │   ├── websocket_client.txt
│   │   ├── polygon_server/
│   │   │   ├── __init__.py
│   │   │   ├── config.py # Configuration settings
│   │   │   ├── models.py
│   │   │   ├── requirements.txt # Python dependencies
│   │   │   ├── server.py
│   │   │   ├── start_server.py
│   │   │   ├── endpoints/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── health.py
│   │   │   │   ├── rest.py
│   │   │   │   ├── websocket.py
│   │   │   ├── utils/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── json_encoder.py
│   │   ├── tests/
│   │   │   ├── test_monitor_websocket.py
│   │   │   ├── test_websocket_live.py
│   │   ├── validators/
│   │   │   ├── __init__.py
│   │   │   ├── anomalies.py
│   │   │   ├── api_features.py
│   │   │   ├── data_quality.py
│   │   │   ├── gaps.py
│   │   │   ├── market_hours.py
│   │   │   ├── ohlcv.py
│   │   │   ├── symbol.py
```
