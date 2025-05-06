import uuid
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

ELEVENLABS_API_KEY = "sk_3a505305430d3ca4d01e4391b85a87e5c8c4eb5a58ed6403"
clientElevenLabs = ElevenLabs(
    api_key=ELEVENLABS_API_KEY,
)

STORAGE_URL_PATH = "https://talkstoragetest.blob.core.windows.net/audio-files/"


def text_to_speech_file(text: str) -> str:
    try:
        # Calling the text_to_speech conversion API with detailed parameters
        print("text_to_speech_file")
        response = clientElevenLabs.text_to_speech.convert(
            voice_id="McVZB9hVxVSk3Equu8EH",  # Adam pre-made voice
            output_format="mp3_22050_32",
            text=text,
            model_id="eleven_turbo_v2_5",  # use the turbo model for low latency
            # model_id="eleven_multilingual_v2",
            # Optional voice settings that allow you to customize the output
            voice_settings=VoiceSettings(
                stability=0.60,
                similarity_boost=1,
                style=0.0,
                use_speaker_boost=True,
                speed=1.0,
            ),
        )
        print("text_to_speech_file2")
        # uncomment the line below to play the audio back
        # play(response)
        # Generating a unique file name for the output MP3 file
        save_file_path = f"{uuid.uuid4()}.mp3"
        # Writing the audio to a file
        with open(save_file_path, "wb") as f:
            for chunk in response:
                if chunk:
                    f.write(chunk)
        print("text_to_speech_file3")

        print(f"{save_file_path}: A new audio file was saved successfully!")
        # Return the path of the saved audio file
        return save_file_path
    except:
        print("ERROR")
        return ""


def text_to_speech_stream(text: str, voice_id="4BHBnkrJUkJYV4HMAnNd") -> IO[bytes]:
    # Perform the text-to-speech conversion
    response = clientElevenLabs.text_to_speech.convert(
        voice_id=voice_id,
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

    # Create a BytesIO object to hold the audio data in memory
    audio_stream = BytesIO()

    # Write each chunk of audio data to the stream
    for chunk in response:
        if chunk:
            audio_stream.write(chunk)

    # Reset stream position to the beginning
    audio_stream.seek(0)

    # Return the stream for further use
    return audio_stream


def text_to_speech(
    process: str,
    text: str,
    source_locale="fr-FR",
    voice="fr-FR-VivienneMultilingualNeural",
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
            return FileSource(url=f"{STORAGE_URL_PATH}{text}.mp3")

        case "file_source":
            file_name = f"{uuid.uuid4()}.mp3"
            audio_stream = text_to_speech_stream(text)
            upload_stream_azure(audio_stream, file_name)
            delete_blob_azure_delay(file_name)
            return FileSource(url=f"{STORAGE_URL_PATH}{file_name}")

        case "text_source":
            return TextSource(
                text=text,
                source_locale=source_locale,
                voice_name=voice,
            )


def generate_text_to_speech() -> bool:
    """
    Generates and uploads an audio file for frequent use
    """
    try:
        for file_name, text in batch_tts.items():
            audio_stream = text_to_speech_stream(text)
            upload_stream_azure(audio_stream, f"{file_name}.mp3")
        return True
    except:
        return False


batch_tts = {
    "intro": "Bonjour! Je suis Lyrae, l'assistante vocale du centre de radiologie. Je suis un agent conversationnel automatisé. Comment puis-je vous aider aujourd’hui ?",
    "repeat_firstname": "Je n'ai pas compris, pouvez-vous répéter votre prénom ?",
    "repeat_lastname": "Je n'ai pas compris, pouvez-vous épeler votre nom de famille à nouveau ?",
    "repeat_birthdate": "Je n'ai pas compris, quelle est votre date de naissance ?",
    "repeat_birthdate2": "Désolé, pouvez-vous me répéter votre date de naissance ?",
    "repeat_exam_type": "Pardonnez moi, pouvez-vous me répéter l'intitulé de l'examen que vous souhaitez passer ? ",
    "repeat_exam_type2": "Je ne vous ai pas entendu. Pouvez-vous répeter l'intitulé de l'examen ?",
    "repeat_exam_type3": "Désolé, je n'ai pas compris. Pouvez-vous répéter l'intitulé de l'examen pour lequel vous souhaitez prendre rendez-vous ?",
    "spell_lastname": "Pouvez-vous m'épeler votre nom de famille ?",
    "spell_lastname2": "Désolé, pouvez-vous m'épeler votre nom de famille ?",
    "ask_firstname": "Et quel est votre prénom ?",
    "ask_exam_type": "Quel examen voulez vous passer ?",
    "ask_prescription": "Avez-vous une ordonnance ?",
    "ask_birthdate": "Pour vous identifier, pouvez-vous me donner votre date de naissance ?",
    "ask_birthdate2": "Très bien. Pouvez-vous me donner votre date de naissance ?",
    "misunderstand_intent": "Il semblerait que je n'ai pas compris votre demande, souhaitez-vous prendre un rendez-vous, modifier un rendez-vous, consulter un rendez-vous planifié, annuler un rendez-vous ou obtenir une information ?",
    "misunderstand_intent2": "Désolé, je n'ai pas compris, qui puis-je faire pour vous ?",
    "misunderstand_exam_type": "Je ne vous ai pas compris, pour quel type d'examen voulez-vous prendre rendez-vous ? ",
    "misunderstand_excuse2": "Désolé, je n'ai pas compris, que puis-je faire pour vous ?",
    "misunderstand_appointment": "Désolé, je n'ai pas compris, voulez-vous prendre, modifier ou annuler un rendez-vous ?",
    "misunderstand_prescription": "Désolé, je n'ai pas compris, Avez-vous une ordonnance ?",
    "misunderstand": "Il semblerait que nous n'arrivons pas à nous comprendre. Je vous transfère vers une secrétaire.",
    "misunderstand_unfortunately": "Malheureusement, il semblerait que nous n'arrivons pas à nous comprendre. Je vais vous rediriger vers une secrétaire afin de pouvoir accéder a vos requêtes.",
    "misunderstand_excuse": "Pardonnez moi, il semblerait que je n'arrive pas à vous comprendre. Je vous transfère vers une secrétaire.",
    "hang_up_emergency": "Il semblerait que vous appeliez pour une urgence. Je vous transfère vers une secrétaire.",
    "hang_up_prescription": "Désolé nous pouvons pas vous planifier un rendez-vous sans ordonnance prescrite de votre médecin. Pour passer un examen d'imagerie, il faut avoir la prescription d'un médecin. Sans ordonnance, ce n'est pas possible. Pour avoir une ordonnance, je vous conseille de consulter un médecin. Je vous souhaite une excellente journée et à bientôt.",
    "hang_up_appointment_error": "Désolé, je n'ai pas pu valider votre rendez-vous. Je vais vous rediriger vers une secrétaire.",
    "hang_up_not_known": "Désolé, je ne peux pas donner de rendez-vous à un patient qui n'est pas déjà connu du cabinet. Vous êtes un nouveau patient : Je vous propose de vous transférer à la secrétaire",
    "wait_booking": "D'accord, patientez pendant que je vous réserve ce créneau.",
    "question": "Bien sûr, posez-moi votre question",
    "more": "Puis-je faire autre chose pour vous ?",
    "ok": "Très bien",
    "ok2": "D'accord",
    "thanks": "Merci",
    "wait": "Merci, un instant s'il vous plaît",
    "wait2": "Très bien, laissez-moi un instant",
    "wait_patient": "Merci, je vous cherche dans notre base patient, laissez moi une petite minute",
    "wait_appointment": "Je regarde les disponibilités, un instant...",
    "wait_appointment2": "Je vais chercher des nouveaux créneaux disponibles pour votre examen.",
    "has_appointment": "J'ai en effet trouvé un rendez-vous à votre nom.",
    "has_appointments": "En effet, j'ai bien trouvé plusieurs rendez-vous à votre nom.",
    "has_no_appointment": "Il semblerait que vous n'ayez pas de rendez-vous prévus ces prochains jours.",
    "impossible": "Je suis désolé, votre requête n'entre pas dans mon champ de compétences, je vous passe un interlocuteur humain.",
    "wait_booking2": "Je vous ai trouvé. Ne quittez pas le temps que je confirme votre rendez-vous.",
}

play_source = text_to_speech("fixed_file_source", "hang_up_not_known")

play_source = text_to_speech("file_source", "")
