from azure.communication.callautomation import CallAutomationClient, TextSource, FileSource, RecognizeInputType, PhoneNumberIdentifier
from azure.storage.blob import BlobServiceClient
import azure.cognitiveservices.speech as speechsdk
from flask import Flask, request, jsonify
import requests
import asyncio
import aiohttp
from pymongo import MongoClient
import json
import time
from bson.json_util import dumps
from datetime import datetime
import ast

COGNITIVE_SERVICE_ENDPOINT = "https://lyraecognitivesservicesus.cognitiveservices.azure.com"
SPEECH_KEY='CwdBzhR9vodZ5lXf4S52ErZaUy9eUG05JJCtDuu4xjjL5rylozVFJQQJ99BAAC5T7U2XJ3w3AAAAACOGuWEK'
SPEECH_REGION='eastus'
MONGO_URL='mongodb+srv://lageistedavid:eaZOnmgtcNN1oGxU@cluster0.pjma4cx.mongodb.net/neuracorp'

app = Flask(__name__)
client = MongoClient(MONGO_URL)
db = client['neuracorp']
collection = db['patientsDB']  # Replace with your collection name

call_automation_client = CallAutomationClient.from_connection_string("endpoint=https://lyraetalk.france.communication.azure.com/;accesskey=3w3cK83UG45fDt4zOVi4mwSsApOvCbqfZhn1tKFn4TPMp5d5umCYJQQJ99ALACULyCpuAreVAAAAAZCS6qkJ")
speech_config = speechsdk.SpeechConfig(subscription=SPEECH_KEY,region=SPEECH_REGION)

global call_connection_id
global caller
global intent
global rdv_intent
global birthdate
global lastname
global firstname
global type_exam_error
global exam_id
global sous_type_id
rdv_intent = None
intent = None
type_exam_error = 0

async def get_model_response_async(user_response):
    url = "https://medical-rad-rag-assistant.azurewebsites.net/api/rag_query?code=MjVVHBDAeLnYyXz0FzwYsaGxSjFXT99s4vaQg_nUlKe9AzFuuU3Z4Q=="
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json={"text": user_response}) as response:
            data = await response.json()
            print(data)
            return data.get("response", "No response found")

def get_model_response(text):
    url = "https://medical-rad-rag-assistant.azurewebsites.net/api/rag_query?code=MjVVHBDAeLnYyXz0FzwYsaGxSjFXT99s4vaQg_nUlKe9AzFuuU3Z4Q=="
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

########## PRISE DE RENDEZ-VOUS ##########

@app.route("/get_firstname", methods=["POST"])
async def get_firstname():
    global firstname
    global lastname
    global birthdate
    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "get_firstname":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_get_firstname = asyncio.create_task(get_firstname_async(user_response=user_response))
        speak("Merci, laissez-moi un instant, j'essaye de vous identifier avec les informations que vous m'avez transmis. Cette opération peut prendre quelques secondes")
        firstname = await task_get_firstname
        find_patient()
    elif request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeFailed" and request.json[0].get("data").get("operationContext") == "get_firstname":
        speak("Désolé je n'ai pas compris votre prénom")
    return jsonify({"success": "success"})

@app.route("/get_lastname", methods=["POST"])
async def get_lastname():
    global lastname
    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "get_lastname":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_get_lastname = asyncio.create_task(get_lastname_async(user_response=user_response))

        play_source = TextSource(text="Et puis-je avoir votre prénom ?", voice_name="fr-FR-VivienneMultilingualNeural")

        call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
            input_type=RecognizeInputType.SPEECH,
            target_participant=PhoneNumberIdentifier("+" + caller.strip()),
            end_silence_timeout=1,
            play_prompt=play_source,
            interrupt_prompt=False,
            speech_language="fr-FR",
            initial_silence_timeout=10,
            operation_context="get_firstname",
            operation_callback_url="https://c5d0-2a01-cb00-844-1d00-95ba-5a9-b375-f641.ngrok-free.app/get_firstname"
        )

        lastname = await task_get_lastname
    elif request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeFailed" and request.json[0].get("data").get("operationContext") == "get_lastname":
        speak("Désolé je n'ai pas compris votre nom de famille")
    return jsonify({"success": "success"})

@app.route("/get_birthdate", methods=["POST"])
async def get_birthdate():
    global birthdate
    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "get_birthdate":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_get_birthdate = asyncio.create_task(get_birthdate_async(user_response=user_response))

        play_source = TextSource(text="Merci, pouvez-vous épeler votre nom de famille ?", voice_name="fr-FR-VivienneMultilingualNeural")

        call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
            input_type=RecognizeInputType.SPEECH,
            target_participant=PhoneNumberIdentifier("+" + caller.strip()),
            end_silence_timeout=0.5,
            play_prompt=play_source,
            interrupt_prompt=False,
            speech_language="fr-FR",
            initial_silence_timeout=5,
            operation_context="get_lastname",
            operation_callback_url="https://c5d0-2a01-cb00-844-1d00-95ba-5a9-b375-f641.ngrok-free.app/get_lastname"
        )

        birthdate = await task_get_birthdate
    elif request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeFailed" and request.json[0].get("data").get("operationContext") == "get_birthdate":
        speak("Désolé je n'ai pas compris votre date de naissance")
    return jsonify({"success": "success"})

@app.route("/prise_rendez_vous", methods=["POST"])
def prise_rendez_vous():
    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        speak("Parfait, laissez-moi trouver les créneaux disponibles.")

@app.route("/confirm_rdv", methods=["POST"])
async def confirm_rdv():
    global type_exam_error
    global exam_id
    global sous_type_id

    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "confirm_rdv":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        url = "https://analyse-reponse-consentement.azurewebsites.net/api/response_analyzer?code=XhZeOIcgHJC5htmtRy5Ckh9FFl7m2QyFpIMqI8NS0-jTAzFuqP2mJw=="
        headers = {
            "Content-Type": "application/json"
        }

        payload = {
            "action": "positive_negative_reponse",
            "texte": user_response
        }
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()

            model_response = response.json().get("response")

            if model_response == "non":
                exam_id = None
                sous_type_id = None
                if type_exam_error <= 2:
                    play_source = TextSource(
                        text="Pardonnez moi, pouvez-vous me répéter l'intitulé de l'examen que vous souhaitez passer ? ", source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural"
                    )

                    call_automation_client.get_call_connection(call_connection_id).play_media_to_all(
                        play_source=play_source,
                        operation_context="hang_up"
                    )
                else:
                    play_source = TextSource(
                        text="Malheureusement, il semblerait que nous n'arrivons pas à nous comprendre. Je vais vous rediriger vers une secrétaire afin de pouvoir accéder a vos requêtes.", source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural"
                    )

                    call_automation_client.get_call_connection(call_connection_id).play_media_to_all(
                        play_source=play_source,
                        operation_context="hang_up"
                    )
            elif model_response == "oui":
                task_creneaux = asyncio.create_task(get_creneaux_async(sous_type=sous_type_id, exam_type=exam_id))
                speak("Très bien, laissez moi un instant le temps que je récupère les créneaux disponibles pour ce type d'examen")
                creneaux = await task_creneaux
                
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
                    operation_callback_url="https://c5d0-2a01-cb00-844-1d00-95ba-5a9-b375-f641.ngrok-free.app/get_creneaux_choice"
                )
                speak(text)
            else:
                type_exam_error += 1
                
        except requests.exceptions.RequestException as e:
            print(f"Erreur lors de l'appel au modèle : {e}")
            return "Erreur lors de la communication avec le modèle."

    return jsonify({"status": "success"})

@app.route("/rdv_exam_type", methods=["POST"])
async def rdv_exam_type():
    global exam_id
    global sous_type_id

    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "rdv_exam_type":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_type = asyncio.create_task(get_exam_type_async(user_response=user_response))
        exam_type = await task_type

        if exam_type["type_examen"] == None:
            play_source = TextSource(text="Désolé, je n'ai pas compris. Pouvez-vous répeter l'intitulé de l'examen pour lequel vous souhaitez prendre rendez-vous ?", voice_name="fr-FR-VivienneMultilingualNeural")

            call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                input_type=RecognizeInputType.SPEECH,
                target_participant=PhoneNumberIdentifier("+" + caller.strip()),
                end_silence_timeout=0.5,
                play_prompt=play_source,
                interrupt_prompt=False,
                speech_language="fr-FR",
                initial_silence_timeout=5,
                operation_context="rdv_exam_type",
                operation_callback_url="https://c5d0-2a01-cb00-844-1d00-95ba-5a9-b375-f641.ngrok-free.app/rdv_exam_type"
            )
        else :
            print(exam_type)
            exam_id = exam_type["type_examen_id"]
            sous_type_id = exam_type["code_examen_id"]
            
            play_source = TextSource(text=f"Vous voulez prendre un rendez-vous pour un ou une {exam_type["code_examen"]}, c'est bien ça ?", voice_name="fr-FR-VivienneMultilingualNeural")
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
                operation_callback_url="https://c5d0-2a01-cb00-844-1d00-95ba-5a9-b375-f641.ngrok-free.app/confirm_rdv"
            )

    return jsonify({"status": "success"})

@app.route("/get_creneaux_choice", methods=["POST"])
async def get_creneaux_choice():
    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted":
        user_response = request.json[0].get("data").get("speechResult").get("speech")

        task_creneau_choice = asyncio.create_task(extract_creneau_async(user_response=user_response))
        
        play_source = TextSource(text="Parfait, je vais vous réserver ce créneau. Laissez-moi un instant", voice_name="fr-FR-VivienneMultilingualNeural")

        call_automation_client.get_call_connection(call_connection_id).play_media_to_all(
            play_source=play_source
        )

        creneau_choice = await task_creneau_choice

        print(creneau_choice)

        play_source = TextSource(text="Done", voice_name="fr-FR-VivienneMultilingualNeural")

        call_automation_client.get_call_connection(call_connection_id).play_media_to_all(
            play_source=play_source
        )
        # call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
        #     input_type=RecognizeInputType.SPEECH,
        #     target_participant=PhoneNumberIdentifier("+" + caller.strip()), 
        #     end_silence_timeout=1,
        #     play_prompt=play_source,
        #     interrupt_prompt=False,
        #     speech_language="fr-FR",
        #     initial_silence_timeout=5,
        #     operation_context="rdv_exam_type",
        #     operation_callback_url="https://c5d0-2a01-cb00-844-1d00-95ba-5a9-b375-f641.ngrok-free.app/rdv_exam_type"
        # )

    return jsonify({"status": "success"})

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

    call_automation_client.answer_call(incoming_call_context=encodedContext, callback_url=f"https://c5d0-2a01-cb00-844-1d00-95ba-5a9-b375-f641.ngrok-free.app/callback?caller={caller}", cognitive_services_endpoint=COGNITIVE_SERVICE_ENDPOINT)
    return jsonify({"status": "success"})

@app.route("/handleResponse", methods=["POST"])
async def handleResponse():
    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "start_conversation":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_intent = asyncio.create_task(get_intent_async(user_response=user_response))
        speak("Bien sûr, patientez un instant")
        intent = await task_intent
        print("USER SAID", user_response)
        print("INTENT IS", intent)
        if intent == "renseignements":
            task = asyncio.create_task(get_model_response_async(user_response))
            model_response = await task
            speak(model_response)
            continue_conversation("Puis-je faire autre chose pour vous ?")
        elif intent.lower() == "prise de rendez-vous" or intent.lower() == "prise de rendez-vous.":
            handle_prise_rdv(user_response=user_response)
        elif intent == "Modification de rendez-vous":
            handle_modification(user_response=user_response)
        elif intent == "Annulation de rendez-vous":
            handle_annulation(user_response=user_response)
        elif intent == "Consultation de rendez-vous":
            handle_consultation(user_response=user_response)
    elif request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeFailed":
        print("ERROR RECOGNIZE")

    return jsonify({"success": "success"})

@app.route("/handleConsentement", methods=["POST"])
async def handleConsentement():
    # if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "get_consentement":
        # user_response = request.json[0].get("data").get("speechResult").get("speech")
        # url = "https://analyse-reponse-consentement.azurewebsites.net/api/response_analyzer?code=XhZeOIcgHJC5htmtRy5Ckh9FFl7m2QyFpIMqI8NS0-jTAzFuqP2mJw=="
        # headers = {
        #     "Content-Type": "application/json"
        # }
        # payload = {"text": user_response}
        # try:
        #     response = requests.post(url, headers=headers, json=payload)
        #     response.raise_for_status()  # Lève une exception si le statut HTTP n'est pas 200
        #     print(response.json())
        #     return response.json().get("response", "Pas de réponse trouvée.")
        # except requests.exceptions.RequestException as e:
        #     print(f"Erreur lors de l'appel au modèle : {e}")
        #     return "Erreur lors de la communication avec le modèle."

    return jsonify({"status": "success"})

@app.route("/has_ordonnance", methods=["POST"])
async def has_ordonnance():
    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "has_ordonnance":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        url = "https://analyse-reponse-consentement.azurewebsites.net/api/response_analyzer?code=XhZeOIcgHJC5htmtRy5Ckh9FFl7m2QyFpIMqI8NS0-jTAzFuqP2mJw=="
        headers = {
            "Content-Type": "application/json"
        }

        payload = {
            "action": "positive_negative_reponse",
            "texte": user_response
        }
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            print("has_ordonnance", response.json())
            model_response = response.json().get("response")

            if model_response == "non":
                play_source = TextSource(
                    text="Désolé nous pouvons pas vous planifier un rendez vous sans ordonnance prescrite de votre médecin. Pour passer un examen d’imagerie, il faut avoir la prescription d’un médecin. Sans ordonnance, ce n’est pas possible. Pour avoir une ordonnance, je vous conseille de consulter un médecin. Je vous souhaite une excellente journée et à bientôt.", source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural"
                )

                call_automation_client.get_call_connection(call_connection_id).play_media_to_all(
                    play_source=play_source,
                    operation_context="hang_up"
                )
            elif model_response == "oui":
                play_source = TextSource(text="Quel examen voulez vous passer ?", voice_name="fr-FR-VivienneMultilingualNeural")

                call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                    input_type=RecognizeInputType.SPEECH,
                    target_participant=PhoneNumberIdentifier("+" + caller.strip()), 
                    end_silence_timeout=1,
                    play_prompt=play_source,
                    interrupt_prompt=False,
                    speech_language="fr-FR",
                    initial_silence_timeout=5,
                    operation_context="rdv_exam_type",
                    operation_callback_url="https://c5d0-2a01-cb00-844-1d00-95ba-5a9-b375-f641.ngrok-free.app/rdv_exam_type"
                )
            else:
                play_source = TextSource(text="Désolé, je n'ai pas compris, Avez-vous une ordonnance ?", voice_name="fr-FR-VivienneMultilingualNeural")
                call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
                    input_type=RecognizeInputType.SPEECH,
                    target_participant=PhoneNumberIdentifier("+" + caller.strip()), 
                    end_silence_timeout=1,
                    play_prompt=play_source,
                    interrupt_prompt=False,
                    speech_language="fr-FR",
                    initial_silence_timeout=5,
                    operation_context="has_ordonnance",
                    operation_callback_url="https://c5d0-2a01-cb00-844-1d00-95ba-5a9-b375-f641.ngrok-free.app/has_ordonnance"
                )
        except requests.exceptions.RequestException as e:
            print(f"Erreur lors de l'appel au modèle : {e}")
            return "Erreur lors de la communication avec le modèle."

    return jsonify({"status": "success"})

@app.route("/callback", methods=["POST"])
def callback():
    global call_connection_id
    global intent
    global rdv_intent

    print(request.json[0].get("type"))
    data = request.json[0]

    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        print(request.json[0])
    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeFailed":
        print(request.json[0])
    if request.json and request.json[0].get("type") == "Microsoft.Communication.PlayFailed":
        print(request.json[0])
    if request.json and request.json[0].get("type") == "Microsoft.Communication.CallConnected":
        call_connection_id = data.get("data").get("callConnectionId")
        server_call_id = data.get("data").get("serverCallId")
        caller = request.args.get('caller')
        start_conversation(call_connection_id=call_connection_id, callerId=caller)
        # find_patient(caller)
        # handle_prise_rdv(caller)
    if request.json and request.json[0].get("type") == "Microsoft.Communication.PlayCompleted" and request.json[0].get("data").get("operationContext") == "hang_up":
        call_automation_client.get_call_connection(call_connection_id).hang_up(is_for_everyone=True)
    return jsonify({"status": "success"})    

########## ASYNC ##########

async def get_firstname_async(user_response):
    url = "https://lyraetalk-patientidentification-creneauextractor.azurewebsites.net/api/ia_modules_script_hugging_face?code=h7RbiwESjKdGApwZ4ro3JoGGZLJczjvkKxpj2JT_uas6AzFua0y1zg=="

    headers = {
        "Content-Type": "application/json"
    }

    payload = {
        "action": "extraire_prenom",
        "texte": user_response
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
    url = "https://get-nom.azurewebsites.net/api/get_nom_famille?code=-MluM5OTMM-I-Iq00V-lQbyUBado5N4uDfAMVjuAKyczAzFuzWLu8Q=="
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
                print("lastname", data)
                return data.get("response", "Pas de réponse trouvée.")
    except aiohttp.ClientError as e:
        print(f"Erreur lors de l'appel au modèle : {e}")
        return "Erreur lors de la communication avec le modèle."

async def get_birthdate_async(user_response):
    url = "https://get-date-naissance.azurewebsites.net/api/get_date_naissance?code=6y8-9aG2MNbWB5WVsjW_QaOQsXLakrA1RFIuaKx4vHDsAzFu-ekgHg=="

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
    url = "https://get-exam-type-code.azurewebsites.net/api/get_type_code_examen?code=ggp6REjpXNQVDagAZxMwRqsW_HoGpRwnFKXkHOI7ELB4AzFuBwtH6Q=="
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "texte": user_response,
        "action": "extraire_creneau"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response.raise_for_status() 
                data = await response.json()
                print("créneau choisi", data)
                return data
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

    payload = {
        "typeExamen": exam_type,
        "codeExamen": sous_type
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response.raise_for_status()
                data = await response.json()
                print("creneaux", data)
                return data
    except aiohttp.ClientError as e:
        print(f"Erreur lors de l'appel au modèle : {e}")
        return "Erreur lors de la communication avec le modèle."

async def get_exam_type_async(user_response):
    url = "https://get-exam-type-code.azurewebsites.net/api/get_type_code_examen?code=ggp6REjpXNQVDagAZxMwRqsW_HoGpRwnFKXkHOI7ELB4AzFuBwtH6Q=="
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
    url = "https://lyraetalk-get-intention.azurewebsites.net/api/detect_intention?code=l3FK0en4_Wc_3ncpcmy5NXGTGB1OKoz6SBnG3egHEgbBAzFuMd7isA=="
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

async def get_rdv_intent_async(user_response):
    url = "https://lyraetalk-rdvmanager.azurewebsites.net/api/rdv_manager_intent?code=zHB4Rq1asqgR2mSumTnp0rvjGg-w77xDG5FQyKTD8xEGAzFu3GTqZQ=="
    headers = {
        "Content-Type": "application/json"
    }
    payload = {"text": user_response}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response.raise_for_status()  # Ensure the request was successful
                data = await response.json()  # ✅ Await response.json() before accessing
                print(data)
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

    # Sort keys numerically to ensure order
    sorted_keys = sorted(data.keys(), key=lambda x: int(x))
    nb_slots = len(sorted_keys)

    # Build individual phrases
    phrases = []
    for idx, key in enumerate(sorted_keys, start=1):
        slot = data[key]
        date_obj = datetime.fromisoformat(slot["date"]).date()
        date_str = date_obj.strftime("%d/%m/%Y")
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
        end_silence_timeout=1,
        play_prompt=play_source,
        interrupt_prompt=False,
        speech_language="fr-FR",
        initial_silence_timeout=5
    )

def handle_prise_rdv(user_response):

    play_source = TextSource(text="Avez-vous une ordonnance ?", voice_name="fr-FR-VivienneMultilingualNeural")
    call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
        input_type=RecognizeInputType.SPEECH,
        target_participant=PhoneNumberIdentifier("+" + caller.strip()), 
        end_silence_timeout=1,
        play_prompt=play_source,
        interrupt_prompt=False,
        speech_language="fr-FR",
        initial_silence_timeout=5,
        operation_context="has_ordonnance",
        operation_callback_url="https://c5d0-2a01-cb00-844-1d00-95ba-5a9-b375-f641.ngrok-free.app/has_ordonnance"
    )
    
    # play_source = TextSource(text="Pouvez-vous me donner votre jour, mois et année de naissance s'il vous plaît ?", voice_name="fr-FR-VivienneMultilingualNeural")

    # call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
    #     input_type=RecognizeInputType.SPEECH,
    #     target_participant=PhoneNumberIdentifier("+" + caller.strip()), 
    #     end_silence_timeout=1,
    #     play_prompt=play_source,
    #     interrupt_prompt=False,
    #     speech_language="fr-FR",
    #     initial_silence_timeout=5,
    #     operation_context="get_birthdate",
    #     operation_callback_url="https://c5d0-2a01-cb00-844-1d00-95ba-5a9-b375-f641.ngrok-free.app/get_birthdate"
    # )

    return "ok"

def handle_modification(user_response):
    return "ok"

def handle_annulation(user_response):
    return "ok"

def handle_consultation(user_response):
    return "ok"

# def get_consentement(callerId):
#     global caller

    # play_source = TextSource(
    #     text="Bonjour, je suis une IA de secrétariat médical. Acceptez-vous que je réponde a vos besoins ?", source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural"
    # )
    

    # call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
    #     input_type=RecognizeInputType.SPEECH,
    #     target_participant=PhoneNumberIdentifier("+" + callerId.strip()), 
    #     end_silence_timeout=0.5,
    #     play_prompt=play_source,
    #     interrupt_call_media_operation=False,
    #     interrupt_prompt=False,
    #     operation_context="get_consentement",
    #     speech_language="fr-FR",
    #     initial_silence_timeout=5,
    #     operation_callback_url="https://c5d0-2a01-cb00-844-1d00-95ba-5a9-b375-f641.ngrok-free.app/handleConsentement"
    # )

def start_conversation(call_connection_id, callerId):
    global caller
    caller = callerId
    
    # get_consentement(caller)

    play_source = TextSource(
        text="Pour des raisons de qualité et de suivi, cet appel peut être enregistré.", source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural"
    )

    call_automation_client.get_call_connection(call_connection_id).play_media_to_all(
        play_source=play_source
    )

    play_source = TextSource(
        text="Bonjour! Je suis Lyrae, l'assistante vocale du centre de radiologie. Je suis un agent conversationnel automatisé. Je peux prendre, modifier ou annuler vos rendez-vous, ainsi que vous fournir des informations. Comment puis-je vous aider aujourd’hui ?", source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural"
    )

    call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
        input_type=RecognizeInputType.SPEECH,
        target_participant=PhoneNumberIdentifier("+" + callerId.strip()),
        end_silence_timeout=0.5,
        play_prompt=play_source,
        interrupt_call_media_operation=False,
        interrupt_prompt=False,
        operation_context="start_conversation",
        speech_language="fr-FR",
        initial_silence_timeout=20,
        operation_callback_url="https://c5d0-2a01-cb00-844-1d00-95ba-5a9-b375-f641.ngrok-free.app/handleResponse"
    )

def speak(text):
    """
    Utilise Azure Text-to-Speech (TTS) pour dire à voix haute le texte et joue l'audio dans l'appel.
    Attend que la lecture audio soit terminée avant de continuer.

    Args:
        text (str): Le texte à convertir en parole.
        call_connection_id (str): L'ID de la connexion d'appel.
    """
    global call_connection_id
    play_source = TextSource(
        text=text, source_locale="fr-FR", voice_name="fr-FR-VivienneMultilingualNeural"
    )

    call_automation_client.get_call_connection(call_connection_id).play_media_to_all(
        play_source=play_source
    )

########## XPLORE API ##########
async def get_soustype_exam(type_exam):
    url = "https://sandbox.xplore.fr:20443/XaPriseRvGateway/Application/api/External/GetListeExamensFromTypeExamen"

    headers = {
        "Content-Type": "application/json"
    }

    if type_exam == "ECHOGRAPHIE":
        result = 'EC'
    elif type_exam == "RADIO":
        result = 'RX'
    elif type_exam == "SCANNER":
        result = 'CT'
    elif type_exam == "Mammographie":
        result = 'MG'

    payload = {"id": result}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response.raise_for_status() 
                data = await response.json()
                print(data)
                return data.get("data")[0].get("code")
    except aiohttp.ClientError as e:
        print(f"Erreur lors de l'appel au modèle : {e}")
        return "Erreur lors de la communication avec le modèle."

########## DATABASE ##########
# CALLER & CALLER ID NOT NEEDED
def find_patient(callerId, retries = 0):
    global birthdate
    global lastname
    global firstname
    global caller
    caller = callerId
    # if (lastname is None or firstname is None or birthdate == None) and retries < 3:
    #     time.sleep(1)
    #     find_patient(retries + 1)
    
    # results = collection.find({
    #     "dateNaissance": {
    #         "$regex": f"^{birthdate}"
    #     },
    #     "nom": {
    #         "$regex": f"^{lastname}$", 
    #         "$options": "i"  # Case-insensitive
    #     },
    #     "prenom": {
    #         "$regex": f"^{firstname}$", 
    #         "$options": "i"  # Case-insensitive
    #     }
    # })

    # json_results = dumps(list(results), indent=4)
    
    # if not json_results:
    #     speak("Je n'ai pas pu vous identifier. Désolé.")
    # else:
    play_source = TextSource(text="J'ai pu vous identifier. Pour quel type d'examen souhaitez-vous prendre rendez-vous ?", voice_name="fr-FR-VivienneMultilingualNeural")
    # play_source = TextSource(text="Oui", voice_name="fr-FR-VivienneMultilingualNeural")

    call_automation_client.get_call_connection(call_connection_id).start_recognizing_media(
        input_type=RecognizeInputType.SPEECH,
        target_participant=PhoneNumberIdentifier("+" + caller.strip()), 
        end_silence_timeout=1,
        play_prompt=play_source,
        interrupt_prompt=False,
        speech_language="fr-FR",
        initial_silence_timeout=10,
        operation_context="prise_rdv",
        operation_callback_url="https://c5d0-2a01-cb00-844-1d00-95ba-5a9-b375-f641.ngrok-free.app/rdv_exam_type"
    )
    # speak("trouvé")
# def get_creneaux_async():

if __name__ == "__main__":
    app.run(port=5000, debug=True)
