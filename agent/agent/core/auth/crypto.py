"""
Ed25519 Cryptographic Module for Academia Shield Agent.
Handles device key-pair generation, signing, and signature verification.
"""

import os
import binascii
from typing import Tuple
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

class Ed25519Signer:
    """
    Manages local Ed25519 device keys and cryptographic signing.
    The private key stays strictly on the local device inside secure OS storage.
    Only the public key is sent to the Academia Shield backend during enrollment.
    """

    @staticmethod
    def generate_keypair() -> Tuple[str, str]:
        """
        Generate a new Ed25519 keypair.
        Returns:
            (private_key_hex, public_key_hex)
        """
        private_key = ed25519.Ed25519PrivateKey.generate()
        priv_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )
        pub_bytes = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        return priv_bytes.hex(), pub_bytes.hex()

    @staticmethod
    def sign_message(private_key_hex: str, message: bytes) -> str:
        """
        Sign message bytes using local Ed25519 private key.
        Returns signature as hex string.
        """
        priv_bytes = bytes.fromhex(private_key_hex)
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(priv_bytes)
        signature = private_key.sign(message)
        return signature.hex()

    @staticmethod
    def verify_signature(public_key_hex: str, signature_hex: str, message: bytes) -> bool:
        """
        Verify signature against public key and message.
        """
        try:
            pub_bytes = bytes.fromhex(public_key_hex)
            sig_bytes = bytes.fromhex(signature_hex)
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
            public_key.verify(sig_bytes, message)
            return True
        except Exception:
            return False
