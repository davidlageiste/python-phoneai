import logging
from flask import Flask, request, jsonify
from azure.communication.callautomation import CallAutomationClient, FileSource
from azure.storage.blob import BlobServiceClient
from twilio.rest import Client
from google.cloud import speech_v1p1beta1 as speech
from pydub import AudioSegment
import azure.cognitiveservices.speech as speechsdk
import requests
import os
import time
import wave
import io
import pyaudio
import numpy as np
import pyaudio
import wave
import numpy as np
import time

app = Flask(__name__)

# Configuration Azure Communication Service
call_automation_client = CallAutomationClient.from_connection_string("endpoint=https://lyraetalk.france.communication.azure.com/;accesskey=3w3cK83UG45fDt4zOVi4mwSsApOvCbqfZhn1tKFn4TPMp5d5umCYJQQJ99ALACULyCpuAreVAAAAAZCS6qkJ")

# Configuration Azure Blob Storage
blob_service_client = BlobServiceClient.from_connection_string("DefaultEndpointsProtocol=https;AccountName=lyraetalk8b7e;AccountKey=zOX5Zz9YrLI4d9bUz0qg8HQFYKvaHL1wGF31BOUzrdGgl7YNjsrZ43ZkvvkvksDAQaIWLcbcvoKp+AStnfIECA==;EndpointSuffix=core.windows.net")
container_name = "recordings"

# Configuration Twilio
twilio_client = Client("AC018cf7591ccc8dc367e58896e52ca76e", "192937914f8c996785bb6ac58c014f5b")

# Configuration Azure TTS
speech_config = speechsdk.SpeechConfig(subscription="CwdBzhR9vodZ5lXf4S52ErZaUy9eUG05JJCtDuu4xjjL5rylozVFJQQJ99BAAC5T7U2XJ3w3AAAAACOGuWEK", region="francecentral")
speech_config.speech_synthesis_voice_name = "fr-FR-DeniseNeural"
is_ia_speaking = False
first_callback_done = False

@app.route("/", methods=["POST"])
def test():
    return jsonify({"status": "success"})

@app.route("/recording_callback", methods=["POST"])
def recording_callback():
    data = request.json[0]
    event_type = data.get("type")
    print(data)
    if event_type == "Microsoft.Communication.RecordingFileStatusUpdated":
        recording_status = data.get("data").get("recordingStatus")
        if recording_status == "available":
            recording_id = data.get("data").get("recordingId")
            print(f"Enregistrement disponible. ID : {recording_id}")
            # Télécharger le fichier .wav depuis Azure Blob Storage
            download_audio_file(recording_id)
    
    return jsonify({"status": "success"})

@app.route("/call_connected", methods=["POST"])
def call_connected():
    if request.json and request.json[0].get("eventType") == "Microsoft.EventGrid.SubscriptionValidationEvent":
        validation_code = request.json[0]["data"]["validationCode"]
        return jsonify({"validationResponse": validation_code}), 200
    return jsonify({"status": "success"})

@app.route("/callback", methods=["POST"])
def callback():
    global first_callback_done
    print(request.json[0].get("type"))
    data = request.json[0]
    if request.json and request.json[0].get("type") == "Microsoft.Communication.PlayCompleted" and first_callback_done == False:
        first_callback_done = True
        call_connection_id = data.get("data").get("callConnectionId")
        audio_stream = capture_audio_stream()
        response_file = f"response_{call_connection_id}_{int(time.time())}.wav"
        record_response(audio_stream, response_file)

        user_response = transcribe_audio(response_file, call_connection_id)
        if user_response == 0:
            while user_response == 0:
                global is_ia_speaking
                is_ia_speaking = False
                speak("Désolé, je n'ai pas entendu, pouvez-vous répéter ?", call_connection_id)
                print("STARTING NEW RECORDING")
                new_audio_stream = capture_audio_stream()
                response_file = f"response_{call_connection_id}_{int(time.time())}.wav"
                record_response(new_audio_stream, response_file)
                user_response = transcribe_audio(response_file, call_connection_id)
            
        print(f"Réponse de l'appelant : {user_response}")

        intent = get_intent(user_response)
        print("INTENT", intent)
        if intent == "gestion":
            handle_gestion(user_response)
        elif intent == "renseignement":
            handle_renseignement(user_response, call_connection_id)
        # # Envoyer la réponse au modèle
    if request.json and request.json[0].get("type") == "Microsoft.Communication.PlayFailed":
        print(request.json[0])

    if request.json and request.json[0].get("type") == "Microsoft.Communication.CallConnected":
        call_connection_id = data.get("data").get("callConnectionId")
        server_call_id = data.get("data").get("serverCallId")
        start_conversation(server_call_id, call_connection_id)
    
    return jsonify({"status": "success"})

@app.route("/incoming_call", methods=["POST"])
def incoming_call():
    if request.json and request.json[0].get("eventType") == "Microsoft.EventGrid.SubscriptionValidationEvent":
        validation_code = request.json[0]["data"]["validationCode"]
        return jsonify({"validationResponse": validation_code}), 200

    data = request.json[0]
    encodedContext = data.get("data").get("incomingCallContext")
    call_automation_client.answer_call(incoming_call_context=encodedContext, callback_url="https://358a-2a01-cb00-844-1d00-9dbf-fa54-3fce-7079.ngrok-free.app/callback")
    return jsonify({"status": "success"})

from pydub import AudioSegment
import time

def speak(text, call_connection_id):
    """
    Utilise Azure Text-to-Speech (TTS) pour dire à voix haute le texte et joue l'audio dans l'appel.
    Attend que la lecture audio soit terminée avant de continuer.

    Args:
        text (str): Le texte à convertir en parole.
        call_connection_id (str): L'ID de la connexion d'appel.
    """
    global is_ia_speaking
    is_ia_speaking = True

    # Configuration du service TTS
    speech_config = speechsdk.SpeechConfig(
        subscription="CwdBzhR9vodZ5lXf4S52ErZaUy9eUG05JJCtDuu4xjjL5rylozVFJQQJ99BAAC5T7U2XJ3w3AAAAACOGuWEK",  # Remplacez par votre clé d'abonnement
        region="francecentral"  # Remplacez par votre région
    )
    speech_config.speech_synthesis_voice_name = "fr-FR-DeniseNeural"  # Choisissez une voix française

    # Créer un fichier audio temporaire
    temp_audio_file = f"temp_tts_output_{int(time.time())}.wav"
    audio_config = speechsdk.audio.AudioOutputConfig(filename=temp_audio_file)

    # Créer un synthesizer TTS
    speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)

    # Convertir le texte en parole
    print(f"Conversion du texte en parole : {text}")
    result = speech_synthesizer.speak_text_async(text).get()

    # Vérifier si la synthèse a réussi
    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        print("Synthèse audio terminée.")
    elif result.reason == speechsdk.ResultReason.Canceled:
        cancellation_details = result.cancellation_details
        print(f"Synthèse audio annulée : {cancellation_details.reason}")
        if cancellation_details.reason == speechsdk.CancellationReason.Error:
            print(f"Erreur : {cancellation_details.error_details}")
        return

    # Récupérer la durée du fichier audio
    audio = AudioSegment.from_file(temp_audio_file)
    duration_in_seconds = len(audio) / 1000  # Convertir la durée en secondes
    print(f"Durée du fichier audio : {duration_in_seconds} secondes")

    # Téléverser le fichier audio vers Azure Blob Storage
    blob_service_client = BlobServiceClient.from_connection_string("DefaultEndpointsProtocol=https;AccountName=lyraetalk8b7e;AccountKey=zOX5Zz9YrLI4d9bUz0qg8HQFYKvaHL1wGF31BOUzrdGgl7YNjsrZ43ZkvvkvksDAQaIWLcbcvoKp+AStnfIECA==;EndpointSuffix=core.windows.net")
    container_name = "recordings"
    blob_name = f"tts_output_{call_connection_id}.wav"

    with open(temp_audio_file, "rb") as audio_file:
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
        blob_client.upload_blob(audio_file, overwrite=True)

    # Générer l'URL du fichier audio
    audio_url = f"https://lyraetalk8b7e.blob.core.windows.net/recordings/{blob_name}"

    # Jouer l'audio dans l'appel
    play_source = FileSource(url=audio_url)
    call_automation_client.get_call_connection(call_connection_id).play_media_to_all(play_source=play_source)

    # Attendre que la durée du fichier audio soit écoulée
    startTime = time.time()
    print(f"Attente de {duration_in_seconds} secondes pour la fin de la lecture...")
    time.sleep(duration_in_seconds + 1)
    endTime = time.time()

    print("TTS message joué dans l'appel.")

def speak_hello(text, call_connection_id):
    audio_url = f"https://lyraetalk8b7e.blob.core.windows.net/recordings/bonjour_message.wav"
    play_source = FileSource(url=audio_url)
    # Play the audio in the call
    call_automation_client.get_call_connection(call_connection_id).play_media_to_all(play_source=play_source)

    print("TTS message played in the call.")

def start_recording(server_call_id, call_connection_id):
    print("CALL_CONNECTION_ID", call_connection_id)
    recording_state = call_automation_client.start_recording(call_locator=server_call_id)
    return recording_state.recording_id

def stop_recording(recording_id):
    call_automation_client.stop_recording(recording_id)

def download_audio_file(recording_id):
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=f"{recording_id}.wav")
    with open(f"{recording_id}.wav", "wb") as audio_file:
        print(blob_client.download_blob())
        audio_file.write(blob_client.download_blob().readall())
    return f"{recording_id}.wav"

def get_intent(user_response):
    print("RETRIEVING INTENT")
    url = "https://lyraetalk-detection-intention-patient-info-rdv.azurewebsites.net/api/detect_intent?code=IE1hYj0VJKw7J3jICYLTfUx7CmOKChjp8xJmqBS6nKi7AzFu4oV75w=="
    headers = {
        "Content-Type": "application/json"
    }
    payload = {"text": user_response}
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()  # Lève une exception si le statut HTTP n'est pas 200
        print(response.json())
        return response.json().get("response", "Pas de réponse trouvée.")
    except requests.exceptions.RequestException as e:
        print(f"Erreur lors de l'appel au modèle : {e}")
        return "Erreur lors de la communication avec le modèle."

def get_model_response(text):
    global is_ia_speaking
    print("SENDING TEXT", text)
    url = "https://medical-rad-rag-assistant.azurewebsites.net/api/rag_query?code=MjVVHBDAeLnYyXz0FzwYsaGxSjFXT99s4vaQg_nUlKe9AzFuuU3Z4Q=="
    headers = {
        "Content-Type": "application/json"
    }
    payload = {"text": text}
    is_ia_speaking=False
    try:
        print("STARTING MODEL REQUEST")
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()  # Lève une exception si le statut HTTP n'est pas 200
        return response.json().get("response", "Pas de réponse trouvée.")
    except requests.exceptions.RequestException as e:
        print(f"Erreur lors de l'appel au modèle : {e}")
        return "Erreur lors de la communication avec le modèle."

def record_response(audio_stream, file_name):
    with wave.open(file_name, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16 bits
        wav_file.setframerate(16000)  # 16 kHz
        wav_file.writeframes(audio_stream.read())

def upload_to_blob_storage(local_file_path, file_name):
    """ Uploads the file to Azure Blob Storage and returns the public URL """
    container_name = "recordings"
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=file_name)

    with open(local_file_path, "rb") as data:
        blob_client.upload_blob(data, overwrite=True)

    return f"https://lyraetalk8b7e.blob.core.windows.net/recordings/bonjour_message.wav"

def capture_audio_stream(silence_threshold=200, silence_duration=2, sample_rate=16000, channels=1, chunk_size=512):
    """
    Capture l'audio en temps réel et s'arrête après 1 seconde de silence.
    
    Args:
        silence_threshold (int): Seuil de silence (amplitude en dessous de laquelle on considère qu'il y a silence).
        silence_duration (float): Durée de silence (en secondes) avant d'arrêter l'enregistrement.
        sample_rate (int): Taux d'échantillonnage (par défaut 16 kHz).
        channels (int): Nombre de canaux audio (1 pour mono, 2 pour stéréo).
        chunk_size (int): Taille des blocs audio à lire.
    
    Returns:
        io.BytesIO: Flux audio en mémoire.
    """
    global is_ia_speaking

    # Attendre que l'IA ait fini de parler
    while is_ia_speaking:
        time.sleep(0.1)

    # Initialiser PyAudio
    audio = pyaudio.PyAudio()

    # Ouvrir le flux audio
    stream = audio.open(
        format=pyaudio.paInt16,  # Format 16 bits
        channels=channels,       # Mono
        rate=sample_rate,        # Taux d'échantillonnage
        input=True,              # Mode entrée (microphone)
        frames_per_buffer=chunk_size
    )

    print("Début de l'enregistrement...")

    # Variables pour la détection de silence
    frames = []
    silent_chunks = 0
    silence_limit = int(silence_duration * sample_rate / chunk_size)  # Nombre de chunks silencieux pour 1 seconde

    while True:
        # Lire un chunk audio
        data = stream.read(chunk_size)
        frames.append(data)

        # Convertir les données audio en tableau numpy pour analyser l'amplitude
        audio_data = np.frombuffer(data, dtype=np.int16)
        amplitude = np.abs(audio_data).mean()

        # Détecter le silence
        if amplitude < silence_threshold:
            silent_chunks += 1
        else:
            silent_chunks = 0

        # Arrêter l'enregistrement après 1 seconde de silence
        if silent_chunks > silence_limit:
            print("Silence détecté, fin de l'enregistrement.")
            break

    # Arrêter et fermer le flux
    stream.stop_stream()
    stream.close()
    audio.terminate()

    # Créer un flux en mémoire avec les données audio
    audio_stream = io.BytesIO()
    with wave.open(audio_stream, 'wb') as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(audio.get_sample_size(pyaudio.paInt16))
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b''.join(frames))

    # Remettre le pointeur du flux au début pour une lecture ultérieure
    audio_stream.seek(0)

    return audio_stream

def handle_gestion(user_response):
    
    return "ok"

def handle_renseignement(user_response, call_connection_id):
    print("CALLING MODEL")
    model_response = get_model_response(user_response)
    print(model_response)
    speak(model_response, call_connection_id=call_connection_id)
    return "ok"

def increase_volume(audio_file_path, target_dBFS=-20.0):
    """
    Augmente le volume d'un fichier audio en normalisant l'audio.

    Args:
        audio_file_path (str): Chemin du fichier audio à modifier.
        target_dBFS (float): Volume cible en dBFS (par défaut -20 dBFS).

    Returns:
        str: Chemin du fichier audio modifié.
    """
    # Charger le fichier audio
    audio = AudioSegment.from_wav(audio_file_path)

    # Normaliser l'audio pour atteindre le volume cible
    normalized_audio = audio.apply_gain(target_dBFS - audio.dBFS)

    # Sauvegarder le fichier audio modifié
    output_file_path = audio_file_path.replace(".wav", "_louder.wav")
    normalized_audio.export(output_file_path, format="wav")

    return output_file_path

def transcribe_audio(audio_file_path, call_connection_id):
    print("CALL_CONNECTION_ID", call_connection_id)
    # Configuration de l'entrée audio (fichier WAV)

    louder_audio_file_path = increase_volume(audio_file_path)
    audio_input = speechsdk.audio.AudioConfig(filename=louder_audio_file_path)

    # Création du recognizer
    speech_config.speech_recognition_language="fr-FR"  # Forcer la reconnaissance en français
    speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_input)

    # Démarrage de la transcription
    print("Début de la transcription...")
    result = speech_recognizer.recognize_once()

    # Vérification du résultat
    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
        print("Transcription réussie.")
        print(result.text)
        # speak("Avec plaisir, laissez-moi vous guider pas à pas", call_connection_id=call_connection_id)
        return result.text
    elif result.reason == speechsdk.ResultReason.NoMatch:
        print("Aucune parole détectée dans l'audio.")
        return 0
    elif result.reason == speechsdk.ResultReason.Canceled:
        cancellation_details = result.cancellation_details
        print(f"Transcription annulée : {cancellation_details.reason}")
        if cancellation_details.reason == speechsdk.CancellationReason.Error:
            print(f"Erreur : {cancellation_details.error_details}")
        return ""

def start_conversation(server_call_id, call_connection_id):
    print("STARTING CONVERSATION")
    
    speech_config.speech_synthesis_voice_name = "fr-FR-DeniseNeural"  # French voice

    speak_hello("Bonjour, comment puis-je vous aider ?", call_connection_id=call_connection_id)
   
    # while True:
        # Détecter quand l'appelant commence à parler
        # print("En attente de la réponse de l'appelant...")

        # Transcrire la réponse de l'appelant

        # # Demander si le besoin est résolu
        # speak("Avez-vous trouvé la réponse à votre besoin ? Répondez par 'Oui' ou 'Non'.")

        # # Enregistrer la confirmation de l'appelant
        # audio_stream = capture_audio_stream()
        # confirmation_file = f"confirmation_{call_connection_id}_{int(time.time())}.wav"
        # record_response(audio_stream, confirmation_file)

        # # Transcrire la confirmation
        # confirmation = transcribe_audio(confirmation_file)
        # print(f"Confirmation de l'appelant : {confirmation}")

        # # Envoyer les fichiers vers Azure Blob Storage
        # upload_to_blob_storage(response_file)
        # upload_to_blob_storage(confirmation_file)

        # if "oui" in confirmation.lower():
        #     speak("Merci d'avoir appelé. À bientôt !")
        #     break
        # elif "non" in confirmation.lower():
        #     speak("Pouvez-vous reformuler votre demande ?")

if __name__ == "__main__":
    app.run(port=5000, debug=True)