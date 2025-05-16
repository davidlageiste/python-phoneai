import uuid
import random
from typing import IO
from io import BytesIO
from typing import Union

from utils.azure_storage import upload_stream_azure, delete_blob_azure_delay
from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs
from azure.communication.callautomation import (
    TextSource,
    FileSource,
)
from utils.recorded_audio import audios

ELEVENLABS_API_KEY = "sk_3a505305430d3ca4d01e4391b85a87e5c8c4eb5a58ed6403"
clientElevenLabs = ElevenLabs(
    api_key=ELEVENLABS_API_KEY,
)

STORAGE_URL_PATH = "https://talkstoragetest.blob.core.windows.net/audio-files/"


def text_to_speech_stream(text: str, language="fr") -> IO[bytes]:
    voices = {
        "fr": "4BHBnkrJUkJYV4HMAnNd",
    }

    response = clientElevenLabs.text_to_speech.convert(
        voice_id=voices[language],
        output_format="mp3_22050_32",
        text=text,
        model_id="eleven_turbo_v2_5",
        voice_settings=VoiceSettings(
            stability=0.60,
            similarity_boost=1,
            style=0.0,
            use_speaker_boost=True,
            speed=1.0,
        ),
    )

    audio_stream = BytesIO()
    for chunk in response:
        if chunk:
            audio_stream.write(chunk)
    audio_stream.seek(0)
    return audio_stream


def text_to_speech(
    process: str,
    text: str,
    language="fr",
) -> Union[FileSource | TextSource]:
    """
    Returns an audio source (FileSource ou TextSource) for Azure Communication Service based on a text
    Different process types:
        - "fixed_file_source":  returns a pre-generated frequently used audio FileSource
        - "file_source":        returms a generated and temporarly uploaded audio FileSource
        - "text_source":        returns a TextSource for CallAutomation TTS use
    """
    print("TTS", process, text)
    match process:
        case "fixed_file_source":
            if isinstance(audios[text][language], list):
                return FileSource(
                    url=f"{STORAGE_URL_PATH}{text}-{language}-{random.randint(0, len(audios[text][language]) - 1)}.mp3"
                )
            return FileSource(url=f"{STORAGE_URL_PATH}{text}-{language}.mp3")

        case "file_source":
            file_name = f"tmp-{uuid.uuid4()}.mp3"
            audio_stream = text_to_speech_stream(text)
            upload_stream_azure(audio_stream, file_name)
            delete_blob_azure_delay(file_name)
            return FileSource(url=f"{STORAGE_URL_PATH}{file_name}")

        case "text_source":
            return TextSource(
                text=text,
                source_locale="fr-FR",
                voice_name="fr-FR-VivienneMultilingualNeural",
            )


def generate_text_to_speech(item=None, language="fr") -> bool:
    """
    Generates and uploads an or all audio file for a language
    """
    try:
        if item is not None:
            if isinstance(audios[item][language], list):
                for i, text in enumerate(audios[item][language]):
                    audio_stream = text_to_speech_stream(text, language)
                    upload_stream_azure(audio_stream, f"{item}-{language}-{i}.mp3")
            else:
                audio_stream = text_to_speech_stream(audios[item][language], language)
                upload_stream_azure(audio_stream, f"{item}-{language}.mp3")
        else:
            for file_name, pack in audios.items():
                texts = pack[language]
                if isinstance(texts, list):
                    for i, text in enumerate(texts):
                        audio_stream = text_to_speech_stream(text, language)
                        upload_stream_azure(
                            audio_stream, f"{file_name}-{language}-{i}.mp3"
                        )
                else:
                    audio_stream = text_to_speech_stream(texts, language)
                    upload_stream_azure(audio_stream, f"{file_name}-{language}.mp3")
        return True
    except:
        return False