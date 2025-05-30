from typing import IO
import time
import threading
import os

from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient


AZURE_CONNECT_STR = "DefaultEndpointsProtocol=https;AccountName=talkstoragetest;AccountKey=KZ9TXxBKz0o/ddD7kwURE5G0JgErNENjmTbqyhobOCGwwNgCtvi6LIx3CINrwwLJxxf3CXZ8sHdd+AStoaftAw==;EndpointSuffix=core.windows.net"
container_name = "audio-files"

from utils.recorded_audio import audios


def get_azure_files():

    blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECT_STR)
    container_client = blob_service_client.get_container_client(container_name)

    # Création du dossier local s'il n'existe pas
    os.makedirs("audios", exist_ok=True)

    # Télécharger chaque blob
    for blob in container_client.list_blobs():
        if blob.name == "test-fr.mp3":

            blob_client = container_client.get_blob_client(blob)
            file_path = os.path.join("audios", blob.name)

            # Crée les dossiers intermédiaires si besoin
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, "wb") as file:
                file.write(blob_client.download_blob().readall())

            print(f"Téléchargé : {blob.name}")


def del_tmp_azure_files():

    blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECT_STR)
    container_client = blob_service_client.get_container_client(f"{container_name}")

    # Télécharger chaque blob
    for blob in container_client.list_blobs():
        # if blob.name.startswith("tmp-"):
        container_client.delete_blob(blob.name)
    # container_client.delete_blob(blob.name)


# del_tmp_azure_files()
get_azure_files()
