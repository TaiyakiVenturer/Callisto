from pathlib import Path
import yaml

_CONFIG_PATH = Path(__file__).parent / "config.yaml"
_cache: dict | None = None


def load_config() -> dict:
    """載入 backend/config.yaml，回傳完整設定 dict。同一 process 內只讀一次檔案。"""
    global _cache
    if _cache is not None:
        return _cache
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"找不到設定檔：{_CONFIG_PATH}\n"
            "請複製 config.example.yaml 並重新命名為 config.yaml，再填入你的設定。"
        )
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            _cache = yaml.safe_load(f)
            return _cache
    except Exception as e:
        raise RuntimeError(f"載入設定檔失敗: {e}") from e


def reset_cache() -> None:
    """清除設定快取，供測試 teardown 使用。"""
    global _cache
    _cache = None
