from logging import getLogger

import ollama

from config import load_config

logger = getLogger(__name__)


class EmbeddingUnavailableError(Exception):
    """Ollama embedding 服務不可用時拋出。"""
    pass


class EmbeddingService:
    """
    Ollama embedding 抽象層。

    透過官方 ollama Python SDK 呼叫本機 Ollama 服務，
    支援單筆 embed() 與批次 embed_batch()。
    """

    def __init__(self):
        config = load_config()["memory"]["embedding"]
        self._host = f"http://{config['host']}:{config['port']}"
        self.model = config["model"]
        self.timeout = float(config["timeout"])
        self._client = ollama.Client(host=self._host, timeout=self.timeout)

    def embed(self, text: str) -> list[float]:
        """
        將單筆文字轉換為向量。

        Raises:
            ValueError: 輸入為空字串。
            EmbeddingUnavailableError: Ollama 服務不可用或 API 回傳錯誤。
        """
        if not text or not text.strip():
            raise ValueError("Input text must not be empty.")

        try:
            result = self._client.embed(model=self.model, input=text)
            embeddings = result["embeddings"]

            if not embeddings or not embeddings[0]:
                raise EmbeddingUnavailableError(
                    f"Ollama returned empty embedding for model '{self.model}'."
                )

            return embeddings[0]

        except EmbeddingUnavailableError:
            raise
        except ollama.ResponseError as e:
            raise EmbeddingUnavailableError(
                f"Ollama API error: {e}"
            ) from e
        except Exception as e:
            raise EmbeddingUnavailableError(
                f"Cannot reach Ollama at {self._host}: {e}"
            ) from e

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        批次將多筆文字轉換為向量。

        空列表直接回傳，不呼叫 SDK。

        Raises:
            EmbeddingUnavailableError: Ollama 服務不可用或 API 回傳錯誤。
        """
        if not texts:
            return []

        try:
            result = self._client.embed(model=self.model, input=texts)
            return result["embeddings"]

        except ollama.ResponseError as e:
            raise EmbeddingUnavailableError(
                f"Ollama API error: {e}"
            ) from e
        except Exception as e:
            raise EmbeddingUnavailableError(
                f"Cannot reach Ollama at {self._host}: {e}"
            ) from e
