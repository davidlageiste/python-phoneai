from tkinter import N
from azure.communication.callautomation import CallAutomationClient, RecognizeInputType, PhoneNumberIdentifier
from azure.storage.blob import BlobServiceClient
import azure.cognitiveservices.speech as speechsdk
from flask import Flask, request, jsonify
import requests
import asyncio
import aiohttp
from pymongo import MongoClient
from bson.json_util import dumps
from datetime import datetime, timedelta
import logging
import unicodedata
import re 
from utils.tts import text_to_speech, generate_text_to_speech
from utils.recorded_audio import recorded_audios_keys
from num2words import num2words

COGNITIVE_SERVICE_ENDPOINT = "https://lyraecognitivesservicesus.cognitiveservices.azure.com"
SPEECH_KEY='CwdBzhR9vodZ5lXf4S52ErZaUy9eUG05JJCtDuu4xjjL5rylozVFJQQJ99BAAC5T7U2XJ3w3AAAAACOGuWEK'
SPEECH_REGION='eastus'
MONGO_URL='mongodb+srv://lageistedavid:eaZOnmgtcNN1oGxU@cluster0.pjma4cx.mongodb.net/neuracorp'

app = Flask(__name__)

client = MongoClient(MONGO_URL)
db = client['neuracorp']
patientCollection = db['patientsDB']
rdvCollection = db["rdv"]

call_automation_client = CallAutomationClient.from_connection_string("endpoint=https://lyraetalktest.france.communication.azure.com/;accesskey=93iEbCDIKt4jKOkuGPgmOzhDBYKeKmCZJvxBt3ZGD7UOUVH56NzjJQQJ99BDACULyCpuAreVAAAAAZCS7YQ9")
speech_config = speechsdk.SpeechConfig(subscription=SPEECH_KEY,region=SPEECH_REGION)

global call_connection_id
global caller
global intent
global rdv_intent
global birthdate
global lastname
global firstname
global patient_email
global exam_id
global sous_type_id
global creneauDate
global all_creneaux
global chosen_creneau
global cancel_creneau
global annulation_phrase
global patient_rdv

global current_creneau_proposition
current_creneau_proposition = 0

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
patient_email = None
exam_id = None
sous_type_id = None

def convert_numbers_to_words_french(text):
    def convert_time(match):
        hours = int(match.group(1))
        minutes = int(match.group(2))
        if minutes == 0:
            return f"{num2words(hours, lang='fr')} heures"
        else:
            return f"{num2words(hours, lang='fr')} heures {num2words(minutes, lang='fr')}"

    text = re.sub(r'(\d{1,2})h(\d{2})', convert_time, text)

    def convert_number(match):
        number = int(match.group())
        return num2words(number, lang='fr')

    text = re.sub(r'\b\d+\b', convert_number, text)

    return text


french_months = {
    1: "janvier", 2: "février", 3: "mars", 4: "avril",
    5: "mai", 6: "juin", 7: "juillet", 8: "août",
    9: "septembre", 10: "octobre", 11: "novembre", 12: "décembre"
}

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

    return convert_numbers_to_words_french(f"Le {jour} {mois} {annee}")

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
        operation_callback_url=f"https://lyraeapi.azurewebsites.net{callback_url}"
    )

def hang_up(text):
    play_source = text_to_speech("file_source", text)

    call_automation_client.get_call_connection(call_connection_id).play_media_to_all(
        play_source=play_source,
        operation_context="hang_up"
    )

def countPatientInDB(query):
    count = patientCollection.count_documents(query)
    return count

def findPatientInDB(query):
    results = patientCollection.find_one(query)
    
    return results

########## ENTRY POINT ##########

@app.route("/incoming_call", methods=["POST"])
def incoming_call():
    # Azure code de vérification
    if request.json and request.json[0].get("eventType") == "Microsoft.EventGrid.SubscriptionValidationEvent":
        validation_code = request.json[0]["data"]["validationCode"]
        return jsonify({"validationResponse": validation_code}), 200

    data = request.json[0]
    caller = data.get("data").get("from").get("phoneNumber").get("value")
    encodedContext = data.get("data").get("incomingCallContext")

    call_automation_client.answer_call(incoming_call_context=encodedContext, callback_url=f"https://lyraeapi.azurewebsites.net/callback?caller={caller}", cognitive_services_endpoint=COGNITIVE_SERVICE_ENDPOINT)
    return jsonify({"status": "success"})

@app.route("/callback", methods=["POST"])
async def callback():
    global call_connection_id
    global intent
    global rdv_intent
    global lastname
    global firstname
    global birthdate
    global patient_email

    print(request.json[0].get("type"))
    data = request.json[0]

    if request.json and request.json[0].get("type") == "Microsoft.Communication.CallDisconnected":
        lastname = None
        firstname = None
        birthdate = None
        patient_email = None
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

        # target = PhoneNumberIdentifier("+33801150143")

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

            play_source = text_to_speech("file_source", "Je n'ai pas compris, pouvez-vous répéter votre prénom ?")
            start_recognizing("/get_firstname", "get_firstname", play_source)
        else:
            clean_firstname = user_response.replace(".", "")
            task_get_firstname = asyncio.create_task(get_firstname_async(user_response=clean_firstname))
            speak("Très bien")

            await asyncio.sleep(1)

            firstname = await task_get_firstname
            clean_firstname = firstname.strip().strip()

            if clean_firstname is None or clean_firstname == "Erreur lors de la communication avec le modèle.":
                    firstname_error += 1
                    if firstname_error > 2:
                        hang_up("Il semblerait que nous n'arrivons pas à nous comprendre. Je vous transfère vers une secrétaire.")
                    play_source = text_to_speech("file_source", "Je n'ai pas compris, pouvez-vous répéter votre prénom ?")
                    start_recognizing("/get_firstname", "get_firstname", play_source)

            else: 
                play_source = text_to_speech("file_source", f"{clean_firstname}, c'est bien ça ?")
                start_recognizing("/confirm_firstname", "confirm_firstname", play_source)

    elif request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeFailed":
        firstname_error += 1
        if firstname_error > 2:
            hang_up("Il semblerait que nous n'arrivons pas à nous comprendre. Je vous transfère vers une secrétaire.")
            
        play_source = text_to_speech("file_source", "Je n'ai pas compris, pouvez-vous répéter votre prénom ?")
        start_recognizing("/get_firstname", "get_firstname", play_source)

    return jsonify({"success": "success"})

@app.route("/get_lastname", methods=["POST"])
async def get_lastname():
    global lastname
    global lastname_error

    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "get_lastname":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        # Remove every "." that comes from the AI response

        speak("Merci")
        clean_name = user_response.replace(".", "")
        task_get_lastname = asyncio.create_task(get_lastname_async(user_response=clean_name))
        lastname = await task_get_lastname

        lastname = lastname
        if clean_name is None:
            if lastname_error > 2:
                play_source = text_to_speech("fixed_file_source", "misunderstand_unfortunately")

                call_automation_client.get_call_connection(call_connection_id).play_media_to_all(
                    play_source=play_source,
                    operation_context="hang_up"
                )

            lastname_error += 1
            play_source = text_to_speech("fixed_file_source", "repeat_lastname")
            start_recognizing("/get_lastname", "get_lastname", play_source)

        else:
            lastname = clean_name
            play_source = text_to_speech("file_source", f"{lastname}, c'est bien ça ?")
            start_recognizing("/confirm_lastname", "confirm_lastname", play_source)

    elif request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeFailed" and request.json[0].get("data").get("operationContext") == "get_lastname":
        play_source = text_to_speech("fixed_file_source", "repeat_lastname")
        start_recognizing("/get_lastname", "get_lastname", play_source)
        
    return jsonify({"success": "success"})

@app.route("/get_birthdate", methods=["POST"])
async def get_birthdate():
    global birthdate

    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "get_birthdate":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_get_birthdate = asyncio.create_task(get_birthdate_async(user_response=user_response))
        # speak("Merci, un instant s'il vous plaît")

        birthdate = await task_get_birthdate

        if birthdate is None or is_date_formatted(birthdate) == False:
            play_source = text_to_speech("fixed_file_source", "repeat_birthdate")
            start_recognizing("/get_birthdate", "get_birthdate", play_source)
        else:
            date_litterale = date_vers_litteral(birthdate)
            print(date_litterale)
            # Formatage en version littérale 
            play_source = text_to_speech("file_source", f"Vous confirmez que vous êtes né {date_litterale} ?")
            start_recognizing("/confirm_birthdate", "confirm_birthdate", play_source)

    elif request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeFailed":
        play_source = text_to_speech("fixed_file_source", "repeat_birthdate")
        start_recognizing("/get_birthdate", "get_birthdate", play_source)

    return jsonify({"success": "success"})

########## CONFIRMATION ##########

@app.route("/confirm_creneau", methods=["POST"])
async def confirm_creneau():
    global all_creneaux
    global current_creneau_proposition
    global chosen_creneau

    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "confirm_creneau":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_model_response = asyncio.create_task(get_positive_negative_async(user_response))
        speak("ok")        
        model_response = await task_model_response
        if model_response == "négative":
            current_creneau_proposition += 1
            if current_creneau_proposition < len(all_creneaux):
                text = build_single_date_phrase(creneau=all_creneaux, index=current_creneau_proposition)
                play_source = text_to_speech("file_source", text)
                start_recognizing("/confirm_creneau", "confirm_creneau", play_source)
            else:
                current_creneau_proposition = 0
                last_key = sorted(all_creneaux.keys(), key=int)[-1]
                last_entry = all_creneaux[last_key]

                # Extract date and time
                date_str = last_entry["date"][:10]
                time_str = last_entry["heureDebut"]

                # Combine into full ISO datetime string
                datetime_str = f"{date_str}T{time_str}:00"
                dt = datetime.fromisoformat(datetime_str)

                # Add one day
                dt_plus_one = dt + timedelta(days=1)

                # Convert back to string if needed
                new_datetime_str = dt_plus_one.isoformat()
                task_creneaux = asyncio.create_task(get_creneaux_async(sous_type=sous_type_id, exam_type=exam_id, date_start=new_datetime_str))
                speak("Je vais vous chercher d'autres créneaux libres.")

                await asyncio.sleep(1)

                creneaux = await task_creneaux
                all_creneaux = creneaux
                text = build_single_date_phrase(creneau=all_creneaux, index=current_creneau_proposition)
                play_source = text_to_speech("file_source", text)
                start_recognizing("/confirm_creneau", "confirm_creneau", play_source)
                
        elif model_response == "positive":
            chosen_creneau = all_creneaux[str(current_creneau_proposition + 1)]
            if lastname is not None or firstname is not None or birthdate is not None:
                await find_patient()
            else:
                play_source = text_to_speech("fixed_file_source", "ask_birthdate2")
                start_recognizing("/get_birthdate", "get_birthdate", play_source)
        else:
            text = build_single_date_phrase(creneau=all_creneaux, index=current_creneau_proposition)
            play_source = text_to_speech("file_source", "Pardonnez moi, je n'ai pas compris." + text)
            start_recognizing("/confirm_creneau", "confirm_creneau", play_source)
    elif request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "modification":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_model_response = asyncio.create_task(get_positive_negative_async(user_response))
        speak("ok")        
        model_response = await task_model_response
        if model_response == "négative":
            current_creneau_proposition += 1
            if current_creneau_proposition < len(all_creneaux):
                text = build_single_date_phrase(creneau=all_creneaux, index=current_creneau_proposition)
                play_source = text_to_speech("file_source", text)
                start_recognizing("/confirm_creneau", "modification", play_source)
            else:
                current_creneau_proposition = 0
                last_key = sorted(all_creneaux.keys(), key=int)[-1]
                last_entry = all_creneaux[last_key]

                # Extract date and time
                date_str = last_entry["date"][:10]
                time_str = last_entry["heureDebut"]

                # Combine into full ISO datetime string
                datetime_str = f"{date_str}T{time_str}:00"
                dt = datetime.fromisoformat(datetime_str)

                # Add one day
                dt_plus_one = dt + timedelta(days=1)

                # Convert back to string if needed
                new_datetime_str = dt_plus_one.isoformat()
                task_creneaux = asyncio.create_task(get_creneaux_async(sous_type=sous_type_id, exam_type=exam_id, date_start=new_datetime_str))
                speak("Je vais vous chercher d'autres créneaux libres.")

                await asyncio.sleep(1)
                
                creneaux = await task_creneaux
                all_creneaux = creneaux
                text = build_single_date_phrase(creneau=all_creneaux, index=current_creneau_proposition)
                play_source = text_to_speech("file_source", text)
                start_recognizing("/confirm_creneau", "modification", play_source)
        elif model_response == "positive":
            chosen_creneau = all_creneaux[str(current_creneau_proposition + 1)]

            dt = datetime.fromisoformat(chosen_creneau)

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
                    play_source = text_to_speech("file_source", f"Vous avez choisi le {phrase}. Puis-je avoir votre date de naissance ?")
                    start_recognizing("/get_birthdate", "get_birthdate", play_source)
                    
                elif rdv_intent == "modification de rendez-vous" or rdv_intent == "modification de rendez-vous":
                    speak(f"Très bien, votre rendez-vous sera déplacé au {phrase}")
                    editRDV()
        else:
            text = build_single_date_phrase(creneau=all_creneaux, index=current_creneau_proposition)
            play_source = text_to_speech("file_source", "Pardonnez moi, je n'ai pas compris." + text)
            start_recognizing("/confirm_creneau", "confirm_creneau", play_source)
    return jsonify({"success": "success"})

@app.route("/confirm_firstname", methods=["POST"])
async def confirm_firstname():
    global firstname_error
    global firstname
    global lastname
    global birthdate

    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "confirm_firstname":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_model_response = asyncio.create_task(get_positive_negative_async(user_response))
        speak("ok")

        await asyncio.sleep(1)
        
        model_response = await task_model_response

        if model_response == "négative":
            firstname_error += 1
            if firstname_error > 2:
                hang_up("Malheureusement, il semblerait que nous n'arrivons pas à nous comprendre. Je vais vous rediriger vers une secrétaire afin de pouvoir accéder a vos requêtes.")

            play_source = text_to_speech("file_source", "Désolé, pouvez-vous me répéter votre prénom ?")
            start_recognizing("/get_firstname", "get_firstname", play_source)

        elif model_response == "positive":
            # speak("Très bien, merci")
            await find_patient()
            return jsonify({"success": "success"})
        
        else: 
            play_source = text_to_speech("file_source", f"Je n'ai pas compris, {firstname}, c'est bien ça ?")
            start_recognizing("/confirm_firstname", "confirm_firstname", play_source)

    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeFailed":
        play_source = text_to_speech("file_source", f"Je n'ai pas compris, {firstname}, c'est bien ça ?")
        start_recognizing("/confirm_firstname", "confirm_firstname", play_source)

    return jsonify({"success": "success"})

@app.route("/confirm_lastname", methods=["POST"])
async def confirm_lastname():
    global lastname_error
    global lastname
    global firstname

    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_model_response = asyncio.create_task(get_positive_negative_async(user_response))
        speak("ok")

        await asyncio.sleep(1)
        
        model_response = await task_model_response

        if model_response == "négative":
            lastname_error += 1
            if lastname_error > 2:
                play_source = text_to_speech("fixed_file_source", "misunderstand_unfortunately")
                call_automation_client.get_call_connection(call_connection_id).play_media_to_all(
                    play_source=play_source,
                    operation_context="hang_up"
                )

            play_source = text_to_speech("fixed_file_source", "spell_lastname2")
            start_recognizing("/get_lastname", "get_lastname", play_source)

        elif model_response == "positive":
            count = countPatientInDB({
                "dateNaissance": {
                    "$regex": f"^{birthdate + 'T00:00:00'}$"
                },
                "nom": {
                    "$regex": f"^{lastname}$",
                    "$options": "i"  # Case-insensitive
                }
            })

            if count > 1 or count == 0:
                play_source = text_to_speech("fixed_file_source", "ask_firstname")
                start_recognizing("/get_firstname", "get_firstname", play_source)

                return jsonify({"success": "success"})
            else:
                patient = findPatientInDB({
                    "dateNaissance": {
                        "$regex": f"^{birthdate + 'T00:00:00'}$"
                    },
                    "nom": {
                        "$regex": f"^{lastname}$",
                        "$options": "i"  # Case-insensitive
                    }
                })
                date_litterale = date_vers_litteral(birthdate)
                play_source = text_to_speech("file_source", f"{patient.get('nom')} {patient.get('prenom')} né {date_litterale} c'est bien vous ?")
                lastname = patient.get("nom")
                firstname = patient.get("prenom")
                start_recognizing(callback_url="/confirm_identity", play_source=play_source, context="confirm_identity")

        else:
            play_source = text_to_speech("file_source", f"Je n'ai pas compris, {lastname}, c'est bien ça ?")
            start_recognizing("/confirm_lastname", "confirm_lastname", play_source)
    return jsonify({"success": "success"})

@app.route("/confirm_annulation", methods=["POST"])
async def confirm_annulation():
    global cancel_creneau
    global annulation_phrase

    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_model_response = asyncio.create_task(get_positive_negative_async(user_response))
        speak("ok")

        await asyncio.sleep(1)
        
        model_response = await task_model_response
        
        if model_response == "négative":
            play_source = text_to_speech("file_source", annulation_phrase)
            start_recognizing("/get_creneaux_choice", "annulation", play_source)
        elif model_response == "positive":
            speak("Patientez un instant.")

            await asyncio.sleep(1)
            
            deletion = deleteRDV(cancel_creneau["idExamen"])
            if deletion is True :
                play_source = text_to_speech("file_source", "Votre rendez-vous a bien été supprimé. Puis-je faire autre chose pour vous ?")
                start_recognizing("/handleResponse", "end_conversation", play_source)
            else:
                hang_up("J'ai eu un problème lors de la suppression de votre rendez-vous. Je vous transfère vers une secrétaire.")
        else:
            date_str = cancel_creneau['datePrevue'][:10]
            time_str = cancel_creneau['heurePrevue']
            
            play_source = text_to_speech("file_source", f"Je n'ai pas compris, voulez-vous annuler le rendez-vous du {date_str} à {time_str} ?")
            start_recognizing("/confirm_annulation", "annulation", play_source)
    elif request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeFailed":
        date_str = cancel_creneau['datePrevue'][:10]
        time_str = cancel_creneau['heurePrevue']

        play_source = text_to_speech("file_source", f"Je n'ai pas compris, voulez-vous annuler le rendez-vous du {date_str} à {time_str} ?")
        start_recognizing("/confirm_annulation", "annulation", play_source)
    return jsonify({"success": "success"})

@app.route("/confirm_birthdate", methods=["POST"])
async def confirm_birthdate():
    global birthdate_error
    global lastname
    global firstname
    
    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "confirm_birthdate":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_model_response = asyncio.create_task(get_positive_negative_async(user_response))
        speak("ok")

        await asyncio.sleep(1)
        
        model_response = await task_model_response

        if model_response == "négative":
            birthdate_error += 1
            if birthdate_error > 2:
                play_source = text_to_speech("fixed_file_source", "misunderstand_unfortunately")
                call_automation_client.get_call_connection(call_connection_id).play_media_to_all(
                    play_source=play_source,
                    operation_context="hang_up"
                )

            play_source = text_to_speech("fixed_file_source", "repeat_birthdate2")
            start_recognizing("/get_birthdate", "get_birthdate", play_source)

        elif model_response == "positive":

            count = countPatientInDB({
                "dateNaissance": {
                    "$regex": f"^{birthdate + 'T00:00:00'}$"
                }
            })

            if count > 1 or count == 0:
                play_source = text_to_speech("fixed_file_source", "spell_lastname")
                start_recognizing("/get_lastname", "get_lastname", play_source)
            else:
                patient = findPatientInDB({
                    "dateNaissance": {
                        "$regex": f"^{birthdate + 'T00:00:00'}$"
                    }
                })

                date_litterale = date_vers_litteral(birthdate)
                play_source = text_to_speech("file_source", f"{patient.get('nom')} {patient.get('prenom')} né {date_litterale} c'est bien vous ?")
                lastname = patient.get("nom")
                firstname = patient.get("prenom")
                start_recognizing(callback_url="/confirm_identity", play_source=play_source, context="confirm_identity")

        else:
            date_litterale = date_vers_litteral(birthdate)

            # Formatage en version littérale
            play_source = text_to_speech("file_source", f"Vous confirmez que vous êtes né {date_litterale} ?")
            start_recognizing("/confirm_birthdate", "confirm_birthdate", play_source)

    elif request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeFailed":
        birthdate_error += 1
        if birthdate_error > 2:
            hang_up("Malheureusement, il semblerait que nous n'arrivons pas à nous comprendre. Je vais vous rediriger vers une secrétaire afin de pouvoir accéder a vos requêtes.")

        date_litterale = date_vers_litteral(birthdate)
        
        play_source = text_to_speech("file_source", f"Je n'ai pas entendu, Vous confirmez que vous êtes né {date_litterale} ?")
        start_recognizing("/confirm_birthdate", "confirm_birthdate", play_source)
    return jsonify({"success": "success"})

@app.route("/confirm_call_intent", methods=["POST"])
async def confirm_call_intent():
    global rdv_intent
    global intent_error

    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "confirm_call_intent":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_model_response = asyncio.create_task(get_positive_negative_async(user_response))
        speak("ok")

        await asyncio.sleep(1)
        
        model_response = await task_model_response

        if model_response == "négative":
            play_source = text_to_speech("fixed_file_source", "misunderstand_intent")
            start_recognizing("/handleResponse", "start_conversation", play_source)
            
        elif model_response == "positive":
            if rdv_intent == "prise de rendez-vous" or rdv_intent == "prise de rendez-vous.":
                handle_prise_rdv()
            elif rdv_intent == "modification de rendez-vous" or rdv_intent == "modification de rendez-vous.":
                if lastname is not None or firstname is not None or birthdate is not None:
                    await find_patient()
                else:
                    handle_modification()
            elif rdv_intent == "annulation de rendez-vous" or rdv_intent == "annulation de rendez-vous.":
                if lastname is not None or firstname is not None or birthdate is not None:
                    await find_patient()
                else:
                    handle_annulation()
            elif rdv_intent == "consultation de rendez-vous" or rdv_intent == "consultation de rendez-vous.":
                if lastname is not None or firstname is not None or birthdate is not None:
                    await find_patient()
                else:
                    handle_consultation()

        else:
            intent_error += 1
            if intent_error > 2:
                hang_up("Pardonnez moi, il semblerait que je n'arrive pas à vous comprendre. Je vous transfère vers une secrétaire.")
            
            text = "Pardonnez moi, je n'ai pas compris"
            if rdv_intent == "prise de rendez-vous" or rdv_intent == "prise de rendez-vous.":
                text += "Est-ce bien pour une prise de rendez-vous ?"
            elif rdv_intent == "modification de rendez-vous" or rdv_intent == "modification de rendez-vous.":
                text += "Est-ce bien pour une modification de rendez-vous ?"
            elif rdv_intent == "annulation de rendez-vous" or rdv_intent == "annulation de rendez-vous.":
                text += "Est-ce bien pour une annulation de rendez-vous ?"
            elif rdv_intent == "consultation de rendez-vous" or rdv_intent == "consultation de rendez-vous.":
                text += "Est-ce bien pour une consultation de rendez-vous ?"

            play_source = text_to_speech("file_source", text)
            start_recognizing("/confirm_call_intent", "confirm_call_intent", play_source)

    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeFailed":
        intent_error += 1
        if intent_error > 2:
            hang_up("Pardonnez moi, il semblerait que je n'arrive pas à vous comprendre. Je vous transfère vers une secrétaire.")

        play_source("file_source", f"Pardonnez moi, je n'ai pas entendu. Est-ce bien pour un ou une {rdv_intent} ?")
        start_recognizing("/confirm_call_intent", "confirm_call_intent", play_source)

    return jsonify({"success": "success"})

@app.route("/confirm_identity", methods=["POST"])
async def confirm_identity():
    global firstname
    global lastname
    global birthdate

    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "confirm_identity":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_model_response = asyncio.create_task(get_positive_negative_async(user_response))
        speak("ok")

        await asyncio.sleep(1)
        
        model_response = await task_model_response
        
        if model_response == "négative":
            hang_up("Désolé, je ne peux pas donner de rendez-vous à un patient qui n'est pas déjà connu du cabinet. Vous êtes un nouveau patient : Je vous propose de vous transférer à la secrétaire")
        elif model_response == "positive":
            speak("Très bien, laissez moi un instant.")

            await asyncio.sleep(1)
            
            await find_patient()
        else:
            date_litterale = date_vers_litteral(birthdate)
            play_source = text_to_speech("file_source", f"Désolé, je n'ai pas compris, vous êtes bien {lastname} {firstname}. Né {date_litterale} ?")
            start_recognizing("/confirm_identity", "confirm_identity", play_source=play_source)
    return jsonify({"success": "success"})

@app.route("/transfer_to_secretary", methods=["POST"])
async def transfer_to_secretary():
    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_model_response = asyncio.create_task(get_positive_negative_async(user_response))
        speak("C'est noté.")
        model_response = await task_model_response
        if model_response == "négative":
            hang_up("A bientôt j'espère !")
        elif model_response == "positive":
            hang_up("Je transmets votre appel")
        else:
            play_source = text_to_speech("file_source", "Pardonnez-moi, je n'ai pas compris. Dois-je vous rediriger vers une secrétaire ?")
            start_recognizing("/transfer_to_secretary", "transfer_to_secretary", play_source)
    return jsonify({"success": "success"})

########## PRISE DE RENDEZ-VOUS ##########

@app.route("/module_informatif", methods=["POST"])
async def module_informatif():
    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "module_informatif":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        task = asyncio.create_task(get_model_response_async(user_response))
        model_response = await task
        speak(model_response)

        play_source = text_to_speech("file_source", "Puis-je faire autre chose pour vous ?")
        start_recognizing("/handleResponse", "end_conversation", play_source)

    return jsonify({"success", "success"})

@app.route("/confirm_rdv", methods=["POST"])
async def confirm_rdv():
    global type_exam_error
    global exam_id
    global sous_type_id
    global all_creneaux

    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "confirm_rdv":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_model_response = asyncio.create_task(get_positive_negative_async(user_response))
        # speak("ok")
        
        model_response = await task_model_response

        if model_response == "négative":
            exam_id = None
            sous_type_id = None
            if type_exam_error <= 2:
                play_source = text_to_speech("fixed_file_source", "repeat_exam_type")
                start_recognizing("/rdv_exam_type", "rdv_exam_type", play_source)
            else:
                hang_up("Malheureusement, il semblerait que nous n'arrivons pas à nous comprendre. Je vais vous rediriger vers une secrétaire afin de pouvoir accéder a vos requêtes.")
        elif model_response == "positive":
            task_creneaux = asyncio.create_task(get_creneaux_async(sous_type=sous_type_id, exam_type=exam_id))
            speak("Je regarde les disponibilités, un instant...")

            await asyncio.sleep(1)
            
            creneaux = await task_creneaux

            print(creneaux)

            all_creneaux = creneaux

            text = build_single_date_phrase(creneau=creneaux)
            play_source = text_to_speech("file_source", text)
            start_recognizing("/confirm_creneau", "confirm_creneau", play_source)
        else:
            play_source = text_to_speech("fixed_file_source", "misunderstand_exam_type")
            start_recognizing("/rdv_exam_type", "rdv_exam_type", play_source)
            
    elif request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeFailed":
        play_source = text_to_speech("fixed_file_source", "repeat_exam_type2")
        start_recognizing("/rdv_exam_type", "rdv_exam_type", play_source) 
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
        # speak("ok")
        exam_type = await task_type

        if exam_type["type_examen"] is not None and exam_type["code_examen_id"] is None:
            hang_up("Désolé, il semblerait qu'il y ait un problème sur ce type d'examen. Je vais vous rediriger vers une secrétaire.")
        elif exam_type["type_examen"] == None or exam_type["code_examen"] == None:
            play_source = text_to_speech("fixed_file_soure", "repeat_exam_type3")
            start_recognizing("/rdv_exam_type", "rdv_exam_type", play_source)
        else :
            exam_id = exam_type["type_examen_id"]
            sous_type_id = exam_type["code_examen_id"]
            
            play_source = text_to_speech("file_source", f"Vous m'avez dit {exam_type['code_examen']}, c'est ça ?")
            start_recognizing("/confirm_rdv", "confirm_rdv", play_source)

    return jsonify({"status": "success"})

@app.route("/get_creneaux_choice", methods=["POST"])
async def get_creneaux_choice():
    global creneauDate
    global all_creneaux
    global chosen_creneau
    global call_connection_id
    global rdv_intent
    global annulation_phrase
    global patient_rdv
    global cancel_creneau

    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "get_creneaux_choice":
        user_response = request.json[0].get("data").get("speechResult").get("speech")

        task_creneau_choice = asyncio.create_task(extract_creneau_async(user_response=user_response))

        speak("D'accord, patientez pendant que je vous réserve ce créneau.")

        await asyncio.sleep(1)
        
        creneau_choice = await task_creneau_choice

        if creneau_choice is None:
            text = build_multiple_dates_phrase(creneaux=all_creneaux)

            play_source = text_to_speech("file_source", f"Je n'ai pas compris le créneau que vous avez choisi. {text}")
            start_recognizing("/get_creneaux_choice", "get_creneaux_choice", play_source)
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
                    play_source = text_to_speech("file_source", f"Vous avez choisi le {phrase}. Puis-je avoir votre date de naissance ?")
                    start_recognizing("/get_birthdate", "get_birthdate", play_source)

            else:
                text = build_multiple_dates_phrase(creneaux=all_creneaux)
                play_source = text_to_speech("file_source", f"Je n'ai pas compris le créneau que vous avez choisi. {text}")
                start_recognizing("/get_creneaux_choice", "get_creneaux_choice", play_source)

    elif request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "modification":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_creneau_choice = asyncio.create_task(extract_creneau_async(user_response=user_response))
        speak("D'accord, patientez pendant que je vous réserve ce créneau.")

        await asyncio.sleep(1)
        
        creneau_choice = await task_creneau_choice

        if creneau_choice is None:
            text = build_multiple_dates_phrase(creneaux=all_creneaux)

            play_source = text_to_speech("file_source", f"Je n'ai pas compris le créneau que vous avez choisi. {text}")
            start_recognizing("/get_creneaux_choice", "get_creneaux_choice", play_source)
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
                    play_source = text_to_speech("file_source", f"Vous avez choisi le {phrase}. Puis-je avoir votre date de naissance ?")
                    start_recognizing("/get_birthdate", "get_birthdate", play_source)
                    
                elif rdv_intent == "modification de rendez-vous" or rdv_intent == "modification de rendez-vous":
                    speak(f"Très bien, votre rendez-vous sera déplacé au {phrase}")
                    editRDV()

            else:
                text = build_multiple_dates_phrase(creneaux=all_creneaux)
                play_source = text_to_speech("file_source", f"Je n'ai pas compris le créneau que vous avez choisi. {text}")
                start_recognizing("/get_creneaux_choice", "get_creneaux_choice", play_source)


    elif request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "annulation":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_creneau_choice = asyncio.create_task(extract_creneau_async(user_response=user_response))
        # speak("ok")
        creneau_choice = await task_creneau_choice

        if creneau_choice is None:
            text = build_multiple_dates_phrase(creneaux=all_creneaux)
            
            play_source = text_to_speech("file_source", f"Je n'ai pas compris le rendez-vous que vous souhaitez annuler. {annulation_phrase}")
            start_recognizing("/get_creneaux_choice", "annulation", play_source)
        else:
            dt = datetime.fromisoformat(creneau_choice)

            matched_creneau = None
            for item in patient_rdv:
                full_datetime_str = item['datePrevue'][:10] + 'T' + item['heurePrevue'] + ':00'
                current_dt = datetime.fromisoformat(full_datetime_str)
                if current_dt == dt:
                    matched_creneau = item
                    break
            if matched_creneau is not None:
                cancel_creneau = matched_creneau
                date_str = matched_creneau['datePrevue'][:10]
                time_str = matched_creneau['heurePrevue']
                
                play_source = text_to_speech("file_soure", f"Vous confirmez que vous voulez annuler votre rendez-vous du {date_str} à {time_str}")
                start_recognizing("/confirm_annulation", "annulation", play_source)
            else:
                play_source = text_to_speech("file_soure", f"Je n'ai pas compris le rendez-vous que vous souhaitez annuler. {annulation_phrase}")
                start_recognizing("/get_creneaux_choice", "annulation", play_source)

    elif request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeFailed":
        play_source = text_to_speech("file_source", f"Je n'ai pas compris le créneau que vous avez choisi. {text}")
        start_recognizing("/get_creneaux_choice", "get_creneaux_choice", play_source)
    
    return jsonify({"status": "success"})

@app.route("/handleResponse", methods=["POST"])
async def handleResponse():
    global rdv_intent
    global call_connection_id
    global caller
    global exam_id
    global sous_type_id

    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "start_conversation":
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
                play_source = text_to_speech("fixed_file_source", "question")
                start_recognizing("/module_informatif", "module_informatif", play_source)

            continue_conversation("more")
            return jsonify({"success": "success"})
        elif intent.lower() == "prise de rendez-vous" or intent.lower() == "prise de rendez-vous.":
            task_type = asyncio.create_task(get_exam_type_async(user_response=user_response))
            rdv_intent = intent.lower()
            # speak("ok")
            exam_type = await task_type
            if exam_type["type_examen"] is None:
                play_source = text_to_speech("file_source", "Vous voulez prendre rendez-vous, c'est bien ça ?")
            else:
                exam_id = exam_type["type_examen_id"]
                sous_type_id = exam_type["code_examen_id"]
                if sous_type_id is None:
                    hang_up("Désolé, je ne suis pas qualifiée pour vous donner un rendez-vous pour ce type d'examen. Je vous transfère vers une secrétaire.")
                else :
                    all_sous_type = get_sous_type_exam(exam_id)
                    sous_type = next((item for item in all_sous_type if item["code"] == sous_type_id), None)
                    play_source = text_to_speech("file_source", f"Vous voulez prendre rendez-vous pour un ou une {sous_type.get('libelle')}, c'est bien ça ?")
        elif intent.lower() == "modification de rendez-vous" or intent.lower() == "modification de rendez-vous.":
            rdv_intent = intent.lower()
            play_source = text_to_speech("file_source", "Vous voulez déplacer un rendez-vous, c'est bien ça ?")
        
        elif intent.lower() == "annulation de rendez-vous" or intent.lower() == "annulation de rendez-vous.":
            rdv_intent = intent.lower()
            play_source = text_to_speech("file_source", "Vous voulez annuler un rendez-vous, c'est bien ça ?")

        elif intent.lower() == "consultation de rendez-vous" or intent.lower() == "consultation de rendez-vous.":
            rdv_intent = intent.lower()
            play_source = text_to_speech("file_source", "Vous voulez consulter un rendez-vous, c'est bien ça ?")

        elif intent.lower() == "autre" or intent.lower() == "autre.":
            play_source = text_to_speech("file_source", "Je suis désolé, votre question n'entre pas dans mon champ de compétences, je vous passe un interlocuteur humain.")
            start_recognizing("/handleResponse", "start_conversation", play_source)

        else:
            play_source = text_to_speech("fixed_file_source", "misunderstand_intent2")
            start_recognizing("/handleResponse", "start_conversation", play_source)


            return jsonify({"succes": "success"})

        start_recognizing("/confirm_call_intent", "confirm_call_intent", play_source)
    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "end_conversation":
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
                play_source = text_to_speech("fixed_file_source", "question")
                start_recognizing("/module_informatif", "module_informatif", play_source)

            continue_conversation("more")
            return jsonify({"success": "success"})
        elif intent.lower() == "prise de rendez-vous" or intent.lower() == "prise de rendez-vous.":

            rdv_intent = intent.lower()
            play_source = text_to_speech("file_source", "Vous voulez prendre rendez-vous, c'est bien ça ?")

        elif intent.lower() == "modification de rendez-vous" or intent.lower() == "modification de rendez-vous.":
            rdv_intent = intent.lower()
            play_source = text_to_speech("file_source", "Vous voulez déplacer un rendez-vous, c'est bien ça ?")
        
        elif intent.lower() == "annulation de rendez-vous" or intent.lower() == "annulation de rendez-vous.":
            rdv_intent = intent.lower()
            play_source = text_to_speech("file_source", "Vous voulez annuler un rendez-vous, c'est bien ça ?")

        elif intent.lower() == "consultation de rendez-vous" or intent.lower() == "consultation de rendez-vous.":
            rdv_intent = intent.lower()
            play_source = text_to_speech("file_source", "Vous voulez consulter un rendez-vous, c'est bien ça ?")

        elif intent.lower() == "autre" or intent.lower() == "autre.":
            task_positive_negative = asyncio.create_task(get_positive_negative_async(user_response))
            positive_negative = await task_positive_negative

            if positive_negative == "positive":
                play_source = text_to_speech("file_source", "Voulez-vous prendre, annuler, consulter ou modifier un rendez vous ? Vous pouvez aussi simplement me poser une question.")
            elif positive_negative == "négative":
                hang_up("Très bien, merci pour votre appel !")
            
            start_recognizing("/handleResponse", "start_conversation", play_source)

        else:
            play_source = text_to_speech("fixed_file_source", "misunderstand_intent2")
            start_recognizing("/handleResponse", "start_conversation", play_source)


            return jsonify({"succes": "success"})

        start_recognizing("/confirm_call_intent", "confirm_call_intent", play_source)

    elif request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeFailed":
        play_source = text_to_speech("fixed_file_source", "misunderstand_intent2")
        start_recognizing("/handleResponse", "start_conversation", play_source)


    return jsonify({"success": "success"})

@app.route("/has_ordonnance", methods=["POST"])
async def has_ordonnance():
    global ordonnance_error
    global exam_id
    global sous_type_id
    global all_creneaux
    if request.json and request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted" and request.json[0].get("data").get("operationContext") == "has_ordonnance":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_model_response = asyncio.create_task(get_positive_negative_async(user_response))
        # speak("ok")
        model_response = await task_model_response

        if model_response == "négative":
            hang_up("Désolé nous pouvons pas vous planifier un rendez-vous sans ordonnance prescrite de votre médecin. Pour passer un examen d'imagerie, il faut avoir la prescription d'un médecin. Sans ordonnance, ce n'est pas possible. Pour avoir une ordonnance, je vous conseille de consulter un médecin. Je vous souhaite une excellente journée et à bientôt.")
        elif model_response == "positive":
            if exam_id is not None and sous_type_id is not None:
                task_creneaux = asyncio.create_task(get_creneaux_async(sous_type=sous_type_id, exam_type=exam_id))
                speak("Je regarde les disponibilités, un instant...")

                await asyncio.sleep(1)
                
                creneaux = await task_creneaux

                print(creneaux)

                all_creneaux = creneaux

                text = build_single_date_phrase(creneau=creneaux)
                play_source = text_to_speech("file_source", text)
                start_recognizing("/confirm_creneau", "confirm_creneau", play_source)
            else:
                play_source = text_to_speech("file_source", "Très bien, quel examen voulez vous passer ?")
                start_recognizing("/rdv_exam_type", "rdv_exam_type", play_source)
        else:
            play_source = text_to_speech("file_source", "Désolé, je n'ai pas compris, Avez-vous une ordonnance ?")
            start_recognizing("/has_ordonnance", "has_ordonnance", play_source)

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

async def get_creneaux_async(sous_type, exam_type, date_start=None):
    url = "https://sparkso-universite.com:8080/api/getCreneaux"
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

    if date_start is None:
        # Format it to match: 2025-04-18T00:00:00
        formatted = now.strftime("%Y-%m-%dT%H:%M:%S")
    else:
        print(date_start)
        formatted = date_start

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

async def get_positive_negative_async(user_response):
    url = "https://lyrae-talk-functions.azurewebsites.net/api/analyseur_reponse?code=z4qZo6X7c4gNDPlKhBoXs2IRV1Z1o4FM_FKRqcgpTJBNAzFu_W0gTA=="
    headers = {
        "Content-Type": "application/json"
    }

    payload = {
        "action": "positive_negative_reponse",
        "text": user_response
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response.raise_for_status()
                data = await response.json()
                model_response =data.get("response")
                return model_response
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
                return data.get("response", "Pas de réponse trouvée.")
    except aiohttp.ClientError as e:
        print(f"Erreur lors de l'appel au modèle : {e}")
        return "Erreur lors de la communication avec le modèle."

########## CONVERSATION ##########

def build_single_date_phrase(creneau, index=0):
    sorted_keys = sorted(creneau.keys(), key=lambda x: int(x))
    nb_slots = len(sorted_keys)
    if nb_slots == 0:
        final_sentence = "Je suis désolé, aucun créneau n'est disponible pour le moment."
    else:
        slot = creneau[str(index + 1)]
        date_obj = datetime.fromisoformat(slot["date"]).date()
        day = date_obj.day
        month_name = french_months[date_obj.month]
        date_str = f"{day} {month_name}"        
        heure = slot["heureDebut"]
        if index == 0:
            time_obj = datetime.strptime(heure, "%H:%M")
            hours = time_obj.hour
            minutes = time_obj.minute
            
            # Format as "8 heures" or "8 heures 15"
            if minutes == 0:
                heure = f"{hours} heures"
            else:
                heure = f"{hours} heures {minutes}"
            final_sentence = f"Je peux vous proposer le {date_str} à {heure}. Est-ce que cela vous convient ?"
        else:
            time_obj = datetime.strptime(heure, "%H:%M")
            hours = time_obj.hour
            minutes = time_obj.minute
            
            # Format as "8 heures" or "8 heures 15"
            if minutes == 0:
                heure = f"{hours} heures"
            else:
                heure = f"{hours} heures {minutes}"
            final_sentence = f"Est-ce que vous préférez le {date_str} à {heure} ?"

    final_sentence = convert_numbers_to_words_french(final_sentence)
    print("final_sentence", final_sentence)
    return final_sentence

def build_multiple_dates_phrase(creneaux, type=None):
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
    if type == "rdv":
        for idx, key in enumerate(sorted_keys, start=1):
            slot = data[key]
            date_obj = datetime.fromisoformat(slot["datePrevue"]).date()
            day = date_obj.day
            month_name = french_months[date_obj.month]
            date_str = f"{day} {month_name}" 
            heure = slot["heurePrevue"]
            time_obj = datetime.strptime(heure, "%H:%M")
            hours = time_obj.hour
            minutes = time_obj.minute
            
            # Format as "8 heures" or "8 heures 15"
            if minutes == 0:
                heure = f"{hours} heures"
            else:
                heure = f"{hours} heures {minutes}"
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
            final_sentence = f"Le {joined_phrases}"
    elif type == "annulation":
        for idx, key in enumerate(sorted_keys, start=1):
            slot = data[key]
            date_obj = datetime.fromisoformat(slot["datePrevue"]).date()
            date_str = date_obj.strftime("%d/%m")
            heure = slot["heurePrevue"]
            time_obj = datetime.strptime(heure, "%H:%M")
            hours = time_obj.hour
            minutes = time_obj.minute
            
            # Format as "8 heures" or "8 heures 15"
            if minutes == 0:
                heure = f"{hours} heures"
            else:
                heure = f"{hours} heures {minutes}"
            phrases.append(f"Celui du {date_str} à {heure}")
        
        # Assemble final sentence
        if nb_slots == 0:
            final_sentence = "Pardonnez-moi, il semblerait que vous n'ayez pas de rendez-vous de prévus."
        else:
            joined_phrases = ", ".join(phrases[:-1])
            if nb_slots > 1:
                joined_phrases += f" ou {phrases[-1]}"
            else:
                joined_phrases = phrases[0]
            final_sentence = f"{joined_phrases}"

    else:
        for idx, key in enumerate(sorted_keys, start=1):
            slot = data[key]
            date_obj = datetime.fromisoformat(slot["date"]).date()
            date_str = date_obj.strftime("%d/%m")
            heure = slot["heureDebut"]
            time_obj = datetime.strptime(heure, "%H:%M")
            hours = time_obj.hour
            minutes = time_obj.minute
            
            # Format as "8 heures" or "8 heures 15"
            if minutes == 0:
                heure = f"{hours} heures"
            else:
                heure = f"{hours} heures {minutes}"
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

    final_sentence = convert_numbers_to_words_french(final_sentence)
    return final_sentence

def continue_conversation(model_response):
    if model_response == "more":
        play_source = text_to_speech("fixed_file_source", model_response)
    else:
        play_source = text_to_speech("file_source", model_response)

    start_recognizing("/handleResponse", "end_conversation", play_source)

def handle_prise_rdv():
    play_source = text_to_speech("file_source", "Avez-vous une ordonannce ?")
    start_recognizing("/has_ordonnance", "has_ordonnance", play_source)

def handle_modification():
    play_source = text_to_speech("fixed_file_source", "ask_birthdate")
    start_recognizing("/get_birthdate", "get_birthdate", play_source)

def handle_consultation():
    play_source = text_to_speech("fixed_file_source", "ask_birthdate")
    start_recognizing("/get_birthdate", "get_birthdate", play_source)

def handle_annulation():
    play_source = text_to_speech("fixed_file_source", "ask_birthdate")
    start_recognizing("/get_birthdate", "get_birthdate", play_source)

def start_conversation(call_connection_id, callerId):
    global caller
    caller = callerId
    
    play_source = text_to_speech("fixed_file_source", "intro")

    # play_source = text_to_speech("file_source", "Oui ?")

    start_recognizing("/handleResponse", "start_conversation", play_source)

def speak(text):

    global call_connection_id

    if text in recorded_audios_keys:
        play_source = text_to_speech("fixed_file_source", text)
    else:
        play_source = text_to_speech("file_source", text)
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

    url = "https://sparkso-universite.com:8080/api/createRDV"
    
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
    url = "https://sparkso-universite.com:8080/api/getRDV"

    # results = list(rdvCollection.find({
    #     "idPatient": patientId
    # }))

    payload = {
        "idPatient": patientId
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()  # Raises HTTPError for bad status
        data = response.json()
        print("getRDV: ", data)
        return data.get("data")
    except requests.RequestException as e:
        print("Request failed:", e)
        return "Error occurred while creating RDV"

    # json_results = dumps(list(results), indent=4)
    # print(json_results)

    # return results

def editRDV():
    global chosen_creneau
    global cancel_creneau
    global firstname
    global lastname
    global birthdate
    global patient_email

    url = "https://sparkso-universite.com:8080/api/editRDV"

    payload = {
        "rdvId" : cancel_creneau.get("idExamen"),
        "externalUserNumber": "NEURACORP",
        "firstName": firstname,
        "lastName": lastname,
        "birthDate": birthdate,
        "email": patient_email,
        "newCreneau": chosen_creneau
    }
 
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.RequestException as e:
        print("Request failed:", e)
        return "Error occurred while creating RDV"
    

def deleteRDV(rdvId):
    global lastname
    global firstname
    global birthdate

    url = "https://sparkso-universite.com:8080/api/deleteRDV"
    payload = {
        "rdvId": rdvId,
        "externalUserNumber": "NEURACORP",
        "firstName": firstname,
        "lastName": lastname,
        "birthDate": birthdate
    }

    try:
        response = requests.delete(url, json=payload)
        response.raise_for_status()  # Raises HTTPError for bad status
        data = response.json()
        print("Suppression: ", data)
        return data
    except requests.RequestException as e:
        print("Request failed:", e)
        return "Error occurred while creating RDV"

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
    global patient_email
    global creneauDate
    global rdv_intent
    global all_creneaux
    global annulation_phrase
    global patient_rdv
    global cancel_creneau
    
    # speak("ok")
    # global exam_id
    # exam_id = "RX"
    # global sous_type_id
    # sous_type_id = "N01RXPOI"
    # global chosen_creneau
    # chosen_creneau = {
    #     "codeSite": "N01",
    #     "numeroPoste": "N01RX1",
    #     "date": "2025-05-09T00:00:00",
    #     "heureDebut": "08:30",
    #     "heureFin": "08:45",
    #     "codesMedecins": [
    #         "JRAC01",
    #         "CTOU01"
    #     ],
    #     "prescripteur": "N",
    #     "typeExamen": "RX",
    #     "codeExamen": "N01RXPOI"
    # }

    # global caller
    # caller = callerId
    # lastname = "DUBOIS"
    # firstname = "MELISSA"
    # birthdate = "1996-03-05"
    # global rdv_intent
    # rdv_intent = "consultation de rendez-vous"

    patient = patientCollection.find_one({
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

    print(patient)

    if patient:
        if rdv_intent == "prise de rendez-vous" or rdv_intent == "prise de rendez-vous.":
            speak("Ne quittez pas le temps que je confirme votre rendez-vous.")
            email = patient.get("email")
            patient_email = email
            # if first_result.get("externalNumber") is None:
            rdv = createRDV(email=email)
                
            if rdv.get("success") is True:

                rdvCollection.insert_one({
                    "idPatient": patient.get("idPatient"),
                    "numeroRDV": rdv.get("data").get("numeroExamen"),
                    "date": chosen_creneau.get("date"),
                    "heure": chosen_creneau.get("heureDebut"),
                    "typeExamen": exam_id,
                    "codeExamen": sous_type_id
                })
                phrase_creneau = full_date_vers_litteral(chosen_creneau.get("date").split("T")[0] + "T" + chosen_creneau.get("heureDebut") + ":00")

                speak(f"Parfait, vous avez donc rendez-vous {phrase_creneau} au nom de {lastname}.")
                continue_conversation("Puis-je faire autre chose pour vous ?")
            else:
                hang_up("Désolé, je n'ai pas pu valider votre rendez-vous. Je vais vous rediriger vers une secrétaire.")
        elif rdv_intent == "modification de rendez-vous" or rdv_intent == "modification de rendez-vous." or rdv_intent == "consultation de rendez-vous" or rdv_intent == "consultation de rendez-vous.":
            planned_rdv = getRDV(patient.get("idPatient"))
            if(patient.get("externalID", None) is not None):
                planned_rdv_external = getRDV(patient.get("externalID"))
                planned_rdv = planned_rdv + planned_rdv_external

            now = datetime.now()
            print(now)
            future_rdvs = [
                rdv for rdv in planned_rdv
                if datetime.strptime(f"{rdv['datePrevue'][:10]}T{rdv['heurePrevue']}", "%Y-%m-%dT%H:%M") >= now
            ]
            if len(future_rdvs) == 0:
                speak("Il semblerait que vous n'ayez pas de rendez-vous prévus ces prochains jours.")
                play_source = text_to_speech("file_source", "Puis-je faire autre chose pour vous ?")
                start_recognizing("/handleResponse", "end_conversation", play_source)

            elif len(future_rdvs) == 1:
                speak("J'ai en effet trouvé un rendez-vous à votre nom.")
                
                cancel_creneau = future_rdvs[0]
                print("FUTURE", future_rdvs[0])
                dt = datetime.fromisoformat(future_rdvs[0].get("datePrevue").split("T")[0] + "T" + future_rdvs[0].get("heurePrevue"))
                formatted_date = f"le {dt.day} {french_months[dt.month]} {dt.year}"
                hours, minutes = future_rdvs[0].get("heurePrevue").split(":")

                all_sous_type = get_sous_type_exam(future_rdvs[0].get("typeExamen"))
                sous_type = next((item for item in all_sous_type if item["code"] == future_rdvs[0].get("codeExamen")), None)

                speak(f"Vous avez rendez-vous {formatted_date} à {int(hours)} heure {int(minutes)} pour un ou une {sous_type.get('libelle')}.")

                if rdv_intent == "modification de rendez-vous" or rdv_intent.lower() == "modification de rendez-vous.":
                    task_creneaux = asyncio.create_task(get_creneaux_async(sous_type=future_rdvs[0].get("codeExamen"), exam_type=future_rdvs[0].get("typeExamen")))
                    speak("Je vais chercher des nouveaux créneaux disponibles pour votre examen.")
                    creneaux = await task_creneaux
                    all_creneaux = creneaux
                    text = build_single_date_phrase(creneau=all_creneaux, index=current_creneau_proposition)
                    play_source = text_to_speech("file_source", text)
                    start_recognizing("/confirm_creneau", "modification", play_source)
                    # text = build_multiple_dates_phrase(creneaux=creneaux)
                    # play_source = text_to_speech("file_source", text)
                    # start_recognizing("/get_creneaux_choice", "modification", play_source)
                    return ("ok")
                play_source = text_to_speech("file_source", "Puis-je faire autre chose pour vous ?")
                start_recognizing("/handleResponse", "end_conversation", play_source)
            else:
                if len(future_rdvs) > 0:
                    speak("En effet, j'ai bien trouvé plusieurs rendez-vous à votre nom.")
                    sorted_rdvs = sorted(
                        future_rdvs,
                        key=lambda x: f"{x['datePrevue'][:10]}T{x['heurePrevue']}"
                    )
                    text = build_multiple_dates_phrase({i + 1: item for i, item in enumerate(sorted_rdvs)}, "rdv")
                    speak(text)
                    continue_conversation("Puis-je faire autre chose pour vous ?")
                else :
                    speak("Il semblerait que vous n'ayez pas de rendez-vous prévu dans le futur.")
                    play_source = text_to_speech("file_source", "Voulez-vous que je vous transfère vers une secrétaire pour avoir plus de détails ?")
                    start_recognizing("/transfer_to_secretary", "transfer_to_secretary", play_source)               
        elif rdv_intent == "annulation de rendez-vous" or rdv_intent == "annulation de rendez-vous.":
            speak("Donnez-moi un instant le temps que je trouve vos rendez-vous.")
            
            await asyncio.sleep(1)
            
            planned_rdv = getRDV(patient.get("idPatient"))
            if(patient.get("externalID", None) is not None):
                planned_rdv_external = getRDV(patient.get("externalID"))
                print("planned_rdv_external", planned_rdv_external)
                planned_rdv = planned_rdv + planned_rdv_external
            now = datetime.now()
            future_rdvs = [
                rdv for rdv in planned_rdv
                if datetime.strptime(f"{rdv['datePrevue'][:10]}T{rdv['heurePrevue']}", "%Y-%m-%dT%H:%M") >= now
            ]
            if len(future_rdvs) == 0:
                play_source = text_to_speech("file_source", "Il semblerait que vous n'ayez pas de rendez-vous prévu. Voulez-vous que je vous transfère vers une secrétaire pour avoir plus d'informations ?")
                start_recognizing("/transfer_to_secretary", "transfer_unknown", play_source)
            elif len(future_rdvs) == 1:
                speak("J'ai en effet trouvé un rendez-vous à votre nom.")
                dt = datetime.fromisoformat(planned_rdv[0].get("datePrevue").split("T")[0] + "T" + planned_rdv[0].get("heurePrevue"))
                formatted_date = f"le {dt.day} {french_months[dt.month]} {dt.year}"
                hours, minutes = planned_rdv[0].get("heurePrevue").split(":")

                cancel_creneau = planned_rdv[0]
                all_sous_type = get_sous_type_exam(planned_rdv[0].get("typeExamen"))
                sous_type = next((item for item in all_sous_type if item["code"] == planned_rdv[0].get("codeExamen")), None)
                speak(f"Vous avez rendez-vous {formatted_date} à {int(hours)} heure {int(minutes)} pour un ou une {sous_type.get('libelle')}.")
                play_source = text_to_speech("file_source", "Est-ce bien celui-là que vous voulez annuler ?")
                start_recognizing("/confirm_annulation", "confirm_annulation", play_source)
            else:
                sorted_rdvs = sorted(
                    future_rdvs,
                    key=lambda x: f"{x['datePrevue'][:10]}T{x['heurePrevue']}"
                )
                patient_rdv = sorted_rdvs
                speak("Vous avez plusieurs rendez-vous prévus. Lequel voulez-vous annuler ?")

                text = build_multiple_dates_phrase({i + 1: item for i, item in enumerate(sorted_rdvs)}, "annulation")
                annulation_phrase = text
                play_source = text_to_speech("file_source", text)
                start_recognizing("/get_creneaux_choice", "annulation", play_source)
    else:
        if rdv_intent == "prise de rendez-vous" or rdv_intent == "prise de rendez-vous.":
            play_source = text_to_speech("fixed_file_source", "hang_up_not_known")
            call_automation_client.get_call_connection(call_connection_id).play_media_to_all(
                play_source=play_source,
                operation_context="hang_up"
            )
        elif rdv_intent == "consultation de rendez-vous" or rdv_intent == "consultation de rendez-vous.":
            play_source = text_to_speech("file_source", "Il semblerait que vous ne soyez pas connu de nos services. Voulez-vous que je vous transfère vers une secrétaire afin d'obtenirs plus d'informations ?")
            start_recognizing("/transfer_to_secretary", "transfer_unknown", play_source)


if __name__ == '__main__':
    app.run(debug=True)
