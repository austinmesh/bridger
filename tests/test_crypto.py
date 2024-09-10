import pytest

from bridger.crypto import CryptoEngine


@pytest.fixture
def crypto_engine():
    # Fixture to initialize the CryptoEngine with the specified key
    key_base64 = "1PG7OiApB1nwvP+rz05pAQ=="
    return CryptoEngine(key_base64)


def test_decrypt(crypto_engine):
    from_node = 1129710788
    packet_id = 812977943
    encrypted_data = b"\xc0W\xf2\xf2\x94\x81`\xf6\xd7\xe7\xb6\xc5>p\xa2\xb8\x00\x9bu\x8e\xaf\xfd\xc1t\x9f\n\x1cr\xd1m"
    expected_plaintext = (
        b"\x08\x03\x12\x15\r\x00\x80\x02\x12\x15\x00\x80\xb6\xc5\x18\xc4\x01%\xefI\xdef\xb8\x01\x105\xd3\xd0<p"  # noqa: E501
    )

    decrypted_data = crypto_engine.decrypt(from_node, packet_id, encrypted_data)

    assert decrypted_data == expected_plaintext, "Decrypted data does not match expected plaintext"


def test_encrypt(crypto_engine):
    from_node = 1129710788
    packet_id = 812977943
    plaintext_bytes = b"\x08\x03\x12\x15\r\x00\x80\x02\x12\x15\x00\x80\xb6\xc5\x18\xc4\x01%\xefI\xdef\xb8\x01\x105\xd3\xd0<p"

    # Encrypt the plaintext
    encrypted_data = crypto_engine.encrypt(from_node, packet_id, plaintext_bytes)

    # Decrypt the data back to verify the encryption
    decrypted_data = crypto_engine.decrypt(from_node, packet_id, encrypted_data)

    assert decrypted_data == plaintext_bytes, "Re-encrypted and decrypted data does not match the original plaintext"


def test_encrypt_decrypt_cycle(crypto_engine):
    from_node = 1129710788
    packet_id = 812977943
    plaintext_bytes = b"Test data for encryption and decryption cycle"

    # Encrypt the plaintext
    encrypted_data = crypto_engine.encrypt(from_node, packet_id, plaintext_bytes)

    # Decrypt the encrypted data
    decrypted_data = crypto_engine.decrypt(from_node, packet_id, encrypted_data)

    assert decrypted_data == plaintext_bytes, "Decrypted data does not match the original plaintext"


def test_nonce_generation(crypto_engine):
    from_node = 1129710788
    packet_id = 812977943
    expected_nonce = b"\x17\x0fu0\x00\x00\x00\x00\xc4\x04VC\x00\x00\x00\x00"

    crypto_engine.init_nonce(from_node, packet_id)

    assert crypto_engine.nonce == expected_nonce, "Nonce generation is incorrect"
