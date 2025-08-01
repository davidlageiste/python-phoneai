from azure.communication.callautomation import CallAutomationClient, TextSource, FileSource, RecognizeInputType, PhoneNumberIdentifier
from azure.storage.blob import BlobServiceClient
import azure.cognitiveservices.speech as speechsdk
from flask import Flask, request, jsonify
import requests
import asyncio
import aiohttp
from pymongo import MongoClient
from bson.json_util import dumps
from datetime import date, datetime
import logging
import unicodedata
import re 
import random

COGNITIVE_SERVICE_ENDPOINT = "https://lyraecognitivesservicesus.cognitiveservices.azure.com"
SPEECH_KEY='CwdBzhR9vodZ5lXf4S52ErZaUy9eUG05JJCtDuu4xjjL5rylozVFJQQJ99BAAC5T7U2XJ3w3AAAAACOGuWEK'
SPEECH_REGION='eastus'
MONGO_URL='mongodb+srv://lageistedavid:eaZOnmgtcNN1oGxU@cluster0.pjma4cx.mongodb.net/neuracorp'

app = Flask(__name__)

client = MongoClient(MONGO_URL)
db = client['neuracorp']
patientCollection = db['patientsDB']
rdvCollection = db["rdv"]

call_automation_client = CallAutomationClient.from_connection_string("endpoint=https://lyraetalk.france.communication.azure.com/;accesskey=9UN73P1bujRMwYm6rR9oaQx3slKfLHlTTEN5YeMkqXdhZ7WBmJ95JQQJ99ALACULyCpuAreVAAAAAZCS5f71")
speech_config = speechsdk.SpeechConfig(subscription=SPEECH_KEY,region=SPEECH_REGION)

global call_connection_id
global caller
global intent
global rdv_intent
global birthdate
global lastname
global firstname
global exam_id
global sous_type_id
global creneauDate
global all_creneaux
global chosen_creneau

# ERRORS HANDLING, MIGHT USE URL PARAMETERS INSTEAD
global type_exam_error
type_exam_error = 0

global firstname_error
firstname_error = 0

global lastname_error
lastname_error = 0

global ordonnance_error
ordonnance_error = 0

global birthdate_error
birthdate_error = 0

global intent_error
intent_error = 0

rdv_intent = None
intent = None
lastname = None
firstname = None
birthdate = None

# birthdate = "1990-01-01"
# lastname = "PROUST"
# firstname = "CHARLES"

french_months = {
    1: "janvier", 2: "février", 3: "mars", 4: "avril",
    5: "mai", 6: "juin", 7: "juillet", 8: "août",
    9: "septembre", 10: "octobre", 11: "novembre", 12: "décembre"
}

phrases_bank = {
    "general": [
        "D'accord, un instant.",
        "Très bien, un instant je vous prie.",
        "Je vois, je regarde cela.",
        "Entendu, un instant.",
        "Parfait, un instant je vous prie.",
        "C'est bien pris en compte, je regarde cela.",
        "Merci pour cette précision.",
        "C’est enregistré, un instant je vous prie.",
        "C'est noté, un instant.",
        "Je prends note de cela."
    ],
    "informationel": [
        "Je regarde ça pour vous, attendez un instant.",
        "Je vais vérifier cette information, ne quittez pas.",
        "Je consulte les données, cela prend juste quelques secondes.",
        "Je cherche la réponse à votre question, merci de patienter un instant.",
        "Je me renseigne pour vous, je vous dis ça tout de suite.",
    ],
    "prise_rdv": [
        "Je regarde les disponibilités, un instant.",
        "Je consulte le planning pour trouver un créneau adapté.",
        "Je vérifie les créneaux disponibles, cela prend juste quelques secondes.",
        "Je cherche les prochaines disponibilités, merci de patienter.",
        "Je vérifie les rendez-vous ouverts pour vous proposer une option.",
    ],
    "modification_rdv": [
        "Je consulte votre dossier pour voir les modifications possibles.",
        "Je regarde les disponibilités pour ajuster votre rendez-vous.",
        "Je vérifie les options pour modifier votre rendez-vous, un instant.",
        "Je me charge de la modification, cela prend juste un court instant.",
        "Je cherche la meilleure solution pour ajuster votre rendez-vous, merci de patienter.",
    ],
    "annulation_rdv": [
        "Je vérifie votre dossier pour procéder à l'annulation.",
        "Je prends en compte votre demande, un instant.",
        "Je m’occupe de l’annulation, cela prend juste un petit moment.",
        "Je vérifie les conditions d’annulation avant de finaliser votre demande.",
        "Je procède à l’annulation de votre rendez-vous, merci de patienter un instant.",
    ]
}

def get_phrase(category):
    phrases = phrases_bank.get(category)
    if not phrases:
        return f"[Aucune phrase disponible pour la catégorie : {category}]"
    return random.choice(phrases)

def full_date_vers_litteral(date_str):
    # Conversion en objet datetime
    date_obj = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S")    
    jour = date_obj.day
    mois = french_months[date_obj.month]
    heure = date_obj.hour
    minute = date_obj.minute

    heure_label = "heure" if heure == 1 else "heures"
    minute_label = "minute" if minute == 1 else "minutes"

    if minute == 0:
        return f"Le {jour} {mois} à {heure} {heure_label}"
    else:
        return f"Le {jour} {mois} à {heure} {heure_label} et {minute} {minute_label}"

def is_date_formatted(date):
    try:
        datetime.strptime(date, "%Y-%m-%d")
        return True
    except ValueError:
        return False

def date_vers_litteral(date_str):
    # Conversion en objet datetime
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    
    jour = date_obj.day
    mois = french_months[date_obj.month]
    annee = date_obj.year

    return f"Le {jour} {mois} {annee}"

def strip_accents(text):
    return ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )

async def get_model_response_async(user_response):
    url = "https://lyrae-talk-functions.azurewebsites.net/api/module_info?code=z4qZo6X7c4gNDPlKhBoXs2IRV1Z1o4FM_FKRqcgpTJBNAzFu_W0gTA=="
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json={"text": user_response}) as response:
            data = await response.json()
            print(data)
            return data.get("response", "No response found")

def get_model_response(text):
    url = "https://lyrae-talk-functions.azurewebsites.net/api/module_info?code=z4qZo6X7c4gNDPlKhBoXs2IRV1Z1o4FM_FKRqcgpTJBNAzFu_W0gTA=="

    headers = {
        "Content-Type": "application/json"
    }

    payload = {"text": text}

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()  # Lève une exception si le statut HTTP n'est pas 200
        return response.json().get("response", "Pas de réponse trouvée.")
    except requests.exceptions.RequestException as e:
        print(f"Erreur lors de l'appel au modèle : {e}")
        return "Erreur lors de la communication avec le modèle."

def start_recognizing(callback_url, context, play_source):

    call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
        input_type=RecognizeInputType.SPEECH,
        target_participant=PhoneNumberIdentifier("+" + caller.strip()),
        end_silence_timeout=0.5,
        play_prompt=play_source,
        interrupt_call_media_operation=False,
        interrupt_prompt=False,
        operation_context=context,
        speech_language="fr-FR",
        initial_silence_timeout=20,
        operation_callback_url=callback_url
    )

def hang_up(text):
    play_source = TextSource(
        text=text, source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural"
    )

    call_automation_client.get_call_connection(call_connection_id).play_media_to_all(
        play_source=play_source,
        operation_context="hang_up"
    )

def countPatientInDB(query):
    count = patientCollection.count_documents(query)
    return count

def findPatientInDB(query):
    results = patientCollection.find(query)
    
    return 

########## ENTRY POINT ##########

@app.route("/incoming_call", methods=["POST"])
def incoming_call():
    # Azure code de vérification
    if request.json and request.json[0].get("eventType") == "Microsoft.EventGrid.SubscriptionValidationEvent":
        validation_code = request.json[0]["data"]["validationCode"]
        return jsonify({"validationResponse": validation_code}), 200

    data = request.json[0]
    print(data.get("data").get("from"))
    caller = data.get("data").get("from").get("phoneNumber").get("value")
    encodedContext = data.get("data").get("incomingCallContext")

    call_automation_client.answer_call(incoming_call_context=encodedContext, callback_url=f"https://lyraeapi.azurewebsites.net/callback?caller={caller}", cognitive_services_endpoint=COGNITIVE_SERVICE_ENDPOINT)
    return jsonify({"status": "success"})

@app.route("/callback", methods=["POST"])
async def callback():
    global call_connection_id
    global intent
    global rdv_intent

    print(request.json[0].get("type"))
    data = request.json[0]

    if request.json and request.json[0].get("type") == "Microsoft.Communication.AnswerFailed":
        print(request.json[0])
    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        print(request.json[0])
    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeFailed":
        print(request.json[0])
    if request.json and request.json[0].get("type") == "Microsoft.Communication.PlayFailed":
        print(request.json[0])
    if request.json and request.json[0].get("type") == "Microsoft.Communication.CallTransferFailed":
        print(request.json[0])
    if request.json and request.json[0].get("type") == "Microsoft.Communication.CallConnected":
        call_connection_id = data.get("data").get("callConnectionId")
        server_call_id = data.get("data").get("serverCallId")
        caller = request.args.get('caller')

        # target = PhoneNumberIdentifier("+33801150376")

        # call_automation_client.get_call_connection(call_connection_id=call_connection_id).transfer_call_to_participant(
        #     target_participant=target,
        #     transferee=PhoneNumberIdentifier("+" + caller.strip()),
        #     operation_callback_url=f"https://lyraeapi.azurewebsites.net/callback",
        # )
        start_conversation(call_connection_id=call_connection_id, callerId=caller)
        # await find_patient(caller)
        # handle_prise_rdv(caller)
    if request.json and request.json[0].get("type") == "Microsoft.Communication.PlayCompleted" and request.json[0].get("data").get("operationContext") == "hang_up":
        call_automation_client.get_call_connection(call_connection_id).hang_up(is_for_everyone=True)
    return jsonify({"status": "success"})    

########## IDENTIFICATION ##########

@app.route("/get_firstname", methods=["POST"])
async def get_firstname():
    global firstname_error
    global firstname

    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "get_firstname":
        user_response = request.json[0].get("data").get("speechResult").get("speech")

        if user_response == "":
            firstname_error += 1
            if firstname_error > 2:
                hang_up("Il semblerait que nous n'arrivons pas à nous comprendre. Je vous transfère vers une secrétaire.")

            play_source = TextSource(text="Je n'ai pas compris, pouvez-vous répéter votre prénom ?", voice_name="fr-FR-VivienneMultilingualNeural")

            call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                input_type=RecognizeInputType.SPEECH,
                target_participant=PhoneNumberIdentifier("+" + caller.strip()),
                end_silence_timeout=0.5,
                play_prompt=play_source,
                interrupt_prompt=False,
                speech_language="fr-FR",
                initial_silence_timeout=5,
                operation_context="get_firstname",
                operation_callback_url="https://lyraeapi.azurewebsites.net/get_firstname"
            )

        else:
            clean_firstname = user_response.replace(".", "")
            task_get_firstname = asyncio.create_task(get_firstname_async(user_response=clean_firstname))
            speak(get_phrase("general")

            firstname = await task_get_firstname
            clean_firstname = firstname.strip().strip()

            if clean_firstname is None or clean_firstname == "Erreur lors de la communication avec le modèle.":
                    firstname_error += 1
                    if firstname_error > 2:
                        hang_up("Il semblerait que nous n'arrivons pas à nous comprendre. Je vous transfère vers une secrétaire.")
                    play_source = TextSource(text="Je n'ai pas compris, pouvez-vous répéter votre prénom ?", voice_name="fr-FR-VivienneMultilingualNeural")

                    call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                        input_type=RecognizeInputType.SPEECH,
                        target_participant=PhoneNumberIdentifier("+" + caller.strip()),
                        end_silence_timeout=0.5,
                        play_prompt=play_source,
                        interrupt_prompt=False,
                        speech_language="fr-FR",
                        initial_silence_timeout=5,
                        operation_context="get_firstname",
                        operation_callback_url="https://lyraeapi.azurewebsites.net/get_firstname"
                    )

            else: 
                play_source = TextSource(text=f"{clean_firstname}, c'est bien ça ?", voice_name="fr-FR-VivienneMultilingualNeural")

                call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                    input_type=RecognizeInputType.SPEECH,
                    target_participant=PhoneNumberIdentifier("+" + caller.strip()),
                    end_silence_timeout=0.5,
                    play_prompt=play_source,
                    interrupt_prompt=False,
                    speech_language="fr-FR",
                    initial_silence_timeout=10,
                    operation_context="confirm_firstname",
                    operation_callback_url="https://lyraeapi.azurewebsites.net/confirm_firstname"
                )

    elif request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeFailed":
        firstname_error += 1
        if firstname_error > 2:
            hang_up("Il semblerait que nous n'arrivons pas à nous comprendre. Je vous transfère vers une secrétaire.")
            
        play_source = TextSource(text="Je n'ai pas compris, pouvez-vous répéter votre prénom ?", voice_name="fr-FR-VivienneMultilingualNeural")

        call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
            input_type=RecognizeInputType.SPEECH,
            target_participant=PhoneNumberIdentifier("+" + caller.strip()),
            end_silence_timeout=0.5,
            play_prompt=play_source,
            interrupt_prompt=False,
            speech_language="fr-FR",
            initial_silence_timeout=5,
            operation_context="get_firstname",
            operation_callback_url="https://lyraeapi.azurewebsites.net/get_firstname"
        )

    return jsonify({"success": "success"})

@app.route("/get_lastname", methods=["POST"])
async def get_lastname():
    global lastname
    global lastname_error

    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "get_lastname":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        # Remove every "." that comes from the AI response

        speak(get_phrase("general")
        clean_name = user_response.replace(".", "")
        task_get_lastname = asyncio.create_task(get_lastname_async(user_response=clean_name))
        lastname = await task_get_lastname

        lastname = lastname
        if clean_name is None:
            if lastname_error > 2:
                play_source = TextSource(
                    text="Malheureusement, il semblerait que nous n'arrivons pas à nous comprendre. Je vais vous rediriger vers une secrétaire afin de pouvoir accéder a vos requêtes.", source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural"
                )

                call_automation_client.get_call_connection(call_connection_id).play_media_to_all(
                    play_source=play_source,
                    operation_context="hang_up"
                )

            lastname_error += 1
            play_source = TextSource(text="Je n'ai pas compris, pouvez-vous épeler votre nom de famille à nouveau ?", voice_name="fr-FR-VivienneMultilingualNeural")

            call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                input_type=RecognizeInputType.SPEECH,
                target_participant=PhoneNumberIdentifier("+" + caller.strip()),
                end_silence_timeout=1,
                play_prompt=play_source,
                interrupt_prompt=False,
                speech_language="fr-FR",
                initial_silence_timeout=5,
                operation_context="get_lastname",
                operation_callback_url="https://lyraeapi.azurewebsites.net/get_lastname"
            )

        else:
            lastname = clean_name
            play_source = TextSource(text=f"{lastname}, c'est bien ça ?", voice_name="fr-FR-VivienneMultilingualNeural")

            call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                input_type=RecognizeInputType.SPEECH,
                target_participant=PhoneNumberIdentifier("+" + caller.strip()),
                end_silence_timeout=0.5,
                play_prompt=play_source,
                interrupt_prompt=False,
                speech_language="fr-FR",
                initial_silence_timeout=10,
                operation_context="confirm_lastname",
                operation_callback_url="https://lyraeapi.azurewebsites.net/confirm_lastname"
            )

    elif request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeFailed" and request.json[0].get("data").get("operationContext") == "get_lastname":
        play_source = TextSource(text="Je n'ai pas compris, pouvez-vous épeler votre nom de famille à nouveau ?", voice_name="fr-FR-VivienneMultilingualNeural")

        call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
            input_type=RecognizeInputType.SPEECH,
            target_participant=PhoneNumberIdentifier("+" + caller.strip()),
            end_silence_timeout=0.5,
            play_prompt=play_source,
            interrupt_prompt=False,
            speech_language="fr-FR",
            initial_silence_timeout=5,
            operation_context="get_lastname",
            operation_callback_url="https://lyraeapi.azurewebsites.net/get_lastname"
        )    
        
    return jsonify({"success": "success"})

@app.route("/get_birthdate", methods=["POST"])
async def get_birthdate():
    global birthdate

    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "get_birthdate":
        speak(get_phrase("general")
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        speak(f"user said {user_response}")
        task_get_birthdate = asyncio.create_task(get_birthdate_async(user_response=user_response))

        birthdate = await task_get_birthdate

        if birthdate is None or is_date_formatted(birthdate) == False:
            play_source = TextSource(text="Je n'ai pas compris, quelle est votre date de naissance ?", voice_name="fr-FR-VivienneMultilingualNeural")

            call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                input_type=RecognizeInputType.SPEECH,
                target_participant=PhoneNumberIdentifier("+" + caller.strip()),
                end_silence_timeout=0.5,
                play_prompt=play_source,
                interrupt_prompt=False,
                speech_language="fr-FR",
                initial_silence_timeout=5,
                operation_context="confirm_birthdate",
                operation_callback_url="https://lyraeapi.azurewebsites.net/get_birthdate"
            )
        else:
            date_litterale = date_vers_litteral(birthdate)
            print(date_litterale)

            # Formatage en version littérale 
            play_source = TextSource(text=f"Vous confirmez que vous êtes né {date_litterale} ?", voice_name="fr-FR-VivienneMultilingualNeural")

        call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
            input_type=RecognizeInputType.SPEECH,
            target_participant=PhoneNumberIdentifier("+" + caller.strip()),
            end_silence_timeout=0.5,
            play_prompt=play_source,
            interrupt_prompt=False,
            speech_language="fr-FR",
            initial_silence_timeout=5,
            operation_context="confirm_birthdate",
            operation_callback_url="https://lyraeapi.azurewebsites.net/confirm_birthdate"
        )

    elif request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeFailed":
        play_source = TextSource(text="Je n'ai pas compris, quelle est votre date de naissance ?", voice_name="fr-FR-VivienneMultilingualNeural")

        call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
            input_type=RecognizeInputType.SPEECH,
            target_participant=PhoneNumberIdentifier("+" + caller.strip()),
            end_silence_timeout=0.5,
            play_prompt=play_source,
            interrupt_prompt=False,
            speech_language="fr-FR",
            initial_silence_timeout=5,
            operation_context="confirm_birthdate",
            operation_callback_url="https://lyraeapi.azurewebsites.net/get_birthdate"
        )
    return jsonify({"success": "success"})

########## CONFIRMATION ##########

@app.route("/confirm_firstname", methods=["POST"])
async def confirm_firstname():
    global firstname_error
    global firstname
    global lastname
    global birthdate

    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "confirm_firstname":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        model_response = get_positive_negative(user_response)

        if model_response == "négative":
            firstname_error += 1
            if firstname_error > 2:
                hang_up("Malheureusement, il semblerait que nous n'arrivons pas à nous comprendre. Je vais vous rediriger vers une secrétaire afin de pouvoir accéder a vos requêtes.")

            play_source = TextSource(text="Désolé, pouvez-vous me répéter votre prénom ?", voice_name="fr-FR-VivienneMultilingualNeural")

            call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                input_type=RecognizeInputType.SPEECH,
                target_participant=PhoneNumberIdentifier("+" + caller.strip()),
                end_silence_timeout=0.5,
                play_prompt=play_source,
                interrupt_prompt=False,
                speech_language="fr-FR",
                initial_silence_timeout=5,
                operation_context="get_firstname",
                operation_callback_url="https://lyraeapi.azurewebsites.net/get_firstname"
            )

        elif model_response == "positive":
            speak("Merci, je vous cherche dans notre base patient, laissez moi une petite minute")
            await find_patient()
        else: 
            play_source = TextSource(text=f"Je n'ai pas compris, {firstname}, c'est bien ça ?", voice_name="fr-FR-VivienneMultilingualNeural")

            call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                input_type=RecognizeInputType.SPEECH,
                target_participant=PhoneNumberIdentifier("+" + caller.strip()),
                end_silence_timeout=0.5,
                play_prompt=play_source,
                interrupt_prompt=False,
                speech_language="fr-FR",
                initial_silence_timeout=10,
                operation_context="confirm_firstname",
                operation_callback_url="https://lyraeapi.azurewebsites.net/confirm_firstname"
            )
    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeFailed":
        play_source = TextSource(text=f"Je n'ai pas compris, {firstname}, c'est bien ça ?", voice_name="fr-FR-VivienneMultilingualNeural")

        call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
            input_type=RecognizeInputType.SPEECH,
            target_participant=PhoneNumberIdentifier("+" + caller.strip()),
            end_silence_timeout=0.5,
            play_prompt=play_source,
            interrupt_prompt=False,
            speech_language="fr-FR",
            initial_silence_timeout=10,
            operation_context="confirm_firstname",
            operation_callback_url="https://lyraeapi.azurewebsites.net/confirm_firstname"
        )

    return jsonify({"success": "success"})

@app.route("/confirm_lastname", methods=["POST"])
async def confirm_lastname():
    global lastname_error
    
    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        speak(get_phrase("general")
        model_response = get_positive_negative(user_response)

        if model_response == "négative":
            lastname_error += 1
            if lastname_error > 2:
                play_source = TextSource(
                    text="Malheureusement, il semblerait que nous n'arrivons pas à nous comprendre. Je vais vous rediriger vers une secrétaire afin de pouvoir accéder a vos requêtes.", source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural"
                )

                call_automation_client.get_call_connection(call_connection_id).play_media_to_all(
                    play_source=play_source,
                    operation_context="hang_up"
                )

            play_source = TextSource(text="Désolé, pouvez-vous m'épeler votre nom de famille ?", voice_name="fr-FR-VivienneMultilingualNeural")

            call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                input_type=RecognizeInputType.SPEECH,
                target_participant=PhoneNumberIdentifier("+" + caller.strip()),
                end_silence_timeout=0.5,
                play_prompt=play_source,
                interrupt_prompt=False,
                speech_language="fr-FR",
                initial_silence_timeout=5,
                operation_context="get_lastname",
                operation_callback_url="https://lyraeapi.azurewebsites.net/get_lastname"
            )

        elif model_response == "positive":
            play_source = TextSource(text="Et quel est votre prénom ?", voice_name="fr-FR-VivienneMultilingualNeural")

            call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                input_type=RecognizeInputType.SPEECH,
                target_participant=PhoneNumberIdentifier("+" + caller.strip()),
                end_silence_timeout=0.5,
                play_prompt=play_source,
                interrupt_prompt=False,
                speech_language="fr-FR",
                initial_silence_timeout=5,
                operation_context="get_firstname",
                operation_callback_url="https://lyraeapi.azurewebsites.net/get_firstname"
            )
        else:
            play_source = TextSource(text=f"Je n'ai pas compris, {lastname}, c'est bien ça ?", voice_name="fr-FR-VivienneMultilingualNeural")

            call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                input_type=RecognizeInputType.SPEECH,
                target_participant=PhoneNumberIdentifier("+" + caller.strip()),
                end_silence_timeout=0.5,
                play_prompt=play_source,
                interrupt_prompt=False,
                speech_language="fr-FR",
                initial_silence_timeout=5,
                operation_context="confirm_lastname",
                operation_callback_url="https://lyraeapi.azurewebsites.net/confirm_lastname"
            )
    return jsonify({"success": "success"})

@app.route("/confirm_birthdate", methods=["POST"])
async def confirm_birthdate():
    global birthdate_error
    
    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "confirm_birthdate":
        speak(get_phrase("general")
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        model_response = get_positive_negative(user_response)

        if model_response == "négative":
            birthdate_error += 1
            if birthdate_error > 2:
                play_source = TextSource(
                    text="Malheureusement, il semblerait que nous n'arrivons pas à nous comprendre. Je vais vous rediriger vers une secrétaire afin de pouvoir accéder a vos requêtes.", source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural"
                )

                call_automation_client.get_call_connection(call_connection_id).play_media_to_all(
                    play_source=play_source,
                    operation_context="hang_up"
                )

            play_source = TextSource(text="Désolé, pouvez-vous me répéter votre date de naissance ?", voice_name="fr-FR-VivienneMultilingualNeural")

            call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                input_type=RecognizeInputType.SPEECH,
                target_participant=PhoneNumberIdentifier("+" + caller.strip()),
                end_silence_timeout=0.5,
                play_prompt=play_source,
                interrupt_prompt=False,
                speech_language="fr-FR",
                initial_silence_timeout=5,
                operation_context="get_birthdate",
                operation_callback_url="https://lyraeapi.azurewebsites.net/get_birthdate"
            )

        elif model_response == "positive":

            count = countPatientInDB({
                "dateNaissance": {
                    "$regex": f"^{birthdate + 'T00:00:00'}$"
                }
            })

            if count > 1 or count == 0:
                play_source = TextSource(text="Pouvez-vous m'épeler votre nom de famille ?", voice_name="fr-FR-VivienneMultilingualNeural")

                call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                    input_type=RecognizeInputType.SPEECH,
                    target_participant=PhoneNumberIdentifier("+" + caller.strip()),
                    end_silence_timeout=0.5,
                    play_prompt=play_source,
                    interrupt_prompt=False,
                    speech_language="fr-FR",
                    initial_silence_timeout=5,
                    operation_context="get_lastname",
                    operation_callback_url="https://lyraeapi.azurewebsites.net/get_lastname"
                )
            else:
                results = findPatientInDB({
                    "dateNaissance": {
                        "$regex": f"^{birthdate + 'T00:00:00'}$"
                    }
                })

                first_result = next(results, None)
                print(first_result)
                # play_source = TextSource(text=f"", voice_name="fr-FR-VivienneMultilingualNeural")



        else:
            date_litterale = date_vers_litteral(birthdate)

            # Formatage en version littérale
            play_source = TextSource(text=f"Vous confirmez que vous êtes né {date_litterale} ?", voice_name="fr-FR-VivienneMultilingualNeural")

            call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                input_type=RecognizeInputType.SPEECH,
                target_participant=PhoneNumberIdentifier("+" + caller.strip()), 
                end_silence_timeout=0.5,
                play_prompt=play_source,
                interrupt_prompt=False,
                speech_language="fr-FR",
                initial_silence_timeout=5,
                operation_context="confirm_birthdate",
                operation_callback_url="https://lyraeapi.azurewebsites.net/confirm_birthdate"
            )

    elif request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeFailed":
        birthdate_error += 1
        if birthdate_error > 2:
            hang_up("Malheureusement, il semblerait que nous n'arrivons pas à nous comprendre. Je vais vous rediriger vers une secrétaire afin de pouvoir accéder a vos requêtes.")

        date_litterale = date_vers_litteral(birthdate)

        play_source = TextSource(text=f"Je n'ai pas entendu, Vous confirmez que vous êtes né {date_litterale} ?", voice_name="fr-FR-VivienneMultilingualNeural")

        call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
            input_type=RecognizeInputType.SPEECH,
            target_participant=PhoneNumberIdentifier("+" + caller.strip()), 
            end_silence_timeout=0.5,
            play_prompt=play_source,
            interrupt_prompt=False,
            speech_language="fr-FR",
            initial_silence_timeout=5,
            operation_context="confirm_birthdate",
            operation_callback_url="https://lyraeapi.azurewebsites.net/confirm_birthdate"
        )
    return jsonify({"success": "success"})

@app.route("/confirm_call_intent", methods=["POST"])

async def confirm_call_intent():
    global rdv_intent
    global intent_error

    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "confirm_call_intent":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        speak(get_phrase("general")
        model_response = get_positive_negative(user_response)

        if model_response == "négative":
            play_source = TextSource(text="Il semblerait que je n'ai pas compris votre demande, souhaitez-vous prendre un rendez-vous, modifier un rendez-vous, consulter un rendez-vous planifié, annuler un rendez-vous ou obtenir une information ?", voice_name="fr-FR-VivienneMultilingualNeural")

            call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                input_type=RecognizeInputType.SPEECH,
                target_participant=PhoneNumberIdentifier("+" + caller.strip()), 
                end_silence_timeout=0.5,
                play_prompt=play_source,
                interrupt_prompt=False,
                speech_language="fr-FR",
                initial_silence_timeout=5,
                operation_context="start_conversation",
                operation_callback_url="https://lyraeapi.azurewebsites.net/handleResponse"
            )
        elif model_response == "positive":
            if rdv_intent == "prise de rendez-vous" or rdv_intent == "prise de rendez-vous.":
                handle_prise_rdv()
            elif rdv_intent == "modification de rendez-vous" or rdv_intent == "modification de rendez-vous.":
                handle_modification()

            elif rdv_intent == "Annulation de rendez-vous":
                rdv_intent = intent.lower()
                handle_annulation()

            elif rdv_intent == "consultation de rendez-vous" or rdv_intent == "consultation de rendez-vous.":
                handle_consultation()

        else:
            intent_error += 1
            if intent_error > 2:
                hang_up("Pardonnez moi, il semblerait que je n'arrive pas à vous comprendre. Je vous transfère vers une secrétaire.")

            play_source = TextSource(
                text=f"Pardonnez moi, je n'ai pas compris. Est-ce bien pour un ou une {rdv_intent} ?", source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural"
            )

            call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                input_type=RecognizeInputType.SPEECH,
                target_participant=PhoneNumberIdentifier("+" + caller.strip()), 
                end_silence_timeout=0.5,
                play_prompt=play_source,
                interrupt_prompt=False,
                speech_language="fr-FR",
                initial_silence_timeout=5,
                operation_context="confirm_call_intent",
                operation_callback_url="https://lyraeapi.azurewebsites.net/confirm_call_intent"
            )
    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeFailed":
        intent_error += 1
        if intent_error > 2:
            hang_up("Pardonnez moi, il semblerait que je n'arrive pas à vous comprendre. Je vous transfère vers une secrétaire.")

        play_source = TextSource(
            text=f"Pardonnez moi, je n'ai pas entendu. Est-ce bien pour un ou une {rdv_intent} ?", source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural"
        )

        call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
            input_type=RecognizeInputType.SPEECH,
            target_participant=PhoneNumberIdentifier("+" + caller.strip()), 
            end_silence_timeout=0.5,
            play_prompt=play_source,
            interrupt_prompt=False,
            speech_language="fr-FR",
            initial_silence_timeout=5,
            operation_context="confirm_call_intent",
            operation_callback_url="https://lyraeapi.azurewebsites.net/confirm_call_intent"
        )
    return jsonify({"success": "success"})

########## PRISE DE RENDEZ-VOUS ##########

@app.route("/module_informatif", methods=["POST"])
async def module_informatif():
    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "confirm_rdv":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        task = asyncio.create_task(get_model_response_async(user_response))
        model_response = await task
        speak(model_response)
    return jsonify({"success", "success"})

@app.route("/confirm_rdv", methods=["POST"])
async def confirm_rdv():
    global type_exam_error
    global exam_id
    global sous_type_id
    global all_creneaux

    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "confirm_rdv":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        speak(get_phrase("general"))
        model_response = get_positive_negative(user_response=user_response)

        if model_response == "négative":
            exam_id = None
            sous_type_id = None
            if type_exam_error <= 2:
                play_source = TextSource(
                    text="Pardonnez moi, pouvez-vous me répéter l'intitulé de l'examen que vous souhaitez passer ? ", source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural"
                )

                call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                    input_type=RecognizeInputType.SPEECH,
                    target_participant=PhoneNumberIdentifier("+" + caller.strip()),
                    end_silence_timeout=0.5,
                    play_prompt=play_source,
                    interrupt_prompt=False,
                    speech_language="fr-FR",
                    initial_silence_timeout=5,
                    operation_context="rdv_exam_type",
                    operation_callback_url="https://lyraeapi.azurewebsites.net/rdv_exam_type"
                )
            else:
                play_source = TextSource(
                    text="Malheureusement, il semblerait que nous n'arrivons pas à nous comprendre. Je vais vous rediriger vers une secrétaire afin de pouvoir accéder a vos requêtes.", source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural"
                )

                call_automation_client.get_call_connection(call_connection_id).play_media_to_all(
                    play_source=play_source,
                    operation_context="hang_up"
                )
        elif model_response == "positive":
            task_creneaux = asyncio.create_task(get_creneaux_async(sous_type=sous_type_id, exam_type=exam_id))
            speak(get_phrase("prise_rdv"))
            creneaux = await task_creneaux

            while creneaux is None:
                task_creneaux = asyncio.create_task(get_creneaux_async(sous_type=sous_type_id, exam_type=exam_id))
                creneaux = await task_creneaux

            all_creneaux = creneaux

            print("creneaux", creneaux)
            text = build_creneaux_phrase(creneaux=creneaux)
            play_source = TextSource(text=text, voice_name="fr-FR-VivienneMultilingualNeural")

            call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                input_type=RecognizeInputType.SPEECH,
                target_participant=PhoneNumberIdentifier("+" + caller.strip()),
                end_silence_timeout=0.5,
                play_prompt=play_source,
                interrupt_prompt=False,
                speech_language="fr-FR",
                initial_silence_timeout=5,
                operation_context="get_creneaux_choice",
                operation_callback_url="https://lyraeapi.azurewebsites.net/get_creneaux_choice"
            )
        else:
            play_source = TextSource(
                text="Je ne vous ai pas compris, pour quel type d'examen voulez-vous prendre rendez-vous ? ", source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural"
            )

            call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                input_type=RecognizeInputType.SPEECH,
                target_participant=PhoneNumberIdentifier("+" + caller.strip()),
                end_silence_timeout=0.5,
                play_prompt=play_source,
                interrupt_prompt=False,
                speech_language="fr-FR",
                initial_silence_timeout=5,
                operation_context="rdv_exam_type",
                operation_callback_url="https://lyraeapi.azurewebsites.net/rdv_exam_type"
            ) 
            
    elif request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeFailed":
        play_source = TextSource(text="Je ne vous ai pas entendu. Pouvez-vous répeter l'intitulé de l'examen ?", voice_name="fr-FR-VivienneMultilingualNeural")

        call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
            input_type=RecognizeInputType.SPEECH,
            target_participant=PhoneNumberIdentifier("+" + caller.strip()),
            end_silence_timeout=0.5,
            play_prompt=play_source,
            interrupt_prompt=False,
            speech_language="fr-FR",
            initial_silence_timeout=5,
            operation_context="rdv_exam_type",
            operation_callback_url="https://lyraeapi.azurewebsites.net/rdv_exam_type"
        )  
    return jsonify({"status": "success"})

@app.route("/rdv_exam_type", methods=["POST"])
async def rdv_exam_type():
    global exam_id
    global sous_type_id

    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "rdv_exam_type":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        pattern = r"\b(Urgence|Urgences|Urgent|Urgemment)\b"
        if re.search(pattern, user_response, re.IGNORECASE):
            hang_up("Il semblerait que vous appeliez pour une urgence. Je vous transfère vers une secrétaire.")
        task_type = asyncio.create_task(get_exam_type_async(user_response=user_response))
        speak(get_phrase("general"))
        exam_type = await task_type

        if exam_type["type_examen"] == None or exam_type["code_examen"] == None:
            play_source = TextSource(text="Désolé, je n'ai pas compris. Pouvez-vous répéter l'intitulé de l'examen pour lequel vous souhaitez prendre rendez-vous ?", voice_name="fr-FR-VivienneMultilingualNeural")

            call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                input_type=RecognizeInputType.SPEECH,
                target_participant=PhoneNumberIdentifier("+" + caller.strip()),
                end_silence_timeout=0.5,
                play_prompt=play_source,
                interrupt_prompt=False,
                speech_language="fr-FR",
                initial_silence_timeout=5,
                operation_context="rdv_exam_type",
                operation_callback_url="https://lyraeapi.azurewebsites.net/rdv_exam_type"
            )
        else :
            exam_id = exam_type["type_examen_id"]
            sous_type_id = exam_type["code_examen_id"]
            
            play_source = TextSource(text=f"Vous voulez prendre un rendez-vous pour un ou une {exam_type['code_examen']}, c'est bien ça ?", voice_name="fr-FR-VivienneMultilingualNeural")
            # play_source = TextSource(text=text, voice_name="fr-FR-VivienneMultilingualNeural")

            call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                input_type=RecognizeInputType.SPEECH,
                target_participant=PhoneNumberIdentifier("+" + caller.strip()),
                end_silence_timeout=0.5,
                play_prompt=play_source,
                interrupt_prompt=False,
                speech_language="fr-FR",
                initial_silence_timeout=5,
                operation_context="confirm_rdv",
                operation_callback_url="https://lyraeapi.azurewebsites.net/confirm_rdv"
            )

    return jsonify({"status": "success"})

@app.route("/get_creneaux_choice", methods=["POST"])
async def get_creneaux_choice():
    global creneauDate
    global all_creneaux
    global chosen_creneau
    global call_connection_id
    global rdv_intent

    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted":
        user_response = request.json[0].get("data").get("speechResult").get("speech")

        task_creneau_choice = asyncio.create_task(extract_creneau_async(user_response=user_response))
        
        play_source = TextSource(text="D'accord, patientez pendant que je vous réserve ce créneau.", voice_name="fr-FR-VivienneMultilingualNeural")

        call_automation_client.get_call_connection(call_connection_id).play_media_to_all(
            play_source=play_source
        )

        creneau_choice = await task_creneau_choice

        if creneau_choice is None:
            text = build_creneaux_phrase(creneaux=all_creneaux)

            play_source = TextSource(text=f"Je n'ai pas compris le créneau que vous avez choisi. {text}", voice_name="fr-FR-VivienneMultilingualNeural")

            call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                input_type=RecognizeInputType.SPEECH,
                target_participant=PhoneNumberIdentifier("+" + caller.strip()),
                end_silence_timeout=0.5,
                play_prompt=play_source,
                interrupt_prompt=False,
                speech_language="fr-FR",
                initial_silence_timeout=5,
                operation_context="get_creneaux_choice",
                operation_callback_url="https://lyraeapi.azurewebsites.net/get_creneaux_choice"
            )
        else:
            dt = datetime.fromisoformat(creneau_choice)

            matched_creneau = None
            for key, value in all_creneaux.items():
                full_datetime_str = value['date'][:10] + 'T' + value['heureDebut'] + ':00'
                current_dt = datetime.fromisoformat(full_datetime_str)
                if current_dt == dt:
                    matched_creneau = value
                    break

            if matched_creneau is not None:
                # Création de la phrase

                phrase = f"{dt.day} {french_months[dt.month]} à {dt.hour} heures {dt.minute:02d}"

                creneauDate = phrase
                chosen_creneau = matched_creneau

                if rdv_intent == "prise de rendez-vous" or rdv_intent == "prise de rendez-vous.":
                    play_source = TextSource(text=f"Vous avez choisi le {phrase}. Puis-je avoir votre date de naissance ?", voice_name="fr-FR-VivienneMultilingualNeural")
                    call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                        input_type=RecognizeInputType.SPEECH,
                        target_participant=PhoneNumberIdentifier("+" + caller.strip()), 
                        end_silence_timeout=0.5,
                        play_prompt=play_source,
                        interrupt_prompt=False,
                        speech_language="fr-FR",
                        initial_silence_timeout=5,
                        operation_context="get_birthdate",
                        operation_callback_url="https://lyraeapi.azurewebsites.net/get_birthdate"
                    )
                elif rdv_intent == "modification de rendez-vous" or rdv_intent == "modification de rendez-vous":
                    speak(f"Très bien, votre rendez-vous sera déplacé au {phrase}", voice_name="fr-FR-VivienneMultilingualNeural")
                    modify_creneau()

            else:
                text = build_creneaux_phrase(creneaux=all_creneaux)

                play_source = TextSource(text=f"Je n'ai pas compris le créneau que vous avez choisi. {text}", voice_name="fr-FR-VivienneMultilingualNeural")

                call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                    input_type=RecognizeInputType.SPEECH,
                    target_participant=PhoneNumberIdentifier("+" + caller.strip()),
                    end_silence_timeout=0.5,
                    play_prompt=play_source,
                    interrupt_prompt=False,
                    speech_language="fr-FR",
                    initial_silence_timeout=5,
                    operation_context="get_creneaux_choice",
                    operation_callback_url="https://lyraeapi.azurewebsites.net/get_creneaux_choice"
                )
    elif request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeFailed":
        play_source = TextSource(text=f"Je n'ai pas compris le créneau que vous avez choisi. {text}", voice_name="fr-FR-VivienneMultilingualNeural")

        call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
            input_type=RecognizeInputType.SPEECH,
            target_participant=PhoneNumberIdentifier("+" + caller.strip()),
            end_silence_timeout=0.5,
            play_prompt=play_source,
            interrupt_prompt=False,
            speech_language="fr-FR",
            initial_silence_timeout=5,
            operation_context="get_creneaux_choice",
            operation_callback_url="https://lyraeapi.azurewebsites.net/get_creneaux_choice"
        )
    
    return jsonify({"status": "success"})

@app.route("/handleResponse", methods=["POST"])
async def handleResponse():
    global rdv_intent
    global call_connection_id
    global caller

    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "start_conversation":
        speak(get_phrase("general"))
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        pattern = r"\b(Urgence|Urgences|Urgent|Urgemment)\b"
        if re.search(pattern, user_response, re.IGNORECASE):
            hang_up("Il semblerait que vous appeliez pour une urgence. Je vous transfère vers une secrétaire.")
        task_intent = asyncio.create_task(get_intent_async(user_response=user_response))
        
        intent = await task_intent
        play_source = None

        if intent.lower() == "renseignements" or intent.lower() == "renseignements.":
            rdv_intent = intent.lower()
            task_is_question = asyncio.create_task(is_question_async(user_response))
            is_question = await task_is_question
            if is_question is True:
                task = asyncio.create_task(get_model_response_async(user_response))
                model_response = await task
                speak(model_response)
            else:
                play_source = TextSource(
                    text="Bien sûr, posez-moi votre question", source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural"
                )
                start_recognizing("https://lyraeapi.azurewebsites.net/module_informatif", "module_informatif", play_source)

            continue_conversation("Puis-je faire autre chose pour vous ?")

        elif intent.lower() == "prise de rendez-vous" or intent.lower() == "prise de rendez-vous.":
            rdv_intent = intent.lower()
    
            speak("Je suis désolé, votre requête n'entre pas dans mon champ de compétences, je vous passe un interlocuteur humain.")
            target = PhoneNumberIdentifier("+33297415591")

            call_automation_client.get_call_connection(call_connection_id=call_connection_id).transfer_call_to_participant(
                target_participant=target,
                transferee=PhoneNumberIdentifier("+" + caller.strip()),
                operation_callback_url=f"https://lyraeapi.azurewebsites.net/callback",
            )

            # play_source = TextSource(text="Vous voulez prendre rendez-vous, c'est bien ça ?",voice_name="fr-FR-VivienneMultilingualNeural")

        elif intent.lower() == "modification de rendez-vous":
            rdv_intent = intent.lower()
            speak("Je suis désolé, votre requête n'entre pas dans mon champ de compétences, je vous passe un interlocuteur humain.")
            target = PhoneNumberIdentifier("+33297415591")

            call_automation_client.get_call_connection(call_connection_id=call_connection_id).transfer_call_to_participant(
                target_participant=target,
                transferee=PhoneNumberIdentifier("+" + caller.strip()),
                operation_callback_url=f"https://lyraeapi.azurewebsites.net/callback",
            )
            # play_source = TextSource(
            #     text="Désolé, je ne suis pas encore assez qualifié pour faire ceci. Voulez-vous prendre, consulter ou annuler un rendez-vous ou obtenir une information ?", source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural"
            # )

            start_recognizing("https://lyraeapi.azurewebsites.net/handleResponse", "start_conversation", play_source=play_source)
            
            return jsonify({"success": "success"})
            # play_source = TextSource(text="Vous voulez modifier un rendez-vous, c'est bien ça ?",voice_name="fr-FR-VivienneMultilingualNeural")

        elif intent.lower() == "annulation de rendez-vous" or intent.lower() == "annulation de rendez-vous.":
            speak("Je suis désolé, votre requête n'entre pas dans mon champ de compétences, je vous passe un interlocuteur humain.")
            target = PhoneNumberIdentifier("+33297415591")

            call_automation_client.get_call_connection(call_connection_id=call_connection_id).transfer_call_to_participant(
                target_participant=target,
                transferee=PhoneNumberIdentifier("+" + caller.strip()),
                operation_callback_url=f"https://lyraeapi.azurewebsites.net/callback",
            )
            rdv_intent = intent.lower()
            return jsonify({"success": "success"})

            # play_source = TextSource(
            #     text="Désolé, je ne suis pas encore assez qualifié pour faire ceci. Voulez-vous prendre, consulter ou modifier un rendez-vous ? Vous pouvez aussi simplement me poser une question.", source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural"
            # )
    
            call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                input_type=RecognizeInputType.SPEECH,
                target_participant=PhoneNumberIdentifier("+" + caller.strip()),
                end_silence_timeout=0.5,
                play_prompt=play_source,
                interrupt_call_media_operation=False,
                interrupt_prompt=False,
                operation_context="start_conversation",
                speech_language="fr-FR",
                initial_silence_timeout=20,
                operation_callback_url="https://lyraeapi.azurewebsites.net/handleResponse"
            )
            return jsonify({"success": "success"})

        elif intent.lower() == "consultation de rendez-vous" or intent.lower() == "consultation de rendez-vous.":
            # play_source = TextSource(
            #     text="Je suis désolé, votre requête n'entre pas dans mon champ de compétences, je vous passe un interlocuteur humain.", source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural"
            # )
            speak("Je suis désolé, votre requête n'entre pas dans mon champ de compétences, je vous passe un interlocuteur humain.")

            target = PhoneNumberIdentifier("+33297415591")

            call_automation_client.get_call_connection(call_connection_id=call_connection_id).transfer_call_to_participant(
                target_participant=target,
                transferee=PhoneNumberIdentifier("+" + caller.strip()),
                operation_callback_url=f"https://lyraeapi.azurewebsites.net/callback",
            )
            rdv_intent = intent.lower()
            return jsonify({"success": "success"})
            # play_source = TextSource(text="Vous voulez consulter un rendez-vous, c'est bien ça ?",voice_name="fr-FR-VivienneMultilingualNeural")

        elif intent.lower() == "autre" or intent.lower() == "autre.":
            speak("Je suis désolé, votre requête n'entre pas dans mon champ de compétences, je vous passe un interlocuteur humain.")

            target = PhoneNumberIdentifier("+33297415591")

            call_automation_client.get_call_connection(call_connection_id=call_connection_id).transfer_call_to_participant(
                target_participant=target,
                transferee=PhoneNumberIdentifier("+" + caller.strip()),
                operation_callback_url=f"https://lyraeapi.azurewebsites.net/callback",
            )
            return jsonify({"success": "success"})

            # call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
            #     input_type=RecognizeInputType.SPEECH,
            #     target_participant=PhoneNumberIdentifier("+" + caller.strip()),
            #     end_silence_timeout=0.5,
            #     play_prompt=play_source,
            #     interrupt_call_media_operation=False,
            #     interrupt_prompt=False,
            #     operation_context="start_conversation",
            #     speech_language="fr-FR",
            #     initial_silence_timeout=20,
            #     operation_callback_url="https://lyraeapi.azurewebsites.net/handleResponse"
            # )

            
        else:
            play_source = TextSource(
                text="Désolé, je n'ai pas compris, qui puis-je faire pour vous ?", source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural"
            )
    
            call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                input_type=RecognizeInputType.SPEECH,
                target_participant=PhoneNumberIdentifier("+" + caller.strip()),
                end_silence_timeout=0.5,
                play_prompt=play_source,
                interrupt_call_media_operation=False,
                interrupt_prompt=False,
                operation_context="start_conversation",
                speech_language="fr-FR",
                initial_silence_timeout=20,
                operation_callback_url="https://lyraeapi.azurewebsites.net/handleResponse"
            )

            return jsonify({"success": "success"})

        # call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
        #     input_type=RecognizeInputType.SPEECH,
        #     target_participant=PhoneNumberIdentifier("+" + caller.strip()), 
        #     end_silence_timeout=0.5,
        #     play_prompt=play_source,
        #     interrupt_prompt=False,
        #     speech_language="fr-FR",
        #     initial_silence_timeout=5,
        #     operation_context="confirm_call_intent",
        #     operation_callback_url="https://lyraeapi.azurewebsites.net/confirm_call_intent"
        # )

    elif request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeFailed":
        play_source = TextSource(
            text="Désolé, je n'ai pas compris, voulez-vous prendre, modifier ou annuler un rendez-vous ?", source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural"
        )
    
        call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
            input_type=RecognizeInputType.SPEECH,
            target_participant=PhoneNumberIdentifier("+" + caller.strip()),
            end_silence_timeout=0.5,
            play_prompt=play_source,
            interrupt_call_media_operation=False,
            interrupt_prompt=False,
            operation_context="start_conversation",
            speech_language="fr-FR",
            initial_silence_timeout=20,
            operation_callback_url="https://lyraeapi.azurewebsites.net/handleResponse"
        )

    return jsonify({"success": "success"})

@app.route("/has_ordonnance", methods=["POST"])
async def has_ordonnance():
    global ordonnance_error
    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "has_ordonnance":
        speak(get_phrase("general"))
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        model_response = get_positive_negative(user_response)

        if model_response == "négative":
            hang_up("Désolé nous pouvons pas vous planifier un rendez-vous sans ordonnance prescrite de votre médecin. Pour passer un examen d'imagerie, il faut avoir la prescription d'un médecin. Sans ordonnance, ce n'est pas possible. Pour avoir une ordonnance, je vous conseille de consulter un médecin. Je vous souhaite une excellente journée et à bientôt.")
        elif model_response == "positive":
            play_source = TextSource(text="Quel examen voulez vous passer ?", voice_name="fr-FR-VivienneMultilingualNeural")

            call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                input_type=RecognizeInputType.SPEECH,
                target_participant=PhoneNumberIdentifier("+" + caller.strip()), 
                end_silence_timeout=0.5,
                play_prompt=play_source,
                interrupt_prompt=False,
                speech_language="fr-FR",
                initial_silence_timeout=5,
                operation_context="rdv_exam_type",
                operation_callback_url="https://lyraeapi.azurewebsites.net/rdv_exam_type"
            )
        else:
            play_source = TextSource(text="Désolé, je n'ai pas compris, Avez-vous une ordonnance ?", voice_name="fr-FR-VivienneMultilingualNeural")

            call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                input_type=RecognizeInputType.SPEECH,
                target_participant=PhoneNumberIdentifier("+" + caller.strip()), 
                end_silence_timeout=0.5,
                play_prompt=play_source,
                interrupt_prompt=False,
                speech_language="fr-FR",
                initial_silence_timeout=5,
                operation_context="has_ordonnance",
                operation_callback_url="https://lyraeapi.azurewebsites.net/has_ordonnance"
            )

    return jsonify({"status": "success"})

########## ASYNC ##########

async def get_firstname_async(user_response):
    url = "https://lyrae-talk-functions.azurewebsites.net/api/get_prenom?code=z4qZo6X7c4gNDPlKhBoXs2IRV1Z1o4FM_FKRqcgpTJBNAzFu_W0gTA=="

    headers = {
        "Content-Type": "application/json"
    }

    payload = {
        "text": "Mon prénom est " + user_response
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response.raise_for_status()
                data = await response.json()
                print("firstname", data)
                return data.get("response", "Pas de réponse trouvée.")
    except aiohttp.ClientError as e:
        print(f"Erreur lors de l'appel au modèle : {e}")
        return "Erreur lors de la communication avec le modèle."

async def get_lastname_async(user_response):
    url = "https://lyrae-talk-functions.azurewebsites.net/api/get_nom_famille?code=z4qZo6X7c4gNDPlKhBoXs2IRV1Z1o4FM_FKRqcgpTJBNAzFu_W0gTA=="

    headers = {
        "Content-Type": "application/json"
    }

    payload = {
        "text": "Mon nom de famille est " + user_response
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response.raise_for_status()
                data = await response.json()
                print("lastname", data)
                return data.get("response", "Pas de réponse trouvée.")
    except aiohttp.ClientError as e:
        print(f"Erreur lors de l'appel au modèle : {e}")
        return "Erreur lors de la communication avec le modèle."

async def get_birthdate_async(user_response):
    url = "https://lyrae-talk-functions.azurewebsites.net/api/get_date_naissance?code=z4qZo6X7c4gNDPlKhBoXs2IRV1Z1o4FM_FKRqcgpTJBNAzFu_W0gTA=="

    headers = {
        "Content-Type": "application/json"
    }
    
    payload = {
        "text": user_response
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response.raise_for_status()
                data = await response.json()
                print("birthdate", data)
                return data.get("response", "Pas de réponse trouvée.")
    except aiohttp.ClientError as e:
        print(f"Erreur lors de l'appel au modèle : {e}")
        return "Erreur lors de la communication avec le modèle."

async def extract_creneau_async(user_response):
    url = "https://lyrae-talk-functions.azurewebsites.net/api/date_time_extractor?code=z4qZo6X7c4gNDPlKhBoXs2IRV1Z1o4FM_FKRqcgpTJBNAzFu_W0gTA=="
    headers = {
        "Content-Type": "application/json"
    }

    payload = {
        "text": user_response
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response.raise_for_status() 
                data = await response.json()
                print("créneau choisi", data)

                return data.get("response")
    except aiohttp.ClientError as e:
        print(f"Erreur lors de l'appel au modèle : {e}")
        return "Erreur lors de la communication avec le modèle."

async def get_creneaux_async(sous_type, exam_type):
    url = "https://ai2xplore.azurewebsites.net/api/getCreneaux"
    headers = {
        "Content-Type": "application/json"
    }

    if exam_type == "ECHOGRAPHIE":
        exam_type = 'EC'
    elif exam_type == "RADIO":
        exam_type = 'RX'
    elif exam_type == "SCANNER":
        exam_type = 'CT'
    elif exam_type == "Mammographie":
        exam_type = 'MG'

    # Get current date and time
    now = datetime.now()

    # Format it to match: 2025-04-18T00:00:00
    formatted = now.strftime("%Y-%m-%dT%H:%M:%S")

    payload = {
        "typeExamen": exam_type,
        "codeExamen": sous_type,
        "dateDebut": formatted
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response.raise_for_status()
                data = await response.json()
                print("creneaux", data)
                return data
    except aiohttp.ClientError as e:
        speak(f"Je ne peux pas trouver les créneaux parce que {e}")
        return None
        print(f"Erreur lors de l'appel au modèle : {e}")
        return "Erreur lors de la communication avec le modèle."

async def get_exam_type_async(user_response):
    url = "https://lyrae-talk-functions.azurewebsites.net/api/get_type_code_examen?code=z4qZo6X7c4gNDPlKhBoXs2IRV1Z1o4FM_FKRqcgpTJBNAzFu_W0gTA=="
    headers = {
        "Content-Type": "application/json"
    }
    payload = {"text": user_response}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response.raise_for_status() 
                data = await response.json()
                print("EXAM TYPE", data)
                return data
    except aiohttp.ClientError as e:
        print(f"Erreur lors de l'appel au modèle : {e}")
        return "Erreur lors de la communication avec le modèle."

async def get_intent_async(user_response):
    url = "https://lyrae-talk-functions.azurewebsites.net/api/detect_intention?code=z4qZo6X7c4gNDPlKhBoXs2IRV1Z1o4FM_FKRqcgpTJBNAzFu_W0gTA=="
    headers = {
        "Content-Type": "application/json"
    }
    payload = {"text": user_response}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response.raise_for_status() 
                data = await response.json()
                print("intent is", data)
                return data.get("response", "Pas de réponse trouvée.")
    except aiohttp.ClientError as e:
        print(f"Erreur lors de l'appel au modèle : {e}")
        return "Erreur lors de la communication avec le modèle."

async def get_rdv_intent_async(user_response):
    url = "https://lyraetalk-rdvmanager.azurewebsites.net/api/rdv_manager_intent?code=zHB4Rq1asqgR2mSumTnp0rvjGg-w77xDG5FQyKTD8xEGAzFu3GTqZQ=="
    headers = {
        "Content-Type": "application/json"
    }
    payload = {"text": user_response}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response.raise_for_status()
                data = await response.json()
                print(data)
                return data.get("response", "Pas de réponse trouvée.")
    except aiohttp.ClientError as e:
        print(f"Erreur lors de l'appel au modèle : {e}")
        return "Erreur lors de la communication avec le modèle."

def get_positive_negative(user_response):
    url = "https://lyrae-talk-functions.azurewebsites.net/api/analyseur_reponse?code=z4qZo6X7c4gNDPlKhBoXs2IRV1Z1o4FM_FKRqcgpTJBNAzFu_W0gTA=="
    headers = {
        "Content-Type": "application/json"
    }

    payload = {
        "action": "positive_negative_reponse",
        "text": user_response
    }
    try:
        response = requests.post(url, headers=headers, json=payload)

        response.raise_for_status()
        print("positive_negative", response.json())
        model_response = response.json().get("response")
        return model_response
    except requests.exceptions.RequestException as e:
            print(f"Erreur lors de l'appel au modèle : {e}")
            logging.info(f"error, {e}")
            return "Erreur lors de la communication avec le modèle."

async def is_question_async(text):
    url = "https://lyrae-talk-functions.azurewebsites.net/api/question_detection?code=z4qZo6X7c4gNDPlKhBoXs2IRV1Z1o4FM_FKRqcgpTJBNAzFu_W0gTA=="

    headers = {
        "Content-Type": "application/json"
    }
    
    payload = {
        "text": text
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response.raise_for_status()
                data = await response.json()
                print("birthdate", data)
                return data.get("response", "Pas de réponse trouvée.")
    except aiohttp.ClientError as e:
        print(f"Erreur lors de l'appel au modèle : {e}")
        return "Erreur lors de la communication avec le modèle."

########## CONVERSATION ##########

def build_creneaux_phrase(creneaux):
    data = creneaux

    # French ordinal indicators
    ordinals = {
        1: "premier",
        2: "deuxième",
        3: "troisième"
    }

    print(data)

    # Sort keys numerically to ensure order
    sorted_keys = sorted(data.keys(), key=lambda x: int(x))
    nb_slots = len(sorted_keys)

    # Build individual phrases
    phrases = []
    for idx, key in enumerate(sorted_keys, start=1):
        slot = data[key]
        date_obj = datetime.fromisoformat(slot["date"]).date()
        date_str = date_obj.strftime("%d/%m")
        heure = slot["heureDebut"]
        phrases.append(f"{ordinals[idx]} est le {date_str} à {heure}")

    # Assemble final sentence
    if nb_slots == 0:
        final_sentence = "Je suis désolé, aucun créneau n'est disponible pour le moment."
    else:
        plural = "créneau" if nb_slots == 1 else "créneaux"
        joined_phrases = ", ".join(phrases[:-1])
        if nb_slots > 1:
            joined_phrases += f" et le {phrases[-1]}"
        else:
            joined_phrases = phrases[0]

    final_sentence = f"Je peux vous proposer {nb_slots} {plural}. Le {joined_phrases}. Lequel choisissez-vous ?"

    return final_sentence

def continue_conversation(model_response):
    global call_connection_id
    global caller

    play_source = TextSource(text=model_response,voice_name="fr-FR-VivienneMultilingualNeural")

    call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
        input_type=RecognizeInputType.SPEECH,
        target_participant=PhoneNumberIdentifier("+" + caller.strip()),
        end_silence_timeout=0.5,
        play_prompt=play_source,
        interrupt_call_media_operation=False,
        interrupt_prompt=False,
        operation_context="start_conversation",
        speech_language="fr-FR",
        initial_silence_timeout=20,
        operation_callback_url="https://lyraeapi.azurewebsites.net/handleResponse"
    )

def handle_prise_rdv():

    play_source = TextSource(text="Avez-vous une ordonnance ?", voice_name="fr-FR-VivienneMultilingualNeural")

    call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
        input_type=RecognizeInputType.SPEECH,
        target_participant=PhoneNumberIdentifier("+" + caller.strip()), 
        end_silence_timeout=0.5,
        play_prompt=play_source,
        interrupt_prompt=False,
        speech_language="fr-FR",
        initial_silence_timeout=5,
        operation_context="has_ordonnance",
        operation_callback_url="https://lyraeapi.azurewebsites.net/has_ordonnance"
    )

def handle_modification():
    play_source = TextSource(text="Pour vous identifier, pouvez-vous me donner votre date de naissance ?", voice_name="fr-FR-VivienneMultilingualNeural")

    call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
        input_type=RecognizeInputType.SPEECH,
        target_participant=PhoneNumberIdentifier("+" + caller.strip()), 
        end_silence_timeout=0.5,
        play_prompt=play_source,
        interrupt_prompt=False,
        speech_language="fr-FR",
        initial_silence_timeout=5,
        operation_context="get_birthdate",
        operation_callback_url="https://lyraeapi.azurewebsites.net/get_birthdate"
    )
    return "ok"

def handle_consultation():
    play_source = TextSource(text="Très bien. Pouvez-vous me donner votre date de naissance ?", voice_name="fr-FR-VivienneMultilingualNeural")

    call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
        input_type=RecognizeInputType.SPEECH,
        target_participant=PhoneNumberIdentifier("+" + caller.strip()), 
        end_silence_timeout=0.5,
        play_prompt=play_source,
        interrupt_prompt=False,
        speech_language="fr-FR",
        initial_silence_timeout=5,
        operation_context="get_birthdate",
        operation_callback_url="https://lyraeapi.azurewebsites.net/get_birthdate"
    )

# def handle_annulation(user_response):
#     return "ok"

# def handle_consultation(user_response):
#     return "ok"

def start_conversation(call_connection_id, callerId):
    global caller
    caller = callerId
    
    # speak("Pour des raisons de qualité et de suivi, cet appel peut être enregistré.")

    play_source = TextSource(
        text="Bonjour! Je suis Lyrae, l'assistante vocale du centre de radiologie. Je suis un agent conversationnel automatisé. Comment puis-je vous aider aujourd’hui ?", source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural"
    )

    # play_source = TextSource(
    #     text="Oui ?", source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural"
    # )

    call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
        input_type=RecognizeInputType.SPEECH,
        target_participant=PhoneNumberIdentifier("+" + callerId.strip()),
        end_silence_timeout=0.5,
        play_prompt=play_source,
        interrupt_call_media_operation=True,
        interrupt_prompt=False,
        operation_context="start_conversation",
        speech_language="fr-FR",
        initial_silence_timeout=20,
        operation_callback_url="https://lyraeapi.azurewebsites.net/handleResponse"
    )

    # call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
    #     input_type=RecognizeInputType.SPEECH,
    #     target_participant=PhoneNumberIdentifier("+" + callerId.strip()),
    #     end_silence_timeout=0.5,
    #     play_prompt=play_source,
    #     interrupt_call_media_operation=False,
    #     interrupt_prompt=False,
    #     operation_context="get_birthdate",
    #     speech_language="fr-FR",
    #     initial_silence_timeout=20,
    #     operation_callback_url="https://lyraeapi.azurewebsites.net/get_birthdate"
    # )

def speak(text):

    global call_connection_id
    play_source = TextSource(
        text=text, source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural"
    )

    call_automation_client.get_call_connection(call_connection_id).play_media_to_all(
        play_source=play_source
    )

########## XPLORE API ##########
# async def get_soustype_exam(type_exam):
#     url = "https://sandbox.xplore.fr:20443/XaPriseRvGateway/Application/api/External/GetListeExamensFromTypeExamen"

#     headers = {
#         "Content-Type": "application/json"
#     }

#     if type_exam == "ECHOGRAPHIE":
#         result = 'EC'
#     elif type_exam == "RADIO":
#         result = 'RX'
#     elif type_exam == "SCANNER":
#         result = 'CT'
#     elif type_exam == "Mammographie":
#         result = 'MG'

#     payload = {"id": result}

#     try:
#         async with aiohttp.ClientSession() as session:
#             async with session.post(url, headers=headers, json=payload) as response:
#                 response.raise_for_status() 
#                 data = await response.json()
#                 print(data)
#                 return data.get("data")[0].get("code")
#     except aiohttp.ClientError as e:
#         print(f"Erreur lors de l'appel au modèle : {e}")
#         return "Erreur lors de la communication avec le modèle."

def createRDV(email, externalNumber = None):
    global lastname
    global firstname
    global birthdate

    url = "https://localhost:8008/api/createRDV"
    
    print("CREATING RDV WITH:", {
        "email": email,
        "firstName": firstname,
        "lastName": lastname,
        "birthDate": birthdate,
        "creneau": chosen_creneau
    })

    payload = {
        "email": email,
        "firstName": firstname,
        "lastName": lastname,
        "birthDate": birthdate,
        "creneau": chosen_creneau
    }

    if externalNumber is not None:
        payload.externalNumber = externalNumber

    print(payload)

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()  # Raises HTTPError for bad status
        data = response.json()
        print("Création: ", data)
        return data
    except requests.RequestException as e:
        print("Request failed:", e)
        return "Error occurred while creating RDV"

def getRDV(patientId):
    # url = "http://localhost:8080/api/getRDV"

    speak("Finding")
    results = list(rdvCollection.find({
        "idPatient": patientId
    }))

    # payload = {
    #     "idPatient": patientId
    # }

    json_results = dumps(list(results), indent=4)
    print(json_results)

    return results

def modify_creneau():
    return "ok"

def get_sous_type_exam(type_examen):
    url = "https://sandbox.xplore.fr:20443/XaPriseRvGateway/Application/api/External/GetListeExamensFromTypeExamen"

    payload = {
        "id": type_examen
    }

    print("requesting")

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()  # Raises HTTPError for bad status
        data = response.json()
        print(data)
        return data.get("data", "No Datas Found")
    except requests.RequestException as e:
        print("Request failed:", e)
        return "Error occurred while retrieving RDV"

########## DATABASE ##########
# CALLER & CALLER ID NOT NEEDED
async def find_patient():
    global birthdate
    global lastname
    global firstname
    global creneauDate
    global rdv_intent
    global all_creneaux

    results = patientCollection.find({
        "dateNaissance": {
            "$regex": f"^{birthdate + 'T00:00:00'}$"
        },
        "nom": {
            "$regex": f"^{lastname}$",
            "$options": "i"  # Case-insensitive
        },
        "prenom": {
            "$regex": f"^{strip_accents(firstname)}$",
            "$options": "i"  # Case-insensitive
        }
    })

    first_result = next(results, None)  # Get the first match, or None if no match

    if first_result is None:
        play_source = TextSource(
            text="Désolé, je ne peux pas donner de rendez-vous à un patient qui n'est pas déjà connu du cabinet. Vous êtes un nouveau patient : Je vous propose de vous transférer à la secrétaire", source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural"
        )

        call_automation_client.get_call_connection(call_connection_id).play_media_to_all(
            play_source=play_source,
            operation_context="hang_up"
        )
    
    else:
        if first_result:
            if rdv_intent == "prise de rendez-vous" or rdv_intent == "prise de rendez-vous.":
                speak("Je vous ai trouvé. Ne quittez pas le temps que je confirme votre rendez-vous.")
                email = first_result.get("email")
                
                # if first_result.get("externalNumber") is None:
                rdv = createRDV(email=email)
                    
                if rdv.get("success") is True:
                    speak("insertion en bdd")

                    rdvCollection.insert_one({
                        "idPatient": first_result.get("idPatient"),
                        "numeroRDV": rdv.get("data").get("numeroExamen"),
                        "date": chosen_creneau.get("date"),
                        "heure": chosen_creneau.get("heureDebut"),
                        "typeExamen": exam_id,
                        "codeExamen": sous_type_id
                    })
                    speak("construction de la phrase")
                    phrase_creneau = full_date_vers_litteral(chosen_creneau.get("date").split("T")[0] + "T" + chosen_creneau.get("heureDebut") + ":00")

                    speak(f"Parfait, vous avez donc rendez-vous {phrase_creneau} au nom de {lastname}.")
                    continue_conversation("Puis-je faire autre chose pour vous ?")
                else:
                    hang_up("Désolé, je n'ai pas pu valider votre rendez-vous. Je vais vous rediriger vers une secrétaire.")

            elif rdv_intent == "modification de rendez-vous" or rdv_intent == "modification de rendez-vous." or rdv_intent == "consultation de rendez-vous" :
                planned_rdv = getRDV(first_result.get("idPatient"))
                print("planned_rdv", planned_rdv)
                if len(planned_rdv) == 0:
                    speak("Il semblerait que vous n'ayez pas de rendez-vous prévus ces prochains jours.")
                    play_source = TextSource(text="Puis-je faire autre chose pour vous ?", source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural")

                    call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                        input_type=RecognizeInputType.SPEECH,
                        target_participant=PhoneNumberIdentifier("+" + caller.strip()),
                        end_silence_timeout=0.5,
                        play_prompt=play_source,
                        interrupt_call_media_operation=False,
                        interrupt_prompt=False,
                        operation_context="start_conversation",
                        speech_language="fr-FR",
                        initial_silence_timeout=20,
                        operation_callback_url="https://lyraeapi.azurewebsites.net/handleResponse"
                    )
                elif len(planned_rdv) == 1:
                    speak("J'ai en effet trouvé un rendez-vous à votre nom.")

                    dt = datetime.fromisoformat(planned_rdv[0].get("date").split("T")[0] + "T" + planned_rdv[0].get("heure"))
                    formatted_date = f"le {dt.day} {french_months[dt.month]} {dt.year}"
                    hours, minutes = planned_rdv[0].get("heure").split(":")

                    all_sous_type = get_sous_type_exam(planned_rdv[0].get("typeExamen"))
                    result = next((item for item in all_sous_type if item["code"] == planned_rdv[0].get("codeExamen")), None)

                    speak(f"Vous avez rendez-vous le {formatted_date} à {int(hours)} heure {int(minutes)} pour un ou une {result.get('libelle')}.")

                    if rdv_intent == "modification de rendez-vous" or rdv_intent.lower() == "modification de rendez-vous.":
                        task_creneaux = asyncio.create_task(get_creneaux_async(sous_type=planned_rdv[0].get("codeExamen"), exam_type=planned_rdv[0].get("typeExamen")))
                        speak(get_phrase("modification_rdv"))
                        creneaux = await task_creneaux
                        all_creneaux = creneaux
                        text = build_creneaux_phrase(creneaux=creneaux)
                        play_source = TextSource(text=text, voice_name="fr-FR-VivienneMultilingualNeural")

                        call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                            input_type=RecognizeInputType.SPEECH,
                            target_participant=PhoneNumberIdentifier("+" + caller.strip()),
                            end_silence_timeout=0.5,
                            play_prompt=play_source,
                            interrupt_prompt=False,
                            speech_language="fr-FR",
                            initial_silence_timeout=5,
                            operation_context="get_creneaux_choice",
                            operation_callback_url="https://lyraeapi.azurewebsites.net/get_creneaux_choice"
                        )
                    else:
                        play_source = TextSource(text="Puis-je faire autre chose pour vous ?", source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural")

                        call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                            input_type=RecognizeInputType.SPEECH,
                            target_participant=PhoneNumberIdentifier("+" + caller.strip()),
                            end_silence_timeout=0.5,
                            play_prompt=play_source,
                            interrupt_call_media_operation=False,
                            interrupt_prompt=False,
                            operation_context="start_conversation",
                            speech_language="fr-FR",
                            initial_silence_timeout=20,
                            operation_callback_url="https://lyraeapi.azurewebsites.net/handleResponse"
                        )
                else:
                    speak("En effet, j'ai bien trouvé plusieurs rendez-vous à votre nom.")
                    print()

            # elif intent == "Annulation de rendez-vous":

            email = first_result.get("email")
            print("Email:", email)
        else:
            play_source = TextSource(
                text="Désolé, je ne peux pas donner de rendez-vous à un patient qui n'est pas déjà connu du cabinet. Vous êtes un nouveau patient : Je vous propose de vous transférer à la secrétaire", source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural"
            )

            call_automation_client.get_call_connection(call_connection_id).play_media_to_all(
                play_source=play_source,
                operation_context="hang_up"
            )

if __name__ == '__main__':
    app.run(debug=True)
