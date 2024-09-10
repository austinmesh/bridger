import base64
import os

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAX_BLOCKSIZE = 1024
MESHTASTIC_KEY = os.getenv("MESHTASTIC_KEY", "1PG7OiApB1nwvP+rz05pAQ==")  # Base64-encoded 32-byte key when set to AQ==


class CryptoEngine:
    def __init__(self, key_base64=MESHTASTIC_KEY):
        self.key = base64.b64decode(key_base64.encode("ascii"))

    def init_nonce(self, from_node, packet_id):
        # Convert fromNode and packetId to bytes (little-endian format)
        nonce_packet_id = packet_id.to_bytes(8, "little")
        nonce_from_node = from_node.to_bytes(8, "little")

        # Combine both parts into a single nonce (16 bytes)
        self.nonce = nonce_packet_id + nonce_from_node

    def decrypt(self, from_node: int, packet_id: int, encrypted_data: bytes) -> bytes:
        self.init_nonce(from_node, packet_id)

        cipher = Cipher(algorithms.AES(self.key), modes.CTR(self.nonce), backend=default_backend())
        decryptor = cipher.decryptor()

        decrypted_bytes = decryptor.update(encrypted_data) + decryptor.finalize()
        return decrypted_bytes

    def encrypt(self, from_node: int, packet_id: int, plaintext_bytes: bytes) -> bytes:
        self.init_nonce(from_node, packet_id)

        cipher = Cipher(algorithms.AES(self.key), modes.CTR(self.nonce), backend=default_backend())
        encryptor = cipher.encryptor()

        encrypted_bytes = encryptor.update(plaintext_bytes) + encryptor.finalize()
        return encrypted_bytes
