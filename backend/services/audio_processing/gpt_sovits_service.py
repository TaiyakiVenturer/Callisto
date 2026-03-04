"""
GPT-SoVITS V2 TTS Streaming Integration Module

This module provides a client for the GPT-SoVITS V2 TTS streaming API,
supporting real-time audio playback and WAV file saving with reference audio.

Features:
- Stream TTS audio generation with reference voice cloning
- Real-time playback (low latency)
- Save to WAV file with automatic header fix
- Support for multiple languages with reference audio prompts
- Optimized for GPU memory constraints (GTX 1060 6GB compatible)

Example:
    >>> from backend.tts_stream_v2 import play_tts, save_tts
    >>> 
    >>> # Play TTS immediately with voice cloning
    >>> play_tts("Hello World", 
    ...          voice="path/to/reference.wav",
    ...          prompt_text="This is the reference text",
    ...          language="en")
    >>> 
    >>> # Save TTS to file
    >>> save_tts("你好世界", 
    ...          save_path="hello.wav",
    ...          voice="path/to/reference.wav", 
    ...          prompt_text="參考文本內容",
    ...          language="zh")
"""

import struct
from typing import Optional, Generator

import numpy as np
import pyaudio
import requests

from config import load_config

class GPTSoVITSV2Client:
    """
    Client for GPT-SoVITS V2 TTS Streaming API.
    
    This client handles communication with the GPT-SoVITS V2 TTS server,
    providing methods for streaming audio generation with voice cloning,
    playback, and saving.
    
    Args:
        base_url: Base URL of the GPT-SoVITS server (default: http://127.0.0.1:9880)
        sample_rate: Audio sample rate in Hz (default: 32000 for V2)
    
    Attributes:
        base_url: The base URL of the TTS server
        tts_endpoint: The API endpoint for TTS generation
        sample_rate: Audio sampling rate
    """
    
    def __init__(self):
        """
        Initialize the GPT-SoVITS V2 TTS client.
        Reads base_url, sample_rate and all TTS params from config.yaml [tts] block.
        """
        self.config = load_config()["tts"]
        self.base_url = f"http://{self.config['host']}:{self.config['port']}"
        self.tts_endpoint = "/tts"
        self.sample_rate = self.config["sample_rate"]
    
    def generate_stream(
        self,
        text: str,
        language: str = "zh",
    ) -> requests.Response:
        """
        Generate TTS audio stream from text with reference voice.
        
        This method sends a request to the GPT-SoVITS V2 API and returns a
        streaming response object with PCM audio data. The response can be 
        used for playback or saving to a file.
        
        Args:
            text: Text to convert to speech
            voice: Path to reference audio file for voice cloning
            prompt_text: Text content of the reference audio
            language: Target language code (e.g., "zh", "en", "ja")
            prompt_lang: Language of the prompt text (default: "zh")
            streaming_mode: Streaming quality mode (0=low, 1=medium, 2=high, default: 2)
            batch_size: Batch size for inference (default: 1 for memory efficiency)
        
        Returns:
            requests.Response object with streaming PCM audio data
        
        Raises:
            ValueError: If text or required parameters are empty
            requests.exceptions.RequestException: If network error occurs
            requests.exceptions.HTTPError: If API returns error status
        
        Example:
            >>> client = GPTSoVITSV2Client()
            >>> response = client.generate_stream(
            ...     text="Hello World",
            ...     voice="voices/ref.wav",
            ...     prompt_text="Reference text here"
            ... )
            >>> client.play_stream(response)
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")
        
        if not self.config["voice"]:
            raise ValueError("Voice (reference audio path) cannot be empty")
        
        if not self.config["prompt_text"] or not self.config["prompt_text"].strip():
            raise ValueError("Prompt text cannot be empty")
        
        # Build the request payload for V2 API
        payload = {
            "text": text,
            "text_lang": language,
            "ref_audio_path": self.config["voice"],
            "prompt_text": self.config["prompt_text"],
            "prompt_lang": self.config["prompt_lang"],
            "media_type": "raw",  # PCM format for streaming
            "streaming_mode": self.config["streaming_mode"],
            "batch_size": self.config["batch_size"],
            "parallel_infer": True
        }
        
        url = f"{self.base_url}{self.tts_endpoint}"
        
        try:
            # Send POST request with streaming enabled
            response = requests.post(url, json=payload, stream=True, timeout=60)
            response.raise_for_status()
            return response
        
        except requests.exceptions.Timeout:
            raise requests.exceptions.RequestException(
                "Request timed out. Please check if the GPT-SoVITS server is running."
            )
        except requests.exceptions.ConnectionError:
            raise requests.exceptions.RequestException(
                f"Failed to connect to GPT-SoVITS server at {self.base_url}. "
                "Please ensure the server is running."
            )
        except requests.exceptions.HTTPError as e:
            error_msg = f"GPT-SoVITS API returned error: {e.response.status_code}"
            try:
                error_detail = e.response.json()
                error_msg += f" - {error_detail}"
            except:
                error_msg += f" - {e.response.text}"
            raise requests.exceptions.HTTPError(error_msg)
    
    def get_stream_generator(self, response: requests.Response, volume: float = 1.0) -> Generator:
        """
        Get audio stream generator with volume control.
        
        This method returns a generator that yields audio chunks from the
        streaming response, with optional volume adjustment applied.
        
        Args:
            response: Response object from generate_stream()
            volume: Volume multiplier (0.0 to 2.0, default: 1.0)
        
        Yields:
            bytes: Audio data chunks (PCM format)
        
        Raises:
            ValueError: If volume is not in valid range
            OSError: If audio processing error occurs
        
        Example:
            >>> client = GPTSoVITSV2Client()
            >>> response = client.generate_stream(...)
            >>> for chunk in client.get_stream_generator(response, volume=0.8):
            ...     # Process audio chunk
            ...     pass
        """
        # Validate volume parameter
        if not (0.0 <= volume <= 2.0):
            raise ValueError(f"Volume must be between 0.0 and 2.0, got {volume}")
        
        def get_chunks() -> Generator:
            try:
                # V2 API returns raw PCM data without WAV header
                for chunk in response.iter_content(chunk_size=1024):
                    # Early return: skip empty chunks
                    if not chunk:
                        continue
                    
                    audio_chunk = chunk
                    
                    # Apply volume control if needed
                    if volume != 1.0:
                        # Convert bytes to numpy array (16-bit PCM)
                        audio_data = np.frombuffer(audio_chunk, dtype=np.int16)
                        # Apply volume multiplier
                        audio_data = (audio_data * volume).astype(np.int16)
                        # Clip to prevent overflow
                        audio_data = np.clip(audio_data, -32768, 32767)
                        # Convert back to bytes
                        audio_chunk = audio_data.tobytes()
                    
                    # Early return: skip if no audio data
                    if not audio_chunk:
                        continue
                    
                    yield audio_chunk
            
            except OSError as e:
                raise OSError(f"Audio processing error: {e}. Please check your audio settings.")
        
        return get_chunks()
    
    def play_stream(self, response: requests.Response, volume: float = 1.0) -> None:
        """
        Play streaming audio in real-time.
        
        This method plays audio as it's being received from the server,
        providing low-latency playback. Since V2 API returns raw PCM data,
        no header skipping is needed.
        
        Args:
            response: Response object from generate_stream()
            volume: Volume multiplier (0.0 to 2.0). 0.0=mute, 1.0=original, 2.0=double (default: 1.0)
        
        Raises:
            OSError: If audio device is not available
            ValueError: If volume is not in valid range (0.0 to 2.0)
        
        Note:
            The response object can only be used once. If you need to
            both play and save, make two separate requests.
        
        Example:
            >>> client = GPTSoVITSV2Client()
            >>> response = client.generate_stream(...)
            >>> client.play_stream(response, volume=0.5)  # Half volume
        """
        # Validate volume parameter
        if not (0.0 <= volume <= 2.0):
            raise ValueError(f"Volume must be between 0.0 and 2.0, got {volume}")
        
        p = None
        stream = None
        
        try:
            # Initialize PyAudio
            p = pyaudio.PyAudio()

            # Open audio stream with PCM format parameters
            # Format: 16-bit PCM, mono, sample rate from client config
            stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                output=True,
            )
            
            generator = self.get_stream_generator(response, volume)
            for audio_chunk in generator:
                stream.write(audio_chunk)
        
        except Exception as e:
            raise RuntimeError(f"Error processing audio stream: {e}")
        
        finally:
            # Clean up audio resources
            if stream is not None:
                stream.stop_stream()
                stream.close()
            if p is not None:
                p.terminate()
    
    def save_to_file(self, response: requests.Response, file_path: str) -> None:
        """
        Save streaming audio to a WAV file with automatic header generation.
        
        This method saves the raw PCM audio stream to a file and automatically
        generates a proper WAV header for playback compatibility.
        
        Args:
            response: Response object from generate_stream()
            file_path: Path where to save the WAV file
        
        Raises:
            IOError: If file cannot be written
        
        Note:
            The response object can only be used once. If you need to
            both play and save, make two separate requests.
        
        Example:
            >>> client = GPTSoVITSV2Client()
            >>> response = client.generate_stream(...)
            >>> client.save_to_file(response, "output.wav")
        """
        try:
            # Collect all PCM data first
            pcm_data = bytearray()
            
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    pcm_data.extend(chunk)
            
            # Generate and write WAV file with proper header
            self._write_wav_file(file_path, pcm_data)
        
        except IOError as e:
            raise IOError(f"Failed to write file {file_path}: {e}")
    
    def _write_wav_file(self, file_path: str, pcm_data: bytes) -> None:
        """
        Write PCM data to WAV file with proper header.
        
        This method creates a complete WAV file from raw PCM data by
        generating the appropriate RIFF/WAV header structure.
        
        Args:
            file_path: Path to the output WAV file
            pcm_data: Raw PCM audio data (16-bit, mono)
        
        Note:
            This is a private method automatically called by save_to_file().
            You should not need to call this directly.
        """
        try:
            with open(file_path, 'wb') as f:
                # WAV file parameters
                num_channels = 1
                sample_width = 2  # 16-bit = 2 bytes
                sample_rate = self.sample_rate
                num_frames = len(pcm_data) // sample_width
                
                # Calculate chunk sizes
                data_size = len(pcm_data)
                riff_size = 36 + data_size  # 36 = header size without RIFF chunk
                
                # Write RIFF header
                f.write(b'RIFF')
                f.write(struct.pack('<I', riff_size))
                f.write(b'WAVE')
                
                # Write fmt subchunk
                f.write(b'fmt ')
                f.write(struct.pack('<I', 16))  # Subchunk1Size (16 for PCM)
                f.write(struct.pack('<H', 1))   # AudioFormat (1 = PCM)
                f.write(struct.pack('<H', num_channels))
                f.write(struct.pack('<I', sample_rate))
                byte_rate = sample_rate * num_channels * sample_width
                f.write(struct.pack('<I', byte_rate))
                block_align = num_channels * sample_width
                f.write(struct.pack('<H', block_align))
                bits_per_sample = sample_width * 8
                f.write(struct.pack('<H', bits_per_sample))
                
                # Write data subchunk
                f.write(b'data')
                f.write(struct.pack('<I', data_size))
                f.write(pcm_data)
        
        except Exception as e:
            raise IOError(f"Failed to write WAV file: {e}")
    
    def _fix_wav_header(self, file_path: str) -> None:
        """
        Fix incomplete WAV header (compatibility method).
        
        This method is kept for API compatibility with the original module,
        but is not needed for V2 since we generate proper headers directly.
        
        Args:
            file_path: Path to the WAV file
        
        Note:
            This is a compatibility shim. V2 client generates correct
            headers from the start via _write_wav_file().
        """
        # No-op: V2 generates correct headers from the start
        pass


def play_tts(
    text: str,
    voice: str,
    prompt_text: str,
    language: str = "zh",
    prompt_lang: str = "zh",
    volume: float = 1.0,
    base_url: str = "http://127.0.0.1:9880",
    sample_rate: int = 32000,
    streaming_mode: int = 2,
    batch_size: int = 1
) -> bool:
    """
    Play TTS audio immediately with voice cloning (convenience function).
    
    This function generates and plays TTS audio with reference voice in one call.
    Audio is streamed and played in real-time for low latency.
    
    Args:
        text: Text to convert to speech
        voice: Path to reference audio file for voice cloning
        prompt_text: Text content of the reference audio
        language: Target language code (default: "zh")
        prompt_lang: Language of the prompt text (default: "zh")
        volume: Volume multiplier (0.0 to 2.0, default: 1.0)
        base_url: GPT-SoVITS server URL (default: "http://127.0.0.1:9880")
        sample_rate: Audio sample rate (default: 32000 for V2)
        streaming_mode: Streaming quality (0-2, default: 2)
        batch_size: Inference batch size (default: 1 for GTX 1060)
    
    Returns:
        True if successful, False otherwise
    
    Example:
        >>> play_tts(
        ...     text="Hello World",
        ...     voice="voices/female.wav",
        ...     prompt_text="This is a reference",
        ...     language="en"
        ... )
        True
        >>> play_tts(
        ...     text="你好世界",
        ...     voice="voices/chinese.wav",
        ...     prompt_text="這是參考文本",
        ...     language="zh",
        ...     volume=0.5
        ... )
        True
    """
    try:
        client = GPTSoVITSV2Client(base_url, sample_rate)
        response = client.generate_stream(
            text=text,
            voice=voice,
            prompt_text=prompt_text,
            language=language,
            prompt_lang=prompt_lang,
            streaming_mode=streaming_mode,
            batch_size=batch_size
        )
        client.play_stream(response, volume=volume)
        return True
    except Exception as e:
        print(f"Error playing TTS: {e}")
        return False


def save_tts(
    text: str,
    save_path: str,
    voice: str,
    prompt_text: str,
    language: str = "zh",
    prompt_lang: str = "zh",
    base_url: str = "http://127.0.0.1:9880",
    sample_rate: int = 32000,
    streaming_mode: int = 2,
    batch_size: int = 1
) -> Optional[str]:
    """
    Generate TTS and save to WAV file with voice cloning (convenience function).
    
    This function generates TTS audio with reference voice and saves it to a file.
    The WAV header is automatically generated for proper playback.
    
    Args:
        text: Text to convert to speech
        save_path: Path where to save the WAV file
        voice: Path to reference audio file for voice cloning
        prompt_text: Text content of the reference audio
        language: Target language code (default: "zh")
        prompt_lang: Language of the prompt text (default: "zh")
        base_url: GPT-SoVITS server URL (default: "http://127.0.0.1:9880")
        sample_rate: Audio sample rate (default: 32000 for V2)
        streaming_mode: Streaming quality (0-2, default: 2)
        batch_size: Inference batch size (default: 1 for GTX 1060)
    
    Returns:
        File path if successful, None otherwise
    
    Example:
        >>> save_tts(
        ...     text="Hello World",
        ...     save_path="hello.wav",
        ...     voice="voices/female.wav",
        ...     prompt_text="Reference text"
        ... )
        'hello.wav'
        >>> save_tts(
        ...     text="你好",
        ...     save_path="nihao.wav",
        ...     voice="voices/chinese.wav",
        ...     prompt_text="參考內容",
        ...     language="zh"
        ... )
        'nihao.wav'
    """
    try:
        client = GPTSoVITSV2Client(base_url, sample_rate)
        response = client.generate_stream(
            text=text,
            voice=voice,
            prompt_text=prompt_text,
            language=language,
            prompt_lang=prompt_lang,
            streaming_mode=streaming_mode,
            batch_size=batch_size
        )
        client.save_to_file(response, save_path)
        return save_path
    except Exception as e:
        print(f"Error saving TTS: {e}")
        return None
