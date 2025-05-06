from typing import IO
import time
import threading

from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient


AZURE_CONNECT_STR = "DefaultEndpointsProtocol=https;AccountName=talkstoragetest;AccountKey=KZ9TXxBKz0o/ddD7kwURE5G0JgErNENjmTbqyhobOCGwwNgCtvi6LIx3CINrwwLJxxf3CXZ8sHdd+AStoaftAw==;EndpointSuffix=core.windows.net"


def upload_stream_azure(stream: IO[bytes], file_name, container_name="audio-files"):
    blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECT_STR)
    blob_client = blob_service_client.get_blob_client(
        container=container_name, blob=file_name
    )
    blob_client.upload_blob(stream, overwrite=True)


def delete_blob_azure_delay(file_name: str, delay=600, container_name="audio-files"):

    def delayed_deletion():
        time.sleep(delay)

        blob_service_client = BlobServiceClient.from_connection_string(
            AZURE_CONNECT_STR
        )
        blob_client = blob_service_client.get_blob_client(
            container=container_name, blob=file_name
        )
        try:
            blob_client.delete_blob()
        except Exception as e:
            print(f"Erreur lors de la suppression du blob : {e}")

    threading.Thread(target=delayed_deletion, daemon=True).start()
