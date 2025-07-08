from azure.communication.callautomation import (
    CallAutomationClient,
    RecognizeInputType,
    PhoneNumberIdentifier,
    FileSource,
)
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
from typing import Dict
from num2words import num2words
import json
import random

from utils.tts import (
    text_to_speech,
    generate_text_to_speech,
    text_to_speech_spell_confirm,
)
from utils.exam import get_client_exam_code
from utils.recorded_audio import recorded_audios_keys, keyboard_sounds, click_sounds
from utils.Call import Call

COGNITIVE_SERVICE_ENDPOINT = (
    "https://lyraecognitivesservicesus.cognitiveservices.azure.com"
)
SPEECH_KEY = "CwdBzhR9vodZ5lXf4S52ErZaUy9eUG05JJCtDuu4xjjL5rylozVFJQQJ99BAAC5T7U2XJ3w3AAAAACOGuWEK"
SPEECH_REGION = "eastus"
# MONGO_URL = "mongodb+srv://neuracorp:amaCtNnLIHMJ4NGZ@riva.yiylf96.mongodb.net/neuracorp"
MONGO_URL = "mongodb+srv://lageistedavid:eaZOnmgtcNN1oGxU@cluster0.pjma4cx.mongodb.net/neuracorp"
APP_URL = "talkpreprodapi.azurewebsites.net"
API_URL = "sparkso-universite.com:8080"

app = Flask(__name__)

client = MongoClient(MONGO_URL)
db = client["neuracorp"]
patientCollection = db["patientsDB"]
rdvCollection = db["rdv"]

call_automation_client = CallAutomationClient.from_connection_string(
    "endpoint=https://lyraepreprod.unitedstates.communication.azure.com/;accesskey=1TsDRImMKFvO8AThS7PUAwww6YBxELviBkGsqFHHmiXErS2PRcAzJQQJ99BFACULyCpuAreVAAAAAZCS3Ids"
)


speech_config = speechsdk.SpeechConfig(subscription=SPEECH_KEY, region=SPEECH_REGION)

calls: Dict[str, Call] = {}


def print_calls():
    for num, call in calls.items():
        print("----", num)
        print(call)


# global call_connection_id
# global caller
# global intent
# global rdv_intent
# global birthdate
# global lastname
# global firstname
# global patient_email
# global exam_id
# global sous_type_id
# global creneauDate
# global all_creneaux
# global chosen_creneau
# global cancel_creneau
# global annulation_phrase
# global patient_rdv

# global current_creneau_proposition
# current_creneau_proposition = 0

# ERRORS HANDLING, MIGHT USE URL PARAMETERS INSTEAD
# global type_exam_error
# type_exam_error = 0

# global firstname_error
# firstname_error = 0

# global lastname_error
# lastname_error = 0

# global ordonnance_error
# ordonnance_error = 0

# global birthdate_error
# birthdate_error = 0

# global intent_error
# intent_error = 0

# rdv_intent = None
# intent = None
# lastname = None
# firstname = None
# birthdate = None
# patient_email = None


def convert_numbers_to_words_french(text):
    def convert_time(match):
        hours = int(match.group(1))
        minutes = int(match.group(2))
        if minutes == 0:
            return f"{num2words(hours, lang='fr')} heures"
        else:
            return (
                f"{num2words(hours, lang='fr')} heures {num2words(minutes, lang='fr')}"
            )

    text = re.sub(r"(\d{1,2})h(\d{2})", convert_time, text)

    def convert_number(match):
        number = int(match.group())
        return num2words(number, lang="fr")

    text = re.sub(r"\b\d+\b", convert_number, text)

    return text


french_months = {
    1: "janvier",
    2: "février",
    3: "mars",
    4: "avril",
    5: "mai",
    6: "juin",
    7: "juillet",
    8: "août",
    9: "septembre",
    10: "octobre",
    11: "novembre",
    12: "décembre",
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
        return convert_numbers_to_words_french(
            f"Le {jour} {mois} à {heure} {heure_label}"
        )
    else:
        return convert_numbers_to_words_french(
            f"Le {jour} {mois} à {heure} {heure_label} et {minute} {minute_label}"
        )


def is_date_formatted(date):
    try:
        datetime.strptime(date, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def date_vers_litteral(date_str):
    # Conversion en objet datetime
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")

    jour = date_obj.day if date_obj.day != 1 else "premier"
    mois = french_months[date_obj.month]
    annee = date_obj.year

    return convert_numbers_to_words_french(f"Le {jour} {mois} {annee}")


def strip_accents(text):
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
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

    headers = {"Content-Type": "application/json"}

    payload = {"text": text}

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()  # Lève une exception si le statut HTTP n'est pas 200
        return response.json().get("response", "Pas de réponse trouvée.")
    except requests.exceptions.RequestException as e:
        print(f"Erreur lors de l'appel au modèle : {e}")
        return "Erreur lors de la communication avec le modèle."


def get_request_infos(request):
    if not request.json:
        return None, None, None, None
    speech = (
        request.json[0].get("data").get("speechResult").get("speech")
        if "speechResult" in request.json[0].get("data").keys()
        else None
    )
    caller = request.json[0].get("data").get("operationContext").split("&&")[0]
    print("____________get_request_infos", speech, caller)
    if speech is not None:
        calls[caller].add_step(f"User: {speech}")
    return (
        caller,
        request.json[0].get("data").get("operationContext").split("&&")[1],
        request.json[0].get("type"),
        speech,
    )


def increment_error(caller, type):
    global calls
    calls[caller].errors[type] += 1
    print("increment_error", type, calls[caller].errors[type])

    if calls[caller].errors[type] > 2:
        return True
    return False


def start_recognizing(
    callback_url,
    context,
    play_source,
    caller,
    background_noise="keyboard",
    end_silence_timeout=0.5,
):
    global calls

    calls[caller].last_text_to_speech["endpoint"] = callback_url
    calls[caller].last_text_to_speech["operation_context"] = context
    calls[caller].last_text_to_speech["play_source"] = play_source

    call_automation_client.get_call_connection(
        calls[caller].call["call_connection_id"]
    ).start_recognizing_media(
        input_type=RecognizeInputType.SPEECH,
        target_participant=PhoneNumberIdentifier("+" + caller.strip()),
        end_silence_timeout=end_silence_timeout,
        play_prompt=play_source,
        interrupt_call_media_operation=False,
        interrupt_prompt=False,
        operation_context=f"{caller}&&{context}",
        speech_language="fr-FR",
        initial_silence_timeout=20,
        operation_callback_url=f"https://{APP_URL}{callback_url}",
    )

    if background_noise == "keyboard":
        play_source = FileSource(url=random.choice(list(keyboard_sounds)))
    else:
        play_source = FileSource(url=random.choice(list(click_sounds)))
    call_automation_client.get_call_connection(
        calls[caller].call["call_connection_id"]
    ).play_media_to_all(play_source=play_source)


def hang_up(text, caller):
    print("HANG UP", caller, text)
    play_source = text_to_speech("file_source", text, calls[caller])
    print("$$$$$$")
    print("PLAYSOURCE", play_source)
    call_automation_client.get_call_connection(
        calls[caller].call["call_connection_id"]
    ).play_media_to_all(play_source=play_source, operation_context="hang_up")


def countPatientInDB(query):
    count = patientCollection.count_documents(query)
    return count


def findPatientInDB(query):
    results = patientCollection.find_one(query)

    return results


########## ENTRY POINT ##########


@app.route("/generate_audio_batch", methods=["POST"])
def generate_audio_batch():
    if request.json and request.json["item"]:
        generate_text_to_speech(request.json["item"])
    else:
        generate_text_to_speech()

    return jsonify({"status": "success"})


@app.route("/incoming_call", methods=["POST"])
def incoming_call():
    # Azure code de vérification
    if (
        request.json
        and request.json[0].get("eventType")
        == "Microsoft.EventGrid.SubscriptionValidationEvent"
    ):
        validation_code = request.json[0]["data"]["validationCode"]
        return jsonify({"validationResponse": validation_code}), 200

    global calls
    data = request.json[0]
    caller = data.get("data").get("from").get("phoneNumber").get("value")[1:]
    called = data.get("data").get("to").get("phoneNumber").get("value")[1:]
    calls[caller] = Call(called)
    encodedContext = data.get("data").get("incomingCallContext")

    call_automation_client.answer_call(
        incoming_call_context=encodedContext,
        callback_url=f"https://{APP_URL}/callback?caller={caller}",
        cognitive_services_endpoint=COGNITIVE_SERVICE_ENDPOINT,
    )
    return jsonify({"status": "success"})


@app.route("/callback", methods=["POST"])
async def callback():
    global calls
    # global call_connection_id
    # global intent
    # global rdv_intent
    # global lastname
    # global firstname
    # global birthdate
    # global patient_email

    caller = request.args.get("caller")
    data = request.json[0]
    type = data.get("type")
    print("CALLBACK", caller, type)
    # print_calls()

    if type == "Microsoft.Communication.CallDisconnected":
        print_calls()
        if caller in calls.keys():
            calls[caller].store_archive(caller)
            # with open("archive_talk.txt", "a", encoding="utf-8") as file:
            #     file.write(calls[caller].to_string_archive(caller))
            del calls[caller]
    if type == "Microsoft.Communication.AnswerFailed":
        print(request.json[0])
    if type == "Microsoft.Communication.RecognizeCompleted":
        user_response = request.json[0].get("data").get("speechResult").get("speech")
        print(request.json[0])
    if type == "Microsoft.Communication.RecognizeFailed":
        print(request.json[0])
    if type == "Microsoft.Communication.PlayFailed":
        print(request.json[0])
    if type == "Microsoft.Communication.CallTransferFailed":
        print(request.json[0])
    if type == "Microsoft.Communication.CallConnected":
        # server_call_id = data.get("data").get("serverCallId")
        calls[caller].call["call_connection_id"] = data.get("data").get(
            "callConnectionId"
        )
        calls[caller].call["caller"] = caller
        # print_calls()

        # target = PhoneNumberIdentifier("+33801150143")

        # call_automation_client.get_call_connection(call_connection_id=call_connection_id).transfer_call_to_participant(
        #     target_participant=target,
        #     transferee=PhoneNumberIdentifier("+" + caller.strip()),
        #     operation_callback_url=f"https://{APP_URL}/callback",
        # )
        start_conversation(caller=caller)
        # await find_patient(caller)
        # handle_prise_rdv(caller)
    if (
        type == "Microsoft.Communication.PlayCompleted"
        and request.json
        and request.json[0].get("data").get("operationContext") == "hang_up"
    ):
        call_automation_client.get_call_connection(
            calls[caller].call["call_connection_id"]
        ).hang_up(is_for_everyone=True)
    return jsonify({"status": "success"})


########## IDENTIFICATION ##########


@app.route("/get_firstname", methods=["POST"])
async def get_firstname():
    # global firstname_error
    # global firstname
    global calls

    if not request.json:
        return jsonify({"success": "success"})

    caller, operation_context, type, user_response = get_request_infos(request)
    if user_response == "":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})
    task_get_repeat = asyncio.create_task(get_repeat_async(user_response=user_response))
    get_repeat = await task_get_repeat
    if get_repeat is True:
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            calls[caller].last_text_to_speech["play_source"],
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})
    if (
        type == "Microsoft.Communication.RecognizeCompleted"
        and operation_context == "get_firstname"
    ):
        # user_response = request.json[0].get("data").get("speechResult").get("speech")

        if user_response == "":
            if increment_error(caller, "firstname"):
                hang_up(
                    "Il semblerait que nous n'arrivons pas à nous comprendre. Je vous transfère vers une secrétaire.",
                    caller,
                )

            play_source = text_to_speech(
                "file_source",
                "Je n'ai pas compris, pouvez-vous répéter votre prénom ?",
                calls[caller],
            )
            start_recognizing("/get_firstname", "get_firstname", play_source, caller)
        else:
            clean_firstname = user_response.replace(".", "")
            task_get_firstname = asyncio.create_task(
                get_firstname_async(user_response=clean_firstname)
            )
            task_human_orientation = asyncio.create_task(
                get_human_orientation_async(user_response=user_response)
            )
            speak("Très bien", caller)
            human_orientation = await task_human_orientation
            if human_orientation is True:
                hang_up(
                    "Vous avez demandé a parler avec une secrétaire, je vais transférer votre appel.",
                    caller,
                )
                return jsonify({"success": "success"})
            task_get_repeat = asyncio.create_task(
                get_repeat_async(user_response=user_response)
            )
            get_repeat = await task_get_repeat
            if get_repeat is True:
                start_recognizing(
                    calls[caller].last_text_to_speech["endpoint"],
                    calls[caller].last_text_to_speech["operation_context"],
                    calls[caller].last_text_to_speech["play_source"],
                    caller,
                    "keyboard",
                )
                return jsonify({"success": "success"})
            await asyncio.sleep(1)

            calls[caller].caller["firstname"] = await task_get_firstname
            clean_firstname = calls[caller].caller["firstname"]

            if (
                clean_firstname is None
                or clean_firstname == "Erreur lors de la communication avec le modèle."
            ):
                if increment_error(caller, "firstname"):
                    hang_up(
                        "Il semblerait que nous n'arrivons pas à nous comprendre. Je vous transfère vers une secrétaire.",
                        caller,
                    )
                play_source = text_to_speech(
                    "file_source",
                    "Je n'ai pas compris, pouvez-vous répéter votre prénom ?",
                    calls[caller],
                )
                start_recognizing(
                    "/get_firstname", "get_firstname", play_source, caller
                )

            else:
                speak(
                    f"{clean_firstname.strip()}",
                    caller,
                    speed=0.82,
                )
                play_source = text_to_speech_spell_confirm(
                    clean_firstname.strip(),
                    calls[caller],
                )
                start_recognizing(
                    "/confirm_firstname",
                    "confirm_firstname",
                    play_source,
                    caller,
                    background_noise="click",
                )

    elif type == "Microsoft.Communication.RecognizeFailed":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})

    return jsonify({"success": "success"})


@app.route("/get_lastname", methods=["POST"])
async def get_lastname():
    global calls

    if not request.json:
        return jsonify({"success": "success"})

    caller, operation_context, type, user_response = get_request_infos(request)
    if user_response == "":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})
    task_get_repeat = asyncio.create_task(get_repeat_async(user_response=user_response))
    get_repeat = await task_get_repeat
    if get_repeat is True:
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            calls[caller].last_text_to_speech["play_source"],
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})
    if (
        type == "Microsoft.Communication.RecognizeCompleted"
        and operation_context == "get_lastname"
    ):
        # user_response = request.json[0].get("data").get("speechResult").get("speech")
        # Remove every "." that comes from the AI response
        task_human_orientation = asyncio.create_task(
            get_human_orientation_async(user_response=user_response)
        )
        speak("Merci", caller)
        human_orientation = await task_human_orientation
        if human_orientation is True:
            hang_up(
                "Vous avez demandé a parler avec une secrétaire, je vais transférer votre appel.",
                caller,
            )
            return jsonify({"success": "success"})
        clean_name = user_response.replace(".", "")
        task_get_lastname = asyncio.create_task(
            get_lastname_async(user_response=clean_name)
        )
        calls[caller].caller["lastname"] = await task_get_lastname

        if clean_name is None:
            if increment_error(caller, "lastname"):
                play_source = text_to_speech(
                    "fixed_file_source", "misunderstand_unfortunately", calls[caller]
                )

                call_automation_client.get_call_connection(
                    calls[caller].call["call_connection_id"]
                ).play_media_to_all(
                    play_source=play_source, operation_context="hang_up"
                )
            play_source = text_to_speech(
                "fixed_file_source", "repeat_lastname", calls[caller]
            )
            start_recognizing("/get_lastname", "get_lastname", play_source, caller)

        else:
            speak(
                f"{calls[caller].caller["lastname"]}",
                caller,
                speed=0.82,
            )
            play_source = text_to_speech_spell_confirm(
                calls[caller].caller["lastname"],
                calls[caller],
            )
            start_recognizing(
                "/confirm_lastname",
                "confirm_lastname",
                play_source,
                caller,
                background_noise="click",
            )

    elif type == "Microsoft.Communication.RecognizeFailed":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})

    return jsonify({"success": "success"})


@app.route("/get_birthdate", methods=["POST"])
async def get_birthdate():
    # global birthdate
    global calls

    if not request.json:
        return jsonify({"success": "success"})

    caller, operation_context, type, user_response = get_request_infos(request)
    if user_response == "":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})
    if (
        type == "Microsoft.Communication.RecognizeCompleted"
        and operation_context == "get_birthdate"
    ):
        # user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_human_orientation = asyncio.create_task(
            get_human_orientation_async(user_response=user_response)
        )
        human_orientation = await task_human_orientation
        if human_orientation is True:
            hang_up(
                "Vous avez demandé a parler avec une secrétaire, je vais transférer votre appel.",
                caller,
            )
            return jsonify({"success": "success"})
        task_get_repeat = asyncio.create_task(
            get_repeat_async(user_response=user_response)
        )
        get_repeat = await task_get_repeat
        if get_repeat is True:
            start_recognizing(
                calls[caller].last_text_to_speech["endpoint"],
                calls[caller].last_text_to_speech["operation_context"],
                calls[caller].last_text_to_speech["play_source"],
                caller,
                "keyboard",
            )
            return jsonify({"success": "success"})
        task_get_birthdate = asyncio.create_task(
            get_birthdate_async(user_response=user_response)
        )
        # speak("Merci, un instant s'il vous plaît")

        calls[caller].caller["birthdate"] = await task_get_birthdate

        if (
            calls[caller].caller["birthdate"] is None
            or is_date_formatted(calls[caller].caller["birthdate"]) == False
        ):
            play_source = text_to_speech(
                "fixed_file_source", "repeat_birthdate", calls[caller]
            )
            start_recognizing("/get_birthdate", "get_birthdate", play_source, caller)
        else:
            date_litterale = date_vers_litteral(calls[caller].caller["birthdate"])
            print(date_litterale)
            # Formatage en version littérale
            play_source = text_to_speech(
                "file_source",
                f"Vous confirmez que vous êtes né {date_litterale} ?",
                calls[caller],
            )
            start_recognizing(
                "/confirm_birthdate",
                "confirm_birthdate",
                play_source,
                caller,
                background_noise="click",
            )

    elif type == "Microsoft.Communication.RecognizeFailed":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})

    return jsonify({"success": "success"})


########## CONFIRMATION ##########


@app.route("/confirm_creneau", methods=["POST"])
async def confirm_creneau():
    # global all_creneaux
    # global current_creneau_proposition
    # global chosen_creneau
    global calls

    if not request.json:
        return jsonify({"success": "success"})

    caller, operation_context, type, user_response = get_request_infos(request)
    if user_response == "":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})
    caller_info = calls[caller].caller
    call_info = calls[caller].call
    rdv_info = calls[caller].rdv
    if (
        type == "Microsoft.Communication.RecognizeCompleted"
        and operation_context == "confirm_creneau"
    ):
        # user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_human_orientation = asyncio.create_task(
            get_human_orientation_async(user_response=user_response)
        )
        human_orientation = await task_human_orientation
        if human_orientation is True:
            hang_up(
                "Vous avez demandé a parler avec une secrétaire, je vais transférer votre appel.",
                caller,
            )
            return jsonify({"success": "success"})
        task_get_repeat = asyncio.create_task(
            get_repeat_async(user_response=user_response)
        )
        get_repeat = await task_get_repeat
        if get_repeat is True:
            start_recognizing(
                calls[caller].last_text_to_speech["endpoint"],
                calls[caller].last_text_to_speech["operation_context"],
                calls[caller].last_text_to_speech["play_source"],
                caller,
                "keyboard",
            )
            return jsonify({"success": "success"})
        task_positive_negative = asyncio.create_task(
            get_positive_negative_async(user_response)
        )
        speak("ok", caller)

        positive_negative = await task_positive_negative
        if positive_negative == "négative":
            rdv_info["current_creneau_proposition"] += 1
            if rdv_info["current_creneau_proposition"] < len(rdv_info["all_creneaux"]):
                text = build_single_date_phrase(
                    creneau=rdv_info["all_creneaux"],
                    index=rdv_info["current_creneau_proposition"],
                )
                play_source = text_to_speech("file_source", text, calls[caller])
                start_recognizing(
                    "/confirm_creneau",
                    "confirm_creneau",
                    play_source,
                    caller,
                    background_noise="click",
                )
            else:
                rdv_info["current_creneau_proposition"] = 0
                last_key = sorted(rdv_info["all_creneaux"].keys(), key=int)[-1]
                last_entry = rdv_info["all_creneaux"][last_key]

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
                task_creneaux = asyncio.create_task(
                    get_creneaux_async(
                        sous_type=rdv_info["sous_type_id"],
                        exam_type=rdv_info["exam_id"],
                        date_start=new_datetime_str,
                        caller=caller,
                    )
                )
                speak("Je vais vous chercher d'autres créneaux libres.", caller)

                await asyncio.sleep(1)

                creneaux = await task_creneaux
                rdv_info["all_creneaux"] = creneaux
                text = build_single_date_phrase(
                    creneau=rdv_info["all_creneaux"],
                    index=rdv_info["current_creneau_proposition"],
                )
                play_source = text_to_speech("file_source", text, calls[caller])
                start_recognizing(
                    "/confirm_creneau",
                    "confirm_creneau",
                    play_source,
                    caller,
                    background_noise="click",
                )

        elif positive_negative == "positive":
            rdv_info["chosen_creneau"] = rdv_info["all_creneaux"][
                str(rdv_info["current_creneau_proposition"] + 1)
            ]
            if (
                caller_info["lastname"] is not None
                or caller_info["firstname"] is not None
                or caller_info["birthdate"] is not None
            ):
                await find_patient(caller)
            else:
                play_source = text_to_speech(
                    "fixed_file_source", "ask_birthdate2", calls[caller]
                )
                start_recognizing(
                    "/get_birthdate", "get_birthdate", play_source, caller
                )
        else:
            text = build_single_date_phrase(
                creneau=rdv_info["all_creneaux"],
                index=rdv_info["current_creneau_proposition"],
            )
            play_source = text_to_speech(
                "file_source",
                "Pardonnez moi, je n'ai pas compris." + text,
                calls[caller],
            )
            start_recognizing(
                "/confirm_creneau",
                "confirm_creneau",
                play_source,
                caller,
                background_noise="click",
            )
    elif (
        type == "Microsoft.Communication.RecognizeCompleted"
        and operation_context == "modification"
    ):
        # user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_positive_negative = asyncio.create_task(
            get_positive_negative_async(user_response)
        )
        speak("ok", caller)
        task_human_orientation = asyncio.create_task(
            get_human_orientation_async(user_response=user_response)
        )
        human_orientation = await task_human_orientation
        if human_orientation is True:
            hang_up(
                "Vous avez demandé a parler avec une secrétaire, je vais transférer votre appel.",
                caller,
            )
            return jsonify({"success": "success"})
        task_get_repeat = asyncio.create_task(
            get_repeat_async(user_response=user_response)
        )
        get_repeat = await task_get_repeat
        if get_repeat is True:
            start_recognizing(
                calls[caller].last_text_to_speech["endpoint"],
                calls[caller].last_text_to_speech["operation_context"],
                calls[caller].last_text_to_speech["play_source"],
                caller,
                "keyboard",
            )
            return jsonify({"success": "success"})
        positive_negative = await task_positive_negative
        if positive_negative == "négative":
            rdv_info["current_creneau_proposition"] += 1
            if rdv_info["current_creneau_proposition"] < len(rdv_info["all_creneaux"]):
                text = build_single_date_phrase(
                    creneau=rdv_info["all_creneaux"],
                    index=rdv_info["current_creneau_proposition"],
                )
                play_source = text_to_speech("file_source", text, calls[caller])
                start_recognizing(
                    "/confirm_creneau",
                    "modification",
                    play_source,
                    caller,
                    background_noise="click",
                )
            else:
                rdv_info["current_creneau_proposition"] = 0
                last_key = sorted(rdv_info["all_creneaux"].keys(), key=int)[-1]
                last_entry = rdv_info["all_creneaux"][last_key]

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
                task_creneaux = asyncio.create_task(
                    get_creneaux_async(
                        sous_type=rdv_info["sous_type_id"],
                        exam_type=rdv_info["exam_id"],
                        caller=caller,
                        date_start=new_datetime_str,
                    )
                )
                speak("Je vais vous chercher d'autres créneaux libres.", caller)

                await asyncio.sleep(1)

                creneaux = await task_creneaux
                rdv_info["all_creneaux"] = creneaux
                text = build_single_date_phrase(
                    creneau=rdv_info["all_creneaux"],
                    index=rdv_info["current_creneau_proposition"],
                )
                play_source = text_to_speech("file_source", text, calls[caller])
                start_recognizing(
                    "/confirm_creneau",
                    "modification",
                    play_source,
                    caller,
                    background_noise="click",
                )
        elif positive_negative == "positive":
            rdv_info["chosen_creneau"] = rdv_info["all_creneaux"][
                str(rdv_info["current_creneau_proposition"] + 1)
            ]

            dt = datetime.fromisoformat(rdv_info["chosen_creneau"])

            matched_creneau = None
            for key, value in rdv_info["all_creneaux"].items():
                full_datetime_str = (
                    value["date"][:10] + "T" + value["heureDebut"] + ":00"
                )
                current_dt = datetime.fromisoformat(full_datetime_str)
                if current_dt == dt:
                    matched_creneau = value
                    break

            if matched_creneau is not None:
                # Création de la phrase

                phrase = f"{dt.day} {french_months[dt.month]} à {dt.hour} heures {dt.minute:02d}"

                rdv_info["creneauDate"] = phrase
                rdv_info["chosen_creneau"] = matched_creneau

                if call_info["intent"] == "prise de rendez-vous":
                    play_source = text_to_speech(
                        "file_source",
                        f"Vous avez choisi le {phrase}. Puis-je avoir votre date de naissance ?",
                        calls[caller],
                    )
                    start_recognizing(
                        "/get_birthdate", "get_birthdate", play_source, caller
                    )

                elif call_info["intent"] == "modification de rendez-vous":
                    speak(
                        f"Très bien, votre rendez-vous sera déplacé au {phrase}", caller
                    )
                    editRDV(caller)
        else:
            text = build_single_date_phrase(
                creneau=rdv_info["all_creneaux"],
                index=rdv_info["current_creneau_proposition"],
            )
            play_source = text_to_speech(
                "file_source",
                "Pardonnez moi, je n'ai pas compris." + text,
                calls[caller],
            )
            start_recognizing(
                "/confirm_creneau",
                "confirm_creneau",
                play_source,
                caller,
                background_noise="click",
            )

    elif type == "Microsoft.Communication.RecognizeFailed":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})

    return jsonify({"success": "success"})


@app.route("/confirm_firstname", methods=["POST"])
async def confirm_firstname():
    # global firstname_error
    # global firstname
    # global lastname
    # global birthdate
    global calls

    if not request.json:
        return jsonify({"success": "success"})

    caller, operation_context, type, user_response = get_request_infos(request)
    if user_response == "":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})
    task_get_repeat = asyncio.create_task(get_repeat_async(user_response=user_response))
    get_repeat = await task_get_repeat
    if get_repeat is True:
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            calls[caller].last_text_to_speech["play_source"],
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})
    if (
        type == "Microsoft.Communication.RecognizeCompleted"
        and operation_context == "confirm_firstname"
    ):
        # user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_model_response = asyncio.create_task(
            get_positive_negative_async(user_response)
        )
        task_human_orientation = asyncio.create_task(
            get_human_orientation_async(user_response=user_response)
        )
        speak("ok", caller)
        human_orientation = await task_human_orientation
        if human_orientation is True:
            hang_up(
                "Vous avez demandé a parler avec une secrétaire, je vais transférer votre appel.",
                caller,
            )
            return jsonify({"success": "success"})
        await asyncio.sleep(1)

        model_response = await task_model_response

        if model_response == "négative":
            if increment_error(caller, "firstname"):
                hang_up(
                    "Malheureusement, il semblerait que nous n'arrivons pas à nous comprendre. Je vais vous rediriger vers une secrétaire afin de pouvoir accéder a vos requêtes.",
                    caller,
                )
            else:
                play_source = text_to_speech(
                    "file_source",
                    "Pouvez-vous s'il vous plaît répéter votre prénom en l'épelant?",
                    calls[caller],
                )
                start_recognizing(
                    "/get_firstname", "get_firstname", play_source, caller
                )

        elif model_response == "positive":
            # speak("Très bien, merci")
            await find_patient(caller)
            return jsonify({"success": "success"})

        else:
            speak(
                f"Je n'ai pas compris, {calls[caller].caller["firstname"]}",
                caller,
                speed=0.82,
            )
            play_source = text_to_speech_spell_confirm(
                calls[caller].caller["firstname"],
                calls[caller],
            )
            start_recognizing(
                "/confirm_firstname",
                "confirm_firstname",
                play_source,
                caller,
                background_noise="click",
            )

    elif type == "Microsoft.Communication.RecognizeFailed":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})

    return jsonify({"success": "success"})


@app.route("/confirm_lastname", methods=["POST"])
async def confirm_lastname():
    # global lastname_error
    # global lastname
    # global firstname
    global calls

    if not request.json:
        return jsonify({"success": "success"})

    caller, operation_context, type, user_response = get_request_infos(request)
    if user_response == "":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})
    task_get_repeat = asyncio.create_task(get_repeat_async(user_response=user_response))
    get_repeat = await task_get_repeat
    if get_repeat is True:
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            calls[caller].last_text_to_speech["play_source"],
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})
    if type == "Microsoft.Communication.RecognizeCompleted":
        # user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_model_response = asyncio.create_task(
            get_positive_negative_async(user_response)
        )
        task_human_orientation = asyncio.create_task(
            get_human_orientation_async(user_response=user_response)
        )
        speak("ok", caller)
        human_orientation = await task_human_orientation
        if human_orientation is True:
            hang_up(
                "Vous avez demandé a parler avec une secrétaire, je vais transférer votre appel.",
                caller,
            )
            return jsonify({"success": "success"})
        await asyncio.sleep(1)

        model_response = await task_model_response

        if model_response == "négative":
            if increment_error(caller, "lastname"):
                play_source = text_to_speech(
                    "fixed_file_source", "misunderstand_unfortunately", calls[caller]
                )
                call_automation_client.get_call_connection(
                    calls[caller].call["call_connection_id"]
                ).play_media_to_all(
                    play_source=play_source, operation_context="hang_up"
                )
                return jsonify({"status": "success"})

            play_source = text_to_speech(
                "fixed_file_source", "spell_lastname2", calls[caller]
            )
            start_recognizing("/get_lastname", "get_lastname", play_source, caller)

        elif model_response == "positive":
            count = countPatientInDB(
                {
                    "dateNaissance": {
                        "$regex": f"^{calls[caller].caller["birthdate"] + 'T00:00:00'}$"
                    },
                    "nom": {
                        "$regex": f"^{calls[caller].caller["lastname"]}$",
                        "$options": "i",  # Case-insensitive
                    },
                }
            )

            if count > 1 or count == 0:
                play_source = text_to_speech(
                    "fixed_file_source", "ask_firstname_spell", calls[caller]
                )
                start_recognizing(
                    "/get_firstname", "get_firstname", play_source, caller
                )

                return jsonify({"success": "success"})
            else:
                patient = findPatientInDB(
                    {
                        "dateNaissance": {
                            "$regex": f"^{calls[caller].caller["birthdate"] + 'T00:00:00'}$"
                        },
                        "nom": {
                            "$regex": f"^{calls[caller].caller["lastname"]}$",
                            "$options": "i",  # Case-insensitive
                        },
                    }
                )
                calls[caller].patient = patient
                date_litterale = date_vers_litteral(calls[caller].caller["birthdate"])
                play_source = text_to_speech(
                    "file_source",
                    f"{patient.get('nom')} {patient.get('prenom')} né {date_litterale} c'est bien vous ?",
                    calls[caller],
                )
                calls[caller].caller["lastname"] = patient.get("nom")
                calls[caller].caller["firstname"] = patient.get("prenom")
                start_recognizing(
                    callback_url="/confirm_identity",
                    play_source=play_source,
                    context="confirm_identity",
                    caller=caller,
                )

        else:
            speak(
                "Je n'ai pas compris",
                caller,
            )
            speak(
                f"Je n'ai pas compris {calls[caller].caller["lastname"]}",
                caller,
                speed=0.82,
            )
            play_source = text_to_speech_spell_confirm(
                calls[caller].caller["lastname"],
                calls[caller],
            )
            start_recognizing(
                "/confirm_lastname", "confirm_lastname", play_source, caller
            )
            return jsonify({"success": "success"})
    elif type == "Microsoft.Communication.RecognizeFailed":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})

    return jsonify({"success": "success"})


@app.route("/confirm_annulation", methods=["POST"])
async def confirm_annulation():
    # global cancel_creneau
    # global annulation_phrase
    global calls

    if not request.json:
        return jsonify({"success": "success"})

    caller, operation_context, type, user_response = get_request_infos(request)
    if user_response == "":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})
    if type == "Microsoft.Communication.RecognizeCompleted":
        # user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_model_response = asyncio.create_task(
            get_positive_negative_async(user_response)
        )
        task_human_orientation = asyncio.create_task(
            get_human_orientation_async(user_response=user_response)
        )
        speak("ok", caller)
        human_orientation = await task_human_orientation
        if human_orientation is True:
            hang_up(
                "Vous avez demandé a parler avec une secrétaire, je vais transférer votre appel.",
                caller,
            )
            return jsonify({"success": "success"})
        task_get_repeat = asyncio.create_task(
            get_repeat_async(user_response=user_response)
        )
        get_repeat = await task_get_repeat
        if get_repeat is True:
            start_recognizing(
                calls[caller].last_text_to_speech["endpoint"],
                calls[caller].last_text_to_speech["operation_context"],
                calls[caller].last_text_to_speech["play_source"],
                caller,
                "keyboard",
            )
            return jsonify({"success": "success"})
        await asyncio.sleep(1)

        model_response = await task_model_response

        if model_response == "négative":
            play_source = text_to_speech(
                "file_source", calls[caller].rdv["annulation_phrase"], calls[caller]
            )
            start_recognizing("/get_creneaux_choice", "annulation", play_source, caller)
        elif model_response == "positive":
            speak("Patientez un instant.", caller)

            await asyncio.sleep(1)

            deletion = deleteRDV(caller)
            if deletion is True:
                play_source = text_to_speech(
                    "file_source",
                    "Votre rendez-vous a bien été supprimé. Puis-je faire autre chose pour vous ?",
                    calls[caller],
                )
                start_recognizing(
                    "/handleResponse", "end_conversation", play_source, caller
                )
            else:
                hang_up(
                    "J'ai eu un problème lors de la suppression de votre rendez-vous. Je vous transfère vers une secrétaire.",
                    caller,
                )
        else:
            date_str = calls[caller].rdv["cancel_creneau"]["datePrevue"][:10]
            time_str = calls[caller].rdv["cancel_creneau"]["heurePrevue"]

            play_source = text_to_speech(
                "file_source",
                f"Je n'ai pas compris, voulez-vous annuler le rendez-vous du {date_str} à {time_str} ?",
                calls[caller],
            )
            start_recognizing("/confirm_annulation", "annulation", play_source, caller)
    elif type == "Microsoft.Communication.RecognizeFailed":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})
    return jsonify({"success": "success"})


@app.route("/confirm_birthdate", methods=["POST"])
async def confirm_birthdate():
    # global birthdate_error
    # global lastname
    # global firstname
    global calls

    if not request.json:
        return jsonify({"success": "success"})

    caller, operation_context, type, user_response = get_request_infos(request)
    if user_response == "":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})
    if (
        type == "Microsoft.Communication.RecognizeCompleted"
        and operation_context == "confirm_birthdate"
    ):
        # user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_human_orientation = asyncio.create_task(
            get_human_orientation_async(user_response=user_response)
        )
        human_orientation = await task_human_orientation
        if human_orientation is True:
            hang_up(
                "Vous avez demandé a parler avec une secrétaire, je vais transférer votre appel.",
                caller,
            )
            return jsonify({"success": "success"})
        task_get_repeat = asyncio.create_task(
            get_repeat_async(user_response=user_response)
        )
        get_repeat = await task_get_repeat
        if get_repeat is True:
            start_recognizing(
                calls[caller].last_text_to_speech["endpoint"],
                calls[caller].last_text_to_speech["operation_context"],
                calls[caller].last_text_to_speech["play_source"],
                caller,
                "keyboard",
            )
            return jsonify({"success": "success"})
        task_model_response = asyncio.create_task(
            get_positive_negative_async(user_response)
        )

        await asyncio.sleep(1)

        model_response = await task_model_response

        if model_response == "négative":
            if increment_error(caller, "birthdate"):
                play_source = text_to_speech(
                    "fixed_file_source",
                    "misunderstand_unfortunately",
                    calls[caller],
                )
                call_automation_client.get_call_connection(
                    calls[caller].call["call_connection_id"]
                ).play_media_to_all(
                    play_source=play_source, operation_context="hang_up"
                )

            play_source = text_to_speech(
                "fixed_file_source", "repeat_birthdate2", calls[caller]
            )
            start_recognizing("/get_birthdate", "get_birthdate", play_source, caller)

        elif model_response == "positive":

            count = countPatientInDB(
                {
                    "dateNaissance": {
                        "$regex": f"^{calls[caller].caller["birthdate"] + 'T00:00:00'}$"
                    }
                }
            )

            if count > 1 or count == 0:
                play_source = text_to_speech(
                    "fixed_file_source", "spell_lastname", calls[caller]
                )
                start_recognizing(
                    "/get_lastname",
                    "get_lastname",
                    play_source,
                    caller,
                    end_silence_timeout=1,
                )
            else:
                patient = findPatientInDB(
                    {
                        "dateNaissance": {
                            "$regex": f"^{calls[caller].caller["birthdate"] + 'T00:00:00'}$"
                        }
                    }
                )

                date_litterale = date_vers_litteral(calls[caller].caller["birthdate"])
                play_source = text_to_speech(
                    "file_source",
                    f"{patient.get('nom').lower()} {patient.get('prenom').lower()} né {date_litterale} c'est bien vous ?",
                    calls[caller],
                )
                calls[caller].caller["lastname"] = patient.get("nom")
                calls[caller].caller["firstname"] = patient.get("prenom")
                start_recognizing(
                    callback_url="/confirm_identity",
                    play_source=play_source,
                    context="confirm_identity",
                    caller=caller,
                )

        else:
            date_litterale = date_vers_litteral(calls[caller].caller["birthdate"])

            # Formatage en version littérale
            play_source = text_to_speech(
                "file_source",
                f"Je n'ai pas compris, Vous confirmez que vous êtes né {date_litterale} ?",
                calls[caller],
            )
            start_recognizing(
                "/confirm_birthdate",
                "confirm_birthdate",
                play_source,
                caller,
                background_noise="click",
            )

    elif type == "Microsoft.Communication.RecognizeFailed":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})
    return jsonify({"success": "success"})


@app.route("/confirm_call_intent", methods=["POST"])
async def confirm_call_intent():
    global calls

    if not request.json:
        return jsonify({"success": "success"})

    caller, operation_context, type, user_response = get_request_infos(request)
    if user_response == "":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})
    caller_info = calls[caller].caller
    rdv_intent = calls[caller].call["intent"]

    if (
        type == "Microsoft.Communication.RecognizeCompleted"
        and operation_context == "confirm_call_intent"
    ):
        # user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_human_orientation = asyncio.create_task(
            get_human_orientation_async(user_response=user_response)
        )
        human_orientation = await task_human_orientation
        if human_orientation is True:
            hang_up(
                "Vous avez demandé a parler avec une secrétaire, je vais transférer votre appel.",
                caller,
            )
            return jsonify({"success": "success"})
        task_get_repeat = asyncio.create_task(
            get_repeat_async(user_response=user_response)
        )
        get_repeat = await task_get_repeat
        if get_repeat is True:
            start_recognizing(
                calls[caller].last_text_to_speech["endpoint"],
                calls[caller].last_text_to_speech["operation_context"],
                calls[caller].last_text_to_speech["play_source"],
                caller,
                "keyboard",
            )
            return jsonify({"success": "success"})
        task_model_response = asyncio.create_task(
            get_positive_negative_async(user_response)
        )
        speak("ok", caller)

        await asyncio.sleep(1)

        model_response = await task_model_response

        if model_response == "négative":
            play_source = text_to_speech(
                "fixed_file_source", "misunderstand_intent", calls[caller]
            )
            start_recognizing(
                "/handleResponse", "start_conversation", play_source, caller
            )

        elif model_response == "positive":
            if rdv_intent == "prise de rendez-vous":
                await handle_prise_rdv(caller)
            elif rdv_intent == "modification de rendez-vous":
                if (
                    caller_info["lastname"] is not None
                    or caller_info["firstname"] is not None
                    or caller_info["birthdate"] is not None
                ):
                    await find_patient(caller)
                else:
                    handle_modification(caller)
            elif rdv_intent == "annulation de rendez-vous":
                if (
                    caller_info["lastname"] is not None
                    or caller_info["firstname"] is not None
                    or caller_info["birthdate"] is not None
                ):
                    await find_patient(caller)
                else:
                    handle_annulation(caller)
            elif rdv_intent == "consultation de rendez-vous":
                if (
                    caller_info["lastname"] is not None
                    or caller_info["firstname"] is not None
                    or caller_info["birthdate"] is not None
                ):
                    await find_patient(caller)
                else:
                    handle_consultation(caller)

        else:
            if increment_error(caller, "intent"):
                hang_up(
                    "Pardonnez moi, il semblerait que je n'arrive pas à vous comprendre. Je vous transfère vers une secrétaire.",
                    caller,
                )

            text = "Pardonnez moi, je n'ai pas compris"
            if rdv_intent == "prise de rendez-vous":
                text += "Est-ce bien pour une prise de rendez-vous ?"
            elif rdv_intent == "modification de rendez-vous":
                text += "Est-ce bien pour une modification de rendez-vous ?"
            elif rdv_intent == "annulation de rendez-vous":
                text += "Est-ce bien pour une annulation de rendez-vous ?"
            elif rdv_intent == "consultation de rendez-vous":
                text += "Est-ce bien pour une consultation de rendez-vous ?"

            play_source = text_to_speech("file_source", text, calls[caller])
            start_recognizing(
                "/confirm_call_intent",
                "confirm_call_intent",
                play_source,
                caller,
                background_noise="click",
            )

    if type == "Microsoft.Communication.RecognizeFailed":
        calls[caller].errors["intent"] += 1
        if calls[caller].errors["intent"] > 2:
            hang_up(
                "Pardonnez moi, il semblerait que je n'arrive pas à vous comprendre. Je vous transfère vers une secrétaire.",
                caller,
            )

        play_source = text_to_speech(
            "file_source",
            f"Pardonnez moi, je n'ai pas entendu. Est-ce bien pour une {rdv_intent} ?",
            calls[caller],
        )
        start_recognizing(
            "/confirm_call_intent",
            "confirm_call_intent",
            play_source,
            caller,
            background_noise="click",
        )

    elif type == "Microsoft.Communication.RecognizeFailed":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})

    return jsonify({"success": "success"})


@app.route("/confirm_identity", methods=["POST"])
async def confirm_identity():
    # global firstname
    # global lastname
    # global birthdate
    global calls

    if not request.json:
        return jsonify({"success": "success"})

    caller, operation_context, type, user_response = get_request_infos(request)
    if user_response == "":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})
    if (
        type == "Microsoft.Communication.RecognizeCompleted"
        and operation_context == "confirm_identity"
    ):
        # user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_human_orientation = asyncio.create_task(
            get_human_orientation_async(user_response=user_response)
        )
        human_orientation = await task_human_orientation
        if human_orientation is True:
            hang_up(
                "Vous avez demandé a parler avec une secrétaire, je vais transférer votre appel.",
                caller,
            )
            return jsonify({"success": "success"})
        task_get_repeat = asyncio.create_task(
            get_repeat_async(user_response=user_response)
        )
        get_repeat = await task_get_repeat
        if get_repeat is True:
            start_recognizing(
                calls[caller].last_text_to_speech["endpoint"],
                calls[caller].last_text_to_speech["operation_context"],
                calls[caller].last_text_to_speech["play_source"],
                caller,
                "keyboard",
            )
            return jsonify({"success": "success"})
        task_model_response = asyncio.create_task(
            get_positive_negative_async(user_response)
        )
        speak("ok", caller)

        await asyncio.sleep(1)

        model_response = await task_model_response

        if model_response == "négative":
            calls[caller].patient = None
            hang_up(
                "Désolé, je ne peux pas donner de rendez-vous à un patient qui n'est pas déjà connu du cabinet. Vous êtes un nouveau patient : Je vous propose de vous transférer à la secrétaire",
                caller,
            )
        elif model_response == "positive":
            speak("Très bien, laissez moi un instant.", caller)

            await asyncio.sleep(1)

            await find_patient(caller)
        else:
            date_litterale = date_vers_litteral(calls[caller].caller["birthdate"])
            play_source = text_to_speech(
                "file_source",
                f"Désolé, je n'ai pas compris, vous êtes bien {calls[caller].caller["lastname"]} {calls[caller].caller["firstname"]}. Né {date_litterale} ?",
                calls[caller],
            )
            start_recognizing(
                "/confirm_identity",
                "confirm_identity",
                play_source=play_source,
                caller=caller,
                background_noise="click",
            )

    elif type == "Microsoft.Communication.RecognizeFailed":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})

    return jsonify({"success": "success"})


@app.route("/transfer_to_secretary", methods=["POST"])
async def transfer_to_secretary():
    global calls

    if not request.json:
        return jsonify({"success": "success"})

    caller, operation_context, type, user_response = get_request_infos(request)
    if user_response == "":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})
    if type == "Microsoft.Communication.RecognizeCompleted":
        # user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_model_response = asyncio.create_task(
            get_positive_negative_async(user_response)
        )
        speak("C'est noté.", caller)
        model_response = await task_model_response
        if model_response == "négative":
            hang_up("A bientôt j'espère !", caller)
        elif model_response == "positive":
            hang_up("Je transmets votre appel", caller)
        else:
            play_source = text_to_speech(
                "file_source",
                "Pardonnez-moi, je n'ai pas compris. Dois-je vous rediriger vers une secrétaire ?",
                calls[caller],
            )
            start_recognizing(
                "/transfer_to_secretary", "transfer_to_secretary", play_source, caller
            )
    elif type == "Microsoft.Communication.RecognizeFailed":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})
    return jsonify({"success": "success"})


########## PRISE DE RENDEZ-VOUS ##########


async def examination_exam_type(caller):
    global calls

    print(calls[caller].rdv["sous_type_id"])

    task_get_examination = asyncio.create_task(
        get_examination(exam_type=calls[caller].rdv["sous_type_id"])
    )

    examination = await task_get_examination
    if len(examination) > 0:
        calls[caller].rdv["interrogatoire"] = examination
        play_source = text_to_speech("file_source", examination[0], calls[caller])
        start_recognizing(
            "/examination_response?question=1",
            "examination_response",
            play_source,
            caller,
        )

    return "ok"


@app.route("/examination_response", methods=["POST"])
async def examination_response():
    global calls
    if not request.json:
        return jsonify({"success": "success"})
    caller, operation_context, type, user_response = get_request_infos(request)
    if user_response == "":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})
    if (
        request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted"
        and operation_context == "examination_response"
    ):
        task_human_orientation = asyncio.create_task(
            get_human_orientation_async(user_response=user_response)
        )
        human_orientation = await task_human_orientation
        if human_orientation is True:
            hang_up(
                "Vous avez demandé a parler avec une secrétaire, je vais transférer votre appel.",
                caller,
            )
            return jsonify({"success": "success"})
        task_get_repeat = asyncio.create_task(
            get_repeat_async(user_response=user_response)
        )
        get_repeat = await task_get_repeat
        if get_repeat is True:
            start_recognizing(
                calls[caller].last_text_to_speech["endpoint"],
                calls[caller].last_text_to_speech["operation_context"],
                calls[caller].last_text_to_speech["play_source"],
                caller,
                "keyboard",
            )
            return jsonify({"success": "success"})
        question = request.args.get("question")
        if int(question) < len(calls[caller].rdv["interrogatoire"]):
            play_source = text_to_speech(
                "file_source",
                calls[caller].rdv["interrogatoire"][int(question)],
                calls[caller],
            )
            if len(calls[caller].rdv["reponses_interrogatoire"]) == 0:
                calls[caller].rdv["reponses_interrogatoire"] = user_response
            else:
                calls[caller].rdv["reponses_interrogatoire"].append(user_response)
            start_recognizing(
                f"/examination_response?question={str(int(question) + 1)}",
                "examination_response",
                play_source,
                caller,
            )
            return jsonify({"success": "success"})
        else:
            play_source = text_to_speech(
                "file_source",
                "Très bien, merci beaucoup pour ces précisions, j'ai fini. Puis-je faire autre chose pour vous ?",
                calls[caller],
            )
            start_recognizing(
                "/handleResponse", "end_conversation", play_source, caller
            )
            return jsonify({"success": "success"})
    if request.json[0].get("type") == "Microsoft.Communication.RecognizeFailed":
        speak("Je n'ai pas entendu", calls[caller])
    return jsonify({"success": "success"})


@app.route("/module_informatif", methods=["POST"])
async def module_informatif():
    print("--> module_informatif")
    if not request.json:
        return jsonify({"success": "success"})

    caller, operation_context, type, user_response = get_request_infos(request)
    if user_response == "":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})
    if (
        request.json[0].get("type") == "Microsoft.Communication.RecognizeCompleted"
        and operation_context == "module_informatif"
    ):
        # user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_human_orientation = asyncio.create_task(
            get_human_orientation_async(user_response=user_response)
        )
        human_orientation = await task_human_orientation
        if human_orientation is True:
            hang_up(
                "Vous avez demandé a parler avec une secrétaire, je vais transférer votre appel.",
                caller,
            )
            return jsonify({"success": "success"})
        task = asyncio.create_task(get_model_response_async(user_response))
        model_response = await task

        play_source = text_to_speech(
            "file_source",
            f"{model_response}. Puis-je faire autre chose pour vous ?",
            calls[caller],
        )
        start_recognizing("/handleResponse", "end_conversation", play_source, caller)

    elif type == "Microsoft.Communication.RecognizeFailed":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})
    return jsonify({"success": "success"})


@app.route("/confirm_rdv", methods=["POST"])
async def confirm_rdv():
    # global type_exam_error
    # global exam_id
    # global sous_type_id
    # global all_creneaux
    global calls

    if not request.json:
        return jsonify({"success": "success"})

    caller, operation_context, type, user_response = get_request_infos(request)
    if user_response == "":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})
    if type == "Microsoft.Communication.RecognizeCompleted" and (
        operation_context == "confirm_rdv" or operation_context == "confirm_rdv_intro"
    ):
        task_human_orientation = asyncio.create_task(
            get_human_orientation_async(user_response=user_response)
        )
        task_model_response = asyncio.create_task(
            get_positive_negative_async(user_response)
        )
        # speak("ok")

        human_orientation = await task_human_orientation
        if human_orientation is True:
            hang_up(
                "Vous avez demandé a parler avec une secrétaire, je vais transférer votre appel.",
                caller,
            )
            return jsonify({"success": "success"})
        task_get_repeat = asyncio.create_task(
            get_repeat_async(user_response=user_response)
        )
        get_repeat = await task_get_repeat
        if get_repeat is True:
            start_recognizing(
                calls[caller].last_text_to_speech["endpoint"],
                calls[caller].last_text_to_speech["operation_context"],
                calls[caller].last_text_to_speech["play_source"],
                caller,
                "keyboard",
            )
            return jsonify({"success": "success"})
        model_response = await task_model_response
        if model_response == "négative":
            calls[caller].rdv["exam_id"] = None
            calls[caller].rdv["sous_type_id"] = None
            if operation_context == "confirm_rdv_intro":
                play_source = text_to_speech(
                    "file_source", "Que puis-je faire pour vous ?", calls[caller]
                )
                start_recognizing(
                    "/handleResponse", "start_conversation", play_source, caller
                )
            elif increment_error(caller, "type_exam"):
                hang_up(
                    "Malheureusement, il semblerait que nous n'arrivons pas à nous comprendre. Je vais vous rediriger vers une secrétaire afin de pouvoir accéder a vos requêtes.",
                    caller,
                )
            else:
                play_source = text_to_speech(
                    "fixed_file_source", "repeat_exam_type", calls[caller]
                )
                start_recognizing(
                    "/rdv_exam_type", "rdv_exam_type", play_source, caller
                )
        elif model_response == "positive":
            # play_source = text_to_speech("file_source", "Pouvez-vous me lire le motif de l'examen présent sur votre ordonnance ?", calls[caller])
            # start_recognizing("/get_motif", "get_motif", play_source, caller)

            task_creneaux = asyncio.create_task(
                get_creneaux_async(
                    sous_type=calls[caller].rdv["sous_type_id"],
                    exam_type=calls[caller].rdv["exam_id"],
                    caller=caller,
                )
            )

            speak("Je regarde les disponibilités, un instant...", caller)

            await asyncio.sleep(1)

            creneaux = await task_creneaux

            print(creneaux)

            calls[caller].rdv["all_creneaux"] = creneaux

            text = build_single_date_phrase(creneau=creneaux)
            play_source = text_to_speech("file_source", text, calls[caller])
            start_recognizing(
                "/confirm_creneau",
                "confirm_creneau",
                play_source,
                caller,
                background_noise="click",
            )
        else:
            play_source = text_to_speech(
                "fixed_file_source", "misunderstand_exam_type", calls[caller]
            )
            start_recognizing("/rdv_exam_type", "rdv_exam_type", play_source, caller)

    elif type == "Microsoft.Communication.RecognizeFailed":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})
    return jsonify({"status": "success"})


@app.route("/rdv_exam_type", methods=["POST"])
async def rdv_exam_type():
    global calls
    # global exam_id
    # global sous_type_id

    if not request.json:
        return jsonify({"success": "success"})

    caller, operation_context, type, user_response = get_request_infos(request)
    if user_response == "":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})
    rdv_info = calls[caller].rdv

    if (
        type == "Microsoft.Communication.RecognizeCompleted"
        and operation_context == "rdv_exam_type"
    ):
        if rdv_info["exam_id"] is not None:
            user_response = f"C'est pour un {rdv_info["exam_id"]} {user_response}"
        # user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_urgence = asyncio.create_task(get_urgence_async(user_response))
        urgence = await task_urgence
        if urgence is True:
            hang_up(
                "Il semblerait que vous appeliez pour une urgence. Je vous transfère vers une secrétaire.",
                caller,
            )
            return jsonify({"success": "success"})

        # pattern = r"\b(Urgence|Urgences|Urgent|Urgemment)\b"
        # if re.search(pattern, user_response, re.IGNORECASE):
        #     hang_up(
        #         "Il semblerait que vous appeliez pour une urgence. Je vous transfère vers une secrétaire.",
        #         caller,
        #     )
        task_human_orientation = asyncio.create_task(
            get_human_orientation_async(user_response=user_response)
        )
        human_orientation = await task_human_orientation
        if human_orientation is True:
            hang_up(
                "Vous avez demandé a parler avec une secrétaire, je vais transférer votre appel.",
                caller,
            )
            return jsonify({"success": "success"})
        task_get_repeat = asyncio.create_task(
            get_repeat_async(user_response=user_response)
        )
        get_repeat = await task_get_repeat
        if get_repeat is True:
            start_recognizing(
                calls[caller].last_text_to_speech["endpoint"],
                calls[caller].last_text_to_speech["operation_context"],
                calls[caller].last_text_to_speech["play_source"],
                caller,
                "keyboard",
            )
            return jsonify({"success": "success"})
        task_type = asyncio.create_task(
            get_exam_type_async(user_response=user_response)
        )

        exam_type = await task_type
        print("#######", user_response, exam_type)
        if (
            exam_type["type_examen"] is not None
            and exam_type["code_examen_id"] is not None
        ):
            actual_exam_id, actual_sous_type_id, is_performed = get_client_exam_code(
                calls[caller].call["called"],
                exam_type["type_examen_id"],
                exam_type["code_examen_id"],
            )
            if not is_performed:
                hang_up(
                    f"Vous avez demandé {"un" if exam_type["type_examen_id"] == "CT" else "une"} {exam_type["code_examen"]}, mais nous ne pratiquons malheureusement pas cet acte ici. Je vous conseille de vous renseigner auprès d'un autre cabinet de radiologie. Merci à vous et à bientôt !",
                    caller,
                )
            else:
                rdv_info["exam_id"] = actual_exam_id
                rdv_info["sous_type_id"] = actual_sous_type_id
                play_source = text_to_speech(
                    "file_source",
                    f"Vous m'avez dit {exam_type['code_examen']}, c'est ça ?",
                    calls[caller],
                )
                start_recognizing("/confirm_rdv", "confirm_rdv", play_source, caller)

        elif (
            exam_type["type_examen"] is not None and exam_type["code_examen_id"] is None
        ):
            if rdv_info["exam_id"] is not None:
                speak("Désolé, je n'ai pas compris", caller)
            rdv_info["exam_id"] = exam_type["type_examen"]
            play_source = text_to_speech(
                "file_source",
                f"Vous m'avez dit {"un" if exam_type["type_examen_id"] == "CT" else "une"} {exam_type["type_examen"]}. Pouvez-vous, s'il vous plaît, préciser la zone anatomique concernée?",
                calls[caller],
            )
            start_recognizing("/rdv_exam_type", "rdv_exam_type", play_source, caller)
        else:
            play_source = text_to_speech(
                "fixed_file_source",
                "repeat_exam_type",
                calls[caller],
            )
            start_recognizing(
                "/rdv_exam_type",
                "rdv_exam_type",
                play_source,
                caller,
                background_noise="click",
            )

    elif type == "Microsoft.Communication.RecognizeFailed":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})
    return jsonify({"status": "success"})


@app.route("/get_creneaux_choice", methods=["POST"])
async def get_creneaux_choice():
    # global creneauDate
    # global all_creneaux
    # global chosen_creneau
    # global call_connection_id
    # global rdv_intent
    # global annulation_phrase
    # global patient_rdv
    # global cancel_creneau
    global calls

    if not request.json:
        return jsonify({"success": "success"})

    caller, operation_context, type, user_response = get_request_infos(request)

    if user_response == "":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})
    call_info = calls[caller].call
    caller_info = calls[caller].caller
    rdv_info = calls[caller].rdv

    if (
        type == "Microsoft.Communication.RecognizeCompleted"
        and operation_context == "get_creneaux_choice"
    ):
        # user_response = request.json[0].get("data").get("speechResult").get("speech")

        task_creneau_choice = asyncio.create_task(
            extract_creneau_async(user_response=user_response)
        )
        task_human_orientation = asyncio.create_task(
            get_human_orientation_async(user_response=user_response)
        )
        human_orientation = await task_human_orientation
        if human_orientation is True:
            hang_up(
                "Vous avez demandé a parler avec une secrétaire, je vais transférer votre appel.",
                caller,
            )
            return jsonify({"success": "success"})
        task_get_repeat = asyncio.create_task(
            get_repeat_async(user_response=user_response)
        )
        get_repeat = await task_get_repeat
        if get_repeat is True:
            start_recognizing(
                calls[caller].last_text_to_speech["endpoint"],
                calls[caller].last_text_to_speech["operation_context"],
                calls[caller].last_text_to_speech["play_source"],
                caller,
                "keyboard",
            )
            return jsonify({"success": "success"})
        speak(
            "D'accord, patientez pendant que je vous réserve ce créneau.",
            caller,
        )

        await asyncio.sleep(1)

        creneau_choice = await task_creneau_choice

        if creneau_choice is None:
            text = build_multiple_dates_phrase(creneaux=rdv_info["all_creneaux"])

            play_source = text_to_speech(
                "file_source",
                f"Je n'ai pas compris le créneau que vous avez choisi. {text}",
                calls[caller],
            )
            start_recognizing(
                "/get_creneaux_choice", "get_creneaux_choice", play_source, caller
            )
        else:
            dt = datetime.fromisoformat(creneau_choice)

            matched_creneau = None
            for key, value in rdv_info["all_creneaux"].items():
                full_datetime_str = (
                    value["date"][:10] + "T" + value["heureDebut"] + ":00"
                )
                current_dt = datetime.fromisoformat(full_datetime_str)
                if current_dt == dt:
                    matched_creneau = value
                    break

            if matched_creneau is not None:
                # Création de la phrase

                phrase = f"{dt.day} {french_months[dt.month]} à {dt.hour} heures {dt.minute:02d}"

                rdv_info["creneauDate"] = phrase
                rdv_info["chosen_creneau"] = matched_creneau

                if call_info["rdvintent"] == "prise de rendez-vous":
                    play_source = text_to_speech(
                        "file_source",
                        f"Vous avez choisi le {phrase}. Puis-je avoir votre date de naissance ?",
                        calls[caller],
                    )
                    start_recognizing(
                        "/get_birthdate", "get_birthdate", play_source, caller
                    )

            else:
                text = build_multiple_dates_phrase(creneaux=rdv_info["all_creneaux"])
                play_source = text_to_speech(
                    "file_source",
                    f"Je n'ai pas compris le créneau que vous avez choisi. {text}",
                    calls[caller],
                )
                start_recognizing(
                    "/get_creneaux_choice", "get_creneaux_choice", play_source, caller
                )

    elif (
        type == "Microsoft.Communication.RecognizeCompleted"
        and operation_context == "modification"
    ):
        # user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_creneau_choice = asyncio.create_task(
            extract_creneau_async(user_response=user_response)
        )
        speak(
            "D'accord, patientez pendant que je vous réserve ce créneau.",
            caller,
        )

        await asyncio.sleep(1)

        creneau_choice = await task_creneau_choice

        if creneau_choice is None:
            text = build_multiple_dates_phrase(creneaux=rdv_info["all_creneaux"])

            play_source = text_to_speech(
                "file_source",
                f"Je n'ai pas compris le créneau que vous avez choisi. {text}",
                calls[caller],
            )
            start_recognizing(
                "/get_creneaux_choice", "get_creneaux_choice", play_source, caller
            )
        else:
            dt = datetime.fromisoformat(creneau_choice)

            matched_creneau = None
            for key, value in rdv_info["all_creneaux"].items():
                full_datetime_str = (
                    value["date"][:10] + "T" + value["heureDebut"] + ":00"
                )
                current_dt = datetime.fromisoformat(full_datetime_str)
                if current_dt == dt:
                    matched_creneau = value
                    break

            if matched_creneau is not None:
                # Création de la phrase

                phrase = f"{dt.day} {french_months[dt.month]} à {dt.hour} heures {dt.minute:02d}"

                rdv_info["creneauDate"] = phrase
                rdv_info["chosen_creneau"] = matched_creneau

                if call_info["intent"] == "prise de rendez-vous":
                    play_source = text_to_speech(
                        "file_source",
                        f"Vous avez choisi le {phrase}. Puis-je avoir votre date de naissance ?",
                        calls[caller],
                    )
                    start_recognizing(
                        "/get_birthdate", "get_birthdate", play_source, caller
                    )

                elif call_info["intent"] == "modification de rendez-vous":
                    speak(
                        f"Très bien, votre rendez-vous sera déplacé au {phrase}",
                        caller,
                    )
                    editRDV(caller)

            else:
                text = build_multiple_dates_phrase(creneaux=rdv_info["all_creneaux"])
                play_source = text_to_speech(
                    "file_source",
                    f"Je n'ai pas compris le créneau que vous avez choisi. {text}",
                    calls[caller],
                )
                start_recognizing(
                    "/get_creneaux_choice", "get_creneaux_choice", play_source, caller
                )

    elif (
        type == "Microsoft.Communication.RecognizeCompleted"
        and operation_context == "annulation"
    ):
        # user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_creneau_choice = asyncio.create_task(
            extract_creneau_async(user_response=user_response)
        )
        # speak("ok")
        creneau_choice = await task_creneau_choice

        if creneau_choice is None:
            text = build_multiple_dates_phrase(creneaux=rdv_info["all_creneaux"])

            play_source = text_to_speech(
                "file_source",
                f"Je n'ai pas compris le rendez-vous que vous souhaitez annuler. {rdv_info["annulation_phrase"]}",
                calls[caller],
            )
            start_recognizing("/get_creneaux_choice", "annulation", play_source, caller)
        else:
            dt = datetime.fromisoformat(creneau_choice)

            matched_creneau = None
            for item in rdv_info["patient_rdv"]:
                full_datetime_str = (
                    item["datePrevue"][:10] + "T" + item["heurePrevue"] + ":00"
                )
                current_dt = datetime.fromisoformat(full_datetime_str)
                if current_dt == dt:
                    matched_creneau = item
                    break
            if matched_creneau is not None:
                rdv_info["cancel_creneau"] = matched_creneau
                date_str = matched_creneau["datePrevue"][:10]
                time_str = matched_creneau["heurePrevue"]

                play_source = text_to_speech(
                    "file_source",
                    f"Vous confirmez que vous voulez annuler votre rendez-vous du {date_str} à {time_str}",
                    calls[caller],
                )
                start_recognizing(
                    "/confirm_annulation",
                    "annulation",
                    play_source,
                    caller,
                    background_noise="click",
                )
            else:
                play_source = text_to_speech(
                    "file_source",
                    f"Je n'ai pas compris le rendez-vous que vous souhaitez annuler. {rdv_info["annulation_phrase"]}",
                    calls[caller],
                )
                start_recognizing(
                    "/get_creneaux_choice", "annulation", play_source, caller
                )

    elif type == "Microsoft.Communication.RecognizeFailed":
        start_recognizing(
            calls[caller].last_text_to_speech["endpoint"],
            calls[caller].last_text_to_speech["operation_context"],
            f"Je ne vous ai pas entendu. {calls[caller].last_text_to_speech['play_source']}",
            caller,
            "keyboard",
        )
        return jsonify({"success": "success"})

    return jsonify({"status": "success"})


@app.route("/handleResponse", methods=["POST"])
async def handleResponse():
    global calls

    if not request.json:
        return jsonify({"success": "success"})

    caller, operation_context, type, user_response = get_request_infos(request)
    if user_response == "":
        play_source = text_to_speech(
            "file_source",
            "Je ne vous ai pas entendu. Que puis-je faire pour vous ?",
            calls[caller],
        )
        start_recognizing(
            "/handleResponse", "start_conversation", play_source, calls[caller], "click"
        )
        return jsonify({"success": "success"})
    call_info = calls[caller].call
    rdv_info = calls[caller].rdv
    # print(
    #     "--> handleResponse",
    #     caller,
    #     operation_context,
    #     json.dumps(request.json[0], indent=2, ensure_ascii=False),
    # )

    if (
        type == "Microsoft.Communication.RecognizeCompleted"
        and operation_context == "start_conversation"
    ):
        # user_response = request.json[0].get("data").get("speechResult").get("speech")
        # print(user_response)

        task_human_orientation = asyncio.create_task(
            get_human_orientation_async(user_response=user_response)
        )
        task_get_repeat = asyncio.create_task(
            get_repeat_async(user_response=user_response)
        )

        task_urgence = asyncio.create_task(get_urgence_async(user_response))
        urgence = await task_urgence
        if urgence is True:
            hang_up(
                "Il semblerait que vous appeliez pour une urgence. Je vous transfère vers une secrétaire.",
                caller,
            )
            return jsonify({"success": "success"})
        # pattern = r"\b(Urgence|Urgences|Urgent|Urgemment)\b"
        # if re.search(pattern, user_response, re.IGNORECASE):
        #     hang_up(
        #         "Il semblerait que vous appeliez pour une urgence. Je vous transfère vers une secrétaire.",
        #         caller,
        #     )
        #     return jsonify({"success": "success"})

        task_intent = asyncio.create_task(get_intent_async(user_response=user_response))
        human_orientation = await task_human_orientation
        if human_orientation is True:
            hang_up(
                "Vous avez demandé a parler avec une secrétaire, je vais transférer votre appel.",
                caller,
            )
            return jsonify({"success": "success"})
        get_repeat = await task_get_repeat
        if get_repeat is True:
            start_recognizing(
                calls[caller].last_text_to_speech["endpoint"],
                calls[caller].last_text_to_speech["operation_context"],
                calls[caller].last_text_to_speech["play_source"],
                caller,
                "keyboard",
            )
            return jsonify({"success": "success"})
        intent = (await task_intent).lower().replace(".", "")

        play_source = None

        if intent == "renseignements":
            call_info["intent"] = intent
            task_is_question = asyncio.create_task(is_question_async(user_response))
            is_question = await task_is_question
            if is_question is True:
                task = asyncio.create_task(get_model_response_async(user_response))
                model_response = await task
                play_source = text_to_speech(
                    "file_source",
                    f"{model_response}. Puis-je faire autre chose pour vous ?",
                    calls[caller],
                )
                start_recognizing(
                    "/handleResponse", "end_conversation", play_source, caller
                )
                return jsonify({"success": "success"})
            else:
                play_source = text_to_speech(
                    "fixed_file_source", "question", calls[caller]
                )
                start_recognizing(
                    "/module_informatif", "module_informatif", play_source, caller
                )
                return jsonify({"success": "success"})
            continue_conversation("more", caller)
            return jsonify({"success": "success"})
        elif intent == "prise de rendez-vous":

            task_type = asyncio.create_task(
                get_exam_type_async(user_response=user_response)
            )
            call_info["intent"] = intent.lower()
            # speak("ok")
            exam_type = await task_type
            if exam_type["type_examen_id"] is None:
                play_source = text_to_speech(
                    "file_source",
                    "Vous voulez prendre rendez-vous, c'est bien ça ?",
                    calls[caller],
                )
            else:
                if (
                    exam_type["type_examen_id"] is not None
                    and exam_type["code_examen_id"] is not None
                ):
                    actual_exam_id, actual_sous_type_id, is_performed = (
                        get_client_exam_code(
                            calls[caller].call["called"],
                            exam_type["type_examen_id"],
                            exam_type["code_examen_id"],
                        )
                    )
                    if not is_performed:
                        hang_up(
                            f"Vous avez demandé {"un" if exam_type["type_examen_id"] == "CT" else "une"} {exam_type["code_examen"]}, mais nous ne pratiquons malheureusement pas cet acte ici. Je vous conseille de vous renseigner auprès d'un autre cabinet de radiologie. Merci à vous et à bientôt !",
                            caller,
                        )
                    else:
                        rdv_info["exam_id"] = actual_exam_id
                        rdv_info["sous_type_id"] = actual_sous_type_id
                        play_source = text_to_speech(
                            "file_source",
                            f"Vous m'avez dit vouloir prendre rendez-vous pour {"un" if exam_type["type_examen_id"] == "CT" else "une"} {exam_type["code_examen"]}, c'est ça ?",
                            calls[caller],
                        )
                        start_recognizing(
                            "/confirm_rdv", "confirm_rdv_intro", play_source, caller
                        )
                    return jsonify({"success": "success"})
                elif (
                    exam_type["type_examen_id"] is not None
                    and exam_type["code_examen_id"] is None
                ):
                    rdv_info["exam_id"] = exam_type["type_examen"]
                    play_source = text_to_speech(
                        "file_source",
                        f"Vous souhaitez prendre rendez-vous pour {"un" if exam_type["type_examen_id"] == "CT" else "une"} {exam_type["type_examen"]}. Pouvez-vous, s'il vous plaît, préciser la zone anatomique concernée?",
                        calls[caller],
                    )
                    start_recognizing(
                        "/rdv_exam_type", "rdv_exam_type", play_source, caller
                    )
                    return jsonify({"success": "success"})
                else:
                    play_source = text_to_speech(
                        "file_source",
                        "Vous voulez prendre rendez-vous, c'est bien ça ?",
                        calls[caller],
                    )

        elif intent.lower() == "modification de rendez-vous":
            call_info["intent"] = intent.lower()
            play_source = text_to_speech(
                "file_source",
                "Vous voulez déplacer un rendez-vous, c'est bien ça ?",
                calls[caller],
            )

        elif intent.lower() == "annulation de rendez-vous":
            call_info["intent"] = intent.lower()
            play_source = text_to_speech(
                "file_source",
                "Vous voulez annuler un rendez-vous, c'est bien ça ?",
                calls[caller],
            )

        elif intent.lower() == "consultation de rendez-vous":
            call_info["intent"] = intent.lower()
            play_source = text_to_speech(
                "file_source",
                "Vous voulez consulter un rendez-vous, c'est bien ça ?",
                calls[caller],
            )

        elif intent.lower() == "autre":
            play_source = text_to_speech(
                "file_source",
                "Je suis désolé, votre question n'entre pas dans mon champ de compétences, je vous passe un interlocuteur humain.",
                calls[caller],
            )
            start_recognizing(
                "/handleResponse", "start_conversation", play_source, caller
            )

        else:
            play_source = text_to_speech(
                "fixed_file_source", "misunderstand_intent2", calls[caller]
            )
            start_recognizing(
                "/handleResponse", "start_conversation", play_source, caller
            )

            return jsonify({"succes": "success"})

        start_recognizing(
            "/confirm_call_intent",
            "confirm_call_intent",
            play_source,
            caller,
            background_noise="click",
        )
    if (
        type == "Microsoft.Communication.RecognizeCompleted"
        and operation_context == "end_conversation"
    ):
        # user_response = request.json[0].get("data").get("speechResult").get("speech")
        task_urgence = asyncio.create_task(get_urgence_async(user_response))
        urgence = await task_urgence
        if urgence is True:
            hang_up(
                "Il semblerait que vous appeliez pour une urgence. Je vous transfère vers une secrétaire.",
                caller,
            )
            return jsonify({"success": "success"})
        # pattern = r"\b(Urgence|Urgences|Urgent|Urgemment)\b"
        # if re.search(pattern, user_response, re.IGNORECASE):
        #     hang_up(
        #         "Il semblerait que vous appeliez pour une urgence. Je vous transfère vers une secrétaire.",
        #         caller,
        #     )
        task_human_orientation = asyncio.create_task(
            get_human_orientation_async(user_response=user_response)
        )
        task_intent = asyncio.create_task(get_intent_async(user_response=user_response))
        human_orientation = await task_human_orientation
        if human_orientation is True:
            hang_up(
                "Vous avez demandé a parler avec une secrétaire, je vais transférer votre appel.",
                caller,
            )
            return jsonify({"success": "success"})
        task_get_repeat = asyncio.create_task(
            get_repeat_async(user_response=user_response)
        )
        get_repeat = await task_get_repeat
        if get_repeat is True:
            start_recognizing(
                calls[caller].last_text_to_speech["endpoint"],
                calls[caller].last_text_to_speech["operation_context"],
                calls[caller].last_text_to_speech["play_source"],
                caller,
                "keyboard",
            )
            return jsonify({"success": "success"})
        intent = await task_intent
        intent = intent.lower().replace(".", "")

        if intent.lower() == "renseignements":
            call_info["intent"] = intent.lower()
            task_is_question = asyncio.create_task(is_question_async(user_response))
            is_question = await task_is_question
            if is_question is True:
                task = asyncio.create_task(get_model_response_async(user_response))
                model_response = await task
                speak(model_response, caller)
            else:
                play_source = text_to_speech(
                    "fixed_file_source", "question", calls[caller]
                )
                start_recognizing(
                    "/module_informatif", "module_informatif", play_source, caller
                )

            continue_conversation("more", caller)
            return jsonify({"success": "success"})
        elif intent.lower() == "prise de rendez-vous":
            task_type = asyncio.create_task(
                get_exam_type_async(user_response=user_response)
            )
            call_info["intent"] = intent.lower()
            # speak("ok")
            exam_type = await task_type
            if exam_type["type_examen_id"] is None:
                play_source = text_to_speech(
                    "file_source",
                    "Vous voulez prendre rendez-vous, c'est bien ça ?",
                    calls[caller],
                )
            else:
                if (
                    exam_type["type_examen_id"] is not None
                    and exam_type["code_examen_id"] is not None
                ):
                    actual_exam_id, actual_sous_type_id, is_performed = (
                        get_client_exam_code(
                            calls[caller].call["called"],
                            exam_type["type_examen_id"],
                            exam_type["code_examen_id"],
                        )
                    )
                    if not is_performed:
                        hang_up(
                            f"Vous avez demandé {"un" if exam_type["type_examen"] == "CT" else "une"} {exam_type["code_examen"]}, mais nous ne pratiquons malheureusement pas cet acte ici. Je vous conseille de vous renseigner auprès d'un autre cabinet de radiologie. Merci à vous et à bientôt !",
                            caller,
                        )
                    else:
                        rdv_info["exam_id"] = actual_exam_id
                        rdv_info["sous_type_id"] = actual_sous_type_id
                        play_source = text_to_speech(
                            "file_source",
                            f"Vous m'avez dit vouloir prendre rendez-vous pour {"un" if exam_type["type_examen"] == "CT" else "une"} {exam_type["code_examen"]}, c'est ça ?",
                            calls[caller],
                        )
                        start_recognizing(
                            "/confirm_rdv", "confirm_rdv_intro", play_source, caller
                        )
                    return jsonify({"success": "success"})
                elif (
                    exam_type["type_examen_id"] is not None
                    and exam_type["code_examen_id"] is None
                ):
                    rdv_info["exam_id"] = exam_type["type_examen"]
                    play_source = text_to_speech(
                        "file_source",
                        f"Vous souhaitez prendre rendez-vous pour {"un" if exam_type["type_examen"] == "CT" else "une"} {exam_type["type_examen"]}. Pouvez-vous, s'il vous plaît, préciser la zone anatomique concernée?",
                        calls[caller],
                    )
                    start_recognizing(
                        "/rdv_exam_type", "rdv_exam_type", play_source, caller
                    )
                    return jsonify({"success": "success"})
                else:
                    play_source = text_to_speech(
                        "file_source",
                        "Vous voulez prendre rendez-vous, c'est bien ça ?",
                        calls[caller],
                    )

        elif intent == "modification de rendez-vous":
            calls[caller].call["intent"] = intent
            play_source = text_to_speech(
                "file_source",
                "Vous voulez déplacer un rendez-vous, c'est bien ça ?",
                calls[caller],
            )

        elif intent == "annulation de rendez-vous":
            calls[caller].call["intent"] = intent
            play_source = text_to_speech(
                "file_source",
                "Vous voulez annuler un rendez-vous, c'est bien ça ?",
                calls[caller],
            )

        elif intent == "consultation de rendez-vous":
            calls[caller].call["intent"] = intent
            play_source = text_to_speech(
                "file_source",
                "Vous voulez consulter un rendez-vous, c'est bien ça ?",
                calls[caller],
            )

        elif intent == "autre":
            task_positive_negative = asyncio.create_task(
                get_positive_negative_async(user_response)
            )
            positive_negative = await task_positive_negative

            if positive_negative == "positive":
                play_source = text_to_speech(
                    "file_source",
                    "Voulez-vous prendre, annuler, consulter ou modifier un rendez vous ? Vous pouvez aussi simplement me poser une question.",
                    calls[caller],
                )
                start_recognizing(
                    "/handleResponse", "start_conversation", play_source, caller
                )
            elif positive_negative == "négative":
                hang_up("Très bien, merci pour votre appel !", caller)
            return jsonify({"succes": "success"})

        else:
            play_source = text_to_speech(
                "fixed_file_source", "misunderstand_intent2", calls[caller]
            )
            start_recognizing(
                "/handleResponse", "start_conversation", play_source, caller
            )

            return jsonify({"succes": "success"})

        start_recognizing(
            "/confirm_call_intent",
            "confirm_call_intent",
            play_source,
            caller,
            background_noise="click",
        )

    elif type == "Microsoft.Communication.RecognizeFailed":
        play_source = text_to_speech(
            "fixed_file_source", "misunderstand_intent2", calls[caller]
        )
        start_recognizing("/handleResponse", "start_conversation", play_source, caller)

    return jsonify({"success": "success"})


# @app.route("/has_ordonnance", methods=["POST"])
# async def has_ordonnance():
#     global calls

#     if not request.json:
#         return jsonify({"success": "success"})

#     caller, operation_context, type, user_response = get_request_infos(request)
#     rdv_info = calls[caller].rdv

#     if (
#         type == "Microsoft.Communication.RecognizeCompleted"
#         and operation_context == "has_ordonnance"
#     ):
#         # user_response = request.json[0].get("data").get("speechResult").get("speech")
#         task_model_response = asyncio.create_task(
#             get_positive_negative_async(user_response)
#         )
#         # speak("ok")
#         model_response = await task_model_response

#         if model_response == "négative":
#             hang_up(
#                 "Désolé nous pouvons pas vous planifier un rendez-vous sans ordonnance prescrite de votre médecin. Pour passer un examen d'imagerie, il faut avoir la prescription d'un médecin. Sans ordonnance, ce n'est pas possible. Pour avoir une ordonnance, je vous conseille de consulter un médecin. Je vous souhaite une excellente journée et à bientôt.",
#                 caller,
#             )
#         elif model_response == "positive":

#             if rdv_info["exam_id"] is not None and rdv_info["sous_type_id"] is not None:
#                 task_creneaux = asyncio.create_task(
#                     get_creneaux_async(
#                         sous_type=rdv_info["sous_type_id"],
#                         exam_type=rdv_info["exam_id"],
#                         caller=caller,
#                     ),
#                 )
#                 speak("Je regarde les disponibilités, un instant...", caller)

#                 await asyncio.sleep(1)

#                 creneaux = await task_creneaux

#                 print(creneaux)

#                 rdv_info["all_creneaux"] = creneaux

#                 text = build_single_date_phrase(creneau=creneaux)
#                 play_source = text_to_speech("file_source", text, calls[caller])
#                 start_recognizing(
#                     "/confirm_creneau",
#                     "confirm_creneau",
#                     play_source,
#                     caller,
#                     background_noise="click",
#                 )
#             else:
#                 play_source = text_to_speech(
#                     "file_source",
#                     "Très bien, quel examen voulez vous passer ?",
#                     calls[caller],
#                 )
#                 start_recognizing(
#                     "/rdv_exam_type", "rdv_exam_type", play_source, caller
#                 )

#         else:
#             if increment_error(caller, "ordonnance"):
#                 hang_up(
#                     "Malheureusement, il semblerait que nous n'arrivons pas à nous comprendre. Je vais vous rediriger vers une secrétaire afin de pouvoir accéder a vos requêtes.",
#                     caller,
#                 )
#             else:
#                 play_source = text_to_speech(
#                     "file_source",
#                     "Désolé, je n'ai pas compris, Avez-vous une ordonnance ?",
#                     calls[caller],
#                 )
#                 start_recognizing(
#                     "/has_ordonnance", "has_ordonnance", play_source, caller
#                 )

#     if type == "Microsoft.Communication.RecognizeFailed":
#         play_source = text_to_speech(
#             "file_source",
#             "Désolé, je n'ai pas compris, Avez-vous une ordonnance ?",
#             calls[caller],
#         )
#         start_recognizing("/has_ordonnance", "has_ordonnance", play_source, caller)

#     return jsonify({"status": "success"})


########## ASYNC ##########


async def get_examination(exam_type):
    url = "https://lyrae-talk-functions.azurewebsites.net/api/interrogatoire?code=z4qZo6X7c4gNDPlKhBoXs2IRV1Z1o4FM_FKRqcgpTJBNAzFu_W0gTA=="

    headers = {"Content-Type": "application/json"}

    payload = {"code_exam": exam_type}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response.raise_for_status()
                data = await response.json()
                print("get_examination", data)
                return data.get("response", "Pas de réponse trouvée.")
    except aiohttp.ClientError as e:
        print(f"Erreur lors de l'appel au modèle : {e}")
        return "Erreur lors de la communication avec le modèle."


async def get_firstname_async(user_response):
    url = "https://lyrae-talk-functions.azurewebsites.net/api/get_prenom?code=z4qZo6X7c4gNDPlKhBoXs2IRV1Z1o4FM_FKRqcgpTJBNAzFu_W0gTA=="

    headers = {"Content-Type": "application/json"}

    payload = {"text": "Mon prénom est " + user_response}

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

    headers = {"Content-Type": "application/json"}

    payload = {"text": "Mon nom de famille est " + user_response}

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

    headers = {"Content-Type": "application/json"}

    payload = {"text": user_response}

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
    headers = {"Content-Type": "application/json"}

    payload = {"text": user_response}

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


async def get_creneaux_async(sous_type, exam_type, caller, date_start=None):
    global calls

    url = f"https://{API_URL}/api/getCreneaux"
    headers = {"Content-Type": "application/json"}

    if exam_type == "ECHOGRAPHIE":
        exam_type = "EC"
    elif exam_type == "RADIO":
        exam_type = "RX"
    elif exam_type == "SCANNER":
        exam_type = "CT"
    elif exam_type == "Mammographie":
        exam_type = "MG"

    # Get current date and time
    now = datetime.now()

    if date_start is None:
        # Format it to match: 2025-04-18T00:00:00
        formatted = now.strftime("%Y-%m-%dT%H:%M:%S")
    else:
        print(date_start)
        formatted = date_start

    payload = {"typeExamen": exam_type, "codeExamen": sous_type, "dateDebut": formatted}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response.raise_for_status()
                data = await response.json()
                print("creneaux", data)
                return data
    except aiohttp.ClientError as e:
        speak(f"Je ne peux pas trouver les créneaux parce que {e}", caller)
        return None
        print(f"Erreur lors de l'appel au modèle : {e}")
        return "Erreur lors de la communication avec le modèle."


async def get_exam_type_async(user_response):
    url = "https://lyrae-talk-functions.azurewebsites.net/api/get_type_code_examen?code=z4qZo6X7c4gNDPlKhBoXs2IRV1Z1o4FM_FKRqcgpTJBNAzFu_W0gTA=="
    headers = {"Content-Type": "application/json"}
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


async def get_urgence_async(user_response):
    if user_response == None:
        return False
    url = "https://lyrae-talk-functions.azurewebsites.net/api/detection_urgence?code=z4qZo6X7c4gNDPlKhBoXs2IRV1Z1o4FM_FKRqcgpTJBNAzFu_W0gTA=="
    headers = {"Content-Type": "application/json"}
    payload = {"text": user_response}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response.raise_for_status()
                data = await response.json()
                print("get_urgence", data)
                return data.get("response", "Pas de réponse trouvée.")
    except aiohttp.ClientError as e:
        print(f"Erreur lors de l'appel au modèle : {e}")
        return "Erreur lors de la communication avec le modèle."


async def get_human_orientation_async(user_response):
    if user_response == None:
        return False
    url = "https://lyrae-talk-functions.azurewebsites.net/api/detect_human_assistant_orientation?code=z4qZo6X7c4gNDPlKhBoXs2IRV1Z1o4FM_FKRqcgpTJBNAzFu_W0gTA=="
    headers = {"Content-Type": "application/json"}
    payload = {"text": user_response}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response.raise_for_status()
                data = await response.json()
                print("human orientation", data)
                return data.get("response", "Pas de réponse trouvée.")
    except aiohttp.ClientError as e:
        print(f"Erreur lors de l'appel au modèle : {e}")
        return "Erreur lors de la communication avec le modèle."


async def get_repeat_async(user_response):
    if user_response == None:
        return False
    url = "https://lyrae-talk-functions.azurewebsites.net/api/detect_repetition?code=z4qZo6X7c4gNDPlKhBoXs2IRV1Z1o4FM_FKRqcgpTJBNAzFu_W0gTA=="
    headers = {"Content-Type": "application/json"}
    payload = {"text": user_response}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response.raise_for_status()
                data = await response.json()
                print("get repeat", data)
                return data.get("response", "Pas de réponse trouvée.")
    except aiohttp.ClientError as e:
        print(f"Erreur lors de l'appel au modèle : {e}")
        return "Erreur lors de la communication avec le modèle."


async def get_intent_async(user_response):
    url = "https://lyrae-talk-functions.azurewebsites.net/api/detect_intention?code=z4qZo6X7c4gNDPlKhBoXs2IRV1Z1o4FM_FKRqcgpTJBNAzFu_W0gTA=="
    headers = {"Content-Type": "application/json"}
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
    headers = {"Content-Type": "application/json"}
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
    headers = {"Content-Type": "application/json"}

    payload = {"action": "positive_negative_reponse", "text": user_response}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response.raise_for_status()
                data = await response.json()
                model_response = data.get("response")
                return model_response
    except aiohttp.ClientError as e:
        print(f"Erreur lors de l'appel au modèle : {e}")
        return "Erreur lors de la communication avec le modèle."


def get_positive_negative(user_response):
    url = "https://lyrae-talk-functions.azurewebsites.net/api/analyseur_reponse?code=z4qZo6X7c4gNDPlKhBoXs2IRV1Z1o4FM_FKRqcgpTJBNAzFu_W0gTA=="
    headers = {"Content-Type": "application/json"}

    payload = {"action": "positive_negative_reponse", "text": user_response}
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

    headers = {"Content-Type": "application/json"}

    payload = {"text": text}

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
        final_sentence = (
            "Je suis désolé, aucun créneau n'est disponible pour le moment."
        )
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
        3: "troisième",
        4: "quatrième",
        5: "cinquième",
        6: "sixième",
        7: "septième",
        8: "huitième",
        9: "neuvième",
        10: "dixième",
        11: "onzième",
        12: "douzième",
        13: "treizième",
        14: "quatorzième",
        15: "quinzième",
        16: "seizième",
        17: "dix-septième",
        18: "dix-huitième",
        19: "dix-neuvième",
        20: "vingtième",
        21: "vingt et unième",
        22: "vingt-deuxième",
        23: "vingt-troisième",
        24: "vingt-quatrième",
        25: "vingt-cinquième",
        26: "vingt-sixième",
        27: "vingt-septième",
        28: "vingt-huitième",
        29: "vingt-neuvième",
        30: "trentième",
        31: "trente et unième",
        32: "trente-deuxième",
        33: "trente-troisième",
        34: "trente-quatrième",
        35: "trente-cinquième",
        36: "trente-sixième",
        37: "trente-septième",
        38: "trente-huitième",
        39: "trente-neuvième",
        40: "quarantième",
        41: "quarante et unième",
        42: "quarante-deuxième",
        43: "quarante-troisième",
        44: "quarante-quatrième",
        45: "quarante-cinquième",
        46: "quarante-sixième",
        47: "quarante-septième",
        48: "quarante-huitième",
        49: "quarante-neuvième",
        50: "cinquantième",
        51: "cinquante et unième",
        52: "cinquante-deuxième",
        53: "cinquante-troisième",
        54: "cinquante-quatrième",
        55: "cinquante-cinquième",
        56: "cinquante-sixième",
        57: "cinquante-septième",
        58: "cinquante-huitième",
        59: "cinquante-neuvième",
        60: "soixantième",
        61: "soixante et unième",
        62: "soixante-deuxième",
        63: "soixante-troisième",
        64: "soixante-quatrième",
        65: "soixante-cinquième",
        66: "soixante-sixième",
        67: "soixante-septième",
        68: "soixante-huitième",
        69: "soixante-neuvième",
        70: "soixante-dixième",
        71: "soixante-onzième",
        72: "soixante-douzième",
        73: "soixante-treizième",
        74: "soixante-quatorzième",
        75: "soixante-quinzième",
        76: "soixante-seizième",
        77: "soixante-dix-septième",
        78: "soixante-dix-huitième",
        79: "soixante-dix-neuvième",
        80: "quatre-vingtième",
        81: "quatre-vingt-unième",
        82: "quatre-vingt-deuxième",
        83: "quatre-vingt-troisième",
        84: "quatre-vingt-quatrième",
        85: "quatre-vingt-cinquième",
        86: "quatre-vingt-sixième",
        87: "quatre-vingt-septième",
        88: "quatre-vingt-huitième",
        89: "quatre-vingt-neuvième",
        90: "quatre-vingt-dixième",
        91: "quatre-vingt-onzième",
        92: "quatre-vingt-douzième",
        93: "quatre-vingt-treizième",
        94: "quatre-vingt-quatorzième",
        95: "quatre-vingt-quinzième",
        96: "quatre-vingt-seizième",
        97: "quatre-vingt-dix-septième",
        98: "quatre-vingt-dix-huitième",
        99: "quatre-vingt-dix-neuvième",
        100: "centième",
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
            phrases.append(f"le {ordinals[idx]} est le {date_str} à {heure}")

        # Assemble final sentence
        if nb_slots == 0:
            final_sentence = (
                "Je suis désolé, aucun créneau n'est disponible pour le moment."
            )
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
            final_sentence = (
                "Je suis désolé, aucun créneau n'est disponible pour le moment."
            )
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


def continue_conversation(model_response, caller):
    if model_response == "more":
        play_source = text_to_speech("fixed_file_source", model_response, calls[caller])
    else:
        play_source = text_to_speech("file_source", model_response, calls[caller])

    start_recognizing("/handleResponse", "end_conversation", play_source, caller)


async def handle_prise_rdv(caller):
    global calls
    rdv_info = calls[caller].rdv

    # play_source = text_to_speech(
    #     "file_source", "Avez-vous une ordonannce ?", calls[caller]
    # )
    # start_recognizing("/has_ordonnance", "has_ordonnance", play_source, caller)
    if rdv_info["exam_id"] is not None and rdv_info["sous_type_id"] is not None:
        task_creneaux = asyncio.create_task(
            get_creneaux_async(
                sous_type=rdv_info["sous_type_id"],
                exam_type=rdv_info["exam_id"],
                caller=caller,
            ),
        )
        speak("Je regarde les disponibilités, un instant...", caller)

        await asyncio.sleep(1)

        creneaux = await task_creneaux

        print(creneaux)

        rdv_info["all_creneaux"] = creneaux

        text = build_single_date_phrase(creneau=creneaux)
        play_source = text_to_speech("file_source", text, calls[caller])
        start_recognizing(
            "/confirm_creneau",
            "confirm_creneau",
            play_source,
            caller,
            background_noise="click",
        )
    else:
        play_source = text_to_speech(
            "file_source",
            "Très bien, quel examen voulez vous passer ?",
            calls[caller],
        )
        start_recognizing("/rdv_exam_type", "rdv_exam_type", play_source, caller)


def handle_modification(caller):
    play_source = text_to_speech("fixed_file_source", "ask_birthdate", calls[caller])
    start_recognizing("/get_birthdate", "get_birthdate", play_source, caller)


def handle_consultation(caller):
    play_source = text_to_speech("fixed_file_source", "ask_birthdate", calls[caller])
    start_recognizing("/get_birthdate", "get_birthdate", play_source, caller)


def handle_annulation(caller):
    play_source = text_to_speech("fixed_file_source", "ask_birthdate", calls[caller])
    start_recognizing("/get_birthdate", "get_birthdate", play_source, caller)


def start_conversation(caller):

    if calls[caller].call["called"] in ["33801150214", "33801150082", "33801150143"]:
        play_source = text_to_speech(
            "fixed_file_source", "intro_preprod", calls[caller]
        )
    else:
        play_source = text_to_speech("fixed_file_source", "intro", calls[caller])

    start_recognizing("/handleResponse", "start_conversation", play_source, caller)


def speak(text, caller, speed=1.05):

    if text in recorded_audios_keys:
        play_source = text_to_speech("fixed_file_source", text, calls[caller])
    else:
        play_source = text_to_speech("file_source", text, calls[caller], speed=speed)
    call_automation_client.get_call_connection(
        calls[caller].call["call_connection_id"]
    ).play_media_to_all(play_source=play_source)


########## XPLORE API ##########


def createRDV(caller, externalNumber=None):
    # global lastname
    # global firstname
    # global birthdate
    rdv_info = calls[caller].rdv
    caller_info = calls[caller].caller

    url = f"https://{API_URL}/api/createRDV"

    payload = {
        "email": caller_info["email"],
        "firstName": caller_info["firstname"],
        "lastName": caller_info["lastname"],
        "birthDate": caller_info["birthdate"],
        "creneau": rdv_info["chosen_creneau"],
        "db": "sandbox",
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
    url = f"https://{API_URL}/api/getRDV"

    # results = list(rdvCollection.find({
    #     "idPatient": patientId
    # }))

    payload = {"idPatient": patientId}

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


def editRDV(caller):
    # global chosen_creneau
    # global cancel_creneau
    # global firstname
    # global lastname
    # global birthdate
    # global patient_email
    rdv_info = calls[caller].rdv
    caller_info = calls[caller].caller

    url = f"https://{API_URL}/api/editRDV"

    payload = {
        "rdvId": rdv_info["cancel_creneau"].get("idExamen"),
        "externalUserNumber": "NEURACORP",
        "firstName": caller_info["firstname"],
        "lastName": caller_info["lastname"],
        "birthDate": caller_info["birthdate"],
        "email": caller_info["patient_email"],
        "newCreneau": rdv_info["chosen_creneau"],
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.RequestException as e:
        print("Request failed:", e)
        return "Error occurred while creating RDV"


def deleteRDV(caller):
    # global lastname
    # global firstname
    # global birthdate
    caller_info = calls[caller].caller
    rdv_info = calls[caller].rdv

    url = f"https://{API_URL}/api/deleteRDV"
    payload = {
        "rdvId": rdv_info["cancel_creneau"]["idExamen"],
        "externalUserNumber": "NEURACORP",
        "firstName": caller_info["firstname"],
        "lastName": caller_info["lastname"],
        "birthDate": caller_info["birthdate"],
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

    payload = {"id": type_examen}

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
async def find_patient(caller):
    # global birthdate
    # global lastname
    # global firstname
    # global patient_email
    # global creneauDate
    # global rdv_intent
    # global all_creneaux
    # global annulation_phrase
    # global patient_rdv
    # global cancel_creneau
    global calls
    call_info = calls[caller].call
    caller_info = calls[caller].caller
    rdv_info = calls[caller].rdv
    patient = None
    if calls[caller].patient is None:
        patient = patientCollection.find_one(
            {
                "dateNaissance": {
                    "$regex": f"^{caller_info["birthdate"] + 'T00:00:00'}$"
                },
                "nom": {
                    "$regex": f"^{caller_info["lastname"]}$",
                    "$options": "i",
                },  # Case-insensitive
                "prenom": {
                    "$regex": f"^{strip_accents(caller_info["firstname"])}$",
                    "$options": "i",  # Case-insensitive
                },
            }
        )
    else:
        patient = calls[caller].patient

    if patient:
        if call_info["intent"] == "prise de rendez-vous":
            speak(
                "Ne quittez pas le temps que je confirme votre rendez-vous.",
                caller,
            )
            email = patient.get("email")
            caller_info["email"] = email
            # if first_result.get("externalNumber") is None:
            rdv = createRDV(caller)

            if rdv.get("success") is True:

                rdvCollection.insert_one(
                    {
                        "idPatient": patient.get("idPatient"),
                        "numeroRDV": rdv.get("data").get("numeroExamen"),
                        "date": rdv_info["chosen_creneau"].get("date"),
                        "heure": rdv_info["chosen_creneau"].get("heureDebut"),
                        "typeExamen": rdv_info["exam_id"],
                        "codeExamen": rdv_info["sous_type_id"],
                    }
                )
                phrase_creneau = full_date_vers_litteral(
                    rdv_info["chosen_creneau"].get("date").split("T")[0]
                    + "T"
                    + rdv_info["chosen_creneau"].get("heureDebut")
                    + ":00"
                )

                speak(
                    f"Parfait, vous avez donc rendez-vous {phrase_creneau} au nom de {caller_info["lastname"]}. Avant de raccorcher, je vais vous poser quelques questions qui nous serons utile lors de votre accueil.",
                    caller,
                )

                await examination_exam_type(caller)
                return
            else:
                if increment_error(caller, "rdv"):
                    hang_up(
                        "Désolé, je n'ai pas pu valider votre rendez-vous. Je vais vous rediriger vers une secrétaire.",
                        caller,
                    )
                else:
                    speak(
                        f"Il semblerait qu'il y ait un problème avec ce créneau. Je vais vous en proposer un nouveau.",
                        caller,
                    )
                    task_creneaux = asyncio.create_task(
                        get_creneaux_async(
                            sous_type=rdv_info["sous_type_id"],
                            exam_type=rdv_info["exam_id"],
                            caller=caller,
                        ),
                    )
                    speak("Je regarde les disponibilités, un instant...", caller)

                    creneaux = await task_creneaux

                    rdv_info["all_creneaux"] = creneaux
                    rdv_info["creneauDate"] = None
                    rdv_info["chosen_creneau"] = None
                    rdv_info["cancel_creneau"] = None
                    rdv_info["current_creneau_proposition"] = 0

                    text = build_single_date_phrase(creneau=creneaux)
                    play_source = text_to_speech("file_source", text, calls[caller])
                    start_recognizing(
                        "/confirm_creneau", "confirm_creneau", play_source, caller
                    )

        elif (
            call_info["intent"] == "modification de rendez-vous"
            or call_info["intent"] == "consultation de rendez-vous"
        ):
            planned_rdv = getRDV(patient.get("idPatient"))
            if patient.get("externalID", None) is not None:
                planned_rdv_external = getRDV(patient.get("externalID"))
                planned_rdv = planned_rdv + planned_rdv_external

            now = datetime.now()
            print(now)
            future_rdvs = [
                rdv
                for rdv in planned_rdv
                if datetime.strptime(
                    f"{rdv['datePrevue'][:10]}T{rdv['heurePrevue']}", "%Y-%m-%dT%H:%M"
                )
                >= now
            ]
            if len(future_rdvs) == 0:
                play_source = text_to_speech(
                    "file_source",
                    "Il semblerait que vous n'ayez pas de rendez-vous prévus ces prochains jours. Puis-je faire autre chose pour vous ?",
                    calls[caller],
                )
                start_recognizing(
                    "/handleResponse", "end_conversation", play_source, caller
                )

            elif len(future_rdvs) == 1:
                speak(
                    "J'ai en effet trouvé un rendez-vous à votre nom.",
                    caller,
                )

                rdv_info["cancel_creneau"] = future_rdvs[0]
                print("FUTURE", future_rdvs[0])
                dt = datetime.fromisoformat(
                    future_rdvs[0].get("datePrevue").split("T")[0]
                    + "T"
                    + future_rdvs[0].get("heurePrevue")
                )
                formatted_date = f"le {dt.day} {french_months[dt.month]} {dt.year}"
                hours, minutes = future_rdvs[0].get("heurePrevue").split(":")

                all_sous_type = get_sous_type_exam(future_rdvs[0].get("typeExamen"))
                sous_type = next(
                    (
                        item
                        for item in all_sous_type
                        if item["code"] == future_rdvs[0].get("codeExamen")
                    ),
                    None,
                )

                text = f"Vous avez rendez-vous {formatted_date} à {int(hours)} heure {int(minutes)} pour un ou une {sous_type.get('libelle')}."

                if call_info["intent"] == "modification de rendez-vous":
                    task_creneaux = asyncio.create_task(
                        get_creneaux_async(
                            sous_type=future_rdvs[0].get("codeExamen"),
                            exam_type=future_rdvs[0].get("typeExamen"),
                            caller=caller,
                        )
                    )
                    speak(
                        "Je vais chercher des nouveaux créneaux disponibles pour votre examen.",
                        caller,
                    )
                    creneaux = await task_creneaux
                    rdv_info["all_creneaux"] = creneaux
                    text = build_single_date_phrase(
                        creneau=rdv_info["all_creneaux"],
                        index=rdv_info["current_creneau_proposition"],
                    )
                    play_source = text_to_speech("file_source", text, calls[caller])
                    start_recognizing(
                        "/confirm_creneau",
                        "modification",
                        play_source,
                        caller,
                        background_noise="click",
                    )
                    # text = build_multiple_dates_phrase(creneaux=creneaux)
                    # play_source = text_to_speech("file_source", text)
                    # start_recognizing("/get_creneaux_choice", "modification", play_source)
                    return "ok"
                play_source = text_to_speech(
                    "file_source",
                    f"{text}. Puis-je faire autre chose pour vous ?",
                    calls[caller],
                )
                start_recognizing(
                    "/handleResponse", "end_conversation", play_source, caller
                )
            else:
                if len(future_rdvs) > 0:
                    speak(
                        "En effet, j'ai bien trouvé plusieurs rendez-vous à votre nom.",
                        caller,
                    )
                    sorted_rdvs = sorted(
                        future_rdvs,
                        key=lambda x: f"{x['datePrevue'][:10]}T{x['heurePrevue']}",
                    )
                    text = build_multiple_dates_phrase(
                        {i + 1: item for i, item in enumerate(sorted_rdvs)}, "rdv"
                    )
                    continue_conversation(
                        f"{text}. Puis-je faire autre chose pour vous ?", caller
                    )
                else:
                    play_source = text_to_speech(
                        "file_source",
                        "Il semblerait que vous n'ayez pas de rendez-vous prévu dans le futur. Voulez-vous que je vous transfère vers une secrétaire pour avoir plus de détails ?",
                        calls[caller],
                    )
                    start_recognizing(
                        "/transfer_to_secretary",
                        "transfer_to_secretary",
                        play_source,
                        caller,
                    )
        elif call_info["intent"] == "annulation de rendez-vous":
            speak(
                "Donnez-moi un instant le temps que je trouve vos rendez-vous.",
                caller,
            )

            await asyncio.sleep(1)

            planned_rdv = getRDV(patient.get("idPatient"))
            if patient.get("externalID", None) is not None:
                planned_rdv_external = getRDV(patient.get("externalID"))
                print("planned_rdv_external", planned_rdv_external)
                planned_rdv = planned_rdv + planned_rdv_external
            now = datetime.now()
            future_rdvs = [
                rdv
                for rdv in planned_rdv
                if datetime.strptime(
                    f"{rdv['datePrevue'][:10]}T{rdv['heurePrevue']}", "%Y-%m-%dT%H:%M"
                )
                >= now
            ]
            if len(future_rdvs) == 0:
                play_source = text_to_speech(
                    "file_source",
                    "Il semblerait que vous n'ayez pas de rendez-vous prévu. Voulez-vous que je vous transfère vers une secrétaire pour avoir plus d'informations ?",
                    calls[caller],
                )
                start_recognizing(
                    "/transfer_to_secretary", "transfer_unknown", play_source, caller
                )
            elif len(future_rdvs) == 1:
                speak(
                    "J'ai en effet trouvé un rendez-vous à votre nom.",
                    caller,
                )
                dt = datetime.fromisoformat(
                    planned_rdv[0].get("datePrevue").split("T")[0]
                    + "T"
                    + planned_rdv[0].get("heurePrevue")
                )
                formatted_date = f"le {dt.day} {french_months[dt.month]} {dt.year}"
                hours, minutes = planned_rdv[0].get("heurePrevue").split(":")

                rdv_info["cancel_creneau"] = planned_rdv[0]
                all_sous_type = get_sous_type_exam(planned_rdv[0].get("typeExamen"))
                sous_type = next(
                    (
                        item
                        for item in all_sous_type
                        if item["code"] == planned_rdv[0].get("codeExamen")
                    ),
                    None,
                )
                play_source = text_to_speech(
                    "file_source",
                    f"Vous avez rendez-vous {formatted_date} à {int(hours)} heure {int(minutes)} pour un ou une {sous_type.get('libelle')}. Est-ce bien celui-là que vous voulez annuler ?",
                    calls[caller],
                )
                start_recognizing(
                    "/confirm_annulation",
                    "confirm_annulation",
                    play_source,
                    caller,
                    background_noise="click",
                )
            else:
                sorted_rdvs = sorted(
                    future_rdvs,
                    key=lambda x: f"{x['datePrevue'][:10]}T{x['heurePrevue']}",
                )
                rdv_info["patient_rdv"] = sorted_rdvs
                speak(
                    "Vous avez plusieurs rendez-vous prévus. Lequel voulez-vous annuler ?",
                    caller,
                )

                text = build_multiple_dates_phrase(
                    {i + 1: item for i, item in enumerate(sorted_rdvs)}, "annulation"
                )
                rdv_info["annulation_phrase"] = text
                play_source = text_to_speech("file_source", text, calls[caller])
                start_recognizing(
                    "/get_creneaux_choice", "annulation", play_source, caller
                )
    else:
        if call_info["intent"] == "prise de rendez-vous":
            play_source = text_to_speech(
                "fixed_file_source", "hang_up_not_known", calls[caller]
            )
            call_automation_client.get_call_connection(
                calls[caller].call["call_connection_id"]
            ).play_media_to_all(play_source=play_source, operation_context="hang_up")
        elif call_info["intent"] in [
            "consultation de rendez-vous",
            "modification de rendez-vous",
        ]:
            play_source = text_to_speech(
                "file_source",
                "Il semblerait que vous ne soyez pas connu de nos services. Voulez-vous que je vous transfère vers une secrétaire afin d'obtenirs plus d'informations ?",
                calls[caller],
            )
            start_recognizing(
                "/transfer_to_secretary", "transfer_unknown", play_source, caller
            )


if __name__ == "__main__":
    app.run(debug=True)
