from typing import List, Dict, Any
from datetime import datetime
import json

from utils.azure_storage import upload_call_recap

# step = {
#     "intro": "Phrase d'intro / question",
#     "required_info": ["firstname"],
#     "handler": function,
#     "outcome": {
#         "yes": state1,
#         "non": state2,
#     },
# }


# 1. play intro
# 2. check required info
# 3. handler
# 4. next with outcome


# global calls

# if not request.json:
#     return jsonify({"success": "success"})

# caller, operation_context, type, user_response = get_request_infos(request)


class Call:
    def __init__(self, called):
        # Call
        self.call: Dict[str, str] = {
            "call_connection_id": None,
            "caller": None,
            "called": called,
            "intent": None,
        }

        # Caller
        self.caller: Dict[str, str] = {
            "birthdate": None,
            "lastname": None,
            "firstname": None,
            "email": None,
        }

        self.patient: any | None = None

        # Rdv
        self.rdv: Dict[str, str | int | Any] = {
            "rdv_intent": None,
            "exam_id": None,
            "sous_type_id": None,
            "creneauDate": None,
            "all_creneaux": None,
            "chosen_creneau": None,
            "cancel_creneau": None,
            "annulation_phrase": None,
            "patient_rdv": None,
            "current_creneau_proposition": 0,
        }

        # Errors
        self.errors: Dict[str, int] = {
            "firstname": 0,
            "lastname": 0,
            "ordonnance": 0,
            "birthdate": 0,
            "intent": 0,
            "type_exam": 0,
            "rdv": 0,
        }

        # Steps
        self.steps: List[str] = []
        # self.steps: List[Step] = [] ??

        # Timestamp
        self.updated_at: datetime = datetime.now()

    def to_string(self) -> str:
        data = {
            "call": self.call,
            "caller": self.caller,
            "rdv": self.rdv,
            "errors": self.errors,
            "steps": self.steps,
            "updated_at": self.updated_at.isoformat(),  # pour un format lisible
        }
        return json.dumps(data, indent=2, ensure_ascii=False)

    def to_string_archive(self, caller) -> str:
        return f"""***********
{caller} / {self.updated_at} / intent: {self.call["intent"]}

CALLER INFO
birthdate / lastname / firstname / email
{self.caller["birthdate"]} / {self.caller["lastname"]} / {self.caller["firstname"]} / {self.caller["email" ]}

TALK
{"\n".join(self.steps)}\n\n
"""

    def store_archive(self, caller):
        content = self.to_string_archive(caller)
        upload_call_recap(
            f"{caller}-{str(self.updated_at).replace(" ", "-")}.txt", "calls", content
        )

    def __str__(self):
        return self.to_string()

    def add_step(self, item: str) -> None:
        self.steps.append(item)
