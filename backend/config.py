from pathlib import Path
import yaml

_CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config() -> dict:
    """載入 backend/config.yaml，回傳完整設定 dict。"""
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"找不到設定檔：{_CONFIG_PATH}\n"
            "請複製 config.example.yaml 並重新命名為 config.yaml，再填入你的設定。"
        )
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        raise RuntimeError(f"載入設定檔失敗: {e}") from e
